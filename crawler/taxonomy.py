"""Local model matching from taxonomy.json (portals can't be searched by parameter, see bazos.py)."""
import json
import os
import re
from pathlib import Path

from .rules import normalize

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "taxonomy.json"
_ID = re.compile(r"[a-z0-9_]{1,40}")


class TaxonomyError(ValueError):
    pass


def load(path=None):
    return json.loads(Path(path or PATH).read_text(encoding="utf-8"))


def save(tax, path=None):
    path = Path(path or PATH)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(tax, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # atomic


def _str(v, field, maxlen, required=False):
    if not isinstance(v, str):
        raise TaxonomyError(f"{field}: musí být text")
    v = v.strip()
    if required and not v:
        raise TaxonomyError(f"{field}: je povinné")
    if len(v) > maxlen:
        raise TaxonomyError(f"{field}: nejvýše {maxlen} znaků")
    return v


def validate_group_id(gid):
    if not isinstance(gid, str) or not _ID.fullmatch(gid):
        raise TaxonomyError("id: jen malá písmena a–z, číslice a _ (nejvýše 40 znaků)")
    return gid


def validate_group(raw):
    """Normalise one model group {name, models: [{make, model, match?, notes?}]} from untrusted input."""
    if not isinstance(raw, dict):
        raise TaxonomyError("skupina musí být objekt")
    models, seen = raw.get("models"), set()
    if not isinstance(models, list) or not 1 <= len(models) <= 100:
        raise TaxonomyError("models: 1 až 100 modelů")
    out_models = []
    for i, m in enumerate(models, 1):
        if not isinstance(m, dict):
            raise TaxonomyError(f"model {i}: musí být objekt")
        entry = {"make": _str(m.get("make"), f"model {i}: značka", 60, True),
                 "model": _str(m.get("model"), f"model {i}: model", 60, True)}
        key = (entry["make"].lower(), entry["model"].lower())
        if key in seen:
            raise TaxonomyError(f"model {i}: {entry['make']} {entry['model']} je v seznamu dvakrát")
        seen.add(key)
        match = m.get("match") or []
        if not isinstance(match, list) or len(match) > 10:
            raise TaxonomyError(f"model {i}: match je seznam nejvýše 10 textů")
        match = [t for t in dict.fromkeys(_str(t, f"model {i}: match", 60) for t in match) if t]
        if match:
            entry["match"] = match
        notes = _str(m.get("notes", ""), f"model {i}: poznámka", 500)
        if notes:
            entry["notes"] = notes
        out_models.append(entry)
    return {"name": _str(raw.get("name"), "name", 80, True), "models": out_models}


def _compile(group):
    out = []
    for entry in group["models"]:
        terms = [normalize(t) for t in entry.get("match") or [entry["model"]]]
        rx = re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(t).replace(r"\ ", r"\s*") for t in terms) + r")(?![a-z0-9])")
        out.append((entry, rx))
    return out


def match_model(text, group):
    """-> (make, model) of the first taxonomy entry whose model name occurs in `text`, else None."""
    norm = normalize(text)
    for entry, rx in _compile(group):
        if rx.search(norm):
            return entry["make"], entry["model"]
    return None
