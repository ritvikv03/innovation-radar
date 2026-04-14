"""
core/agents.py — Fendt PESTEL-EL Sentinel: Multi-Agent Relational Brain
========================================================================
A LangGraph parallel multi-agent framework powered by HuggingFace
Inference API (meta-llama/Llama-3.2-3B-Instruct).  Zero Anthropic
dependency — all inference runs through the HuggingFace free tier.

Architecture
------------
  AgentState
      │
  router_node          ← LLM classifies question type
      │
  ┌───▼──────────────────────┐
  │ route = "quantitative"   │ → calculator_node  (Tool-Calling Agent)
  │ route = "synthesis"      │ → analyst_node     (RAG-hydrated Agent)
  └──────────────────────────┘
      │                           │
  finalize_node ◄─────────────────┘
      │
     END

Route A — Quantitative
    The Calculator Agent interprets the question, selects a pre-built
    aggregation tool (avg score, count by dimension, top-N, etc.),
    executes it against the live signal metadata, then narrates results.

Route B — Synthesis
    The Analyst Agent receives Astra DB RAG context serialised via
    dict_to_string() (eliminating context poisoning from raw dicts)
    and produces a structured strategic analysis.

Public API
----------
    from core.agents import run_agent_query

    result = run_agent_query(question, signals)
    # result keys: final_answer, route, agent_trace, confidence
"""

from __future__ import annotations

import os
import statistics
from typing import Any, Optional

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from core.logger import get_logger

log = get_logger(__name__)

_HF_TOKEN    = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
_HF_MODEL    = "meta-llama/Llama-3.1-8B-Instruct"
_HF_PROVIDER = "cerebras"


# ── Utility: dict_to_string ───────────────────────────────────────────────────

def dict_to_string(data: Any, indent: int = 0, _depth: int = 0) -> str:
    """
    Recursively unpack nested dicts / lists into clean plain-text lines.

    Eliminates "context poisoning" caused by raw Python repr strings
    being injected into LLM prompts.  Handles:
      - nested dicts  → indented key: value pairs
      - lists         → bulleted items (nested dicts are expanded inline)
      - scalars       → converted to str, floats rounded to 4dp

    Parameters
    ----------
    data   : any Python value
    indent : visual indent level (auto-incremented by recursion)

    Returns
    -------
    Clean multi-line string suitable for LLM prompt injection.
    """
    if _depth > 8:                         # hard recursion guard
        return f"{'  ' * indent}…"

    pad = "  " * indent

    if isinstance(data, dict):
        lines: list[str] = []
        for k, v in data.items():
            key_label = str(k).replace("_", " ").title()
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{key_label}:")
                lines.append(dict_to_string(v, indent + 1, _depth + 1))
            elif isinstance(v, float):
                lines.append(f"{pad}{key_label}: {v:.4f}")
            else:
                lines.append(f"{pad}{key_label}: {v}")
        return "\n".join(lines)

    if isinstance(data, list):
        if not data:
            return f"{pad}(none)"
        lines = []
        for item in data:
            if isinstance(item, dict):
                lines.append(dict_to_string(item, indent, _depth + 1))
                lines.append("")          # blank line between records
            else:
                lines.append(f"{pad}• {item}")
        return "\n".join(lines).rstrip()

    if isinstance(data, float):
        return f"{pad}{data:.4f}"
    return f"{pad}{data}"


# ── LangGraph State ───────────────────────────────────────────────────────────

class AgentState(TypedDict):
    question:     str
    signals:      list[dict]      # pre-fetched RAG context (Signal.to_metadata() dicts)
    route:        str             # "quantitative" | "synthesis" | "unknown"
    tool_result:  str             # output from Calculator tool execution
    final_answer: str
    agent_trace:  list[str]       # ordered list of nodes that ran
    confidence:   str             # "high" | "medium" | "low"


# ── HuggingFace helper ────────────────────────────────────────────────────────

