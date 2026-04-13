"""
SummaryEngine — Use-case agnostic AI summary generator with persistence.
========================================================================

Generates executive summaries using HuggingFace with a rule-based fallback.
Results are persisted to SQLite so session restarts don't lose summaries.

Usage (from any module)::

    from core.summary_engine import SummaryEngine

    engine = SummaryEngine(use_case_id="fendt-pestel")

    text, source = engine.generate(
        context_data={"total": 42, "critical": 3},
        prompt_template="Summarize {total} signals, {critical} are CRITICAL.",
        fallback_fn=my_rule_based_fn,
    )
    # source is "ai" or "rule_based"

    # Retrieve the most recently persisted summary without calling the API:
    cached = engine.get_latest()
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class SummaryEngine:
    """
    AI summary generator with automatic fallback and SQLite persistence.

    Parameters
    ----------
    use_case_id:
        Stable identifier for the caller (e.g. "fendt-pestel").
        Used as a namespace key in the summaries table.
    db_path:
        Path to the SQLite database.  Defaults to the shared summaries.db
        inside data/ so no extra file is created.
    hf_token:
        Read from ``HUGGINGFACEHUB_API_TOKEN`` env var automatically.
        If unset or quota is exhausted, falls back to ``fallback_fn``.
    """

    def __init__(
        self,
        use_case_id: str,
        db_path: Optional[str] = None,
        hf_token: Optional[str] = None,
    ) -> None:
        self.use_case_id = use_case_id
        self._quota_hit = False

        if db_path is None:
            db_path = str(
                Path(__file__).parent.parent / "data" / "summaries.db"
            )
        self.db_path = db_path
        self._ensure_summaries_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        context_data: Dict[str, Any],
        prompt_template: str,
        fallback_fn: Callable[[Dict[str, Any]], str],
        max_tokens: int = 300,
        persist: bool = True,
    ) -> Tuple[str, str]:
        """
        Generate a summary using AI with automatic fallback.

        Parameters
        ----------
        context_data:
            Arbitrary dict.  Values are substituted into ``prompt_template``
            via ``str.format_map`` and passed to ``fallback_fn``.
        prompt_template:
            String with ``{key}`` placeholders matching keys in
            ``context_data``.
        fallback_fn:
            ``callable(context_data) -> str`` used when Gemini is
            unavailable or quota is exhausted.
        max_tokens:
            Max output tokens for the Gemini call.
        persist:
            If ``True``, save the result to SQLite (default).

        Returns
        -------
        (summary_text, source)
            ``source`` is ``"ai"`` or ``"rule_based"``.
        """
        # Guard: empty / None data must never crash here
        if not context_data:
            return self._no_data_message(), "rule_based"

        ai_text = self._call_llm(prompt_template, context_data, max_tokens)

        if ai_text:
            result, source = ai_text, "ai"
        else:
            result, source = self._safe_fallback(fallback_fn, context_data), "rule_based"

        if persist:
            self._persist(result, source)

        return result, source

    def get_latest(self) -> Optional[str]:
        """Return the most recently persisted summary for this use case."""
        try:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT content FROM summaries "
                    "WHERE use_case_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (self.use_case_id,),
                ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        prompt_template: str,
        context_data: Dict[str, Any],
        max_tokens: int,
    ) -> Optional[str]:
        """Try HuggingFace InferenceClient chat_completion. Returns text or None on failure."""
        if self._quota_hit:
            return None
        hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
        if not hf_token:
            return None

        try:
            from huggingface_hub import InferenceClient

            prompt = prompt_template.format_map(context_data)
            client = InferenceClient(api_key=hf_token)
            response = client.chat_completion(
                model="meta-llama/Llama-3.2-3B-Instruct",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            result = response.choices[0].message.content.strip()
            return result or None
        except Exception as exc:
            err = str(exc)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                self._quota_hit = True
            return None

    def _safe_fallback(
        self,
        fallback_fn: Callable[[Dict[str, Any]], str],
        context_data: Dict[str, Any],
    ) -> str:
        """Run the caller-supplied fallback, catching all exceptions."""
        try:
            return fallback_fn(context_data)
        except Exception:
            return self._no_data_message()

    def _no_data_message(self) -> str:
        return (
            f"No data available for '{self.use_case_id}'. "
            "Run the pipeline to generate intelligence."
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _ensure_summaries_table(self) -> None:
        try:
            with self._connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS summaries (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        use_case_id TEXT    NOT NULL,
                        content     TEXT    NOT NULL,
                        source      TEXT    NOT NULL,
                        created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_summaries_use_case
                    ON summaries(use_case_id, created_at)
                """)
        except Exception:
            pass  # DB may not exist yet; first pipeline run creates it

    def _persist(self, content: str, source: str) -> None:
        """Write the summary to SQLite.  Failures are silent."""
        try:
            with self._connection() as conn:
                conn.execute(
                    "INSERT INTO summaries (use_case_id, content, source) VALUES (?, ?, ?)",
                    (self.use_case_id, content, source),
                )
        except Exception:
            pass

    def _connection(self):
        """Return a WAL-mode SQLite connection as a context manager."""
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        return _ctx()


