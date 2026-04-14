"""
core/pipeline.py — Fendt PESTEL-EL Sentinel: Scoring Pipeline
==============================================================
Takes raw text (news article, report snippet, any string) and
returns a fully-validated Signal ready for Astra DB insertion.

Flow
----
  raw_text  →  _call_llm()     →  LLMScoreResponse (Pydantic)
           →  _to_signal()     →  Signal (validated, UUID assigned)
           →  SignalDB.insert()

Public API
----------
  score_text(text)         → (Signal, LLMScoreResponse)
  score_and_save(text, db) → Optional[(Signal, LLMScoreResponse)]
                             Returns None when the text is a near-duplicate.
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from core.database import PESTELDimension, Signal, SignalDB
from core.logger import get_logger
from core.utils import retry_with_backoff

log = get_logger(__name__)

# ─── HuggingFace setup ────────────────────────────────────────────────────────
# Use InferenceClient.chat_completion() — the same path as the chat tab.
# This targets the `conversational` provider task, avoiding the
# `text-generation` endpoint that novita does not expose for this model.

_HF_TOKEN       = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
_HF_REPO_ID     = "meta-llama/Llama-3.1-8B-Instruct"
_HF_PROVIDER    = "cerebras"
_MAX_NEW_TOKENS = 1024


# ─── LLM response schema (strict Pydantic) ────────────────────────────────────

class LLMScoreResponse(BaseModel):
    """
    Intermediate model: validates raw JSON returned by the LLM before
    converting to a full Signal.
    """

    title: str = Field(..., min_length=5, max_length=300,
                       description="Concise headline summarising the signal")
    pestel_dimension: str = Field(
        ..., description="One of: POLITICAL ECONOMIC SOCIAL TECHNOLOGICAL ENVIRONMENTAL LEGAL"
    )
    content: str = Field(
        ..., min_length=20,
        description="2–4 sentence synthesis of the signal's strategic disruption relevance"
    )
    source_url: str = Field(
        default="https://unknown-source.placeholder",
        description="Verbatim URL if detectable in the text, else placeholder"
    )
    impact_score: float = Field(..., ge=0.0, le=1.0,
                                description="Magnitude of potential disruption (0–1)")
    novelty_score: float = Field(..., ge=0.0, le=1.0,
                                 description="How new/unexpected this development is (0–1)")
    velocity_score: float = Field(..., ge=0.0, le=1.0,
                                  description="Rate of change / momentum (0–1)")
    entities: list[str] = Field(default_factory=list,
                                description="Key organisations, regulations, technologies named")
    themes: list[str] = Field(default_factory=list,
                              description="2–5 short thematic tags")
    reasoning: str = Field(
        default="",
        description="One sentence: why these scores were assigned"
    )

    @field_validator("pestel_dimension")
    @classmethod
    def validate_dimension(cls, v: str) -> str:
        v = v.strip().upper()
        valid = {d.value for d in PESTELDimension}
        if v not in valid:
            # attempt common remaps before failing
            remap = {
                "INNOVATION": "TECHNOLOGICAL",
                "SOCIAL_MEDIA": "SOCIAL",
                "TECHNOLOGY": "TECHNOLOGICAL",
                "ENVIRONMENT": "ENVIRONMENTAL",
                "POLITICS": "POLITICAL",
                "ECONOMY": "ECONOMIC",
                "LAW": "LEGAL",
                "REGULATION": "LEGAL",
            }
            v = remap.get(v, v)
        if v not in valid:
            raise ValueError(f"Unknown PESTEL dimension: {v!r}. Must be one of {sorted(valid)}")
        return v

    @field_validator("source_url", mode="before")
    @classmethod
    def fix_url(cls, v: object) -> str:
        if not v or not isinstance(v, str):
            return "https://unknown-source.placeholder"
        if not v.startswith(("http://", "https://")):
            return "https://unknown-source.placeholder"
        return v


# ─── Prompt ───────────────────────────────────────────────────────────────────
# Universal strategic prompt — no company-specific copy (sponsor requirement #3).

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert macro-environmental intelligence analyst specialising in
    strategic disruption signals. Your job is to score incoming text signals for
    their strategic relevance across the PESTEL framework.

    SCORING RUBRIC:
    - impact_score (0–1): How severely could this disrupt an organisation's market,
      supply chain, or competitive position? 0=no impact, 1=existential threat or
      major opportunity.
    - novelty_score (0–1): How surprising or new is this information relative to
      established trends? 0=widely known, 1=completely new signal.
    - velocity_score (0–1): How fast is this situation evolving? Consider regulatory
      timelines, market adoption curves, and urgency of decision-making. 0=slow/stable,
      1=requires immediate board attention.

    PESTEL DIMENSION: Assign the single most relevant dimension:
    POLITICAL, ECONOMIC, SOCIAL, TECHNOLOGICAL, ENVIRONMENTAL, or LEGAL.

    RULES:
    - Be precise and conservative. Reserve scores > 0.85 for genuinely disruptive signals.
    - content must be your OWN synthesis (2–4 sentences), not a copy of the input.
    - Respond ONLY with a valid JSON object. No markdown fences, no preamble, no trailing text.
""")

_USER_TEMPLATE = textwrap.dedent("""\
    Analyse the following text and return a JSON object with these exact fields:
    title, pestel_dimension, content, source_url, impact_score, novelty_score,
    velocity_score, entities, themes, reasoning.

    TEXT TO ANALYSE:
    ---
    {text}
    ---

    JSON RESPONSE:
""")


# ─── LLM call ─────────────────────────────────────────────────────────────────

_MIN_INPUT_CHARS = 200   # skip sources with too little text to score meaningfully