def _hf_chat(
    messages: list[dict],
    max_tokens: int = 512,
    temperature: float = 0.2,
) -> str:
    """Fire a chat_completion call via HuggingFace InferenceClient."""
    if not _HF_TOKEN:
        raise RuntimeError("HUGGINGFACEHUB_API_TOKEN not set")
    from huggingface_hub import InferenceClient
    client   = InferenceClient(api_key=_HF_TOKEN, provider=_HF_PROVIDER)
    response = client.chat_completion(
        model=_HF_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


# ── Node 1: router_node ───────────────────────────────────────────────────────

_ROUTER_SYSTEM = """\
You are a query router for an agricultural intelligence system.
Classify the user question into exactly one category:

QUANTITATIVE — the question asks for numbers, scores, counts, averages,
  rankings, percentages, or statistical comparisons across signals.

SYNTHESIS — the question asks for analysis, strategy, implications,
  recommendations, causality, or narrative explanation.

Respond with ONLY one word: QUANTITATIVE or SYNTHESIS.
No punctuation, no explanation."""


def router_node(state: AgentState) -> AgentState:
    """LLM-based conditional router: classifies question → sets state['route']."""
    question = state["question"]
    trace    = list(state.get("agent_trace", []))
    trace.append("router")

    if not _HF_TOKEN:
        log.warning("agents: no HF token — defaulting to synthesis route")
        return {**state, "route": "synthesis", "agent_trace": trace}

    try:
        raw = _hf_chat(
            messages=[
                {"role": "system", "content": _ROUTER_SYSTEM},
                {"role": "user",   "content": f"Question: {question}"},
            ],
            max_tokens=8,
            temperature=0.0,
        )
        route = "quantitative" if "QUANT" in raw.upper() else "synthesis"
        log.info("agents.router: %r → route=%s", question[:60], route)
        return {**state, "route": route, "agent_trace": trace}

    except Exception as exc:
        log.warning("agents.router failed (%s) — falling back to synthesis", exc)
        return {**state, "route": "synthesis", "agent_trace": trace}


# ── Node 2A: calculator_node (Route A — Tool-Calling Agent) ──────────────────

# ── Calculator tools ──────────────────────────────────────────────────────────

def _tool_average_score(signals: list[dict], dimension: Optional[str] = None) -> str:
    """Compute mean disruption score, optionally filtered by PESTEL dimension."""
    subset = (
        [s for s in signals if s.get("pestel_dimension", "").upper() == dimension.upper()]
        if dimension else signals
    )
    if not subset:
        return f"No signals found{' for ' + dimension if dimension else ''}."
    scores = [float(s.get("disruption_score", 0)) for s in subset]
    avg    = statistics.mean(scores)
    hi     = max(scores)
    lo     = min(scores)
    dim_label = f" ({dimension})" if dimension else ""
    return (
        f"Average disruption score{dim_label}: {avg:.3f}\n"
        f"Range: {lo:.3f} – {hi:.3f}\n"
        f"Signals analysed: {len(subset)}"
    )


def _tool_count_by_dimension(signals: list[dict]) -> str:
    """Count signals per PESTEL dimension and compute coverage percentages."""
    counts: dict[str, int] = {}
    for s in signals:
        dim = s.get("pestel_dimension", "UNKNOWN")
        counts[dim] = counts.get(dim, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return "No signals in database."
    lines = [f"Total signals: {total}"]
    for dim, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        pct = cnt / total * 100
        lines.append(f"  {dim:<15} {cnt:>3} signals  ({pct:.1f}%)")
    return "\n".join(lines)


def _tool_top_signals(signals: list[dict], n: int = 5) -> str:
    """Return the top-N signals by disruption score."""
    ranked = sorted(signals, key=lambda s: float(s.get("disruption_score", 0)), reverse=True)
    top    = ranked[:n]
    if not top:
        return "No signals available."
    lines = [f"Top {n} signals by disruption score:"]
    for i, s in enumerate(top, 1):
        lines.append(
            f"  {i}. [{s.get('pestel_dimension', '?')[:3]}] "
            f"{s.get('title', 'Untitled')[:70]}  "
            f"score={float(s.get('disruption_score', 0)):.3f}"
        )
    return "\n".join(lines)


def _tool_score_distribution(signals: list[dict]) -> str:
    """Bucket signals into CRITICAL / HIGH / MEDIUM / LOW bands."""
    bands: dict[str, list[str]] = {
        "CRITICAL (≥0.85)": [],
        "HIGH (0.65–0.84)": [],
        "MEDIUM (0.45–0.64)": [],
        "LOW (<0.45)": [],
    }
    for s in signals:
        score = float(s.get("disruption_score", 0))
        title = s.get("title", "Untitled")[:60]
        if score >= 0.85:
            bands["CRITICAL (≥0.85)"].append(title)
        elif score >= 0.65:
            bands["HIGH (0.65–0.84)"].append(title)
        elif score >= 0.45:
            bands["MEDIUM (0.45–0.64)"].append(title)
        else:
            bands["LOW (<0.45)"].append(title)
    lines = [f"Disruption score distribution ({len(signals)} signals):"]
    for band, titles in bands.items():
        lines.append(f"  {band}: {len(titles)} signals")
        for t in titles[:3]:
            lines.append(f"    · {t}")
        if len(titles) > 3:
            lines.append(f"    · … and {len(titles) - 3} more")
    return "\n".join(lines)


# Registry exposed to the LLM
_TOOL_REGISTRY: dict[str, str] = {
    "average_score":       "Compute the average disruption score, optionally for one dimension",
    "count_by_dimension":  "Count signals per PESTEL dimension with percentages",
    "top_signals":         "List top-N signals ranked by disruption score",
    "score_distribution":  "Bucket all signals into CRITICAL / HIGH / MEDIUM / LOW bands",
}

_TOOL_SELECTOR_SYSTEM = f"""\
You are the tool-selector for a PESTEL intelligence calculator.
Available tools:
{chr(10).join(f'  {name}: {desc}' for name, desc in _TOOL_REGISTRY.items())}

Respond with a JSON object (no markdown) with these keys:
  tool      — one of the tool names above
  dimension — (optional) PESTEL dimension: POLITICAL|ECONOMIC|SOCIAL|TECHNOLOGICAL|ENVIRONMENTAL|LEGAL
  n         — (optional) integer for top-N queries (default 5)

Example: {{"tool": "average_score", "dimension": "POLITICAL"}}"""


def calculator_node(state: AgentState) -> AgentState:
    """
    Tool-Calling Calculator Agent.

    Step 1: LLM selects the right aggregation tool from the registry.
    Step 2: Python executes the tool against the signal metadata.
    Step 3: LLM narrates the result as a concise strategic insight.
    """
    question = state["question"]
    signals  = state["signals"]
    trace    = list(state.get("agent_trace", []))
    trace.append("calculator")

    # ── Step 1: tool selection ────────────────────────────────────────────────
    tool_result = ""
    try:
        import json as _json

        raw = _hf_chat(
            messages=[
                {"role": "system", "content": _TOOL_SELECTOR_SYSTEM},
                {"role": "user",   "content": f"Question: {question}"},
            ],
            max_tokens=64,
            temperature=0.0,
        )
        # Strip markdown fences if present
        raw_clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        tool_spec = _json.loads(raw_clean)
        tool_name = tool_spec.get("tool", "count_by_dimension")
        dimension = tool_spec.get("dimension") or None
        n_val     = int(tool_spec.get("n") or 5)

        log.info("agents.calculator: selected tool=%s dim=%s n=%d", tool_name, dimension, n_val)

        # ── Step 2: execute ───────────────────────────────────────────────────
        if tool_name == "average_score":
            tool_result = _tool_average_score(signals, dimension)
        elif tool_name == "count_by_dimension":
            tool_result = _tool_count_by_dimension(signals)
        elif tool_name == "top_signals":
            tool_result = _tool_top_signals(signals, n_val)
        elif tool_name == "score_distribution":
            tool_result = _tool_score_distribution(signals)
        else:
            tool_result = _tool_count_by_dimension(signals)   # safe default

    except Exception as exc:
        log.warning("agents.calculator tool selection failed: %s — using default", exc)
        tool_result = _tool_count_by_dimension(signals)

    # ── Step 3: narrate ───────────────────────────────────────────────────────
    final_answer = tool_result          # default: raw output
    if _HF_TOKEN:
        try:
            final_answer = _hf_chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a concise PESTEL intelligence analyst. "
                            "Given the quantitative results below and the original question, "
                            "write a 2-3 sentence strategic insight. Be precise. No fluff."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question: {question}\n\n"
                            f"Calculator output:\n{tool_result}"
                        ),
                    },
                ],
                max_tokens=200,
                temperature=0.2,
            )
        except Exception as exc:
            log.warning("agents.calculator narration failed: %s — returning raw output", exc)

    return {
        **state,
        "tool_result":  tool_result,
        "final_answer": final_answer,
        "agent_trace":  trace,
        "confidence":   "high",
    }


