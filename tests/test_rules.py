"""Run from project root: python -m unittest discover -s tests -v"""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler import rules  # noqa: E402

TODAY = date(2026, 11, 16)
PROFILE = json.loads((ROOT / "profiles.json").read_text(encoding="utf-8"))["profiles"][0]


class Normalize(unittest.TestCase):
    def test_diacritics_case_whitespace(self):
        self.assertEqual(rules.normalize("  Nová  STK, TAŽNÉ "), "nova stk, tazne")

    def test_dotted_stk(self):
        self.assertEqual(rules.normalize("S.T.K. do 5/2027"), "stk do 5/2027")


class Stk(unittest.TestCase):
    def check(self, text, status, until=None):
        r = rules.extract_stk(text, TODAY)
        self.assertEqual((r["status"], r["valid_until"]), (status, until), text)

    def test_dated_variants(self):
        self.check("STK do 08/2027", "valid", "2027-08")
        self.check("Stk do 8.2027", "valid", "2027-08")
        self.check("TK do 3/27", "valid", "2027-03")
        self.check("STK platná do srpna 2027", "valid", "2027-08")
        self.check("STK do června 2027", "valid", "2027-06")
        self.check("STK do července 2027", "valid", "2027-07")
        self.check("STK 12/2026", "valid", "2026-12")
        self.check("STK do 14.5.2027", "valid", "2027-05")
        self.check("STK a emise do 03/2028", "valid", "2028-03")
        self.check("STK do 2028", "valid", "2028-12")

    def test_current_month_still_valid(self):
        self.check("STK do 11/2026", "valid", "2026-11")

    def test_expired_date(self):
        self.check("STK do 03/2025", "expired", "2025-03")

    def test_negative(self):
        for t in ["bez STK", "Prodám bez stk a bez TP", "STK propadlá", "propadlá stk", "STK nutno udělat",
                  "nutno udělat STK", "nemá STK", "STK vypršela", "stk je třeba udělat", "bez platné STK"]:
            self.check(t, "none")

    def test_fresh(self):
        for t in ["nová STK", "čerstvá TK", "Čerstvě po STK", "svěží STK"]:
            self.check(t, "fresh")

    def test_generic_valid(self):
        self.check("platná STK", "valid")
        self.check("STK ok", "valid")

    def test_unknown(self):
        self.check("Prodám dodávku, jezdí dobře.", "unknown")

    def test_no_false_date_from_engine_or_km(self):
        self.check("STK 2.0 HDi výborný stav", "unknown")
        self.check("STK 2000 km od servisu", "unknown")

    def test_future_date_beats_old_negative(self):
        self.check("Bez STK minule, teď nová STK do 09/2028", "valid", "2028-09")

    def test_label(self):
        self.assertEqual(rules.extract_stk("STK do 9/2027", TODAY)["label"], "STK do 09/2027")


class Equipment(unittest.TestCase):
    def norm(self, t):
        return rules.normalize(t)

    def test_tow_bar(self):
        self.assertTrue(rules.extract_tow_bar(self.norm("Tažné zařízení, nový olej")))
        self.assertTrue(rules.extract_tow_bar(self.norm("s tažným zařízením")))
        self.assertFalse(rules.extract_tow_bar(self.norm("bez tažného zařízení")))
        self.assertFalse(rules.extract_tow_bar(self.norm("Nemá tažné")))
        self.assertFalse(rules.extract_tow_bar(self.norm("jen dodávka")))

    def test_equipment(self):
        self.assertEqual(rules.extract_equipment(self.norm("Expert L2 H2, výdřeva, regály")), ["L2H2", "výdřeva", "regály"])
        self.assertEqual(rules.extract_equipment(self.norm("bez regálů")), [])


class Warnings(unittest.TestCase):
    def w(self, t):
        return rules.extract_warnings(rules.normalize(t))

    def test_hits(self):
        self.assertIn("klepe", self.w("Motor klepe za studena"))
        self.assertIn("vaří", self.w("Občas vaří"))
        self.assertIn("nouzový režim", self.w("Přechází do nouzového režimu"))
        self.assertIn("na náhradní díly", self.w("Prodám na náhradní díly"))
        self.assertIn("k.o.", self.w("Auto k.o. po nehodě"))
        self.assertIn("bez TP", self.w("Prodám bez TP"))
        self.assertIn("bez přepisu", self.w("Prodej bez přepisu"))
        self.assertIn("koroze prahů", self.w("Pozor koroze prahů"))
        self.assertIn("havarované", self.w("Havarované auto"))

    def test_negations(self):
        self.assertEqual(self.w("Motor neklepe, nevaří"), [])
        self.assertEqual(self.w("Nehavarované, nebourané"), [])
        self.assertEqual(self.w("Bez klepání a bez koroze"), [])

    def test_false_friends(self):
        self.assertEqual(self.w("Pozor, vařila jsem čaj v autě"), [])  # not the verb 'vaří'


