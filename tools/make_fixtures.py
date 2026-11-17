"""Generate hand-made sample data (data/index.json + data/listings/*) for UI development.

Run from project root: python tools/make_fixtures.py
Replaced by real crawler output later (crawler/run.py writes the same shapes).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PROFILES = [
    {k: p[k] for k in ("id", "name", "purpose", "reference_model", "equivalence_group")}
    | {"price_target_czk": p["params"]["price_target_czk"]}
    for p in json.loads((ROOT / "profiles.json").read_text(encoding="utf-8"))["profiles"]
]

LISTINGS = [
    dict(uid="bazos_100000001", portal="bazos", title="Citroen Jumpy 2.0 HDi L2H1, nová STK, tažné",
         make="Citroën", model="Jumpy", year=2009, km=285000, fuel="diesel", price=68000, prev=75000,
         loc="Olomouc", stk="2027-09", tow=True, status="active", score=82,
         pos=["STK do 09/2027", "tažné", "2.0 HDi", "L2H1"], warn=[],
         desc="Prodám pracanta po stavbě, motor šlape pěkně, STK do 09/2027. Tažné zařízení, výdřeva v nákladovém prostoru. "
              "Kosmetické vady karoserie, škrábance. Nová spojka před 20 tis. km. Cena 68 000 Kč, mírná sleva možná při osobním převzetí.",
         first="2026-11-14", last="2026-11-16"),
    dict(uid="sauto_200000002", portal="sauto", title="Peugeot Expert 2.0 HDi 120 kW, servisní kniha",
         make="Peugeot", model="Expert", year=2011, km=241000, fuel="diesel", price=89000, prev=None,
         loc="Prostějov", stk="2027-03", tow=False, status="active", score=74,
         pos=["STK do 03/2027", "2.0 HDi"], warn=[], vin="VF3XXXXXXXXXXXXXX",
         desc="Pravidelně servisováno, servisní kniha, 2. majitel. STK do 03/2027. Bez tažného zařízení. Nové brzdy a pneu.",
         first="2026-11-10", last="2026-11-16"),
    dict(uid="bazos_100000003", portal="bazos", title="Renault Trafic 1.9 dCi - na dožití, bez STK",
         make="Renault", model="Trafic", year=2006, km=412000, fuel="diesel", price=45000, prev=None,
         loc="Šumperk", stk=None, tow=False, status="active", score=31,
         pos=[], warn=["bez STK", "klepe"],
         desc="Prodám Trafic, motor klepe při studeném startu, bez STK, vhodné na dílnu nebo náhradní díly. Cena dohodou.",
         first="2026-11-12", last="2026-11-16"),
    dict(uid="bazos_100000004", portal="bazos", title="Fiat Scudo 2.0 JTD, tažné, L2H1",
         make="Fiat", model="Scudo", year=2010, km=268000, fuel="diesel", price=72000, prev=None,
         loc="Brno", stk=None, tow=True, status="active", score=55,
         pos=["tažné", "L2H1"], warn=[],
         desc="Fiat Scudo ve slušném stavu, tažné, dlouhá verze. STK nutno udělat, jinak pojízdné a bez závad.",
         first="2026-11-15", last="2026-11-16"),
    dict(uid="sauto_200000005", portal="sauto", title="Volkswagen Transporter T5 1.9 TDI",
         make="Volkswagen", model="Transporter", year=2008, km=330000, fuel="diesel", price=95000, prev=105000,
         loc="Zlín", stk="2026-12", tow=True, status="inactive", score=60,
         pos=["tažné", "1.9 TDI"], warn=[],
         desc="T5 1.9 TDI, tažné, STK do 12/2026. Inzerát byl stažen (ukázka neaktivního inzerátu).",
         first="2026-10-28", last="2026-11-13"),
]

COLORS = ["#8aa4c8", "#c8a48a", "#8ac8a4", "#c88aa4", "#a48ac8", "#c8c88a"]


def svg_photo(n, title, color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600">'
            f'<rect width="800" height="600" fill="{color}"/>'
            f'<text x="400" y="290" font-size="64" text-anchor="middle" fill="#fff" font-family="sans-serif">Foto {n}</text>'
            f'<text x="400" y="350" font-size="28" text-anchor="middle" fill="#fff" font-family="sans-serif">{title[:40]}</text></svg>')


def svg_collage(title, n=6):
    cells = []
    for i in range(n):
        x, y = (i % 3) * 400, (i // 3) * 300
        cells.append(f'<rect x="{x}" y="{y}" width="400" height="300" fill="{COLORS[i]}" stroke="#fff" stroke-width="4"/>'
                     f'<text x="{x + 24}" y="{y + 70}" font-size="64" font-weight="bold" fill="#fff" font-family="sans-serif">[{i + 1}]</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="600" viewBox="0 0 1200 600">{"".join(cells)}</svg>'


def main():
    index = []
    for L in LISTINGS:
        folder = DATA / "listings" / L["uid"]
        (folder / "images").mkdir(parents=True, exist_ok=True)
        images = []
        for i in range(1, 5):
            rel = f"images/{i:02d}.svg"
            (folder / rel).write_text(svg_photo(i, L["title"], COLORS[i - 1]), encoding="utf-8")
            images.append(rel)
        (folder / "collage_1.svg").write_text(svg_collage(L["title"]), encoding="utf-8")

        history = [{"date": L["first"], "price_czk": L["prev"]}, {"date": L["last"], "price_czk": L["price"]}] \
            if L["prev"] else [{"date": L["first"], "price_czk": L["price"]}]
        listing = {
            "uid": L["uid"], "portal": L["portal"], "external_id": L["uid"].split("_")[1],
            "url": f"https://example.invalid/{L['uid']}", "status": L["status"],
            "first_seen": L["first"] + "T08:15:00Z", "last_seen": L["last"] + "T12:00:00Z",
            "price_czk": L["price"], "price_history": history,
            "vehicle": {"make": L["make"], "model": L["model"], "equivalence_group": "stredni_dodavky",
                        "year": L["year"], "mileage_km": L["km"], "fuel": L["fuel"],
                        "stk_detected": L["stk"], "tow_bar_detected": L["tow"], "vin": L.get("vin")},
            "location": L["loc"], "title": L["title"], "description": L["desc"],
            "images": images, "collages": ["collage_1.svg"],
            "rule_scoring": {"dodavka_na_sut": {"base_score": L["score"], "positive_hits": L["pos"], "warning_hits": L["warn"]}},
        }
        (folder / "listing.json").write_text(json.dumps(listing, ensure_ascii=False, indent=2), encoding="utf-8")

        tags = []
        if L["stk"]:
            tags.append("STK")
        if L["tow"]:
            tags.append("Tažné")
        if L["prev"]:
            tags.append("Sleva")
        if L["status"] != "active":
            tags.append("Neaktivní")
        index.append({
            "uid": L["uid"], "portal": L["portal"], "title": L["title"], "url": listing["url"],
            "status": L["status"], "price_czk": L["price"], "price_prev_czk": L["prev"],
            "location": L["loc"], "make": L["make"], "model": L["model"], "year": L["year"],
            "mileage_km": L["km"], "fuel": L["fuel"], "stk_detected": L["stk"], "tow_bar": L["tow"],
            "first_seen": listing["first_seen"], "last_seen": listing["last_seen"],
            "scores": {"dodavka_na_sut": L["score"]}, "tags": tags,
            "thumb": f"listings/{L['uid']}/images/01.svg", "search_text": (L["title"] + " " + L["desc"]).lower(),
        })

    out = {"generated_at": "2026-11-16T12:00:00Z", "profiles": PROFILES, "listings": index}
    (DATA / "index.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(index)} listings")


if __name__ == "__main__":
    main()