# ── Node 2B: analyst_node (Route B — RAG Analyst Agent) ──────────────────────

_ANALYST_SYSTEM = """\
You are a senior strategic intelligence analyst for Tier-1 Agricultural OEM leadership.

ANALYSIS FRAMEWORK — structure every response as:
1. SIGNAL FINDING: What macro-level force is operating?
2. INDUSTRY IMPLICATION: How does this affect ALL Tier-1 Agricultural OEMs?
3. STRATEGIC RECOMMENDATION: What universal, actionable decisions must OEM leadership make?

RULES:
- Cite specific signal titles and disruption scores from the context.
- Do NOT name companies as winners/losers without evidence.
- Maximum 220 words. Be direct, strategic, decisive."""


def analyst_node(state: AgentState) -> AgentState:
    """
    RAG-hydrated Analyst Agent.

    Serialises signal context via dict_to_string() before injecting
    into the LLM prompt, preventing context poisoning from raw dicts.
    """
    question = state["question"]
    signals  = state["signals"]
    trace    = list(state.get("agent_trace", []))
    trace.append("analyst")

    if not _HF_TOKEN:
        return {
            **state,
            "final_answer": (
                "HuggingFace API token not configured. "
                "Set HUGGINGFACEHUB_API_TOKEN in your .env file."
            ),
            "agent_trace": trace,
            "confidence":  "low",
        }

    # Serialise signals through dict_to_string — clean, structured, no raw Python repr
    if signals:
        context_parts = []
        for i, sig in enumerate(signals[:8], 1):       # cap at 8 to stay within token budget
            context_parts.append(f"[Signal {i}]")
            context_parts.append(dict_to_string(sig, indent=1))
        context_block = "\n".join(context_parts)
    else:
        context_block = "(No signals in Astra DB — run Scout first to ingest data.)"

    try:
        answer = _hf_chat(
            messages=[
                {"role": "system", "content": _ANALYST_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"INTELLIGENCE CONTEXT:\n{context_block}\n\n"
                        f"STRATEGIC QUESTION: {question}"
                    ),
                },
            ],
            max_tokens=400,
            temperature=0.25,
        )
        confidence = "high" if signals else "low"
    except Exception as exc:
        log.error("agents.analyst failed: %s", exc)
        answer     = f"Analysis unavailable: {exc}"
        confidence = "low"

    return {
        **state,
        "final_answer": answer,
        "agent_trace":  trace,
        "confidence":   confidence,
    }