class Facts(unittest.TestCase):
    def test_year(self):
        self.assertEqual(rules.extract_year("Citroen Jumpy 2009", "", TODAY), {"value": 2009, "confidence": "low"})
        self.assertEqual(rules.extract_year("Jumpy", "rok výroby 2011, tažné", TODAY), {"value": 2011, "confidence": "high"})
        self.assertEqual(rules.extract_year("Jumpy r.v. 2008", "", TODAY), {"value": 2008, "confidence": "high"})
        self.assertIsNone(rules.extract_year("Jumpy STK do 2027", "", TODAY)["value"])
        self.assertIsNone(rules.extract_year("Jumpy 2.0 HDi", "", TODAY)["value"])

    def test_mileage(self):
        self.assertEqual(rules.extract_mileage("", "Najeto 285 000 km, servis"), {"value": 285000, "confidence": "high"})
        self.assertEqual(rules.extract_mileage("Expert 241000km", ""), {"value": 241000, "confidence": "low"})
        self.assertEqual(rules.extract_mileage("", "nájezd 250 tis. km")["value"], 250000)
        self.assertEqual(rules.extract_mileage("Trafic 330tkm", "")["value"], 330000)
        self.assertIsNone(rules.extract_mileage("", "olej se mění po 15 000 km")["value"])
        self.assertIsNone(rules.extract_mileage("", "Nová spojka před 20 tis. km")["value"])
        self.assertIsNone(rules.extract_mileage("Jumpy", "bez údajů")["value"])

    def test_fuel(self):
        n = rules.normalize
        self.assertEqual(rules.extract_fuel(n("Jumpy 2.0 HDi")), "diesel")
        self.assertEqual(rules.extract_fuel(n("Octavia 1.4 TSI benzín")), "benzín")
        self.assertEqual(rules.extract_fuel(n("Octavia LPG")), "lpg")
        self.assertIsNone(rules.extract_fuel(n("Prodám auto")))

    def test_price(self):
        self.assertEqual(rules.extract_price_czk("Cena 68 000 Kč"), 68000)
        self.assertEqual(rules.extract_price_czk("65.000,-"), 65000)
        self.assertEqual(rules.extract_price_czk("89000 Kč"), 89000)
        self.assertIsNone(rules.extract_price_czk("Cena dohodou"))


class Scoring(unittest.TestCase):
    def listing(self, **kw):
        base = dict(title="Citroen Jumpy 2.0 HDi L2H1, nová STK, tažné", price_czk=68000, image_count=8, location="Olomouc",
                    description="Pracant po stavbě, STK do 09/2027, tažné zařízení, výdřeva. " * 4)
        base.update(kw)
        return base

    def score(self, **kw):
        return rules.score_listing(self.listing(**kw), PROFILE, TODAY)

    def test_good_listing_scores_high(self):
        r = self.score()
        self.assertGreaterEqual(r["base_score"], 80)
        self.assertFalse(r["excluded"])
        self.assertIn("STK do 09/2027", r["positive_hits"])
        self.assertIn("tažné", r["positive_hits"])
        self.assertIn("2.0 hdi", r["positive_hits"])
        self.assertEqual(r["warning_hits"], [])

    def test_stk_keyword_not_credited_when_missing(self):
        r = self.score(title="Fiat Scudo", description="Bez STK, tažné.")
        self.assertNotIn("stk", [h.lower() for h in r["positive_hits"]])
        self.assertEqual(r["breakdown"]["stk"], 0)

    def test_unknown_stk_is_neutral_not_zero(self):
        unknown = self.score(title="Fiat Scudo", description="Slušný stav.")["breakdown"]["stk"]
        none = self.score(title="Fiat Scudo", description="Bez STK.")["breakdown"]["stk"]
        valid = self.score(title="Fiat Scudo", description="STK do 12/2027.")["breakdown"]["stk"]
        self.assertTrue(none < unknown < valid)

    def test_price_bands(self):
        self.assertEqual(self.score(price_czk=70000)["breakdown"]["price"], 30.0)
        mid = self.score(price_czk=88000)["breakdown"]["price"]
        self.assertTrue(0 < mid < 30)
        self.assertEqual(self.score(price_czk=120000)["breakdown"]["price"], 0)
        self.assertEqual(self.score(price_czk=None)["breakdown"]["price"], 15.0)

    def test_exclude_keywords(self):
        r = self.score(description="Prodám na náhradní díly, havarované.")
        self.assertTrue(r["excluded"])
        self.assertIn("na náhradní díly", r["exclude_hits"])
        self.assertFalse(self.score(description="Nehavarované, bez nehody.")["excluded"])

    def test_warnings_lower_score(self):
        clean = self.score(description="STK do 09/2027, tažné.")["base_score"]
        bad = self.score(description="STK do 09/2027, tažné. Motor klepe a občas nouzový režim.")
        self.assertEqual(sorted(bad["warning_hits"]), ["klepe", "nouzový režim"])
        self.assertLess(bad["base_score"], clean)

    def test_score_clamped(self):
        r = self.score(price_czk=200000, description="Klepe, vaří, nouzový režim, koroze prahů, AdBlue, bez přepisu.", image_count=0, location=None)
        self.assertEqual(r["base_score"], 0)

    def test_presentation(self):
        rich = self.score()["breakdown"]["presentation"]
        poor = self.score(image_count=1, location=None, description="Krátce.")["breakdown"]["presentation"]
        self.assertEqual(rich, 15.0)
        self.assertEqual(poor, 0.0)

    def test_expired_stk_zero(self):
        self.assertEqual(self.score(title="Citroen Jumpy", description="STK do 01/2025")["breakdown"]["stk"], 0)


class SampleData(unittest.TestCase):
    """Fixture ads: the rules must rank them like a human would."""

    def test_fixture_ordering(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import make_fixtures  # sample ads used for UI development; independent of whatever is in data/
        scores = {}
        for l in make_fixtures.LISTINGS:
            scores[l["uid"]] = rules.score_listing(
                dict(title=l["title"], description=l["desc"], price_czk=l["price"],
                     image_count=4, location=l["loc"]), PROFILE, TODAY)["base_score"]
        self.assertGreater(scores["bazos_100000001"], scores["sauto_200000002"])
        self.assertGreater(scores["sauto_200000002"], scores["bazos_100000004"])
        self.assertGreater(scores["bazos_100000004"], scores["bazos_100000003"])


if __name__ == "__main__":
    unittest.main()
