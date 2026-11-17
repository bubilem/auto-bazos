"""Bazoš categories in config.json (portals.bazos.categories): validate and save. Other config keys are preserved."""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "config.json"
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


class SourceError(ValueError):
    pass


def load_categories(path=None):
    return json.loads(Path(path or PATH).read_text(encoding="utf-8"))["portals"]["bazos"]["categories"]


def validate_categories(raw):
    if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
        raise SourceError("categories: 1 až 100 kategorií")
    out, seen = [], set()
    for i, c in enumerate(raw, 1):
        slug, pages = (c.get("slug"), c.get("max_pages")) if isinstance(c, dict) else (None, None)
        if not isinstance(slug, str) or not _SLUG.fullmatch(slug.strip().lower()):
            raise SourceError(f"kategorie {i}: slug je část adresy auto.bazos.cz/<slug>/ (malá písmena, číslice, pomlčka)")
        slug = slug.strip().lower()
        if isinstance(pages, bool) or not isinstance(pages, (int, float)) or pages != int(pages) or not 1 <= pages <= 50:
            raise SourceError(f"kategorie {slug}: počet stránek je celé číslo 1 až 50")
        if slug in seen:
            raise SourceError(f"kategorie {slug}: je v seznamu dvakrát")
        seen.add(slug)
        out.append({"slug": slug, "max_pages": int(pages)})
    return out


def save_categories(categories, path=None):
    path = Path(path or PATH)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["portals"]["bazos"]["categories"] = categories
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
