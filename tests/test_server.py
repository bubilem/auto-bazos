"""Local server: static files, state API, and the guards (path traversal, foreign Origin / Host)."""
import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        (tmp / "web").mkdir()
        (tmp / "data").mkdir()
        (tmp / "web" / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
        (tmp / "data" / "index.json").write_text('{"listings": []}', encoding="utf-8")
        (tmp / "secret.txt").write_text("nope", encoding="utf-8")
        cls.saved = (server.WEB_DIR, server.DATA_DIR, server.STATE_FILE, server.CRAWLER)
        server.WEB_DIR, server.DATA_DIR = tmp / "web", tmp / "data"
        server.STATE_FILE = tmp / "data" / "user_state.json"
        server.CRAWLER = tmp / "no_such_crawler.py"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.httpd.allowed_hosts = {f"127.0.0.1:{cls.port}", f"localhost:{cls.port}"}
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.WEB_DIR, server.DATA_DIR, server.STATE_FILE, server.CRAWLER = cls.saved
        cls.tmp.cleanup()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def test_static_files(self):
        self.assertEqual(self.req("GET", "/"), (200, b"<h1>ok</h1>"))
        status, data = self.req("GET", "/data/index.json")
        self.assertEqual((status, json.loads(data)), (200, {"listings": []}))

    def test_path_traversal_is_blocked(self):
        for path in ["/data/../secret.txt", "/../secret.txt", "/%2e%2e/secret.txt", "/data/%2e%2e/secret.txt"]:
            status, data = self.req("GET", path)
            self.assertNotEqual(data, b"nope", path)
            self.assertEqual(status, 404, path)

    def test_state_roundtrip_keeps_diacritics_and_merges(self):
        body = json.dumps({"uid": "bazos_1", "patch": {"notes": "Volat v úterý ěščř"}}, ensure_ascii=False).encode("utf-8")
        self.assertEqual(self.req("POST", "/api/state", body)[0], 200)
        self.req("POST", "/api/state", json.dumps({"uid": "bazos_1", "patch": {"workflow_status": "shortlisted"}}).encode())
        state = json.loads(self.req("GET", "/api/state")[1])
        self.assertEqual(state["bazos_1"]["notes"], "Volat v úterý ěščř")
        self.assertEqual(state["bazos_1"]["workflow_status"], "shortlisted")
        raw = server.STATE_FILE.read_text(encoding="utf-8")
        self.assertIn("Volat v úterý ěščř", raw)  # stored as real UTF-8, not \u escapes
        self.assertFalse(server.STATE_FILE.with_suffix(".json.tmp").exists())

    def test_bad_state_payloads_rejected(self):
        for body in (b'{"uid": 1, "patch": {}}', b'{"uid": "x", "patch": []}', b"not json", b"{}"):
            self.assertEqual(self.req("POST", "/api/state", body)[0], 400, body)

    def test_foreign_origin_rejected(self):
        status, _ = self.req("POST", "/api/state", b'{"uid":"x","patch":{}}', {"Origin": "http://evil.example"})
        self.assertEqual(status, 403)

    def test_foreign_host_rejected_dns_rebinding(self):
        # Rebinding: attacker's domain resolves to 127.0.0.1, so Host and Origin are both "evil.example".
        h = {"Host": "evil.example", "Origin": "http://evil.example"}
        self.assertEqual(self.req("GET", "/api/state", headers=h)[0], 403)
        self.assertEqual(self.req("GET", "/data/index.json", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/state", b'{"uid":"x","patch":{}}', h)[0], 403)
        self.assertEqual(self.req("HEAD", "/", headers={"Host": "evil.example"})[0], 403)

    def test_localhost_alias_is_allowed(self):
        self.assertEqual(self.req("GET", "/", headers={"Host": f"localhost:{self.port}"})[0], 200)

    def test_profiles_api_create_update_delete(self):
        import shutil
        from crawler import profiles
        saved = profiles.PATH
        profiles.PATH = Path(self.tmp.name) / "profiles.json"
        shutil.copy(saved, profiles.PATH)
        try:
            status, data = self.req("GET", "/api/profiles")
            body = json.loads(data)
            self.assertEqual(status, 200)
            self.assertEqual([g["id"] for g in body["groups"]], ["stredni_dodavky", "starsi_mpv"])
            new = dict(body["profiles"][0], name="Moje auto")
            del new["id"]
            status, data = self.req("POST", "/api/profiles", json.dumps({"profile": new}).encode())
            self.assertEqual(status, 200)
            self.assertEqual([p["id"] for p in json.loads(data)["profiles"]][-1], "moje_auto")
            edited = dict(new, id="moje_auto", name="Přejmenováno")
            self.req("POST", "/api/profiles", json.dumps({"profile": edited}).encode())
            saved_profiles = profiles.load()
            self.assertEqual(len(saved_profiles), 3)
            self.assertEqual(saved_profiles[-1]["name"], "Přejmenováno")
            invalid = dict(new, equivalence_group="nope")
            self.assertEqual(self.req("POST", "/api/profiles", json.dumps({"profile": invalid}).encode())[0], 400)
            self.assertEqual(len(profiles.load()), 3)
            self.assertEqual(self.req("POST", "/api/profiles/delete", b'{"id": "moje_auto"}')[0], 200)
            self.assertEqual(self.req("POST", "/api/profiles/delete", b'{"id": "moje_auto"}')[0], 400)
            self.assertEqual(len(profiles.load()), 2)
            for pid in [p["id"] for p in profiles.load()]:
                self.req("POST", "/api/profiles/delete", json.dumps({"id": pid}).encode())
            self.assertEqual(len(profiles.load()), 1)  # the last profile cannot be deleted
        finally:
            profiles.PATH = saved

    def test_groups_and_categories_api(self):
        import shutil
        from crawler import sources, taxonomy
        saved = taxonomy.PATH, sources.PATH
        taxonomy.PATH, sources.PATH = Path(self.tmp.name) / "taxonomy.json", Path(self.tmp.name) / "config.json"
        shutil.copy(saved[0], taxonomy.PATH)
        shutil.copy(saved[1], sources.PATH)
        post = lambda path, body: self.req("POST", path, json.dumps(body).encode())
        try:
            body = json.loads(self.req("GET", "/api/groups")[1])
            self.assertEqual(body["used"], ["starsi_mpv", "stredni_dodavky"])
            group = {"name": "Kombi", "models": [{"make": "Škoda", "model": "Octavia"}]}
            status, data = post("/api/groups", {"group": group})
            self.assertEqual((status, json.loads(data)["id"]), (200, "kombi"))
            self.assertEqual(taxonomy.load()["groups"]["kombi"]["models"][0]["make"], "Škoda")
            self.assertEqual(post("/api/groups", {"id": "kombi", "group": {"name": "x", "models": []}})[0], 400)
            self.assertEqual(post("/api/groups", {"id": "Bad Id", "group": group})[0], 400)
            self.assertEqual(post("/api/groups/delete", {"id": "stredni_dodavky"})[0], 400)  # used by a profile
            self.assertEqual(post("/api/groups/delete", {"id": "kombi"})[0], 200)
            self.assertNotIn("kombi", taxonomy.load()["groups"])
            self.assertEqual(post("/api/groups/delete", {"id": "kombi"})[0], 400)

            self.assertEqual(post("/api/categories", {"categories": [{"slug": "skoda", "max_pages": 2}]})[0], 200)
            self.assertEqual(sources.load_categories(), [{"slug": "skoda", "max_pages": 2}])
            self.assertEqual(post("/api/categories", {"categories": [{"slug": "../x", "max_pages": 2}]})[0], 400)
            self.assertEqual(post("/api/categories", {"categories": []})[0], 400)
            self.assertEqual(json.loads(self.req("GET", "/api/categories")[1])["categories"], [{"slug": "skoda", "max_pages": 2}])
        finally:
            taxonomy.PATH, sources.PATH = saved

    def test_add_endpoint_rejects_foreign_urls(self):
        for url in ("https://evil.example/inzerat/1/x.php", "file:///etc/passwd", "", None, 5):
            self.assertEqual(self.req("POST", "/api/add", json.dumps({"url": url}).encode())[0], 400, url)

    def test_crawl_endpoint_without_crawler_and_status(self):
        self.assertEqual(self.req("POST", "/api/crawl", b"{}")[0], 501)
        status, data = self.req("GET", "/api/crawl/status")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(data)["running"])


if __name__ == "__main__":
    unittest.main()
