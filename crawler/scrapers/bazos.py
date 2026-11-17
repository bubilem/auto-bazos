"""Bazoš.cz adapter (auto.bazos.cz).

robots.txt forbids parameterised search URLs (hledat=, cenaod=, humkreis=, ...), so we only
walk plain category pages (/dodavka/, /citroen/, /citroen/40/ ...) and filter locally.
Seller name and phone number are deliberately NOT parsed or stored.
"""
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

PAGE_SIZE = 40
_DATE = re.compile(r"\[(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\]")
_ID = re.compile(r"/inzerat/(\d+)/")


def _price(text):
    """'  424 990 Kč' -> 424990; 'Dohodou' / 'Vyplaceno' / '' -> None."""
    if not text or "kč" not in text.lower():
        return None
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


def _iso_date(text):
    m = _DATE.search(text or "")
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_list_page(html, base_url="https://auto.bazos.cz"):
    """-> {"items": [...], "total": int | None}. Items without an ad id are skipped."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for box in soup.select("div.inzeraty"):
        link = box.select_one("h2.nadpis a")
        m = _ID.search(link["href"]) if link and link.get("href") else None
        if not m:
            continue
        loc_lines = [s.strip() for s in box.select_one(".inzeratylok").get_text("\n").split("\n") if s.strip()] \
            if box.select_one(".inzeratylok") else []
        views = box.select_one(".inzeratyview")
        views_n = re.sub(r"\D", "", views.get_text()) if views else ""
        img = box.select_one("img.obrazek")
        popis = box.select_one(".popis")
        meta = box.select_one(".velikost10")
        items.append({
            "external_id": m.group(1),
            "url": urljoin(base_url, link["href"]),
            "title": link.get_text(" ", strip=True),
            "snippet": popis.get_text(" ", strip=True) if popis else "",
            "price_czk": _price(box.select_one(".inzeratycena").get_text(" ", strip=True)) if box.select_one(".inzeratycena") else None,
            "location": loc_lines[0] if loc_lines else None,
            "zip": loc_lines[1] if len(loc_lines) > 1 else None,
            "listed_on": _iso_date(meta.get_text(" ") if meta else ""),
            "views": int(views_n) if views_n else None,
            "thumb": img["src"] if img and img.get("src") else None,
            "top": bool(box.select_one(".ztop")),
        })
    total = None
    m = re.search(r"Zobrazeno\s+\d+\s*-\s*\d+\s+inzerátů\s+z\s+([\d\s ]+)", soup.get_text(" "))
    if m:
        total = int(re.sub(r"\D", "", m.group(1)) or 0) or None
    return {"items": items, "total": total}


def parse_detail(html, base_url="https://auto.bazos.cz"):
    """-> dict, or None if the page is not a live ad (deleted / unexpected markup)."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("h1.nadpisdetail")
    desc = soup.select_one(".popisdetail")
    if not h1 or not desc:
        return None

    images = []
    for img in soup.select(".carousel img"):
        src = img.get("data-flickity-lazyload") or img.get("src")
        if src and src not in images:
            images.append(urljoin(base_url, src))

    location = zip_code = price_text = views = None
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        label = tds[0].get_text(" ", strip=True).rstrip(":").strip() if tds else ""
        if label == "Lokalita":
            anchors = [a.get_text(strip=True) for a in tr.find_all("a")]
            zip_code = next((a for a in anchors if re.fullmatch(r"\d{3}\s?\d{2}", a)), None)
            location = next((a for a in anchors if a and a != zip_code), None)
        elif label == "Cena":
            price_text = tds[-1].get_text(" ", strip=True)
        elif label == "Vidělo":
            digits = re.sub(r"\D", "", tds[-1].get_text())
            views = int(digits) if digits else None

    meta = soup.select_one(".inzeratydetnadpis .velikost10")
    return {
        "title": h1.get_text(" ", strip=True),
        "description": desc.get_text("\n", strip=True),
        "price_czk": _price(price_text),
        "price_text": price_text,
        "location": location,
        "zip": zip_code,
        "views": views,
        "listed_on": _iso_date(meta.get_text(" ") if meta else ""),
        "images": images,
    }


class BazosScraper:
    def __init__(self, portal_cfg, fetcher):
        self.base = portal_cfg["base_url"].rstrip("/")
        self.fetcher = fetcher
        self.last_status = None

    def category_url(self, slug, page):
        return f"{self.base}/{slug}/" if page == 0 else f"{self.base}/{slug}/{page * PAGE_SIZE}/"

    def iter_category(self, slug, max_pages):
        """Yield (page_index, parsed_list_page) newest-first; stops at an empty page."""
        for page in range(max_pages):
            r = self.fetcher.get(self.category_url(slug, page))
            self.last_status = r.status_code
            if r.status_code != 200:
                break
            parsed = parse_list_page(r.text, self.base)
            if not parsed["items"]:
                break
            yield page, parsed

    def fetch_detail(self, url):
        """-> parsed detail, None if the ad is gone, raises on transport trouble."""
        r = self.fetcher.get(url)
        if r.status_code == 410:
            return None
        return parse_detail(r.text, self.base)
