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

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple


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
        """Try the HuggingFace Inference API via LangChain. Returns text or None on failure."""
        if self._quota_hit:
            return None
        hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
        if not hf_token:
            return None

        try:
            from langchain_huggingface import HuggingFaceEndpoint

            prompt = prompt_template.format_map(context_data)
            llm = HuggingFaceEndpoint(
                repo_id="mistralai/Mistral-7B-Instruct-v0.3",
                huggingfacehub_api_token=hf_token,
                max_new_tokens=max_tokens,
                temperature=0.3,
                timeout=60,
            )
            result = llm.invoke(prompt)
            if hasattr(result, "content"):
                result = result.content
            if isinstance(result, list):
                result = " ".join(str(part) for part in result)
            return str(result).strip() or None
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