# ── Conditional edge ──────────────────────────────────────────────────────────

def _route_selector(state: AgentState) -> str:
    """LangGraph conditional edge: maps state['route'] to the next node name."""
    return state.get("route", "synthesis")


# ── Compile LangGraph workflow ────────────────────────────────────────────────

def _build_agent_graph():
    builder = StateGraph(AgentState)

    builder.add_node("router",     router_node)
    builder.add_node("quantitative", calculator_node)
    builder.add_node("synthesis",  analyst_node)

    builder.set_entry_point("router")

    builder.add_conditional_edges(
        "router",
        _route_selector,
        {
            "quantitative": "quantitative",
            "synthesis":    "synthesis",
            "unknown":      "synthesis",    # safe fallback
        },
    )

    builder.add_edge("quantitative", END)
    builder.add_edge("synthesis",    END)

    return builder.compile()


_agent_graph = _build_agent_graph()


# ── Public API ────────────────────────────────────────────────────────────────

def run_agent_query(
    question: str,
    signals: list,              # list[Signal] or list[dict] — both accepted
) -> dict:
    """
    Route a strategic question through the multi-agent system.

    Parameters
    ----------
    question : the user's natural-language question
    signals  : Signal objects or to_metadata() dicts from Astra DB search

    Returns
    -------
    dict with keys:
      final_answer  — the response text
      route         — "quantitative" | "synthesis"
      agent_trace   — ordered list of agents that ran
      confidence    — "high" | "medium" | "low"
      tool_result   — raw calculator output (empty string if synthesis route)
    """
    # Normalise: accept both Signal objects and plain dicts
    sig_dicts: list[dict] = []
    for s in signals:
        if isinstance(s, dict):
            sig_dicts.append(s)
        elif hasattr(s, "to_metadata"):
            sig_dicts.append(s.to_metadata())
        else:
            try:
                sig_dicts.append(dict(s))
            except Exception:
                pass

    initial_state: AgentState = {
        "question":     question,
        "signals":      sig_dicts,
        "route":        "unknown",
        "tool_result":  "",
        "final_answer": "",
        "agent_trace":  [],
        "confidence":   "medium",
    }

    try:
        result = _agent_graph.invoke(initial_state)
        log.info(
            "agents: answered via route=%s agents=%s confidence=%s",
            result.get("route"),
            result.get("agent_trace"),
            result.get("confidence"),
        )
        return result
    except Exception as exc:
        log.error("run_agent_query failed: %s", exc)
        return {
            "final_answer": f"Agent system error: {exc}",
            "route":        "synthesis",
            "agent_trace":  ["error"],
            "confidence":   "low",
            "tool_result":  "",
        }