# ── Module-level helper ───────────────────────────────────────────────────────

_BRIEF_SYSTEM = (
    "You are a senior strategic intelligence analyst for Fendt (AGCO). "
    "Write a concise, actionable executive intelligence brief in Markdown. "
    "Structure: ## Executive Summary, ## Critical Signals (bullet list), "
    "## Strategic Implications, ## Recommended Actions. "
    "Be direct, concrete, and board-ready. No fluff."
)


def generate_brief_markdown(signals: List[Any]) -> str:
    """
    Generate a full strategic intelligence brief in Markdown format.

    Parameters
    ----------
    signals:
        List of Signal objects (or dicts with title/content/pestel_dimension/
        disruption_score keys). Typically the top 10 by disruption score.

    Returns
    -------
    Markdown string.  Falls back to a rule-based brief if the LLM is unavailable.
    """
    hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")

    # Build signal digest regardless of LLM availability
    lines: List[str] = []
    for s in signals:
        if hasattr(s, "title"):
            title   = s.title
            content = s.content
            dim     = s.pestel_dimension.value if hasattr(s.pestel_dimension, "value") else str(s.pestel_dimension)
            score   = getattr(s, "disruption_score", 0.0)
        else:
            title   = s.get("title", "Untitled")
            content = s.get("content", "")
            dim     = s.get("pestel_dimension", "UNKNOWN")
            score   = s.get("disruption_score", 0.0)
        lines.append(f"[{dim} | score={score:.2f}] {title}: {content[:200]}")

    digest = "\n".join(lines)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not hf_token:
        return _rule_based_brief(signals, digest, ts)

    try:
        from huggingface_hub import InferenceClient

        user_prompt = (
            f"Date: {ts}\n\n"
            f"Top signals by disruption score:\n{digest}\n\n"
            "Write the full strategic intelligence brief now."
        )
        client = InferenceClient(api_key=hf_token)
        response = client.chat_completion(
            model="meta-llama/Llama-3.2-3B-Instruct",
            messages=[
                {"role": "system", "content": _BRIEF_SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=1024,
            temperature=0.4,
        )
        text = response.choices[0].message.content.strip()
        return text if text else _rule_based_brief(signals, digest, ts)
    except Exception:
        return _rule_based_brief(signals, digest, ts)


def _rule_based_brief(signals: List[Any], digest: str, ts: str) -> str:
    """Deterministic fallback brief when the LLM is unavailable."""
    count = len(signals)
    dims: dict[str, int] = {}
    for s in signals:
        dim = (
            s.pestel_dimension.value
            if hasattr(s, "pestel_dimension") and hasattr(s.pestel_dimension, "value")
            else str(getattr(s, "pestel_dimension", s.get("pestel_dimension", "UNKNOWN")))
        )
        dims[dim] = dims.get(dim, 0) + 1
    dim_summary = ", ".join(f"{k}: {v}" for k, v in sorted(dims.items()))

    bullets = []
    for s in signals[:5]:
        title = s.title if hasattr(s, "title") else s.get("title", "Untitled")
        score = getattr(s, "disruption_score", s.get("disruption_score", 0.0)) if not hasattr(s, "disruption_score") else s.disruption_score
        bullets.append(f"- **{title}** (disruption score: {score:.2f})")
    bullet_str = "\n".join(bullets)

    return f"""# Fendt Strategic Intelligence Brief
**Classification:** INTERNAL — C-SUITE
**Generated:** {ts}
**Signal Count:** {count}

---

## Executive Summary
This brief synthesises the {count} highest-disruption signals currently tracked across the EU agricultural machinery market. Dimension distribution: {dim_summary}.

## Critical Signals
{bullet_str}

## Strategic Implications
Review the full signal feed for detailed analysis. High-velocity signals in the TECHNOLOGICAL and REGULATORY dimensions warrant immediate attention from product and policy teams.

## Recommended Actions
1. Brief the board on the top 3 signals flagged above.
2. Assign PESTEL owners to monitor velocity trends over the next 30 days.
3. Schedule a competitive response session if any signal exceeds disruption score 0.85.

---
*Generated by Fendt PESTEL-EL Sentinel — rule-based fallback (LLM unavailable)*
"""
