"""
core/logger.py — Centralised logging for the Fendt PESTEL-EL Agent
===================================================================
Usage:
    from core.logger import get_logger
    log = get_logger(__name__)
    log.info("Pipeline started")
    log.warning("Gemini quota low")
    log.error("ChromaDB unreachable: %s", exc)

All log records go to:
  - logs/agent.log  (rotating, 5 MB × 3 backups, always)
  - stderr console  (INFO+ in dev, WARNING+ in prod)

Set LOG_LEVEL env var to override console level (DEBUG / INFO / WARNING / ERROR).
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ── Config ────────────────────────────────────────────────────

_LOG_DIR  = Path(__file__).parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "agent.log"
_LOG_DIR.mkdir(exist_ok=True)

_FMT = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

# Respect LOG_LEVEL env var; default INFO
_CONSOLE_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

# ── Root handler setup (called once) ─────────────────────────

def _configure_root() -> None:
    root = logging.getLogger()
    # Check specifically for our file handler to avoid double-adding,
    # but don't bail just because pytest/another framework added its own handlers.
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return

    root.setLevel(logging.DEBUG)   # capture everything; handlers filter

    formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

    # File handler — always DEBUG level, rotating 5 MB × 3 backups
    fh = RotatingFileHandler(
        _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Console handler — respects LOG_LEVEL env var
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(_CONSOLE_LEVEL)
    ch.setFormatter(formatter)
    root.addHandler(ch)

    # Silence noisy third-party loggers
    for noisy in ("werkzeug", "dash", "dash.dash", "httpx",
                  "urllib3", "chromadb", "apscheduler.executors"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_configure_root()


# ── Public factory ────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger. Call once at module top-level."""
    return logging.getLogger(name)
