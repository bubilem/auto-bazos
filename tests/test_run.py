"""End-to-end crawl against a fake Bazoš (httpx.MockTransport + saved pages). No network."""
import argparse
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler import run, taxonomy  # noqa: E402
from crawler.fetcher import Fetcher, RobotsDisallowed  # noqa: E402
from crawler.portals import PORTALS  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "bazos"
ROBOTS = "User-agent: *\nDisallow: /*hledat=\nDisallow: /*cenado=\nDisallow: /ad-phone.php\n"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PROFILES = json.loads((ROOT / "profiles.json").read_text(encoding="utf-8"))["profiles"]


def jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (90, 120, 160)).save(buf, "JPEG")
    return buf.getvalue()


class FakeBazos:
    def __init__(self, gone=()):
        self.requests, self.gone = [], set(gone)
        self.list_html = (FIX / "list_citroen.html").read_text(encoding="utf-8")
        self.detail_html = (FIX / "detail_jumpy.html").read_text(encoding="utf-8")

    def __call__(self, request):
        url = str(request.url)
        self.requests.append(url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=ROBOTS)
        if "/img/" in url:
            return httpx.Response(200, content=jpeg_bytes(), headers={"content-type": "image/jpeg"})
        if "/inzerat/" in url:
            if any(g in url for g in self.gone):
                return httpx.Response(404, text="<html><body>Inzerát již neexistuje</body></html>")
            return httpx.Response(200, text=self.detail_html)
        if request.url.path in ("/citroen/", "/citroen"):
            return httpx.Response(200, text=self.list_html)
        return httpx.Response(200, text="<html><body></body></html>")


def make_fetcher(fake):
    scraping = {**CFG["scraping"], "delay_seconds": [0, 0], "image_delay_seconds": [0, 0]}
    return Fetcher(scraping, client=httpx.Client(transport=httpx.MockTransport(fake)), sleep=lambda s: None)


def args(**kw):
    base = dict(max_pages=1, limit=None, slug="citroen", stale_limit=10, dry_run=False)
    base.update(kw)
    return argparse.Namespace(**base)


class CrawlBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg = json.loads(json.dumps(CFG))
        self.cfg["portals"]["bazos"]["categories"] = [{"slug": "citroen", "max_pages": 1}]
        self.tax = taxonomy.load()
        self.profiles = json.loads(json.dumps(PROFILES))

    def tearDown(self):
        self.tmp.cleanup()

    def crawl(self, fake, portal="bazos", **kw):
        store, state = run.Store(self.dir), run.read_json(self.dir / "crawl_state.json", {})
        fetcher, a = make_fetcher(fake), args(**kw)
        groups = [(g, self.tax["groups"][g]) for g in sorted({p["equivalence_group"] for p in self.profiles})]
        pobj = PORTALS[portal](self.cfg["portals"][portal], fetcher, groups, a)
        problem = run.crawl_portal(pobj, self.cfg, groups, self.profiles, store, fetcher, state, a)
        run.write_json(self.dir / "crawl_state.json", state)
        run.rebuild_index(store, self.profiles, datetime.now(timezone.utc).date(), self.dir)
        return store, problem


