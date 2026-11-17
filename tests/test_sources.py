"""Editable model groups (taxonomy.json) and Bazoš categories (config.json): validation and saving."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler import sources, taxonomy  # noqa: E402


class Group(unittest.TestCase):
    OK = {"name": "Kombi", "models": [{"make": "Škoda", "model": "Octavia", "match": [" octavia ", "oktavia", ""], "notes": " ok "}]}

    def bad(self, group):
        with self.assertRaises(taxonomy.TaxonomyError):
            taxonomy.validate_group(group)

    def test_normalises(self):
        g = taxonomy.validate_group(self.OK)
        self.assertEqual(g["models"][0], {"make": "Škoda", "model": "Octavia", "match": ["octavia", "oktavia"], "notes": "ok"})

    def test_shipped_taxonomy_is_valid(self):
        for gid, g in taxonomy.load()["groups"].items():
            taxonomy.validate_group_id(gid)
            taxonomy.validate_group(g)

    def test_rejects_bad_input(self):
        self.bad("x")
        self.bad({"name": "", "models": self.OK["models"]})
        self.bad({"name": "A", "models": []})
        self.bad({"name": "A", "models": [{"make": "Škoda", "model": ""}]})
        self.bad({"name": "A", "models": [{"make": "Škoda", "model": "Octavia"}, {"make": "škoda", "model": "OCTAVIA"}]})
        self.bad({"name": "A", "models": [{"make": "Š", "model": "O", "match": "octavia"}]})
        self.bad({"name": "A", "models": [{"make": "Š", "model": "O", "match": ["x"] * 11}]})
        self.bad({"name": "A", "models": [{"make": 5, "model": "O"}]})
        with self.assertRaises(taxonomy.TaxonomyError):
            taxonomy.validate_group_id("Bad Id")


class Categories(unittest.TestCase):
    def test_normalises_and_rejects(self):
        self.assertEqual(sources.validate_categories([{"slug": " Dodavka ", "max_pages": 8}]), [{"slug": "dodavka", "max_pages": 8}])
        for bad in ([], "x", [{"slug": "../etc", "max_pages": 3}], [{"slug": "a b", "max_pages": 3}], [{"slug": "a", "max_pages": 0}],
                    [{"slug": "a", "max_pages": 51}], [{"slug": "a", "max_pages": True}],
                    [{"slug": "a", "max_pages": 1}, {"slug": "a", "max_pages": 2}], [{"slug": "a?hledat=x", "max_pages": 1}]):
            with self.assertRaises(sources.SourceError, msg=bad):
                sources.validate_categories(bad)

    def test_save_keeps_other_config_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            shutil.copy(ROOT / "config.json", path)
            sources.save_categories([{"slug": "skoda", "max_pages": 2}], path)
            cfg = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(cfg["portals"]["bazos"]["categories"], [{"slug": "skoda", "max_pages": 2}])
            self.assertIn("scraping", cfg)
            self.assertIn("server", cfg)


if __name__ == "__main__":
    unittest.main()
