"""profiles.json: validation of untrusted profile input and id generation."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler import profiles  # noqa: E402

GROUPS = {"stredni_dodavky", "starsi_mpv"}
BASE = json.loads((ROOT / "profiles.json").read_text(encoding="utf-8"))["profiles"][0]


class Validate(unittest.TestCase):
    def bad(self, **change):
        p = copy.deepcopy(BASE)
        for k, v in change.items():
            p[k] = v
        with self.assertRaises(profiles.ProfileError):
            profiles.validate(p, GROUPS)

    def test_shipped_profiles_are_valid(self):
        for p in profiles.load():
            self.assertEqual(profiles.validate(p, GROUPS), p)

    def test_strips_and_dedupes_keywords(self):
        p = copy.deepcopy(BASE)
        p["positive_keywords"] = [" stk ", "stk", "", "tažné"]
        self.assertEqual(profiles.validate(p, GROUPS)["positive_keywords"], ["stk", "tažné"])

    def test_rejects_bad_input(self):
        self.bad(id="Bad Id!")
        self.bad(id=5)
        self.bad(name="  ")
        self.bad(equivalence_group="neexistuje")
        self.bad(params={"price_target_czk": 90000, "price_max_czk": 80000})
        self.bad(params={"price_target_czk": -1, "price_max_czk": 80000})
        self.bad(params={"price_target_czk": "80000", "price_max_czk": 90000})
        self.bad(params={"price_target_czk": True, "price_max_czk": 90000})
        self.bad(positive_keywords="stk")
        self.bad(positive_keywords=["x" * 61])
        self.bad(score_weights={"price": 30, "evil": 5})
        self.bad(score_weights={"price": 0, "stk": 0, "keywords": 0, "presentation": 0})
        self.bad(score_weights={"price": 500, "stk": 30, "keywords": 25, "presentation": 15})
        with self.assertRaises(profiles.ProfileError):
            profiles.validate("not a dict", GROUPS)

    def test_make_id(self):
        self.assertEqual(profiles.make_id("Dodávka na suť!"), "dodavka_na_sut")
        self.assertEqual(profiles.make_id("Dodávka na suť", {"dodavka_na_sut"}), "dodavka_na_sut_2")
        self.assertEqual(profiles.make_id("???"), "profil")


if __name__ == "__main__":
    unittest.main()
