"""Lightweight local server for Add-Check (stdlib only).

Serves web/ at "/" and data/ at "/data/", plus a tiny JSON API:
  GET  /api/state         -> whole user_state.json
  POST /api/state         -> {"uid": "...", "patch": {...}}  shallow-merge into state[uid]
  POST /api/crawl         -> start crawler/run.py in background
  GET  /api/profiles      -> {"profiles": [...], "groups": [{"id", "name"}]}   (profiles.json + taxonomy.json)
  POST /api/profiles      -> {"profile": {...}}  create (no id) or update (existing id), then re-score
  POST /api/profiles/delete -> {"id": "..."}     delete a profile (the last one cannot be deleted), then re-score
  GET  /api/groups        -> {"groups": {id: {name, models}}, "used": [group ids used by profiles]}
  POST /api/groups        -> {"id"?: "...", "group": {...}}  create / update a model group (taxonomy.json)
  POST /api/groups/delete -> {"id": "..."}                  delete a group no profile uses
  GET  /api/categories    -> {"categories": [{slug, max_pages}]}
  POST /api/categories    -> {"categories": [...]}          replace the Bazoš category list (config.json)
  POST /api/add          -> {"url": "..."}  fetch one hand-picked ad (crawler/run.py --add-url)
  GET  /api/crawl/status  -> {"running": bool, "returncode": int|null, "log_tail": [...]}
Binds to 127.0.0.1 only.
"""
import json
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from crawler import profiles as profiles_mod  # noqa: E402
from crawler import sources, taxonomy  # noqa: E402

WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
STATE_FILE = DATA_DIR / "user_state.json"
CRAWLER = ROOT / "crawler" / "run.py"
MAX_BODY = 5 * 1024 * 1024

state_lock = threading.Lock()
crawl_lock = threading.Lock()
crawl = {"proc": None, "log": [], "returncode": None}


def load_config():
    with open(ROOT / "config.json", encoding="utf-8") as f:
        return json.load(f)


def read_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def write_state(state):
    DATA_DIR.mkdir(exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)  # atomic


def _pump_crawl_output(proc):
    for line in proc.stdout:
        crawl["log"].append(line.rstrip())
        del crawl["log"][:-200]
    proc.wait()
    crawl["returncode"] = proc.returncode


def valid_ad_url(url):
    """Only plain http(s) ad-page URLs on a configured portal host reach the crawler (it validates again)."""
    from urllib.parse import urlsplit
    if not isinstance(url, str) or len(url) > 500 or not url.isprintable():
        return False
    u = urlsplit(url.strip())
    hosts = {urlsplit(p.get("base_url", "")).hostname for p in load_config().get("portals", {}).values()}
    return u.scheme in ("http", "https") and u.hostname in hosts


def crawl_running():
    proc = crawl["proc"]
    return proc is not None and proc.poll() is None


def group_list():
    return [{"id": gid, "name": g.get("name", gid)} for gid, g in taxonomy.load()["groups"].items()]


def save_profiles(profiles):
    """Write profiles.json and re-score everything (background `--rebuild`, same status channel as a crawl)."""
    profiles_mod.save(profiles)
    return start_crawl(["--rebuild"])


