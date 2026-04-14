"""
core/database.py — Fendt PESTEL-EL Sentinel: Astra DB Vector Store
===================================================================
Production-grade serverless vector store backed by DataStax Astra DB.
Embeddings are generated automatically via Astra Vectorize (Nvidia
NV-Embed-QA, 1024 dims, cosine similarity) — no local GPU or API key
overhead required at insert/query time.

Architecture
------------
  SignalDB             — thin façade: insert / upsert / query / delete
  Signal               — canonical Pydantic v2 data model (unchanged)
  PESTELDimension      — strict enum prevents tag drift
  _build_document()    — deterministic text sent to Astra Vectorize
  Signal._to_astra_doc()   — Signal → Astra document dict
  Signal._from_astra_doc() — Astra document dict → Signal

Similarity convention
---------------------
  Astra returns `$similarity` in [0.0, 1.0] (higher = more similar).
  All existing call sites expect ChromaDB-style distance (lower = more
  similar). SignalDB.search() converts: distance = 1.0 − similarity.

Environment
-----------
  ASTRA_DB_TOKEN — Application token from Astra DB console (required)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from astrapy import DataAPIClient
from astrapy.constants import VectorMetric
from astrapy.info import (
    CollectionDefinition,
    CollectionVectorOptions,
    VectorServiceOptions,
)
from pydantic import BaseModel, Field, field_validator, model_validator

# ─── Constants ────────────────────────────────────────────────────────────────

_ASTRA_ENDPOINT  = "https://8debd070-7481-4ab4-bedd-3c06e680be00-us-east-2.apps.astra.datastax.com"
_COLLECTION_NAME = "pestel_signals"

# Astra Vectorize provider / model (no separate API key needed)
_VECTORIZE_PROVIDER = "nvidia"
_VECTORIZE_MODEL    = "NV-Embed-QA"


# ─── Enums ────────────────────────────────────────────────────────────────────

class PESTELDimension(str, Enum):
    POLITICAL     = "POLITICAL"
    ECONOMIC      = "ECONOMIC"
    SOCIAL        = "SOCIAL"
    TECHNOLOGICAL = "TECHNOLOGICAL"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    LEGAL         = "LEGAL"


# ─── Core Data Model ──────────────────────────────────────────────────────────

class Signal(BaseModel):
    """
    Canonical representation of one intelligence signal.

    Scores are normalised to [0.0, 1.0]:
      impact_score   — how much disruption this signal may cause
      novelty_score  — how new / unexpected the information is
      velocity_score — rate of change / momentum (temporal)
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Stable UUID for deduplication",
    )
    title: str = Field(..., min_length=5, max_length=300)
    pestel_dimension: PESTELDimension
    content: str = Field(..., min_length=20)
    source_url: str = Field(..., description="Verbatim provenance URL")

    impact_score: float = Field(..., ge=0.0, le=1.0)
    novelty_score: float = Field(..., ge=0.0, le=1.0)
    velocity_score: float = Field(..., ge=0.0, le=1.0)

    date_ingested: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    entities: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)

    # ── derived ───────────────────────────────────────────────────────────────

    @property
    def disruption_score(self) -> float:
        """Composite score: Impact×0.5 + Novelty×0.3 + Velocity×0.2."""
        return round(
            self.impact_score * 0.5
            + self.novelty_score * 0.3
            + self.velocity_score * 0.2,
            4,
        )

    # ── validators ────────────────────────────────────────────────────────────

    @field_validator("source_url")
    @classmethod
    def url_must_have_scheme(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"source_url must start with http(s)://: {v!r}")
        return v

    @model_validator(mode="after")
    def title_not_in_content(self) -> Signal:
        if self.content.strip() == self.title.strip():
            raise ValueError("content must differ from title")
        return self

    # ── graph-engine serialisation (JSON-safe flat dict) ─────────────────────
    # Used by core/graph_engine.py LangGraph state — must stay stable.

    def to_metadata(self) -> dict:
        """Flat dict safe for LangGraph state (strings/ints/floats/bools only)."""
        return {
            "id":                self.id,
            "title":             self.title,
            "pestel_dimension":  self.pestel_dimension.value,
            "content":           self.content,
            "source_url":        self.source_url,
            "impact_score":      self.impact_score,
            "novelty_score":     self.novelty_score,
            "velocity_score":    self.velocity_score,
            "disruption_score":  self.disruption_score,
            "date_ingested":     self.date_ingested.isoformat(),
            "entities":          json.dumps(self.entities),
            "themes":            json.dumps(self.themes),
        }

    @classmethod
    def from_metadata(cls, metadata: dict) -> Signal:
        """Reconstruct a Signal from a to_metadata() dict (graph engine use)."""
        return cls(
            id=metadata["id"],
            title=metadata["title"],
            pestel_dimension=PESTELDimension(metadata["pestel_dimension"]),
            content=metadata["content"],
            source_url=metadata["source_url"],
            impact_score=float(metadata["impact_score"]),
            novelty_score=float(metadata["novelty_score"]),
            velocity_score=float(metadata["velocity_score"]),
            date_ingested=datetime.fromisoformat(metadata["date_ingested"]),
            entities=json.loads(metadata.get("entities", "[]")),
            themes=json.loads(metadata.get("themes", "[]")),
        )

    # ── Astra DB document serialisation ──────────────────────────────────────

    def _to_astra_doc(self) -> dict:
        """
        Convert to an Astra DB document.

        The ``$vectorize`` field is passed to Astra Vectorize (Nvidia
        NV-Embed-QA) which generates the embedding server-side.
        Entities and themes are stored as native lists (Astra supports
        rich types; JSON-stringification is not required here).
        """
        return {
            "_id":              self.id,
            "$vectorize":       _build_document(self),
            "title":            self.title,
            "pestel_dimension": self.pestel_dimension.value,
            "content":          self.content,
            "source_url":       self.source_url,
            "impact_score":     self.impact_score,
            "novelty_score":    self.novelty_score,
            "velocity_score":   self.velocity_score,
            "disruption_score": self.disruption_score,
            "date_ingested":    self.date_ingested.isoformat(),
            "entities":         self.entities,
            "themes":           self.themes,
        }

    @classmethod
    def _from_astra_doc(cls, doc: dict) -> Signal:
        """Reconstruct a Signal from an Astra DB document."""
        entities = doc.get("entities") or []
        themes   = doc.get("themes")   or []
        # Accept both native lists and legacy JSON strings (migration safety)
        if isinstance(entities, str):
            entities = json.loads(entities)
        if isinstance(themes, str):
            themes = json.loads(themes)
        return cls(
            id=doc["_id"],
            title=doc["title"],
            pestel_dimension=PESTELDimension(doc["pestel_dimension"]),
            content=doc["content"],
            source_url=doc["source_url"],
            impact_score=float(doc["impact_score"]),
            novelty_score=float(doc["novelty_score"]),
            velocity_score=float(doc["velocity_score"]),
            date_ingested=datetime.fromisoformat(doc["date_ingested"]),
            entities=entities,
            themes=themes,
        )


