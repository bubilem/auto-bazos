"""Portal adapters: one uniform interface for run.py, portal specifics stay in crawler/scrapers/.

Interface:
    name, early_stop
    sources()              -> [{"label", "slug", "max_pages", "hint"}]   what to walk (hint = (group, make, model) or None)
    iter_source(src)       -> yields (page_index, [item dicts]) ; item keys: external_id, url, title, price_czk, hint, ...
    source_missing(src)    -> True if the source simply does not exist on the portal (404), not a layout problem
    blocked()              -> True if the portal answered 401/403/429 (bot protection) on the last request
    fetch_detail(url)      -> normalized detail dict, or None if the ad is gone
"""
import re
from urllib.parse import urlsplit, urlunsplit

from .scrapers import bazos

# Bot protection / access refusal. We never work around it (no fingerprint spoofing, no challenge solving):
# the crawler reports it, stops talking to that portal for this run and exits with an error code.
BLOCK_STATUSES = (401, 403, 429)


class BazosPortal:
    name = "bazos"
    early_stop = True  # lists are newest-first, so a page with nothing new means the rest is old

    def __init__(self, cfg, fetcher, groups, args):
        self.cfg, self.args = cfg, args
        self.scraper = bazos.BazosScraper(cfg, fetcher)

    @staticmethod
    def parse_url(url, cfg):
        """Ad-page URL on this portal -> (external_id, canonical_url), else None. Only the configured host is accepted."""
        base = urlsplit(cfg["base_url"])
        u = urlsplit(url)
        m = re.fullmatch(r"/inzerat/(\d+)/[^/]*", u.path)
        if u.scheme not in ("http", "https") or (u.hostname or "").lower() != base.hostname or not m:
            return None
        return m.group(1), urlunsplit((base.scheme, base.netloc, u.path, "", ""))

    def sources(self):
        return [{"label": c["slug"], "slug": c["slug"], "max_pages": self.args.max_pages or c["max_pages"], "hint": None}
                for c in self.cfg["categories"] if not self.args.slug or c["slug"] == self.args.slug]

    def iter_source(self, src):
        for page, parsed in self.scraper.iter_category(src["slug"], src["max_pages"]):
            yield page, [dict(it, hint=None) for it in parsed["items"]]

    def source_missing(self, src):
        return False

    def blocked(self):
        return self.scraper.last_status in BLOCK_STATUSES

    def fetch_detail(self, url):
        d = self.scraper.fetch_detail(url)
        return None if d is None else dict(d, structured=None)


PORTALS = {"bazos": BazosPortal}
