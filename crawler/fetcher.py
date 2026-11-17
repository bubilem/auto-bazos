"""Polite HTTP client: robots.txt enforcement, randomised delay between requests, small retry."""
import random
import time

import httpx

from .robots import RobotsCache


class RobotsDisallowed(Exception):
    pass


class Fetcher:
    def __init__(self, scraping_cfg, client=None, sleep=time.sleep, rand=random.uniform, clock=time.monotonic):
        self.cfg = scraping_cfg
        self.ua = scraping_cfg["user_agent"]
        self.client = client or httpx.Client(
            headers={"User-Agent": self.ua, "Accept-Language": "cs,en;q=0.5"},
            timeout=scraping_cfg.get("request_timeout_seconds", 20),
            follow_redirects=True,
        )
        self._sleep, self._rand, self._clock = sleep, rand, clock
        self._last = None
        self.requests_made = 0
        self.robots = RobotsCache(self._fetch_robots, self.ua)

    def _fetch_robots(self, url):
        try:
            r = self.client.get(url)
            return r.text if r.status_code == 200 else None
        except httpx.HTTPError:
            return None

    def _wait(self, delay_range):
        lo, hi = delay_range
        if self._last is not None:
            wait = self._rand(lo, hi) - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def get(self, url, delay_key="delay_seconds"):
        """GET with robots check + delay. Returns httpx.Response (any status except transport errors)."""
        if not self.robots.allowed(url):
            raise RobotsDisallowed(url)
        delay = self.cfg.get(delay_key) or self.cfg["delay_seconds"]
        last_exc = None
        for attempt in range(3):
            self._wait(delay)
            self.requests_made += 1
            try:
                r = self.client.get(url)
            except httpx.TransportError as e:
                last_exc = e
                self._sleep(5 * (attempt + 1))
                continue
            if r.status_code in (429, 503):
                self._sleep(30 * (attempt + 1))
                last_exc = httpx.HTTPStatusError(f"{r.status_code} for {url}", request=r.request, response=r)
                continue
            return r
        raise last_exc
