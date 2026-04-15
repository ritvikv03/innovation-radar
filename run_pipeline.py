#!/usr/bin/env python3
"""
run_pipeline.py — Fendt PESTEL-EL Sentinel: Interactive CLI
============================================================
Score a news article or free text via HuggingFace, validate with
Pydantic, and save the result to Astra DB.

Usage
-----
  python run_pipeline.py                     # interactive prompt
  python run_pipeline.py --text "..."        # inline text
  python run_pipeline.py --url https://...   # fetch + score a URL
  python run_pipeline.py --no-save           # dry-run, don't persist
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
import urllib.request
from pathlib import Path

# Load .env automatically if dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=False)
except ImportError:
    # If python-dotenv is not installed, fall back to manual parse
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent))

from core.database import SignalDB
from core.pipeline import score_and_save, score_text

# ─── ANSI colour helpers ───────────────────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_GREEN  = "\033[92m"
_CYAN   = "\033[96m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_DIM    = "\033[2m"
_PURPLE = "\033[35m"

def _c(text: str, colour: str) -> str:
    """Wrap text in ANSI colour if stdout is a TTY."""
    if sys.stdout.isatty():
        return f"{colour}{text}{_RESET}"
    return text

def _header(msg: str) -> None:
    width = 65
    print()
    print(_c("─" * width, _DIM))
    print(_c(f"  {msg}", _BOLD + _CYAN))
    print(_c("─" * width, _DIM))

def _score_bar(value: float, width: int = 20) -> str:
    """Render a simple ASCII progress bar for a 0–1 score."""
    filled = round(value * width)
    bar    = "█" * filled + "░" * (width - filled)
    colour = _GREEN if value >= 0.7 else (_YELLOW if value >= 0.4 else _RED)
    return _c(f"[{bar}]", colour) + f" {value:.2f}"


# ─── URL fetcher ──────────────────────────────────────────────────────────────

def _fetch_url(url: str) -> str:
    """Fetch plain text from a URL using only stdlib."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Sentinel/1.0; +https://fendt.com)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_bytes = resp.read(200_000)   # cap at ~200 KB
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch URL: {exc}") from exc

    # Strip HTML tags if looks like HTML
    text = raw_bytes.decode("utf-8", errors="replace")
    if "<html" in text.lower():
        import re
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
    return text


# ─── Pretty print results ─────────────────────────────────────────────────────

def _print_results(signal, scored, saved: bool) -> None:
    """Print a rich terminal report of the scored signal."""

    _header("GEMINI SCORING RESULTS")

    print(f"\n  {_c('Title', _BOLD)}     : {signal.title}")
    print(f"  {_c('Dimension', _BOLD)} : {_c(signal.pestel_dimension.value, _PURPLE)}")
    print(f"  {_c('Signal ID', _BOLD)} : {_c(signal.id[:8] + '…', _DIM)}")

    print(f"\n  {_c('SCORES', _BOLD + _CYAN)}")
    print(f"    Impact   {_score_bar(signal.impact_score)}")
    print(f"    Novelty  {_score_bar(signal.novelty_score)}")
    print(f"    Velocity {_score_bar(signal.velocity_score)}")
    print(f"    Severity {_score_bar(scored.severity_score)}")
    print(f"    {_c('Disruption (composite)', _BOLD)} = "
          f"{_c(f'{signal.disruption_score:.3f}', _GREEN)}"
          f"  {_c('(Impact×0.5 + Novelty×0.3 + Velocity×0.2)', _DIM)}")

    print(f"\n  {_c('Synthesis', _BOLD)}")
    wrapped = textwrap.fill(signal.content, width=60, initial_indent="    ", subsequent_indent="    ")
    print(wrapped)

    if scored.reasoning:
        print(f"\n  {_c('Reasoning', _BOLD)}")
        print(textwrap.fill(scored.reasoning, width=60,
                            initial_indent="    ", subsequent_indent="    "))

    if signal.entities:
        print(f"\n  {_c('Entities', _BOLD)} : {', '.join(signal.entities)}")
    if signal.themes:
        print(f"  {_c('Themes', _BOLD)}   : {', '.join(signal.themes)}")

    print(f"\n  {_c('Source URL', _BOLD)}: {signal.source_url}")

    status = _c("✅  Saved to Astra DB", _GREEN) if saved else _c("⚠️  Dry-run (not saved)", _YELLOW)
    print(f"\n  {status}")
    print(_c("─" * 65, _DIM))
    print()


# ─── Interactive input mode ───────────────────────────────────────────────────

_INTRO = """
┌─────────────────────────────────────────────────────────────┐
│        Fendt PESTEL-EL Sentinel — Signal Scoring CLI        │
│  Paste article text (or type END on its own line to score)  │
│  Type 'quit' to exit                                        │
└─────────────────────────────────────────────────────────────┘
"""

def _interactive_loop(db: SignalDB, save: bool) -> None:
    print(_c(_INTRO, _CYAN))
    while True:
        print(_c("Paste article text below (END on blank line to submit, 'quit' to exit):", _BOLD))
        lines: list[str] = []
        try:
            while True:
                line = input()
                if line.strip().lower() == "quit":
                    print(_c("  Goodbye.", _DIM))
                    return
                if line.strip().upper() == "END":
                    break
                lines.append(line)
        except (KeyboardInterrupt, EOFError):
            print()
            return

        text = "\n".join(lines).strip()
        if not text:
            print(_c("  No text entered — try again.", _YELLOW))
            continue

        _run_scoring(text, source_url=None, db=db, save=save)


# ─── Core scoring runner ──────────────────────────────────────────────────────

def _run_scoring(
    text: str,
    source_url: str | None,
    db: SignalDB,
    save: bool,
) -> None:
    # Inject URL into text so the LLM can pick it up for source_url field
    if source_url and source_url not in text:
        text = f"SOURCE: {source_url}\n\n{text}"

    print(_c("\n  Sending to HuggingFace for scoring…", _DIM))

    try:
        if save:
            signal, scored = score_and_save(text, db=db)
        else:
            signal, scored = score_text(text)
    except (ValueError, RuntimeError) as exc:
        print(_c(f"\n  ❌  Error: {exc}", _RED))
        return

    _print_results(signal, scored, saved=save)


# ─── CLI entry point ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="run_pipeline.py",
        description="Score a news article or free text for agricultural disruption",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--text", "-t", metavar="TEXT",
                       help="Inline text to score (quote it in the shell)")
    group.add_argument("--url", "-u", metavar="URL",
                       help="Fetch a web page and score its content")
    parser.add_argument("--no-save", action="store_true",
                        help="Dry-run: score but do NOT write to Astra DB")
    args = parser.parse_args()

    save = not args.no_save
    db   = SignalDB()

    if args.url:
        print(_c(f"\n  Fetching: {args.url}", _DIM))
        try:
            text = _fetch_url(args.url)
        except RuntimeError as exc:
            print(_c(f"  ❌  {exc}", _RED))
            sys.exit(1)
        _run_scoring(text, source_url=args.url, db=db, save=save)

    elif args.text:
        _run_scoring(args.text, source_url=None, db=db, save=save)

    else:
        _interactive_loop(db=db, save=save)


if __name__ == "__main__":
    main()
