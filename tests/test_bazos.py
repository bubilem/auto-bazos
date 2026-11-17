import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler import robots, taxonomy  # noqa: E402
from crawler.scrapers import bazos  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "bazos"
BAZOS_ROBOTS = """
User-agent: *
Disallow: /*hledat=
Disallow: /*hlokalita=
Disallow: /*humkreis
Disallow: /*order=
Disallow: /*cenaod=
Disallow: /*cenado=
Disallow: /ad-phone.php
Disallow: /smazat/

User-agent: SemrushBot
Disallow: /
"""


class ListPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = bazos.parse_list_page((FIX / "list_citroen.html").read_text(encoding="utf-8"))

    def test_counts(self):
        self.assertEqual(len(self.page["items"]), 40)
        self.assertEqual(self.page["total"], 3453)

    def test_item_fields(self):
        it = next(i for i in self.page["items"] if i["external_id"] == "226472643")
        self.assertEqual(it["title"], "Citroën jumpy 2011 1.6 hdi 66kw")
        self.assertEqual(it["price_czk"], 85000)
        self.assertTrue(it["url"].startswith("https://auto.bazos.cz/inzerat/226472643/"))
        self.assertEqual(it["listed_on"], "2026-11-16")
        self.assertEqual(it["location"], "Olomouc")
        self.assertRegex(it["zip"], r"^\d{3}\s?\d{2}$")
        self.assertIsInstance(it["views"], int)

    def test_non_numeric_price_is_none(self):
        it = next(i for i in self.page["items"] if i["external_id"] == "226425900")  # "Dohodou"
        self.assertIsNone(it["price_czk"])

    def test_every_item_has_id_title_url(self):
        for it in self.page["items"]:
            self.assertTrue(it["external_id"].isdigit())
            self.assertTrue(it["title"])
            self.assertIn(it["external_id"], it["url"])

    def test_garbage_html(self):
        self.assertEqual(bazos.parse_list_page("<html><body>nic</body></html>"), {"items": [], "total": None})


class DetailPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = bazos.parse_detail((FIX / "detail_jumpy.html").read_text(encoding="utf-8"))

    def test_fields(self):
        d = self.d
        self.assertEqual(d["title"], "Citroën jumpy 2011 1.6 hdi 66kw")
        self.assertEqual(d["price_czk"], 85000)
        self.assertEqual(d["location"], "Olomouc")
        self.assertEqual(d["zip"], "783 21")
        self.assertEqual(d["views"], 133)
        self.assertEqual(d["listed_on"], "2026-11-16")
        self.assertIn("Najeto 190 000", d["description"])

    def test_images(self):
        imgs = self.d["images"]
        self.assertGreaterEqual(len(imgs), 5)
        self.assertTrue(all(u.startswith("https://www.bazos.cz/img/") for u in imgs))
        self.assertEqual(len(imgs), len(set(imgs)))
        self.assertIn("/img/1/", imgs[0])

    def test_no_personal_data_kept(self):
        blob = json.dumps(self.d, ensure_ascii=False)
        self.assertNotIn("Jméno prodejce", blob)
        self.assertNotIn("zobraz číslo", blob)

    def test_deleted_or_unknown_page_is_none(self):
        self.assertIsNone(bazos.parse_detail("<html><body><p>Inzerát neexistuje</p></body></html>"))


class Robots(unittest.TestCase):
    def setUp(self):
        self.rc = robots.RobotsCache(lambda url: BAZOS_ROBOTS, "AddCheck-personal/0.1")

    def test_category_pages_allowed(self):
        for u in ["https://auto.bazos.cz/dodavka/", "https://auto.bazos.cz/citroen/80/",
                  "https://auto.bazos.cz/inzerat/226472643/x.php", "https://www.bazos.cz/img/1/643/226472643.jpg"]:
            self.assertTrue(self.rc.allowed(u), u)

    def test_search_params_disallowed(self):
        for u in ["https://auto.bazos.cz/?hledat=jumpy", "https://auto.bazos.cz/dodavka/?cenado=90000",
                  "https://auto.bazos.cz/?hlokalita=77900&humkreis=100", "https://auto.bazos.cz/dodavka/?order=1",
                  "https://auto.bazos.cz/ad-phone.php"]:
            self.assertFalse(self.rc.allowed(u), u)

    def test_other_agent_rules_dont_apply_to_us(self):
        self.assertTrue(self.rc.allowed("https://auto.bazos.cz/dodavka/"))

    def test_allow_beats_equal_disallow_and_missing_robots(self):
        rules = robots.parse_rules("User-agent: *\nDisallow: /a\nAllow: /a/ok", "x")
        self.assertFalse(robots.is_allowed(rules, "/a/bad"))
        self.assertTrue(robots.is_allowed(rules, "/a/ok"))
        self.assertTrue(robots.RobotsCache(lambda u: None, "x").allowed("https://e.cz/anything?hledat=1"))


class Taxonomy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.group = taxonomy.load()["groups"]["stredni_dodavky"]

    def m(self, text):
        return taxonomy.match_model(text, self.group)

    def test_matches(self):
        self.assertEqual(self.m("Citroën jumpy 2011 1.6 hdi"), ("Citroën", "Jumpy"))
        self.assertEqual(self.m("PEUGEOT EXPERT 2.0 HDi L2H1"), ("Peugeot", "Expert"))
        self.assertEqual(self.m("Fiat Scudo, tažné"), ("Fiat", "Scudo"))
        self.assertEqual(self.m("Toyota Pro Ace 2014"), ("Toyota", "ProAce"))
        self.assertEqual(self.m("VW Transporter T5"), ("Volkswagen", "Transporter"))

    def test_no_false_positives(self):
        self.assertIsNone(self.m("Citroën Jumper L2H2"))
        self.assertIsNone(self.m("Škoda Octavia 2.0 TDI"))
        self.assertIsNone(self.m("Opel Vivarosa"))  # no partial words


if __name__ == "__main__":
    unittest.main()
