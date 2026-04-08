"""
core/database.py — Fendt PESTEL-EL Sentinel: Vector Signal Store
=================================================================
Persistent ChromaDB collection backed by Pydantic-validated Signal models.

Architecture
------------
  SignalDB             — thin façade: insert / query / delete
  Signal               — canonical Pydantic v2 data model
  PESTELDimension      — strict enum prevents tag drift
  _build_document()    — deterministic text used for embedding
  _to_signal()         — raw Chroma hit → validated Signal

Embedding
---------
  Uses ChromaDB's default embedding function (sentence-transformers
  "all-MiniLM-L6-v2" via chroma's bundled `chromadb.utils.embedding_functions`).
  No external API key required.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions
from pydantic import BaseModel, Field, field_validator, model_validator

# ─── Constants ────────────────────────────────────────────────────────────────

_DB_DIR = Path(__file__).parent.parent / "data" / "chroma_db"
_COLLECTION_NAME = "pestel_signals"
_EMBED_MODEL = "all-MiniLM-L6-v2"   # fast, runs fully offline via ONNX


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
        # Soft sanity: content should be richer than just the title
        if self.content.strip() == self.title.strip():
            raise ValueError("content must differ from title")
        return self

    # ── serialisation helpers ─────────────────────────────────────────────────

    def to_metadata(self) -> dict:
        """Flat dict safe for ChromaDB metadata (strings/ints/floats/bools only)."""
        return {
            "id":                self.id,
            "title":             self.title,
            "pestel_dimension":  self.pestel_dimension.value,
            "content":           self.content,          # stored for lossless reconstruction
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
        """Reconstruct a Signal from a ChromaDB metadata dict."""
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


# ─── Embedding helper ─────────────────────────────────────────────────────────

def _build_document(signal: Signal) -> str:
    """
    Deterministic text fed to the embedding model.

    Concatenates the semantically richest fields so that similarity search
    works on both titles and full content.
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
    Thin façade over a persistent ChromaDB collection.

    Usage
    -----
    >>> db = SignalDB()
    >>> db.insert(signal)
    >>> results = db.search("EU tractor subsidies", n_results=5)
    """

    def __init__(self, db_dir: Optional[Path] = None):
        _DB_DIR.mkdir(parents=True, exist_ok=True)
        path = str(db_dir or _DB_DIR)

        self._client = chromadb.PersistentClient(path=path)
        # DefaultEmbeddingFunction uses ONNX (all-MiniLM-L6-v2) —
        # no PyTorch / GPU required; fully offline after first download.
        self._ef = embedding_functions.DefaultEmbeddingFunction()
        self._col = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ── write ──────────────────────────────────────────────────────────────────

    def insert(self, signal: Signal) -> str:
        """
        Insert or update a Signal (upsert by signal.id).

        Returns the signal id.
        """
        self._col.upsert(
            ids=[signal.id],
            documents=[_build_document(signal)],
            metadatas=[signal.to_metadata()],
        )
        return signal.id

    def insert_many(self, signals: list[Signal]) -> list[str]:
        """Batch upsert. Returns list of ids."""
        if not signals:
            return []
        self._col.upsert(
            ids=[s.id for s in signals],
            documents=[_build_document(s) for s in signals],
            metadatas=[s.to_metadata() for s in signals],
        )
        return [s.id for s in signals]

    # ── read ───────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        n_results: int = 5,
        dimension_filter: Optional[PESTELDimension] = None,
    ) -> list[tuple[Signal, float]]:
        """
        Semantic similarity search.

        Parameters
        ----------
        query           : natural-language query string
        n_results       : how many signals to return
        dimension_filter: restrict results to one PESTEL dimension

        Returns
        -------
        List of (Signal, distance) tuples, sorted by distance ascending
        (lower = more similar).
        """
        where = (
            {"pestel_dimension": dimension_filter.value}
            if dimension_filter
            else None
        )
        kwargs: dict = dict(
            query_texts=[query],
            n_results=min(n_results, self._col.count() or 1),
            include=["documents", "metadatas", "distances"],
        )
        if where:
            kwargs["where"] = where

        raw = self._col.query(**kwargs)

        results: list[tuple[Signal, float]] = []
        for doc, meta, dist in zip(
            raw["documents"][0],
            raw["metadatas"][0],
            raw["distances"][0],
        ):
            sig = Signal.from_metadata(meta)
            results.append((sig, round(dist, 4)))
        return results

    def get_by_id(self, signal_id: str) -> Optional[Signal]:
        """Exact fetch by UUID."""
        raw = self._col.get(
            ids=[signal_id],
            include=["documents", "metadatas"],
        )
        if not raw["ids"]:
            return None
        return Signal.from_metadata(raw["metadatas"][0])

    def get_all(self) -> list[Signal]:
        """Return every signal in the collection."""
        raw = self._col.get(include=["documents", "metadatas"])
        return [Signal.from_metadata(m) for m in raw["metadatas"]]

    # ── stats ──────────────────────────────────────────────────────────────────

    def count(self) -> int:
        return self._col.count()

    def stats(self) -> dict:
        all_signals = self.get_all()
        by_dim: dict[str, int] = {}
        for s in all_signals:
            by_dim[s.pestel_dimension.value] = by_dim.get(s.pestel_dimension.value, 0) + 1
        return {
            "total_signals": self.count(),
            "by_dimension": by_dim,
            "collection": _COLLECTION_NAME,
            "db_path": str(_DB_DIR),
        }

    # ── delete ─────────────────────────────────────────────────────────────────

    def delete(self, signal_id: str) -> None:
        self._col.delete(ids=[signal_id])

    def clear(self) -> None:
        """Wipe the collection. Use with caution."""
        self._client.delete_collection(_COLLECTION_NAME)
        self._col = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