class CrawlFlow(CrawlBase):
    def test_first_run_stores_matching_affordable_van(self):
        fake = FakeBazos()
        store, problem = self.crawl(fake)
        self.assertFalse(problem)
        # Jumpy 226472643 (85 000 Kč) matches; the pricier Jumpy (229 000 Kč) is over price_max; Jumper is not in taxonomy.
        self.assertEqual(sorted(store.listings), ["bazos_226472643"])
        l = store.listings["bazos_226472643"]
        self.assertEqual((l["vehicle"]["make"], l["vehicle"]["model"]), ("Citroën", "Jumpy"))
        self.assertEqual(l["price_czk"], 85000)
        self.assertGreaterEqual(len(l["images"]), 5)
        self.assertTrue((self.dir / "listings" / l["uid"] / "images" / "01.jpg").exists())
        self.assertEqual(l["collages"][0], "collage_1.jpg")
        self.assertTrue((self.dir / "listings" / l["uid"] / "collage_1.jpg").exists())
        self.assertIn("dodavka_na_sut", l["rule_scoring"])

    def test_never_requests_forbidden_urls_and_stores_no_personal_data(self):
        fake = FakeBazos()
        self.crawl(fake)
        for u in fake.requests:
            self.assertNotIn("hledat=", u)
            self.assertNotIn("cenado=", u)
            self.assertNotIn("ad-phone", u)
        blob = (self.dir / "listings" / "bazos_226472643" / "listing.json").read_text(encoding="utf-8")
        self.assertNotIn("Jméno prodejce", blob)

    def test_index_is_ui_compatible(self):
        self.crawl(FakeBazos())
        idx = json.loads((self.dir / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(idx["profiles"][0]["id"], "dodavka_na_sut")
        e = idx["listings"][0]
        for key in ("uid", "title", "url", "price_czk", "scores", "tags", "thumb", "search_text", "first_seen", "status"):
            self.assertIn(key, e)
        self.assertEqual(e["thumb"], "listings/bazos_226472643/images/01.jpg")

    def test_second_run_is_incremental(self):
        self.crawl(FakeBazos())
        fake2 = FakeBazos()
        store, _ = self.crawl(fake2)
        self.assertEqual(len(store.listings), 1)
        self.assertFalse([u for u in fake2.requests if "/inzerat/" in u or "/img/" in u])  # no detail/photos again

    def test_price_drop_recorded_and_tagged(self):
        self.crawl(FakeBazos())
        f = self.dir / "listings" / "bazos_226472643" / "listing.json"
        d = json.loads(f.read_text(encoding="utf-8"))
        d["price_czk"] = 99000
        d["price_history"] = [{"date": "2026-11-01", "price_czk": 99000}]
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        store, _ = self.crawl(FakeBazos())  # list shows 85 000 -> drop
        self.assertEqual([h["price_czk"] for h in store.listings["bazos_226472643"]["price_history"]], [99000, 85000])
        idx = json.loads((self.dir / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(idx["listings"][0]["price_prev_czk"], 99000)
        self.assertIn("Sleva", idx["listings"][0]["tags"])

    def test_vanished_ad_becomes_inactive_but_data_kept(self):
        self.crawl(FakeBazos())
        old = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ghost = json.loads((self.dir / "listings" / "bazos_226472643" / "listing.json").read_text(encoding="utf-8"))
        ghost.update(uid="bazos_111", external_id="111", url="https://auto.bazos.cz/inzerat/111/x.php", last_seen=old, status="active")
        run.write_json(self.dir / "listings" / "bazos_111" / "listing.json", ghost)
        store, _ = self.crawl(FakeBazos(gone=["/inzerat/111/"]), stale_limit=5)
        self.assertEqual(store.listings["bazos_111"]["status"], "inactive")
        self.assertTrue((self.dir / "listings" / "bazos_111" / "listing.json").exists())
        self.assertEqual(store.listings["bazos_226472643"]["status"], "active")

    def test_limit_defers_candidates_without_forgetting_them(self):
        store, _ = self.crawl(FakeBazos(), limit=0)
        self.assertEqual(store.listings, {})
        store, _ = self.crawl(FakeBazos())  # next run still finds it
        self.assertIn("bazos_226472643", store.listings)

    def test_empty_category_page_flags_layout_problem(self):
        class Empty(FakeBazos):
            def __call__(self, request):
                if request.url.path.startswith("/citroen"):
                    return httpx.Response(200, text="<html><body>blokace</body></html>")
                return super().__call__(request)
        _, problem = self.crawl(Empty())
        self.assertTrue(problem)

    def test_network_error_in_one_category_does_not_abort_the_run(self):
        self.cfg["portals"]["bazos"]["categories"] = [{"slug": "dodavka", "max_pages": 1}, {"slug": "citroen", "max_pages": 1}]

        class Flaky(FakeBazos):
            def __call__(self, request):
                if request.url.path == "/dodavka/":
                    raise httpx.ConnectError("boom", request=request)
                return super().__call__(request)
        store, problem = self.crawl(Flaky(), slug=None)
        self.assertTrue(problem)  # reported ...
        self.assertIn("bazos_226472643", store.listings)  # ... but the other category was still processed
        self.assertIn("226472643", run.read_json(self.dir / "crawl_state.json", {})["bazos_seen"])

    def test_dry_run_writes_nothing(self):
        store, _ = self.crawl(FakeBazos(), dry_run=True)
        self.assertEqual(store.listings, {})


class AddByUrl(CrawlBase):
    URL = "https://auto.bazos.cz/inzerat/999111/hand-picked-van.php"

    def add(self, url=None, fake=None):
        store, state = run.Store(self.dir), run.read_json(self.dir / "crawl_state.json", {})
        fetcher, a = make_fetcher(fake or FakeBazos()), args(slug=None)
        groups = [(g, self.tax["groups"][g]) for g in sorted({p["equivalence_group"] for p in self.profiles})]
        problem = run.add_url(url or self.URL, self.cfg, groups, self.profiles, store, fetcher, state, a)
        return store, state, problem

    def test_adds_ad_ignoring_price_cap_and_marks_it_manual(self):
        for p in self.profiles:
            p["params"]["price_max_czk"] = 1  # nothing would pass the category filter
        store, state, problem = self.add()
        self.assertFalse(problem)
        l = store.listings["bazos_999111"]
        self.assertTrue(l["manual"])
        self.assertEqual((l["vehicle"]["make"], l["vehicle"]["model"]), ("Citroën", "Jumpy"))  # model from the title
        self.assertGreaterEqual(len(l["images"]), 5)
        self.assertIn("999111", state["bazos_seen"])

    def test_adding_twice_does_not_duplicate(self):
        self.add()
        store, _, problem = self.add(fake=FakeBazos())
        self.assertFalse(problem)
        self.assertEqual(list(store.listings), ["bazos_999111"])

    def test_foreign_or_non_ad_urls_are_rejected_without_requests(self):
        for url in ("https://evil.example/inzerat/1/x.php", "https://auto.bazos.cz/citroen/", "file:///etc/passwd",
                    "https://auto.bazos.cz.evil.example/inzerat/1/x.php"):
            fake = FakeBazos()
            store, _, problem = self.add(url, fake)
            self.assertTrue(problem, url)
            self.assertEqual(store.listings, {})
            self.assertEqual(fake.requests, [])

    def test_gone_ad_is_a_problem(self):
        _, _, problem = self.add(fake=FakeBazos(gone=["999111"]))
        self.assertTrue(problem)


class FetcherGuards(unittest.TestCase):
    def test_robots_blocks_search_urls(self):
        f = make_fetcher(FakeBazos())
        with self.assertRaises(RobotsDisallowed):
            f.get("https://auto.bazos.cz/?hledat=jumpy")
        self.assertEqual(f.get("https://auto.bazos.cz/citroen/").status_code, 200)

    def test_delay_between_requests(self):
        sleeps = []
        t = [0.0]
        scraping = {**CFG["scraping"], "delay_seconds": [2, 2]}
        f = Fetcher(scraping, client=httpx.Client(transport=httpx.MockTransport(FakeBazos())),
                    sleep=sleeps.append, rand=lambda a, b: a, clock=lambda: t[0])
        f.get("https://auto.bazos.cz/citroen/")
        f.get("https://auto.bazos.cz/citroen/40/")
        self.assertEqual(sleeps, [2.0])  # first request immediate, second waits the full delay


if __name__ == "__main__":
    unittest.main()
