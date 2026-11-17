"""Search profiles (profiles.json): load, validate, save. Shared by the crawler and the local server (GUI editor)."""
import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "profiles.json"

WEIGHT_KEYS = ("price", "stk", "keywords", "presentation")
KEYWORD_LISTS = ("exclude_keywords", "positive_keywords", "warning_keywords")
_ID = re.compile(r"[a-z0-9_]{1,40}")


class ProfileError(ValueError):
    pass


def load(path=None):
    return json.loads(Path(path or PATH).read_text(encoding="utf-8"))["profiles"]


def save(profiles, path=None):
    path = Path(path or PATH)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"profiles": profiles}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # atomic


def make_id(name, taken=()):
    """'Dodávka na suť!' -> 'dodavka_na_sut' (unique among `taken`)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")[:32] or "profil"
    pid, n = base, 2
    while pid in taken:
        pid, n = f"{base}_{n}", n + 1
    return pid


def _text(raw, field, maxlen, required=False):
    s = raw.get(field, "")
    if not isinstance(s, str):
        raise ProfileError(f"{field}: musí být text")
    s = s.strip()
    if required and not s:
        raise ProfileError(f"{field}: je povinné")
    if len(s) > maxlen:
        raise ProfileError(f"{field}: nejvýše {maxlen} znaků")
    return s


def _int(raw, field, lo, hi):
    v = raw.get(field)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v) or not lo <= v <= hi:
        raise ProfileError(f"{field}: celé číslo {lo} až {hi}")
    return int(v)


def validate(raw, group_ids):
    """Normalise and check one profile from untrusted input. Raises ProfileError with a Czech message."""
    if not isinstance(raw, dict):
        raise ProfileError("profil musí být objekt")
    pid = raw.get("id")
    if not isinstance(pid, str) or not _ID.fullmatch(pid):
        raise ProfileError("id: jen malá písmena a–z, číslice a _ (nejvýše 40 znaků)")
    group = raw.get("equivalence_group")
    if group not in group_ids:
        raise ProfileError("equivalence_group: neznámá skupina modelů")
    params = raw.get("params")
    if not isinstance(params, dict):
        raise ProfileError("params: chybí")
    target = _int(params, "price_target_czk", 0, 10_000_000)
    top = _int(params, "price_max_czk", 0, 10_000_000)
    if target > top:
        raise ProfileError("cílová cena nesmí být vyšší než maximální")
    out = {
        "id": pid,
        "name": _text(raw, "name", 80, required=True),
        "purpose": _text(raw, "purpose", 2000),
        "reference_model": _text(raw, "reference_model", 80),
        "equivalence_group": group,
        "params": {"price_target_czk": target, "price_max_czk": top},
    }
    for field in KEYWORD_LISTS:
        words = raw.get(field, [])
        if not isinstance(words, list) or len(words) > 100 or not all(isinstance(w, str) for w in words):
            raise ProfileError(f"{field}: seznam textů (nejvýše 100)")
        cleaned = list(dict.fromkeys(w.strip() for w in words if w.strip()))
        if any(len(w) > 60 for w in cleaned):
            raise ProfileError(f"{field}: slovo je delší než 60 znaků")
        out[field] = cleaned
    weights = raw.get("score_weights")
    if not isinstance(weights, dict) or set(weights) - set(WEIGHT_KEYS):
        raise ProfileError("score_weights: povolené klíče " + ", ".join(WEIGHT_KEYS))
    out["score_weights"] = {k: _int(weights, k, 0, 100) for k in WEIGHT_KEYS if k in weights}
    if not out["score_weights"] or sum(out["score_weights"].values()) == 0:
        raise ProfileError("score_weights: alespoň jedna váha musí být větší než 0")
    return out