def start_crawl(extra_args=()):
    with crawl_lock:
        proc = crawl["proc"]
        if proc is not None and proc.poll() is None:
            return "already_running"
        if not CRAWLER.exists():
            return "not_implemented"
        crawl["log"] = []
        crawl["returncode"] = None
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "crawler.run", *extra_args],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        crawl["proc"] = proc
        threading.Thread(target=_pump_crawl_output, args=(proc,), daemon=True).start()
        return "started"


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        rel = Path(*[p for p in path.split("/") if p not in ("", ".", "..")]) if path.strip("/") else Path()
        parts = rel.parts
        if parts and parts[0] == "data":
            base, rel = DATA_DIR, Path(*parts[1:]) if len(parts) > 1 else Path()
        else:
            base = WEB_DIR
        target = (base / rel).resolve()
        if base.resolve() not in target.parents and target != base.resolve():
            return str(base / "__forbidden__")
        return str(target)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # --- helpers
    def _json(self, obj, status=HTTPStatus.OK):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def _host_ok(self):
        """Reject foreign Host headers (DNS-rebinding guard): only the address we are bound to is accepted."""
        allowed = getattr(self.server, "allowed_hosts", None)
        if allowed is not None and self.headers.get("Host", "").lower() not in allowed:
            self._json({"error": "forbidden host"}, HTTPStatus.FORBIDDEN)
            return False
        return True

    def do_HEAD(self):
        if self._host_ok():
            super().do_HEAD()

    def _origin_ok(self):
        # Basic CSRF guard: only accept same-origin / non-browser requests.
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return origin in (f"http://{host}",)

    # --- routes
    def do_GET(self):
        if not self._host_ok():
            return
        if self.path.startswith("/api/state"):
            with state_lock:
                return self._json(read_state())
        if self.path == "/api/profiles":
            return self._json({"profiles": profiles_mod.load(), "groups": group_list()})
        if self.path == "/api/groups":
            return self._json({"groups": taxonomy.load()["groups"],
                               "used": sorted({p["equivalence_group"] for p in profiles_mod.load()})})
        if self.path == "/api/categories":
            return self._json({"categories": sources.load_categories()})
        if self.path.startswith("/api/crawl/status"):
            proc = crawl["proc"]
            return self._json({
                "running": proc is not None and proc.poll() is None,
                "returncode": crawl["returncode"],
                "log_tail": crawl["log"][-30:],
            })
        return super().do_GET()

    def do_POST(self):
        if not self._host_ok():
            return
        if not self._origin_ok():
            return self._json({"error": "forbidden origin"}, HTTPStatus.FORBIDDEN)
        try:
            if self.path == "/api/state":
                body = self._read_json()
                uid, patch = body.get("uid"), body.get("patch")
                if not isinstance(uid, str) or not uid or not isinstance(patch, dict):
                    return self._json({"error": "expected {uid: str, patch: object}"}, HTTPStatus.BAD_REQUEST)
                with state_lock:
                    state = read_state()
                    entry = state.setdefault(uid, {})
                    entry.update(patch)
                    entry["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    write_state(state)
                return self._json(entry)
            if self.path in ("/api/profiles", "/api/profiles/delete"):
                body = self._read_json()
                if crawl_running():  # the running crawler already holds the old profiles; do not race it
                    return self._json({"error": "crawl running"}, HTTPStatus.CONFLICT)
                with state_lock:
                    profiles = profiles_mod.load()
                    if self.path == "/api/profiles/delete":
                        if len(profiles) <= 1 or not any(p["id"] == body.get("id") for p in profiles):
                            return self._json({"error": "unknown profile, or it is the last one"}, HTTPStatus.BAD_REQUEST)
                        profiles = [p for p in profiles if p["id"] != body["id"]]
                    else:
                        raw = body.get("profile")
                        if not isinstance(raw, dict):
                            return self._json({"error": "expected {profile: object}"}, HTTPStatus.BAD_REQUEST)
                        raw = dict(raw)
                        if not raw.get("id"):
                            raw["id"] = profiles_mod.make_id(str(raw.get("name") or ""), {p["id"] for p in profiles})
                        profile = profiles_mod.validate(raw, {g["id"] for g in group_list()})
                        i = next((i for i, p in enumerate(profiles) if p["id"] == profile["id"]), None)
                        if i is None:
                            profiles.append(profile)
                        else:
                            profiles[i] = profile
                    result = save_profiles(profiles)
                return self._json({"result": result, "profiles": profiles}, HTTPStatus.OK)
            if self.path in ("/api/groups", "/api/groups/delete", "/api/categories"):
                body = self._read_json()
                if crawl_running():  # the crawler reads these files once at start; do not change them under it
                    return self._json({"error": "crawl running"}, HTTPStatus.CONFLICT)
                with state_lock:
                    if self.path == "/api/categories":
                        sources.save_categories(sources.validate_categories(body.get("categories")))
                        return self._json({"categories": sources.load_categories()})
                    tax = taxonomy.load()
                    groups = tax["groups"]
                    if self.path == "/api/groups/delete":
                        gid = body.get("id")
                        users = [p["name"] for p in profiles_mod.load() if p["equivalence_group"] == gid]
                        if gid not in groups or users:
                            msg = "skupinu používá profil: " + ", ".join(users) if users else "neznámá skupina"
                            return self._json({"error": msg}, HTTPStatus.BAD_REQUEST)
                        del groups[gid]
                    else:
                        group = taxonomy.validate_group(body.get("group"))
                        gid = body.get("id") or profiles_mod.make_id(group["name"], set(groups))
                        groups[taxonomy.validate_group_id(gid)] = group
                    taxonomy.save(tax)
                    return self._json({"groups": groups, "id": gid})
            if self.path == "/api/add":
                url = self._read_json().get("url")
                if not valid_ad_url(url):
                    return self._json({"error": "expected an ad URL on a configured portal"}, HTTPStatus.BAD_REQUEST)
                result = start_crawl([f"--add-url={url.strip()}"])
                status = {"started": HTTPStatus.ACCEPTED, "already_running": HTTPStatus.CONFLICT,
                          "not_implemented": HTTPStatus.NOT_IMPLEMENTED}[result]
                return self._json({"result": result}, status)
            if self.path == "/api/crawl":
                result = start_crawl()
                status = {"started": HTTPStatus.ACCEPTED, "already_running": HTTPStatus.CONFLICT,
                          "not_implemented": HTTPStatus.NOT_IMPLEMENTED}[result]
                return self._json({"result": result}, status)
        except (ValueError, json.JSONDecodeError) as e:  # includes ProfileError
            return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
        return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    cfg = load_config()["server"]
    host, port = cfg["host"], int(cfg["port"])
    DATA_DIR.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.allowed_hosts = {f"{h}:{port}" for h in (host, "localhost", "127.0.0.1")}
    url = f"http://{host}:{port}/"
    print(f"Add-Check běží na {url}  (Ctrl+C ukončí)")
    if "--open" in sys.argv:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nKonec.")
    finally:
        proc = crawl["proc"]
        if proc is not None and proc.poll() is None:  # don't leave a crawler running without its server
            proc.terminate()


if __name__ == "__main__":
    main()
