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

    # ── POLITICAL — EU farm policy & subsidy environment ───────
    {
        "url":         "https://www.politico.eu/section/agriculture/feed/",
        "dimension":   "POLITICAL",
        "source_name": "Politico EU Agriculture",
        "scrape_mode": "rss",
    },
    {
        "url":         "https://www.politico.eu/feed/",
        "dimension":   "POLITICAL",
        "source_name": "Politico EU",
        "scrape_mode": "rss",
    },
    {
        "url":         "https://ec.europa.eu/commission/presscorner/api/documents?keyword=agriculture&institution=COMM&documenttype=IP&limit=10&sortby=date",
        "dimension":   "POLITICAL",
        "source_name": "EC Agriculture Press Releases",
        "scrape_mode": "page",
    },

    # ── ECONOMIC — commodity prices, farm income, AGCO financials
    {
        "url":         "https://feeds.feedburner.com/euractiv/agriculture",
        "dimension":   "ECONOMIC",
        "source_name": "Euractiv Agriculture",
        "scrape_mode": "rss",
    },
    {
        "url":         "https://www.agweb.com/rss/news",
        "dimension":   "ECONOMIC",
        "source_name": "AgWeb Farm News",
        "scrape_mode": "rss",
    },
    {
        "url":         "https://www.farminguk.com/rss/news.xml",
        "dimension":   "ECONOMIC",
        "source_name": "Farming UK — Farm Business",
        "scrape_mode": "rss",
    },
    {
        "url":         "https://www.agriexpo.online/news/",
        "dimension":   "ECONOMIC",
        "source_name": "AgriExpo Industry News",
        "scrape_mode": "page",
    },

    # ── TECHNOLOGICAL — precision ag, autonomy, connectivity ───
    {
        "url":         "https://www.agriland.co.uk/farming-news/category/machinery/",
        "dimension":   "TECHNOLOGICAL",
        "source_name": "Agriland Machinery",
        "scrape_mode": "page",
    },
    {
        "url":         "https://www.precisionag.com/feed/",
        "dimension":   "TECHNOLOGICAL",
        "source_name": "Precision Ag Magazine",
        "scrape_mode": "rss",
    },
    {
        "url":         "https://www.agritechfuture.com/feed/",
        "dimension":   "TECHNOLOGICAL",
        "source_name": "AgriTech Future",
        "scrape_mode": "rss",
    },
    {
        "url":         "https://cordis.europa.eu/search/en?q=precision+farming+autonomous&p=1&num=5&srt=Relevance:decreasing",
        "dimension":   "TECHNOLOGICAL",
        "source_name": "CORDIS Precision Farming R&D",
        "scrape_mode": "page",
    },
    {
        "url":         "https://www.dtnpf.com/agriculture/web/ag/crops/article/2024/01/01/precision-ag-technology-trends",
        "dimension":   "TECHNOLOGICAL",
        "source_name": "DTN Precision Ag Trends",
        "scrape_mode": "page",
    },

    # ── LEGAL — emissions standards, machinery regs, CAP ───────
    {
        "url":         "https://eur-lex.europa.eu/search.html?qid=1&text=agricultural+machinery+emissions&scope=EURLEX&type=quick&lang=en&displayProfile=allResults",
        "dimension":   "LEGAL",
        "source_name": "EUR-Lex Machinery Emissions",
        "scrape_mode": "page",
    },
    {
        "url":         "https://eur-lex.europa.eu/search.html?qid=1&text=CAP+strategic+plan+2026&scope=EURLEX&type=quick&lang=en",
        "dimension":   "LEGAL",
        "source_name": "EUR-Lex CAP 2026",
        "scrape_mode": "page",
    },
    {
        "url":         "https://www.euromachineryparts.com/news/",
        "dimension":   "LEGAL",
        "source_name": "Euro Machinery Parts & Regulation",
        "scrape_mode": "page",
    },

    # ── ENVIRONMENTAL — Green Deal, sustainability, soil health ─
    {
        "url":         "https://www.eea.europa.eu/en/topics/in-depth/agriculture",
        "dimension":   "ENVIRONMENTAL",
        "source_name": "EEA Agriculture & Environment",
        "scrape_mode": "page",
    },
    {
        "url":         "https://www.agriland.ie/farming-news/environment/",
        "dimension":   "ENVIRONMENTAL",
        "source_name": "Agriland Environment",
        "scrape_mode": "page",
    },

    # ── SOCIAL — farmer sentiment, protests, labour, adoption ──
    {
        "url":         "https://copa-cogeca.eu/press-releases",
        "dimension":   "SOCIAL",
        "source_name": "Copa-Cogeca Farmer Union",
        "scrape_mode": "page",
    },
    {
        "url":         "https://www.farmersweeekly.co.uk/feed",
        "dimension":   "SOCIAL",
        "source_name": "Farmers Weekly",
        "scrape_mode": "rss",
    },
    {
        "url":         "https://www.agriculture.com/rss-feeds",
        "dimension":   "SOCIAL",
        "source_name": "Agriculture.com Farmer Voice",
        "scrape_mode": "page",
    },
]

# Minimum character length for scraped text to be worth scoring
MIN_TEXT_LENGTH = 200

# Maximum characters to send to the HuggingFace model per article
MAX_TEXT_LENGTH = 8_000
