"""
core/scheduler.py — Autonomous Background Intelligence Engine
=============================================================
Uses APScheduler to run the Scout + Pipeline continuously.

Architecture
------------
  SchedulerEngine.start()
    → every 6 hours: _run_scout_cycle()
        → scrape each PESTEL_SOURCE
        → score each article via Gemini
        → save to Astra DB
    → every 30 seconds: _heartbeat()
        → update HEALTH dict (alive, last_run, counts)

Health State (module-level HEALTH dict)
----------------------------------------
  Import and read `HEALTH` from anywhere in the app:
    from core.scheduler import HEALTH, engine

  Fields:
    scheduler_alive   bool
    scout_running     bool
    last_run_utc      str | None
    signals_this_run  int
    total_signals     int
    last_error        str | None
    errors_today      int
    next_run_utc      str | None
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import get_logger
from core.sources import PESTEL_SOURCES

log = get_logger(__name__)

_SOURCE_TIMEOUT = 60   # seconds per source before we give up and move on

# ── Global health state ───────────────────────────────────────
# Written by scheduler jobs, read by Dash callbacks.

HEALTH: dict = {
    "scheduler_alive":  False,
    "scout_running":    False,
    "last_run_utc":     None,
    "signals_this_run": 0,
    "total_signals":    0,
    "last_error":       None,
    "errors_today":     0,
    "next_run_utc":     None,
}


# ── Scout cycle ───────────────────────────────────────────────

def _run_scout_cycle() -> None:
    """
    One full intelligence cycle:
      scrape all sources → score via Gemini → save to Astra DB.
    Errors per source are caught; they never abort the full cycle.
    """
    from core.scraper      import scrape_source
    from core.pipeline     import score_and_save
    from core.database     import SignalDB
    from core.graph_engine import run_graph_update, rebuild_graph_from_db

    HEALTH["scout_running"] = True
    cycle_start = datetime.now(timezone.utc)
    log.info("Scout cycle started at %s", cycle_start.isoformat())

    db = SignalDB()
    saved = 0
    errors = 0

    for source in PESTEL_SOURCES:
        dim  = source["dimension"]
        name = source["source_name"]

        _executor = ThreadPoolExecutor(max_workers=1)
        future = _executor.submit(scrape_source, source)
        try:
            articles = future.result(timeout=_SOURCE_TIMEOUT)
        except FuturesTimeoutError:
            log.error("scrape_source timed out after %ds [%s] %s", _SOURCE_TIMEOUT, dim, name)
            _executor.shutdown(wait=False)   # abandon the hanging thread; don't block
            errors += 1
            continue
        except Exception as exc:
            log.error("scrape_source failed [%s] %s: %s", dim, name, exc)
            _executor.shutdown(wait=False)
            errors += 1
            continue
        _executor.shutdown(wait=False)

        for article in articles:
            url  = article.get("url",  source["url"])
            text = article.get("text", "")
            if not text.strip():
                continue

            annotated = f"SOURCE_URL: {url}\nDIMENSION_HINT: {dim}\n\n{text}"

            try:
                result = score_and_save(annotated, db=db)
                if result is None:
                    log.debug("Skipped duplicate article from %s", name)
                    continue
                signal, _scored = result
                log.info("Saved [%s] %s  disruption=%.3f",
                         signal.pestel_dimension.value,
                         signal.title[:60],
                         signal.disruption_score)
                saved += 1
                run_graph_update(signal)   # RAG knowledge-graph update
            except Exception as exc:
                log.warning("Score/save failed (%s): %s", name, exc)
                HEALTH["last_error"] = str(exc)
                errors += 1

    HEALTH["signals_this_run"] = saved
    HEALTH["total_signals"]    = db.count()
    HEALTH["last_run_utc"]     = cycle_start.isoformat()
    HEALTH["scout_running"]    = False
    HEALTH["errors_today"]     = HEALTH.get("errors_today", 0) + errors

    elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
    log.info("Scout cycle done: saved=%d errors=%d elapsed=%.1fs", saved, errors, elapsed)

    # Rebuild the Knowledge Graph from the full current Astra DB state
    # so every run produces an accurate, non-stale graph.
    if saved > 0:
        try:
            rebuild_graph_from_db()
        except Exception as exc:
            log.error("Post-cycle graph rebuild failed: %s", exc)


def _heartbeat() -> None:
    HEALTH["scheduler_alive"] = True


def _update_next_run(scheduler: BackgroundScheduler) -> None:
    for job in scheduler.get_jobs():
        if job.id == "scout":
            nxt = job.next_run_time
            HEALTH["next_run_utc"] = nxt.isoformat() if nxt else None
            break


# ── Engine class ──────────────────────────────────────────────

class SchedulerEngine:
    """
    Wraps APScheduler BackgroundScheduler.
    Usage:
        engine.start()        # call once at app startup
        engine.trigger_now()  # force immediate cycle (non-blocking)
        engine.stop()         # graceful shutdown
    """

    def __init__(self, interval_hours: int = 6):
        self._interval_hours = interval_hours
        self._scheduler: Optional[BackgroundScheduler] = None

    def start(self) -> None:
        if self._scheduler and self._scheduler.running:
            log.warning("Scheduler already running — ignoring duplicate start()")
            return

        log.info("Starting SchedulerEngine (interval=%dh)", self._interval_hours)
        self._scheduler = BackgroundScheduler(
            job_defaults={"misfire_grace_time": 300, "coalesce": True},
            timezone="UTC",
        )

        # Scout job — runs every N hours, NOT immediately on startup
        self._scheduler.add_job(
            _run_scout_cycle,
            trigger=IntervalTrigger(hours=self._interval_hours),
            id="scout",
            name="PESTEL Scout Cycle",
            replace_existing=True,
            next_run_time=None,
        )

        # Heartbeat — every 30 s
        self._scheduler.add_job(
            _heartbeat,
            trigger=IntervalTrigger(seconds=30),
            id="heartbeat",
            name="Scheduler Heartbeat",
            replace_existing=True,
        )

        self._scheduler.start()
        HEALTH["scheduler_alive"] = True
        _update_next_run(self._scheduler)
        log.info("SchedulerEngine running. Next scout: %s", HEALTH["next_run_utc"])

    def trigger_now(self) -> None:
        """Enqueue an immediate scout cycle (runs in background thread)."""
        if not self._scheduler:
            log.error("trigger_now() called before start()")
            return
        log.info("Manually triggering scout cycle…")
        self._scheduler.add_job(
            _run_scout_cycle,
            id="scout_manual",
            name="Manual Scout Run",
            replace_existing=True,
        )

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            HEALTH["scheduler_alive"] = False
            log.info("SchedulerEngine stopped.")

    @property
    def running(self) -> bool:
        return bool(self._scheduler and self._scheduler.running)


# ── Module-level singleton ────────────────────────────────────

engine = SchedulerEngine(interval_hours=6)