# ─── Vectorize document builder ───────────────────────────────────────────────

def _build_document(signal: Signal) -> str:
    """
    Deterministic text sent to Astra Vectorize (Nvidia NV-Embed-QA).

    Concatenates the semantically richest fields so similarity search
    works across titles, content, entities, and themes.
    """
    parts = [
        f"[{signal.pestel_dimension.value}]",
        signal.title,
        signal.content,
    ]
    if signal.entities:
        parts.append("Entities: " + ", ".join(signal.entities))
    if signal.themes:
        parts.append("Themes: " + ", ".join(signal.themes))
    return " | ".join(parts)


# ─── SignalDB ─────────────────────────────────────────────────────────────────

class SignalDB:
    """
    Thin façade over an Astra DB collection with Astra Vectorize.

    The collection is lazily created on first instantiation if it does
    not yet exist. Embeddings are generated automatically by the Nvidia
    NV-Embed-QA model hosted inside Astra — no local model or external
    embedding API call is made by this class.

    Usage
    -----
    >>> db = SignalDB()
    >>> db.insert(signal)
    >>> results = db.search("EU tractor subsidies", n_results=5)
    """

    def __init__(self) -> None:
        token = os.getenv("ASTRA_DB_TOKEN", "")
        if not token:
            raise RuntimeError(
                "ASTRA_DB_TOKEN is not set. "
                "Add it to your .env file and restart the app."
            )

        client    = DataAPIClient(token=token)
        self._db  = client.get_database(_ASTRA_ENDPOINT)
        self._col = self._get_or_create_collection()

    # ── collection bootstrap ───────────────────────────────────────────────────

    def _get_or_create_collection(self):
        """Return the existing collection or create it with Astra Vectorize."""
        existing_names = {c.name for c in self._db.list_collections()}
        if _COLLECTION_NAME in existing_names:
            return self._db.get_collection(_COLLECTION_NAME)

        return self._db.create_collection(
            _COLLECTION_NAME,
            definition=CollectionDefinition(
                vector=CollectionVectorOptions(
                    metric=VectorMetric.COSINE,
                    service=VectorServiceOptions(
                        provider=_VECTORIZE_PROVIDER,
                        model_name=_VECTORIZE_MODEL,
                    ),
                )
            ),
        )

    # ── write ──────────────────────────────────────────────────────────────────

    def insert(self, signal: Signal) -> str:
        """
        Upsert a Signal by its UUID.

        Astra Vectorize auto-embeds the ``$vectorize`` field using
        Nvidia NV-Embed-QA. No local embedding computation occurs.

        Returns the signal id.
        """
        doc = signal._to_astra_doc()
        self._col.find_one_and_replace(
            {"_id": signal.id},
            doc,
            upsert=True,
        )
        return signal.id

    def insert_many(self, signals: list[Signal]) -> list[str]:
        """
        Batch upsert. Each signal is individually replaced/inserted so
        Astra Vectorize can embed each ``$vectorize`` field.

        Returns list of ids.
        """
        if not signals:
            return []
        for s in signals:
            self.insert(s)
        return [s.id for s in signals]

    # ── read ───────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        n_results: int = 5,
        dimension_filter: Optional[PESTELDimension] = None,
    ) -> list[tuple[Signal, float]]:
        """
        Semantic similarity search powered by Astra Vectorize.

        The query string is embedded server-side using Nvidia NV-Embed-QA;
        the top-k most similar signals are returned.

        Parameters
        ----------
        query           : natural-language query string
        n_results       : how many signals to return
        dimension_filter: restrict results to one PESTEL dimension

        Returns
        -------
        List of (Signal, distance) tuples, sorted by distance ascending
        (lower = more similar).  Distance = 1.0 − Astra similarity score,
        preserving the ChromaDB convention used throughout the codebase.
        """
        filter_: dict = {}
        if dimension_filter:
            filter_["pestel_dimension"] = dimension_filter.value

        cursor = self._col.find(
            filter_,
            sort={"$vectorize": query},
            limit=n_results,
            include_similarity=True,
            projection={"$vector": False},   # omit raw embedding bytes
        )

        results: list[tuple[Signal, float]] = []
        for doc in cursor:
            similarity = float(doc.pop("$similarity", 0.0))
            distance   = round(1.0 - similarity, 4)
            sig        = Signal._from_astra_doc(doc)
            results.append((sig, distance))
        return results

    def get_by_id(self, signal_id: str) -> Optional[Signal]:
        """Exact fetch by UUID."""
        doc = self._col.find_one(
            {"_id": signal_id},
            projection={"$vector": False},
        )
        if doc is None:
            return None
        return Signal._from_astra_doc(doc)

    def get_all(self) -> list[Signal]:
        """
        Return every signal in the collection (up to 2 000).

        For dashboard and export use. Signals are returned in arbitrary
        order; callers are responsible for sorting.
        """
        cursor = self._col.find(
            {},
            projection={"$vector": False},
            limit=2_000,
        )
        return [Signal._from_astra_doc(doc) for doc in cursor]

    # ── stats ──────────────────────────────────────────────────────────────────

    def count(self) -> int:
        """Fast estimated document count (no full scan)."""
        return self._col.count_documents({}, upper_bound=10_000)

    def stats(self) -> dict:
        all_signals = self.get_all()
        by_dim: dict[str, int] = {}
        for s in all_signals:
            by_dim[s.pestel_dimension.value] = by_dim.get(s.pestel_dimension.value, 0) + 1
        return {
            "total_signals": self.count(),
            "by_dimension":  by_dim,
            "collection":    _COLLECTION_NAME,
            "endpoint":      _ASTRA_ENDPOINT,
            "vectorize":     f"{_VECTORIZE_PROVIDER}/{_VECTORIZE_MODEL}",
        }

    # ── delete ─────────────────────────────────────────────────────────────────

    def delete(self, signal_id: str) -> None:
        self._col.delete_one({"_id": signal_id})

    def clear(self) -> None:
        """Drop and recreate the collection. Use with caution."""
        self._db.drop_collection(_COLLECTION_NAME)
        self._col = self._get_or_create_collection()
