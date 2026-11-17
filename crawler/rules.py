"""Deterministic rules for Czech car ads: fact extraction + base scoring.

Public API:
    normalize(text)                      -> lowercase, diacritics stripped, whitespace collapsed
    analyze(title, description, today)   -> dict of extracted facts (stk, tow_bar, year, mileage, ...)
    score_listing(listing, profile, today) -> dict (base_score, breakdown, hits, excluded, facts)
    extract_price_czk(text)              -> int | None

All matching runs on normalized text, so "STK", "stk", "S.T.K." and "Stk" are equal and
Czech diacritics never matter. Unknown facts are returned as None / "unknown" - never guessed
silently; year / mileage carry a `confidence` ("high" = explicit context, "low" = bare guess).
"""
import re
import unicodedata
from datetime import date

# --------------------------------------------------------------------------- normalization


def normalize(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace(" ", " ")
    text = re.sub(r"(?<![a-z0-9])s\.\s?t\.\s?k\.?", "stk", text)  # "s.t.k." -> "stk"
    return re.sub(r"\s+", " ", text).strip()


def _negated(text, start):
    """True if the match at `start` is preceded by a negation ("bez", "žádné", "ne", ...)."""
    prefix = text[max(0, start - 24):start]
    return bool(re.search(r"(?<![a-z0-9])(?:bez|zadn[aeyiu]m?|nema|nemaji|nebyl[aoiy]?|nikdy|ne)\s+(?:zadn\w+\s+)?$", prefix))


def _phrase_regex(keyword):
    """Regex for a user/config keyword: tolerant to inflection endings and spacing."""
    words = normalize(keyword).split()
    if not words:
        return None
    parts = []
    for i, w in enumerate(words):
        parts.append(re.escape(w))
        if i < len(words) - 1:
            nxt = words[i + 1]
            parts.append(r"\s+" if w[-1].isalpha() and nxt[0].isalpha() else r"\s*")
    body = "".join(parts)
    last = words[-1]
    pre = r"(?<![a-z0-9])" if words[0][0].isalnum() else ""
    if last[-1].isalpha() and len(last) >= 4:
        post = r"[a-z]{0,4}(?![a-z0-9])"  # tolerate Czech endings: tazne -> tazneho
    elif last[-1].isalnum():
        post = r"(?![a-z0-9])"
    else:
        post = ""
    return re.compile(pre + body + post)


def find_phrase(norm_text, keyword):
    """First non-negated occurrence of `keyword` in normalized text, or None."""
    rx = _phrase_regex(keyword)
    if rx is None:
        return None
    for m in rx.finditer(norm_text):
        if not _negated(norm_text, m.start()):
            return m
    return None


# --------------------------------------------------------------------------- STK

_TOK = r"(?<![a-z0-9])(?:stk|tk)(?![a-z0-9])"
_MONTH_PREFIX = {"led": 1, "uno": 2, "bre": 3, "dub": 4, "kve": 5, "srp": 8, "zar": 9, "rij": 10, "lis": 11, "pro": 12}
_DATE = (
    r"(?:\d{1,2}\s*\.\s*(?P<fm>\d{1,2})\s*\.\s*(?P<fy>\d{4})"            # 14.5.2027
    r"|(?P<m>\d{1,2})\s*[/.\-]\s*(?P<y>\d{4}|\d{2})(?!\d)"                 # 08/2027, 8/27, 8.2027
    r"|(?P<mon>[a-z]{4,10})\s+(?P<y2>(?:19|20)\d{2})(?!\d)"                # srpna 2027
    r"|(?P<yo>(?:19|20)\d{2})(?!\d)(?!\s*km))"                              # 2027
)
_STK_DATED = re.compile(
    _TOK + r"(?:\s+(?:a|i)\s+emise)?\s*(?:je\s+)?(?:platn\w*\s+)?(?:do\s+|:\s*|-\s*|v\s+)?" + _DATE
)
_STK_NEGATIVE = [
    re.compile(r"(?<![a-z0-9])(?:bez|nema|nemame|neni|propadl\w*|vyprsel\w*|neplatn\w*)\s+(?:platn\w+\s+)?" + _TOK),
    re.compile(_TOK + r"\s+(?:je\s+)?(?:propadl\w*|vyprsel\w*|neplatn\w*|chybi|nutn\w*|treba|bude\s+potreba)"),
    re.compile(r"nutn\w*\s+(?:udelat\s+)?" + _TOK),
    re.compile(_TOK + r"\s+(?:je\s+)?(?:nutn\w*|treba)?\s*(?:udelat|obnovit)"),
]
_STK_FRESH = re.compile(r"(?:(?<![a-z0-9])(?:nov[aey]|cerstv[aey]|svez[ie]|po)\s+" + _TOK + r"|" + _TOK + r"\s+(?:prave|nedavno)\s+\w+)")
_STK_GENERIC_VALID = re.compile(r"(?:platn\w+\s+" + _TOK + r"|" + _TOK + r"\s+(?:je\s+)?(?:platn\w+|ok|v\s+poradku))")


def _month_from_name(word):
    if word.startswith("cerv"):
        return 7 if word.startswith("cervenc") else 6
    for prefix, num in _MONTH_PREFIX.items():
        if word.startswith(prefix) and len(word) >= (6 if prefix == "pro" else 4):
            return num
    return None


def _parse_dated(norm):
    """Return (year, month) of the first valid dated STK mention, else None."""
    for m in _STK_DATED.finditer(norm):
        g = m.groupdict()
        year = month = None
        if g["fm"]:
            year, month = int(g["fy"]), int(g["fm"])
        elif g["m"]:
            year, month = int(g["y"]), int(g["m"])
            if year < 100:
                year += 2000
        elif g["mon"]:
            month = _month_from_name(g["mon"])
            year = int(g["y2"])
        elif g["yo"]:
            year, month = int(g["yo"]), 12
        if month and 1 <= month <= 12 and 2000 <= (year or 0) <= 2100:
            return year, month
    return None


def extract_stk(text, today=None):
    """-> {"status": valid|fresh|expired|none|unknown, "valid_until": "YYYY-MM"|None, "label": str|None}"""
    today = today or date.today()
    norm = text if text == normalize(text) else normalize(text)
    dated = _parse_dated(norm)
    negative = any(rx.search(norm) for rx in _STK_NEGATIVE)
    fresh = bool(_STK_FRESH.search(norm))

    if dated:
        y, m = dated
        until = f"{y:04d}-{m:02d}"
        if (y, m) >= (today.year, today.month):
            return {"status": "valid", "valid_until": until, "label": f"STK do {m:02d}/{y}"}
        if not negative and not fresh:
            return {"status": "expired", "valid_until": until, "label": f"STK vypršela {m:02d}/{y}"}
    if negative:
        return {"status": "none", "valid_until": None, "label": "bez STK"}
    if fresh:
        return {"status": "fresh", "valid_until": None, "label": "nová STK"}
    if _STK_GENERIC_VALID.search(norm):
        return {"status": "valid", "valid_until": None, "label": "platná STK"}
    return {"status": "unknown", "valid_until": None, "label": None}


def _months_left(stk, today):
    y, m = map(int, stk["valid_until"].split("-"))
    return (y - today.year) * 12 + (m - today.month)


# --------------------------------------------------------------------------- equipment / warnings

_TOW = re.compile(r"(?<![a-z0-9])(?:tazn\w*|tazak\w*)")
_EQUIPMENT = [
    (re.compile(r"(?<![a-z0-9])(l[1-4]\s?h[1-3])(?![a-z0-9])"), None),  # label = match upper-cased
    (re.compile(r"(?<![a-z0-9])vydrev\w*"), "výdřeva"),
    (re.compile(r"(?<![a-z0-9])zahradk\w*"), "zahrádka"),
    (re.compile(r"(?<![a-z0-9])regal\w*"), "regály"),
]
WARNING_PATTERNS = [
    (r"na nahradni dily", "na náhradní díly"),
    (r"bez prepisu", "bez přepisu"),
    (r"nouzov\w+\s+rezim", "nouzový režim"),
    (r"(?<![a-z0-9])(?:klepe|klepani)", "klepe"),
    (r"(?<![a-z0-9])vari(?![a-z0-9])", "vaří"),
    (r"koroz\w+\s+prah\w*|zrezl\w+\s+prah\w*", "koroze prahů"),
    (r"(?<!ne)havarovan\w*|(?<!ne)bourane?\w*", "havarované"),
    (r"nepojizdn\w*", "nepojízdné"),
    (r"bez\s+tp(?![a-z0-9])|bez\s+technick\w+\s+prukaz\w*", "bez TP"),
    (r"(?<![a-z0-9])adblue", "AdBlue"),
    (r"(?<![a-z0-9])k\.\s?o\.", "k.o."),
]
_WARNING_RX = [(re.compile(p), label) for p, label in WARNING_PATTERNS]


def extract_tow_bar(norm):
    for m in _TOW.finditer(norm):
        if not _negated(norm, m.start()):
            return True
    return False


def extract_equipment(norm):
    found = []
    for rx, label in _EQUIPMENT:
        for m in rx.finditer(norm):
            if _negated(norm, m.start()):
                continue
            text = label or m.group(1).replace(" ", "").upper()
            if text not in found:
                found.append(text)
            break
    return found


def extract_warnings(norm):
    hits = []
    for rx, label in _WARNING_RX:
        for m in rx.finditer(norm):
            # "bez prepisu"/"bez tp" start with "bez" themselves; others must not be negated
            if label not in ("bez přepisu", "bez TP") and _negated(norm, m.start()):
                continue
            hits.append(label)
            break
    return hits


# --------------------------------------------------------------------------- year / mileage / fuel / price


def extract_year(title, description, today=None):
    today = today or date.today()
    max_year = today.year + 1
    ctx = re.compile(r"(?:r\.?\s?v\.?|rok\s+vyroby|rocnik|vyroba|rok)\s*:?\s*((?:19|20)\d{2})(?!\d)")
    for part in (normalize(title), normalize(description)):
        m = ctx.search(part)
        if m and 1980 <= int(m.group(1)) <= max_year:
            return {"value": int(m.group(1)), "confidence": "high"}
    bare = re.compile(r"(?<![\d.,/])((?:19[89]\d|20[0-3]\d))(?![\d])(?!\s*(?:km|kc|czk|kw|ccm))")
    norm_title = normalize(title)
    for m in bare.finditer(norm_title):
        before = norm_title[max(0, m.start() - 6):m.start()]
        if re.search(r"(?:do|stk|tk)\s*$", before) or re.search(r"\d\s*[/.]\s*$", before):
            continue
        if 1980 <= int(m.group(1)) <= max_year:
            return {"value": int(m.group(1)), "confidence": "low"}
    return {"value": None, "confidence": None}


_KM_NUM = r"(\d{1,3}(?:[ .]\d{3})+|\d{4,7})"
_KM_CONTEXT = re.compile(r"(?:najeto|najezd|ujeto|tachometr\w*|stav\s+km|km\s*:)\s*[:\-]?\s*" + _KM_NUM + r"\s*(?:km|tis\.?|tkm)?")
_KM_PLAIN = re.compile(_KM_NUM + r"\s*km(?![a-z])")
_KM_TIS = re.compile(r"(?<![\d.,])(\d{2,3})\s*(?:tis\.?|tkm)(?:\s*km)?(?![a-z])")


def _to_int(s):
    return int(re.sub(r"[ .]", "", s))


def extract_mileage(title, description):
    norm = normalize(title + " . " + description)
    m = _KM_CONTEXT.search(norm)
    if m:
        v = _to_int(m.group(1))
        if 1000 <= v <= 1_500_000:
            return {"value": v, "confidence": "high"}
    for rx, mult in ((_KM_PLAIN, 1), (_KM_TIS, 1000)):
        for m in rx.finditer(norm):
            v = _to_int(m.group(1)) * mult
            # skip service intervals like "servis po 15 000 km" / "do 3 000 km"
            before = norm[max(0, m.start() - 14):m.start()]
            if re.search(r"(?:po|pred|kazdych|interval|za|do|cca po)\s*$", before):
                continue
            if 1000 <= v <= 1_500_000:
                return {"value": v, "confidence": "low"}
    return {"value": None, "confidence": None}


_FUEL = [
    ("lpg", r"(?<![a-z0-9])lpg(?![a-z0-9])"), ("cng", r"(?<![a-z0-9])cng(?![a-z0-9])"),
    ("diesel", r"(?<![a-z0-9])(?:diesel|nafta|tdi|hdi|dci|jtd|jtdm|cdi|tdci|crdi|bluehdi|multijet)(?![a-z0-9])"),
    ("benzín", r"(?<![a-z0-9])(?:benzin\w*|tsi|tfsi|vti|thp)(?![a-z0-9])"),
]


def extract_fuel(norm):
    for fuel, pat in _FUEL:
        if re.search(pat, norm):
            return fuel
    return None


def extract_price_czk(text):
    norm = normalize(text)
    m = re.search(r"(\d{1,3}(?:[ .]\d{3})+|\d{4,7})\s*(?:kc|czk|,-|\.-|,\s*-)", norm)
    return _to_int(m.group(1)) if m else None


# --------------------------------------------------------------------------- analyze + score


def analyze(title, description, today=None):
    today = today or date.today()
    norm = normalize(f"{title} . {description}")
    return {
        "stk": extract_stk(norm, today),
        "tow_bar": extract_tow_bar(norm),
        "equipment": extract_equipment(norm),
        "warnings": extract_warnings(norm),
        "year": extract_year(title, description, today),
        "mileage_km": extract_mileage(title, description),
        "fuel": extract_fuel(norm),
    }


DEFAULT_WEIGHTS = {"price": 30, "stk": 30, "keywords": 25, "presentation": 15}
UNKNOWN_STK_FRACTION = 0.4  # neutral: not knowing is not the same as "expired"
WARNING_PENALTY = 8


def _price_fraction(price, profile):
    if price is None:
        return 0.5
    params = profile.get("params", {})
    target, high = params.get("price_target_czk"), params.get("price_max_czk")
    if not target:
        return 0.5
    if price <= target:
        return 1.0
    if not high or price > high:
        return 0.0
    return 1.0 - 0.7 * (price - target) / (high - target)


def _stk_fraction(stk, today):
    status = stk["status"]
    if status == "fresh":
        return 1.0
    if status == "valid":
        if stk["valid_until"]:
            left = _months_left(stk, today)
            return 1.0 if left >= 12 else 0.8 if left >= 6 else 0.5
        return 0.65
    if status in ("expired", "none"):
        return 0.0
    return UNKNOWN_STK_FRACTION


def _presentation_fraction(listing):
    pts = 0.0
    n = listing.get("image_count") or 0
    pts += 8 if n >= 5 else 4 if n >= 3 else 0
    pts += 4 if len(listing.get("description") or "") >= 200 else 0
    pts += 3 if listing.get("location") else 0
    return pts / 15


def score_listing(listing, profile, today=None):
    """listing: {title, description, price_czk, image_count, location}; profile: config.json profile."""
    today = today or date.today()
    title, desc = listing.get("title", ""), listing.get("description", "")
    facts = analyze(title, desc, today)
    if listing.get("known_stk"):  # structured value from the portal beats text extraction
        facts["stk"] = listing["known_stk"]
    norm = normalize(f"{title} . {desc}")
    w = {**DEFAULT_WEIGHTS, **profile.get("score_weights", {})}

    exclude_hits = [kw for kw in profile.get("exclude_keywords", []) if find_phrase(norm, kw)]

    positive_hits = []
    for kw in profile.get("positive_keywords", []):
        if normalize(kw) == "stk":
            if facts["stk"]["status"] in ("valid", "fresh"):
                positive_hits.append(facts["stk"]["label"])
        elif find_phrase(norm, kw):
            positive_hits.append(kw)
    warning_hits = list(dict.fromkeys(
        facts["warnings"] + [kw for kw in profile.get("warning_keywords", [])
                             if find_phrase(norm, kw) and kw not in facts["warnings"]]
    ))

    n_pos_cfg = max(len(profile.get("positive_keywords", [])), 1)
    kw_fraction = min(1.0, len(positive_hits) / min(n_pos_cfg, 4))

    breakdown = {
        "price": round(w["price"] * _price_fraction(listing.get("price_czk"), profile), 1),
        "stk": round(w["stk"] * _stk_fraction(facts["stk"], today), 1),
        "keywords": round(w["keywords"] * kw_fraction, 1),
        "presentation": round(w["presentation"] * _presentation_fraction(listing), 1),
        "warning_penalty": -WARNING_PENALTY * len(warning_hits),
    }
    total = sum(breakdown.values())
    return {
        "profile_id": profile.get("id"),
        "base_score": max(0, min(100, round(total))),
        "breakdown": breakdown,
        "positive_hits": positive_hits,
        "warning_hits": warning_hits,
        "excluded": bool(exclude_hits),
        "exclude_hits": exclude_hits,
        "facts": facts,
    }
