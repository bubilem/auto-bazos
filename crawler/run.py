"""Crawler entry point:  python -m crawler.run [--max-pages N] [--limit N] [--slug S] [--dry-run]

Flow: category list pages -> local model/price filter -> detail + photos for NEW matches ->
rules scoring -> collage -> data/index.json.  Incremental: ids already seen are not re-fetched,
paging stops at the first page with nothing new.  user_state.json is never touched.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler import collage, rules, taxonomy  # noqa: E402
from crawler import profiles as profiles_mod  # noqa: E402
from crawler.fetcher import Fetcher, RobotsDisallowed  # noqa: E402
from crawler.portals import PORTALS  # noqa: E402

MAX_SEEN_IDS = 30000


def log(msg):
    print(msg, flush=True)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


# ----------------------------------------------------------------------------- store


class Store:
    """data/listings/<uid>/listing.json files, loaded into memory."""

    def __init__(self, data_dir):
        self.dir = Path(data_dir)
        self.listings = {}
        for f in sorted((self.dir / "listings").glob("*/listing.json")):
            d = read_json(f, None)
            if d and d.get("uid"):
                self.listings[d["uid"]] = d

    def folder(self, uid):
        return self.dir / "listings" / uid

    def save(self, listing):
        write_json(self.folder(listing["uid"]) / "listing.json", listing)
        self.listings[listing["uid"]] = listing


def record_price(listing, price, today):
    """Append to price_history when the price changed. Returns True if changed."""
    if price is None:
        return False
    hist = listing.setdefault("price_history", [])
    if hist and hist[-1]["price_czk"] == price:
        return False
    hist.append({"date": today, "price_czk": price})
    listing["price_czk"] = price
    return True


# ----------------------------------------------------------------------------- rules


def apply_rules(listing, profiles, today):
    """(Re)compute vehicle facts + per-profile scoring from the stored text. Deterministic."""
    d = today
    facts = rules.analyze(listing["title"], listing["description"], d)
    st = listing.get("structured") or {}  # portal-provided facts beat guesses from free text
    if st.get("year"):
        facts["year"] = {"value": st["year"], "confidence": "high"}
    if st.get("mileage_km"):
        facts["mileage_km"] = {"value": st["mileage_km"], "confidence": "high"}
    if st.get("fuel"):
        facts["fuel"] = st["fuel"]
    if st.get("stk_valid_until"):
        y, m = map(int, st["stk_valid_until"].split("-"))
        expired = (y, m) < (d.year, d.month)
        facts["stk"] = {"status": "expired" if expired else "valid", "valid_until": st["stk_valid_until"],
                        "label": f"STK {'vypršela' if expired else 'do'} {m:02d}/{y}"}
    v = listing.setdefault("vehicle", {})
    v["year"], v["year_confidence"] = facts["year"]["value"], facts["year"]["confidence"]
    v["mileage_km"], v["mileage_confidence"] = facts["mileage_km"]["value"], facts["mileage_km"]["confidence"]
    v["fuel"] = facts["fuel"]
    v["stk_status"] = facts["stk"]["status"]
    v["stk_detected"] = facts["stk"]["valid_until"]
    v["tow_bar_detected"] = facts["tow_bar"]
    v["equipment"] = facts["equipment"]
    v["vin"] = st.get("vin") or v.get("vin")
    scoring = {}
    for p in profiles:
        r = rules.score_listing(
            {"title": listing["title"], "description": listing["description"], "price_czk": listing.get("price_czk"),
             "image_count": len(listing.get("images", [])), "location": listing.get("location"),
             "known_stk": facts["stk"] if st.get("stk_valid_until") else None}, p, d)
        scoring[p["id"]] = {k: r[k] for k in ("base_score", "breakdown", "positive_hits", "warning_hits", "excluded", "exclude_hits")}
    listing["rule_scoring"] = scoring


def index_entry(l, profiles):
    v = l.get("vehicle", {})
    hist = l.get("price_history", [])
    prev = hist[-2]["price_czk"] if len(hist) > 1 and hist[-1]["price_czk"] < hist[-2]["price_czk"] else None
    tags = []
    if v.get("stk_status") in ("valid", "fresh"):
        tags.append("STK")
    if v.get("tow_bar_detected"):
        tags.append("Tažné")
    if prev:
        tags.append("Sleva")
    if l.get("status") != "active":
        tags.append("Neaktivní")
    images = l.get("images", [])
    return {
        "uid": l["uid"], "portal": l["portal"], "title": l["title"], "url": l["url"], "status": l["status"],
        "price_czk": l.get("price_czk"), "price_prev_czk": prev, "location": l.get("location"),
        "make": v.get("make"), "model": v.get("model"), "year": v.get("year"), "mileage_km": v.get("mileage_km"),
        "fuel": v.get("fuel"), "stk_detected": v.get("stk_detected") or (v.get("stk_status") in ("valid", "fresh") or None),
        "tow_bar": v.get("tow_bar_detected"), "first_seen": l["first_seen"], "last_seen": l["last_seen"],
        "scores": {pid: s["base_score"] for pid, s in l.get("rule_scoring", {}).items()},
        "excluded": {pid: s["excluded"] for pid, s in l.get("rule_scoring", {}).items() if s["excluded"]},
        "tags": tags,
        "thumb": f"listings/{l['uid']}/{images[0]}" if images else None,
        "search_text": f"{l['title']} {l['description']}".lower(),
    }


def rebuild_index(store, profiles, today, data_dir):
    entries = []
    for uid, l in store.listings.items():
        before = json.dumps(l, sort_keys=True, ensure_ascii=False)
        apply_rules(l, profiles, today)
        if json.dumps(l, sort_keys=True, ensure_ascii=False) != before:
            store.save(l)
        entries.append(index_entry(l, profiles))
    entries.sort(key=lambda e: e["first_seen"], reverse=True)
    out = {
        "generated_at": now_iso(),
        "profiles": [{"id": p["id"], "name": p["name"], "purpose": p["purpose"], "reference_model": p.get("reference_model"),
                      "equivalence_group": p.get("equivalence_group"), "price_target_czk": p["params"].get("price_target_czk")}
                     for p in profiles],
        "listings": entries,
    }
    write_json(Path(data_dir) / "index.json", out)
    return len(entries)


# ----------------------------------------------------------------------------- crawl


def download_images(fetcher, urls, folder, max_images):
    img_dir = Path(folder) / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    expected, saved = [], []
    for i, url in enumerate(urls[:max_images], start=1):
        name = f"{i:02d}.jpg"
        expected.append(img_dir / name)
        try:
            r = fetcher.get(url, delay_key="image_delay_seconds")
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") and len(r.content) < 8_000_000:
                (img_dir / name).write_bytes(r.content)
                saved.append(f"images/{name}")
        except (RobotsDisallowed, Exception) as e:  # keep going: one bad photo must not lose the ad
            log(f"    photo {i} failed: {e}")
    return expected, saved


def ingest(portal_name, store, fetcher, cfg, profiles, it, detail, make, model, group_name, manual=False):
    """Download photos, build and store one new listing from a list item `it` and its parsed `detail`."""
    uid = f"{portal_name}_{it['external_id']}"
    today = datetime.now(timezone.utc).date().isoformat()
    folder = store.folder(uid)
    expected, saved = download_images(fetcher, detail["images"], folder, cfg["scraping"]["max_images_per_listing"])
    collages = collage.make_collages(expected, folder, per_collage=cfg["scraping"]["collage_images"]) if saved else []
    now = now_iso()
    price = detail["price_czk"] if detail["price_czk"] is not None else it["price_czk"]
    listing = {
        "uid": uid, "portal": portal_name, "external_id": it["external_id"], "url": it["url"], "status": "active",
        "first_seen": now, "last_seen": now, "listed_on": detail["listed_on"] or it.get("listed_on"),
        "price_czk": price, "price_history": [{"date": today, "price_czk": price}] if price is not None else [],
        "vehicle": {"make": make, "model": model, "equivalence_group": group_name},
        "location": detail["location"] or it.get("location"), "zip": detail["zip"] or it.get("zip"),
        "title": detail["title"], "description": detail["description"],
        "images": saved, "collages": collages, "rule_scoring": {},
    }
    if manual:
        listing["manual"] = True  # added by URL, not found by the category crawl
    if detail.get("structured"):
        listing["structured"] = detail["structured"]
    apply_rules(listing, profiles, datetime.now(timezone.utc).date())
    store.save(listing)
    return listing


def add_url(url, cfg, groups, profiles, store, fetcher, state, args):
    """Add one hand-picked ad by URL. No model/price filter: the user chose it. Returns True on failure."""
    for pname, cls in PORTALS.items():
        pcfg = cfg["portals"].get(pname)
        parsed = pcfg and cls.parse_url(url, pcfg)
        if not parsed:
            continue
        if not pcfg.get("enabled"):
            log(f"{pname}: disabled in config.json (portals.{pname}.enabled)")
            return True
        eid, url = parsed
        uid = f"{pname}_{eid}"
        portal = cls(pcfg, fetcher, groups, args)
        log(f"{pname}: {url}")
        try:
            detail = portal.fetch_detail(url)
        except Exception as e:
            log(f"  ERROR {type(e).__name__}: {e}")
            return True
        if detail is None:
            log("  This page is not a live ad (deleted, or unexpected markup).")
            return True
        today = datetime.now(timezone.utc).date().isoformat()
        if uid in store.listings:
            l = store.listings[uid]
            l["last_seen"], l["status"] = now_iso(), "active"
            record_price(l, detail["price_czk"], today)
            store.save(l)
            log(f"  Already stored as {uid}; refreshed.")
        else:
            hit = next(((gn, mm) for gn, g in groups if (mm := taxonomy.match_model(detail["title"], g))), None)
            make, model = hit[1] if hit else ("Neurčeno", "")
            item = {"external_id": eid, "url": url, "price_czk": None}
            ingest(pname, store, fetcher, cfg, profiles, item, detail, make, model, hit[0] if hit else None, manual=True)
            log(f"  Added {uid}: {detail['title'][:60]}")
        key = f"{pname}_seen"
        state[key] = sorted(set(state.get(key, [])) | {eid}, key=int)[-MAX_SEEN_IDS:]
        return False
    log(f"URL does not belong to any enabled portal ad page: {url}")
    return True


def crawl_portal(portal, cfg, groups, profiles, store, fetcher, state, args):
    """Generic crawl for one portal adapter. Returns True if a layout problem was detected."""
    name = portal.name
    price_cap = max((p["params"].get("price_max_czk") or 0) for p in profiles) or None
    today = datetime.now(timezone.utc).date().isoformat()
    seen_key = f"{name}_seen"

    seen_old = set(state.get(seen_key, []))
    decided, seen_run, candidates = set(), set(), {}
    layout_problem = False

    for src in portal.sources():
        pages_done, errored = 0, False
        pages = portal.iter_source(src)
        while True:
            try:
                page, items = next(pages)
            except StopIteration:
                break
            except Exception as e:  # network trouble in one category must not lose the whole run
                layout_problem = errored = True
                log(f"  ERROR {src['label']}: {type(e).__name__}: {e} - continuing with the next source")
                break
            pages_done += 1
            new = 0
            for it in items:
                uid, eid = f"{name}_{it['external_id']}", it["external_id"]
                seen_run.add(uid)
                if eid not in seen_old:
                    new += 1
                if uid in store.listings:
                    l = store.listings[uid]
                    l["last_seen"], l["status"] = now_iso(), "active"
                    record_price(l, it["price_czk"], today)
                    store.save(l)
                    decided.add(eid)
                    continue
                if uid in candidates:
                    continue
                # Model: from the portal source when it is model-specific, else title only -
                # snippets mention other models ("kola pasují na ProAce") and cause false hits.
                hit = (src["hint"][0], src["hint"][1:]) if src["hint"] else next(
                    ((gn, mm) for gn, g in groups if (mm := taxonomy.match_model(it["title"], g))), None)
                if not hit or (it["price_czk"] is not None and price_cap and it["price_czk"] > price_cap):
                    decided.add(eid)
                    continue
                candidates[uid] = (it, hit[1], hit[0])
            log(f"  {src['label']} p{page + 1}: {len(items)} ads, {new} new, {len(candidates)} candidates so far")
            if new == 0 and portal.early_stop:
                break
        if pages_done == 0 and not errored:
            if portal.blocked():
                layout_problem = True
                log(f"  BLOCKED: {name} refused access (HTTP 401/403/429, likely bot protection). "
                    f"Not working around it; skipping the rest of {name} for this run.")
                break
            if portal.source_missing(src):
                log(f"  {src['label']}: no such page on {name} (skipped)")
            else:
                layout_problem = True
                log(f"  WARNING {src['label']}: no ads parsed on first page - layout changed or blocked?")

    log(f"Candidates to fetch: {len(candidates)}")
    if args.dry_run:
        for uid, (it, m, _) in candidates.items():
            log(f"  {uid}  {m[0]} {m[1]}  {it['price_czk']}  {it['title'][:60]}")
        return layout_problem

    fetched = 0
    for uid, (it, (make, model), group_name) in candidates.items():
        if args.limit is not None and fetched >= args.limit:
            log(f"Limit {args.limit} reached; remaining candidates will be picked up next run.")
            break
        fetched += 1
        log(f"  detail {uid}: {it['title'][:60]}")
        try:
            detail = portal.fetch_detail(it["url"])
        except Exception as e:
            log(f"    skipped ({type(e).__name__}: {e})")
            continue
        if detail is None:
            log("    page has no ad markup - skipped")
            decided.add(it["external_id"])
            continue
        ingest(name, store, fetcher, cfg, profiles, it, detail, make, model, group_name)
        decided.add(it["external_id"])

    # Verify ads we did not see this run (they may be deeper than our paging depth, or deleted).
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = sorted((l for l in store.listings.values() if l["portal"] == name and l["status"] == "active"
                    and l["uid"] not in seen_run and l["last_seen"] < cutoff), key=lambda l: l["last_seen"])[: args.stale_limit]
    for l in stale:
        try:
            detail = portal.fetch_detail(l["url"])
        except Exception as e:
            log(f"  stale check {l['uid']} failed ({e}); left unchanged")
            continue
        if detail is None:
            l["status"] = "inactive"
            log(f"  {l['uid']} is gone -> inactive (data and photos kept)")
        else:
            l["last_seen"] = now_iso()
            record_price(l, detail["price_czk"], today)
        store.save(l)

    state[seen_key] = sorted(seen_old | decided, key=int)[-MAX_SEEN_IDS:]
    return layout_problem


# ----------------------------------------------------------------------------- main


def main(argv=None):
    ap = argparse.ArgumentParser(description="Add-Check crawler")
    ap.add_argument("--max-pages", type=int, help="override max pages per category")
    ap.add_argument("--limit", type=int, help="max NEW ads to fetch in detail this run")
    ap.add_argument("--portal", choices=["bazos"], help="crawl only this portal")
    ap.add_argument("--slug", help="crawl only this category / model slug")
    ap.add_argument("--stale-limit", type=int, default=10, help="max unseen ads to re-verify per run")
    ap.add_argument("--dry-run", action="store_true", help="list candidates, fetch no details/photos, write nothing")
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--reset-state", action="store_true", help="forget seen ad ids")
    ap.add_argument("--rebuild", action="store_true", help="only re-score stored ads and rewrite index.json (after editing profiles)")
    ap.add_argument("--add-url", metavar="URL", help="add one ad by its URL (no category crawl, no model/price filter)")
    args = ap.parse_args(argv)
    if args.add_url and args.dry_run:
        ap.error("--add-url cannot be combined with --dry-run")
    if args.rebuild and (args.add_url or args.dry_run):
        ap.error("--rebuild cannot be combined with --add-url or --dry-run")
    sys.stdout.reconfigure(encoding="utf-8")

    cfg = read_json(ROOT / "config.json", None)
    tax = taxonomy.load()
    profiles = profiles_mod.load()
    data_dir = Path(args.data_dir)
    store = Store(data_dir)
    state_path = data_dir / "crawl_state.json"
    state = {} if args.reset_state else read_json(state_path, {})
    fetcher = Fetcher(cfg["scraping"])

    groups = [(g, tax["groups"][g]) for g in sorted({p["equivalence_group"] for p in profiles if p.get("equivalence_group")})]
    wanted = [args.portal] if args.portal else list(PORTALS)
    problem = False
    try:
        if args.rebuild:
            wanted = []
        elif args.add_url:
            wanted = []
            problem = add_url(args.add_url.strip(), cfg, groups, profiles, store, fetcher, state, args)
        for pname in wanted:
            pcfg = cfg["portals"].get(pname)
            if not pcfg or not pcfg.get("enabled"):
                if args.portal:
                    log(f"{pname}: disabled in config.json (portals.{pname}.enabled)")
                continue
            log(f"{pname}:")
            portal = PORTALS[pname](pcfg, fetcher, groups, args)
            problem |= crawl_portal(portal, cfg, groups, profiles, store, fetcher, state, args)
    except KeyboardInterrupt:
        log("Interrupted - saving what we have.")
    finally:
        if not args.dry_run:
            write_json(state_path, state)
            n = rebuild_index(store, profiles, datetime.now(timezone.utc).date(), data_dir)
            log(f"index.json: {n} listings. HTTP requests this run: {fetcher.requests_made}")
    return 2 if problem else 0


if __name__ == "__main__":
    sys.exit(main())
