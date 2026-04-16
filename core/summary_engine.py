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
            ``callable(context_data) -> str`` used when HuggingFace is
            unavailable or quota is exhausted.
        max_tokens:
            Max output tokens for the HuggingFace call.
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
            client = InferenceClient(api_key=hf_token, provider="cerebras")
            response = client.chat_completion(
                model="meta-llama/Llama-3.1-8B-Instruct",
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

_BRIEF_SYSTEM = """\
You are a senior strategic intelligence analyst writing an executive briefing \
for C-suite leadership at a Tier-1 agricultural OEM. Your briefs are the sole \
decision-support document the board will read before allocating resources.

STRICT FORMAT — use this exact Markdown structure:

# Strategic Intelligence Brief
**Classification:** INTERNAL — C-SUITE ONLY
**Generated:** {date}
**Signal Count:** {count}

---

## Purpose and Background
One paragraph (3–4 sentences) stating:
- What this brief covers and why it was produced
- The time horizon of the intelligence window
- Why the board must read this now (the "so what?")

---

## Key Findings

For each of the top 3–5 signals, create a subsection:

### Finding N: [Signal Title]
- **PESTEL Dimension:** [dimension]
- **Disruption Score:** [score]
- **Time Horizon:** [12M / 24M / 36M based on velocity]

**Evidence:** Quote or paraphrase the key intelligence from the signal content.

**Industry Implication:** One sentence on how this affects ALL agricultural OEMs.

---

## Strategic Implications
3–5 bullet points synthesising cross-cutting themes. Connect the dots between \
findings. Identify convergence patterns (e.g., regulatory + economic pressure).

---

## Recommended Actions
Numbered list of 5–7 concrete, actionable steps. Each must include:
- **Timeline** (Immediate / Q2 2026 / Q3 2026 etc.)
- **Owner** (Board, R&D, Policy, Finance, etc.)
- **Action** (specific verb + object)

---

## Value Proposition and Impact

| Action | Investment Signal | Risk if Ignored |
|--------|-------------------|-----------------|
| (row per recommendation) | cost/effort hint | consequence |

---

## Conclusion
2–3 sentences reinforcing the strategic inflection point. End with a specific \
next step and deadline.

---
*Generated by Fendt PESTEL-EL Sentinel — AI Strategic Writer*

RULES:
- Be decisive, not hedging. Use "must" not "could consider".
- Cite specific signal titles and scores from the provided data.
- Do NOT invent data not present in the signals.
- Keep the total brief under 800 words.
- Use **bold** for key numbers, dates, and risk levels.
"""


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
    signal_data: List[dict] = []
    for s in signals:
        if hasattr(s, "title"):
            title   = s.title
            content = s.content
            dim     = s.pestel_dimension.value if hasattr(s.pestel_dimension, "value") else str(s.pestel_dimension)
            score   = getattr(s, "disruption_score", 0.0)
            velocity = getattr(s, "velocity_score", 0.0)
            impact   = getattr(s, "impact_score", 0.0)
            novelty  = getattr(s, "novelty_score", 0.0)
            entities = getattr(s, "entities", [])
            themes   = getattr(s, "themes", [])
            source_url = getattr(s, "source_url", "")
        else:
            title   = s.get("title", "Untitled")
            content = s.get("content", "")
            dim     = s.get("pestel_dimension", "UNKNOWN")
            score   = s.get("disruption_score", 0.0)
            velocity = s.get("velocity_score", 0.0)
            impact   = s.get("impact_score", 0.0)
            novelty  = s.get("novelty_score", 0.0)
            entities = s.get("entities", [])
            themes   = s.get("themes", [])
            source_url = s.get("source_url", "")
        signal_data.append({
            "title": title, "content": content, "dim": dim,
            "score": score, "velocity": velocity, "impact": impact,
            "novelty": novelty, "entities": entities, "themes": themes,
            "source_url": source_url,
        })

    # Build a rich digest for the LLM
    digest_lines: List[str] = []
    for i, sd in enumerate(signal_data, 1):
        horizon = "12M — CRITICAL" if sd["velocity"] >= 0.7 else "24M — HIGH" if sd["velocity"] >= 0.4 else "36M — MONITOR"
        ents = ", ".join(sd["entities"][:5]) if sd["entities"] else "N/A"
        digest_lines.append(
            f"Signal {i}:\n"
            f"  Title: {sd['title']}\n"
            f"  Dimension: {sd['dim']}\n"
            f"  Disruption Score: {sd['score']:.2f} (impact={sd['impact']:.2f}, novelty={sd['novelty']:.2f}, velocity={sd['velocity']:.2f})\n"
            f"  Time Horizon: {horizon}\n"
            f"  Key Entities: {ents}\n"
            f"  Content: {sd['content'][:300]}\n"
        )

    digest = "\n".join(digest_lines)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    count = len(signal_data)

    if not hf_token:
        return _rule_based_brief(signal_data, ts)

    try:
        from huggingface_hub import InferenceClient

        system = _BRIEF_SYSTEM.replace("{date}", ts).replace("{count}", str(count))
        user_prompt = (
            f"Intelligence Window: {ts}\n"
            f"Total Signals Analysed: {count}\n\n"
            f"SIGNAL DATA (ranked by disruption score, highest first):\n\n{digest}\n\n"
            "Write the full strategic intelligence brief now using the exact "
            "format specified in your system instructions. Focus on the top 3–5 "
            "most disruptive signals. Be board-ready."
        )
        client = InferenceClient(
            api_key=hf_token,
            provider=os.getenv("HF_PROVIDER", "novita"),
        )
        response = client.chat_completion(
            model="meta-llama/Llama-3.1-8B-Instruct",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=2048,
            temperature=0.35,
        )
        if not response or not getattr(response, "choices", None):
            return _rule_based_brief(signal_data, ts)
        text = response.choices[0].message.content.strip()
        return text if text else _rule_based_brief(signal_data, ts)
    except Exception:
        return _rule_based_brief(signal_data, ts)


def _rule_based_brief(signal_data: List[dict], ts: str) -> str:
    """Deterministic fallback brief when the LLM is unavailable."""
    count = len(signal_data)

    # Dimension counts
    dims: dict[str, int] = {}
    for sd in signal_data:
        dims[sd["dim"]] = dims.get(sd["dim"], 0) + 1
    dim_summary = ", ".join(f"**{k}**: {v}" for k, v in sorted(dims.items(), key=lambda x: x[1], reverse=True))

    # Severity breakdown
    critical = [sd for sd in signal_data if sd["score"] >= 0.75]
    high     = [sd for sd in signal_data if 0.50 <= sd["score"] < 0.75]

    # Top signals as findings
    findings: List[str] = []
    for i, sd in enumerate(signal_data[:5], 1):
        horizon = "12M — CRITICAL" if sd["velocity"] >= 0.7 else "24M — HIGH" if sd["velocity"] >= 0.4 else "36M — MONITOR"
        findings.append(
            f"### Finding {i}: {sd['title']}\n"
            f"- **PESTEL Dimension:** {sd['dim']}\n"
            f"- **Disruption Score:** {sd['score']:.2f}\n"
            f"- **Time Horizon:** {horizon}\n\n"
            f"**Evidence:** {sd['content'][:250]}\n\n"
            f"**Industry Implication:** Signals in the {sd['dim']} dimension at this "
            f"disruption level ({sd['score']:.2f}) indicate structural market shifts "
            f"requiring strategic response within the {horizon.split(' — ')[0]} window.\n"
        )
    findings_str = "\n---\n\n".join(findings)

    # Actions table
    table_rows: List[str] = []
    for i, sd in enumerate(signal_data[:5], 1):
        risk = "Market exclusion" if sd["score"] >= 0.75 else "Competitive lag" if sd["score"] >= 0.50 else "Missed opportunity"
        table_rows.append(f"| Address {sd['dim']} signal #{i} | Resource reallocation | {risk} |")
    table_str = "\n".join(table_rows)

    return f"""# Strategic Intelligence Brief
**Classification:** INTERNAL — C-SUITE ONLY
**Generated:** {ts}
**Signal Count:** {count}

---

## Purpose and Background

This brief synthesises the **{count}** highest-disruption signals currently tracked across the macro-environmental landscape by the PESTEL-EL Sentinel. The intelligence window covers the **preceding 30 days** of automated signal ingestion from regulatory databases, patent filings, market reports, and industry news. Of the signals analysed, **{len(critical)}** are rated CRITICAL (score ≥ 0.75) and **{len(high)}** are HIGH (0.50–0.74), indicating a concentrated period of strategic disruption requiring board-level attention.

---

## Key Findings

{findings_str}

---

## Strategic Implications

- **Regulatory convergence:** {dims.get('LEGAL', 0) + dims.get('POLITICAL', 0)} of {count} signals originate from Legal/Political dimensions, suggesting an accelerating regulatory environment that will constrain product development timelines.
- **Technology velocity:** {dims.get('TECHNOLOGICAL', 0)} signals in the Technological dimension indicate rapid innovation cycles — competitors who move first will capture market share.
- **Economic headwinds:** {dims.get('ECONOMIC', 0)} signals highlight macroeconomic pressures on customer purchasing power and subsidy structures.
- **Cross-dimensional risk:** The convergence of regulatory, economic, and technological signals creates a **strategic inflection point** — addressing any single dimension in isolation will be insufficient.
- **Dimension distribution:** {dim_summary}.

---

## Recommended Actions

1. **Immediate — Board:** Convene emergency strategy review to address the top 3 CRITICAL signals.
2. **Immediate — R&D:** Establish cross-functional task force for the highest-velocity technological signal.
3. **Q2 2026 — Policy:** Engage EU regulatory affairs team on all Legal/Political signals exceeding score 0.60.
4. **Q2 2026 — Finance:** Model revenue impact scenarios for Economic dimension signals.
5. **Q3 2026 — Strategy:** Develop competitive response playbook for each Technological signal.
6. **Ongoing — Intelligence:** Increase monitoring frequency to daily for all CRITICAL-rated signals.

---

## Value Proposition and Impact

| Action | Investment Signal | Risk if Ignored |
|--------|-------------------|-----------------|
{table_str}

---

## Conclusion

The current intelligence landscape reveals a **concentrated period of strategic disruption** across {len(dims)} PESTEL dimensions. With **{len(critical)} CRITICAL** and **{len(high)} HIGH** signals active simultaneously, the cost of inaction far exceeds the cost of response. Failure to act within the next **90 days** risks permanent competitive disadvantage in the EU's largest agricultural markets.

**Immediate Next Step:** Schedule C-suite portfolio review with CEO and CFO by end of current week.

---
*Generated by Fendt PESTEL-EL Sentinel — rule-based fallback (LLM unavailable)*
"""