def _extract_json(raw: str) -> str:
    """
    Strip markdown fences, sanitise control characters, and extract the
    first JSON object from the LLM response.

    Handles two common model misbehaviours:
    1. Prose instead of JSON   → raises ValueError (No JSON object found)
    2. Raw control chars in    → replaced with spaces before parsing
       JSON string values        (fixes 'Invalid control character' errors)
    """
    # Remove ```json ... ``` or ``` ... ``` wrappers
    clean = re.sub(r"```(?:json)?", "", raw).strip()
    # Find the outermost { ... }
    start = clean.find("{")
    end   = clean.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in LLM response:\n{raw[:400]}")
    candidate = clean[start : end + 1]
    # Replace unescaped control characters (tabs, newlines inside strings)
    # that cause json.JSONDecodeError: Invalid control character
    candidate = re.sub(r'(?<!\\)[\x00-\x1f\x7f]', " ", candidate)
    return candidate


# Cosine distance threshold for near-duplicate detection.
# Astra returns distance = 1.0 − similarity, so range is [0.0, 1.0].
# A threshold of 0.08 catches rephrased duplicates of the same article
# while allowing genuinely new signals through.
_DEDUP_THRESHOLD = 0.08


def _is_duplicate(text: str, db: SignalDB) -> bool:
    """
    Return True if Astra DB already contains a semantically near-identical document.

    Uses cosine distance in [0.0, 1.0] (lower = more similar).
    """
    if db.count() == 0:
        return False
    results = db.search(text[:500], n_results=1)
    if not results:
        return False
    _, distance = results[0]
    if distance < _DEDUP_THRESHOLD:
        log.info("Dedup: skipping near-duplicate (distance=%.4f < %.4f)", distance, _DEDUP_THRESHOLD)
        return True
    return False


def _call_llm(text: str, max_input_chars: int = 8_000) -> LLMScoreResponse:
    """
    Send text to HuggingFace via InferenceClient.chat_completion() and
    parse the JSON scoring response.

    Uses the `conversational` task (chat_completion), which works across
    all HuggingFace inference providers including Cerebras.

    Raises
    ------
    RuntimeError  if HUGGINGFACEHUB_API_TOKEN is not set
    ValueError    if model returns malformed JSON or out-of-range scores
    """
    if not _HF_TOKEN:
        raise RuntimeError(
            "HUGGINGFACEHUB_API_TOKEN is not set. "
            "Add it to your .env file."
        )

    if len(text.strip()) < _MIN_INPUT_CHARS:
        raise ValueError(
            f"Input too short to score meaningfully ({len(text)} chars < {_MIN_INPUT_CHARS}). "
            "Skipping — scraper likely returned near-empty content."
        )

    truncated = text[:max_input_chars]
    if len(text) > max_input_chars:
        truncated += "\n\n[... article truncated for analysis ...]"

    user_content = _USER_TEMPLATE.format(text=truncated)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]

    log.info("Calling HuggingFace (%s) — text_len=%d chars", _HF_REPO_ID, len(truncated))

    def _invoke() -> str:
        from huggingface_hub import InferenceClient  # local import — avoids circular deps
        client   = InferenceClient(api_key=_HF_TOKEN, provider=_HF_PROVIDER)
        response = client.chat_completion(
            model=_HF_REPO_ID,
            messages=messages,
            max_tokens=_MAX_NEW_TOKENS,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()

    try:
        raw_text = retry_with_backoff(_invoke, max_attempts=3, base_delay=4.0)
    except (RuntimeError, ValueError, OSError) as exc:
        log.error("HuggingFace API error after retries: %s", exc)
        raise RuntimeError(f"HuggingFace API error: {exc}") from exc

    json_str = _extract_json(raw_text)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        log.error("HuggingFace returned invalid JSON: %s\nRaw: %s", exc, json_str[:300])
        raise ValueError(f"HuggingFace returned invalid JSON: {exc}") from exc

    log.debug("LLM response parsed: title=%r dim=%s",
              data.get("title", "?")[:60], data.get("pestel_dimension"))
    return LLMScoreResponse(**data)


# ─── Conversion ───────────────────────────────────────────────────────────────

def _to_signal(scored: LLMScoreResponse) -> Signal:
    """Convert a validated LLMScoreResponse into a Signal."""
    return Signal(
        title=scored.title,
        pestel_dimension=PESTELDimension(scored.pestel_dimension),
        content=scored.content,
        source_url=scored.source_url,
        impact_score=scored.impact_score,
        novelty_score=scored.novelty_score,
        velocity_score=scored.velocity_score,
        entities=scored.entities,
        themes=scored.themes,
    )


# ─── Public API ───────────────────────────────────────────────────────────────


def score_text(text: str) -> tuple[Signal, LLMScoreResponse]:
    """Score raw text via HuggingFace LLM. Returns (Signal, LLMScoreResponse)."""
    scored  = _call_llm(text)
    signal  = _to_signal(scored)
    log.info("Scored: [%s] %s  disruption=%.3f",
             signal.pestel_dimension.value, signal.title[:60], signal.disruption_score)
    return signal, scored


def score_and_save(
    text: str, db: Optional[SignalDB] = None
) -> Optional[tuple[Signal, LLMScoreResponse]]:
    """
    Score text and persist to Astra DB.

    Returns None if the text is a near-duplicate of an existing signal.
    Returns (Signal, LLMScoreResponse) otherwise.
    """
    if db is None:
        db = SignalDB()
    if _is_duplicate(text, db):
        return None
    signal, scored = score_text(text)
    db.insert(signal)
    return signal, scored
