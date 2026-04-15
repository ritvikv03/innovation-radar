"""
core/sources.py — PESTEL-EL Intelligence Source Registry
=========================================================
Defines the canonical list of sources the Scout scrapes.
Each entry maps to one PESTEL dimension so the router can
tag signals before HuggingFace scoring.

Adding a new source:
    Append a dict to PESTEL_SOURCES with all required keys.
    The scheduler will pick it up on the next run automatically.
"""

from __future__ import annotations

# Each entry:
#   url          — direct article / RSS / API endpoint
#   dimension    — one of the 6 PESTEL values
#   source_name  — short human-readable label
#   scrape_mode  — "rss"         → parse XML feed (multiple articles)
#                  "page"        → scrape single page (Firecrawl / requests)
#                  "api_ec_press"→ EC Press Releases JSON REST endpoint

PESTEL_SOURCES: list[dict] = [
    # ── POLITICAL ──────────────────────────────────────────────
    {
        "url":         "https://www.politico.eu/section/agriculture/feed/",
        "dimension":   "POLITICAL",
        "source_name": "Politico EU Agriculture",
        "scrape_mode": "rss",
    },
    {
        "url":         "https://www.politico.eu/feed/",
        "dimension":   "POLITICAL",
        "source_name": "Politico EU News",
        "scrape_mode": "rss",
    },

    # ── ECONOMIC ───────────────────────────────────────────────
    {
        "url":         "https://ec.europa.eu/eurostat/databrowser/view/APRI_AP_INA/default/table",
        "dimension":   "ECONOMIC",
        "source_name": "Eurostat Agricultural Price Indices",
        "scrape_mode": "page",
    },
    {
        "url":         "https://feeds.feedburner.com/euractiv/agriculture",
        "dimension":   "ECONOMIC",
        "source_name": "Euractiv Agriculture RSS",
        "scrape_mode": "rss",
    },

    # ── LEGAL ──────────────────────────────────────────────────
    {
        "url":         "https://eur-lex.europa.eu/search.html?qid=1&text=agricultural+machinery&scope=EURLEX&type=quick&lang=en&displayProfile=allResults",
        "dimension":   "LEGAL",
        "source_name": "EUR-Lex Agricultural Machinery",
        "scrape_mode": "page",
    },
    {
        "url":         "https://eur-lex.europa.eu/search.html?qid=1&text=CAP+reform+2026&scope=EURLEX&type=quick&lang=en",
        "dimension":   "LEGAL",
        "source_name": "EUR-Lex CAP Reform 2026",
        "scrape_mode": "page",
    },

    # ── TECHNOLOGICAL ──────────────────────────────────────────
    {
        "url":         "https://cordis.europa.eu/search/en?q=agricultural+robotics&p=1&num=5&srt=Relevance:decreasing",
        "dimension":   "TECHNOLOGICAL",
        "source_name": "CORDIS AgriRobotics Projects",
        "scrape_mode": "page",
    },
    {
        "url":         "https://www.agriland.co.uk/farming-news/category/machinery/",
        "dimension":   "TECHNOLOGICAL",
        "source_name": "Agriland Machinery News",
        "scrape_mode": "page",
    },

    # ── ENVIRONMENTAL ──────────────────────────────────────────
    {
        "url":         "https://www.eea.europa.eu/en/topics/in-depth/agriculture",
        "dimension":   "ENVIRONMENTAL",
        "source_name": "EEA Agriculture & Environment",
        "scrape_mode": "page",
    },

    # ── SOCIAL ─────────────────────────────────────────────────
    {
        "url":         "https://copa-cogeca.eu/press-releases",
        "dimension":   "SOCIAL",
        "source_name": "Copa-Cogeca Farmer Union Press",
        "scrape_mode": "page",
    },
]

# Minimum character length for scraped text to be worth scoring
MIN_TEXT_LENGTH = 200

# Maximum characters to send to the HuggingFace model per article
MAX_TEXT_LENGTH = 8_000
