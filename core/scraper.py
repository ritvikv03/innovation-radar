"""
core/scraper.py — Resilient Web Scraper with Retry/Backoff
===========================================================
Provides text extraction from:
  - RSS/Atom XML feeds  (parse multiple <item> entries)
  - HTML pages          (Firecrawl API, strips to text)
  - EC Press API        (custom JSON handler)

All external calls use exponential backoff with jitter.
Failed fetches are logged at WARNING and skipped — they never
crash the scheduler.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import TypedDict

import requests

from core.logger import get_logger
from core.sources import MAX_TEXT_LENGTH, MIN_TEXT_LENGTH
from core.utils import retry_with_backoff

log = get_logger(__name__)

_FIRECRAWL_KEY = os.getenv("FIRECRAWL_API_KEY", "")
_FC_ENDPOINT   = "https://api.firecrawl.dev/v1/scrape"
_REQUEST_TIMEOUT = 20   # seconds


# ── Data contract ─────────────────────────────────────────────

class ScrapedArticle(TypedDict):
    """Typed return value from all scraper functions."""
    url:  str
    text: str


# ── RSS parser ────────────────────────────────────────────────

_RSS_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc":   "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

def _scrape_rss(url: str) -> list[ScrapedArticle]:
    """
    Parse an RSS/Atom feed and return a list of {url, text} dicts.
    Skips items with text below MIN_TEXT_LENGTH.
    """
    log.debug("Fetching RSS: %s", url)

    def _fetch():
        r = requests.get(url, timeout=_REQUEST_TIMEOUT,
                         headers={"User-Agent": "FendtAgent/2.0"})
        r.raise_for_status()
        return r.text

    xml_text = retry_with_backoff(_fetch)
    root = ET.fromstring(xml_text)

    items = []
    # Support both RSS <item> and Atom <entry>
    for tag in ("item", "{http://www.w3.org/2005/Atom}entry"):
        for item in root.iter(tag):
            title_el   = item.find("title")
            if title_el is None:
                title_el = item.find("{http://www.w3.org/2005/Atom}title")
            desc_el    = item.find("description")
            if desc_el is None:
                desc_el = item.find("{http://www.w3.org/2005/Atom}summary")
            link_el    = item.find("link")
            if link_el is None:
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
            content_el = item.find("content:encoded", _RSS_NAMESPACES)

            title   = (title_el.text   or "").strip()  if title_el   is not None else ""
            desc    = (desc_el.text    or "").strip()  if desc_el    is not None else ""
            content = (content_el.text or "").strip()  if content_el is not None else ""
            link    = (link_el.text    or link_el.get("href", "")) if link_el is not None else url

            # Strip HTML tags from content
            import re
            for s in (content, desc):
                clean = re.sub(r"<[^>]+>", " ", s)
                clean = re.sub(r"\s{2,}", " ", clean).strip()
                if len(clean) >= MIN_TEXT_LENGTH:
                    text = f"{title}\n\n{clean}"
                    items.append({"url": link, "text": text[:MAX_TEXT_LENGTH]})
                    break

    log.info("RSS '%s' → %d usable articles", url, len(items))
    return items


# ── Firecrawl page scraper ─────────────────────────────────────

def _scrape_page_firecrawl(url: str) -> list[ScrapedArticle]:
    """
    Use the Firecrawl API to extract clean Markdown from a URL.
    Returns a single-item list.
    """
    if not _FIRECRAWL_KEY:
        log.warning("FIRECRAWL_API_KEY not set — falling back to requests for %s", url)
        return _scrape_page_requests(url)

    log.debug("Firecrawl scraping: %s", url)

    def _call():
        r = requests.post(
            _FC_ENDPOINT,
            json={"url": url, "formats": ["markdown"]},
            headers={"Authorization": f"Bearer {_FIRECRAWL_KEY}"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    try:
        data = retry_with_backoff(_call)
    except Exception as exc:
        log.error("Firecrawl failed for %s: %s", url, exc)
        return _scrape_page_requests(url)

    md = data.get("data", {}).get("markdown", "")
    if len(md) < MIN_TEXT_LENGTH:
        log.warning("Firecrawl returned too little text for %s (%d chars)", url, len(md))
        return []

    log.info("Firecrawl '%s' → %d chars extracted", url, len(md))
    return [{"url": url, "text": md[:MAX_TEXT_LENGTH]}]


def _scrape_page_requests(url: str) -> list[ScrapedArticle]:
    """Fallback: plain requests + regex stripping."""
    import re
    log.debug("requests fallback for: %s", url)

    def _fetch():
        r = requests.get(url, timeout=_REQUEST_TIMEOUT,
                         headers={"User-Agent": "FendtAgent/2.0"})
        r.raise_for_status()
        return r.text

    try:
        html = retry_with_backoff(_fetch)
    except Exception as exc:
        log.error("requests fallback failed for %s: %s", url, exc)
        return []

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    if len(text) < MIN_TEXT_LENGTH:
        log.warning("requests fallback returned too little text for %s", url)
        return []

    return [{"url": url, "text": text[:MAX_TEXT_LENGTH]}]


# ── EC Press API ───────────────────────────────────────────────

def _scrape_ec_press(url: str) -> list[ScrapedArticle]:
    """Parse the EC Commission press release JSON API."""
    log.debug("EC Press API: %s", url)

    def _fetch():
        r = requests.get(url, timeout=_REQUEST_TIMEOUT,
                         headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json()

    try:
        data = retry_with_backoff(_fetch)
    except Exception as exc:
        log.error("EC Press API failed: %s — %s", url, exc)
        return []

    items = []
    for doc in data.get("results", [])[:5]:
        title   = doc.get("title",   "")
        summary = doc.get("summary", "") or doc.get("body", "")
        link    = doc.get("url",     url)
        text    = f"{title}\n\n{summary}".strip()
        if len(text) >= MIN_TEXT_LENGTH:
            items.append({"url": link, "text": text[:MAX_TEXT_LENGTH]})

    log.info("EC Press API → %d articles", len(items))
    return items


# ── Public dispatcher ─────────────────────────────────────────

def scrape_source(source: dict) -> list[ScrapedArticle]:
    """
    Dispatch to the correct scraper based on source['scrape_mode'].

    Parameters
    ----------
    source : dict from core.sources.PESTEL_SOURCES

    Returns
    -------
    List of {"url": str, "text": str} dicts, or [] on any failure.
    """
    mode = source.get("scrape_mode", "page")
    url  = source["url"]
    name = source.get("source_name", url)

    log.info("Scraping [%s] mode=%s  source=%s", source["dimension"], mode, name)

    try:
        if mode == "rss":
            return _scrape_rss(url)
        elif mode == "page":
            return _scrape_page_firecrawl(url)
        elif mode == "api_ec_press":
            return _scrape_ec_press(url)
        else:
            log.warning("Unknown scrape_mode '%s' for %s — skipping", mode, url)
            return []
    except Exception as exc:
        log.error("Unhandled error scraping %s: %s", name, exc, exc_info=True)
        return []
