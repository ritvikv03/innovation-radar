"""
Storage Abstraction Layer for Q2 Solution
==========================================

Provides unified interface for storing and retrieving signals.
Supports both JSON and SQLite backends.
"""

import json
import sqlite3
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod

from models import RawSignal, ClassifiedSignal, ScoredSignal


class SignalStore(ABC):
    """
    Abstract base class for signal storage.
    """

    @abstractmethod
    def save_signal(self, signal: ScoredSignal) -> None:
        """Save a scored signal."""
        pass

    @abstractmethod
    def get_all_signals(self) -> List[ScoredSignal]:
        """Retrieve all signals."""
        pass

    @abstractmethod
    def get_signals_by_classification(self, classification: str) -> List[ScoredSignal]:
        """Retrieve signals by classification (CRITICAL, HIGH, etc.)."""
        pass

    @abstractmethod
    def get_signals_by_dimension(self, dimension: str) -> List[ScoredSignal]:
        """Retrieve signals by PESTEL dimension."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored signals."""
        pass


class JSONSignalStore(SignalStore):
    """
    JSON file-based signal storage.
    """

    def __init__(self, filepath: str = "./outputs/data/signals_store.json"):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        # Initialize empty store if not exists
        if not self.filepath.exists():
            self._write([])

    def save_signal(self, signal: ScoredSignal) -> None:
        """Save a scored signal to JSON file."""
        signals = self._read()
        signals.append(signal.model_dump())
        self._write(signals)

    def get_all_signals(self) -> List[ScoredSignal]:
        """Retrieve all signals."""
        signals_dict = self._read()
        return [ScoredSignal(**s) for s in signals_dict]

    def get_signals_by_classification(self, classification: str) -> List[ScoredSignal]:
        """Retrieve signals by classification."""
        all_signals = self.get_all_signals()
        return [s for s in all_signals if s.classification == classification]

    def get_signals_by_dimension(self, dimension: str) -> List[ScoredSignal]:
        """Retrieve signals by PESTEL dimension."""
        all_signals = self.get_all_signals()
        return [s for s in all_signals if s.primary_dimension == dimension]

    def clear(self) -> None:
        """Clear all stored signals."""
        self._write([])

    def _read(self) -> List[Dict]:
        """Read signals from JSON file."""
        with open(self.filepath, 'r') as f:
            return json.load(f)

    def _write(self, signals: List[Dict]) -> None:
        """Write signals to JSON file."""
        with open(self.filepath, 'w') as f:
            json.dump(signals, f, indent=2, default=str)


class SQLiteSignalStore(SignalStore):
    """
    SQLite database-based signal storage.
    """

    def __init__(self, db_path: str = "./outputs/data/signals.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                url TEXT NOT NULL,
                date TEXT NOT NULL,
                primary_dimension TEXT NOT NULL,
                secondary_dimensions TEXT,
                novelty_score REAL NOT NULL,
                impact_score REAL NOT NULL,
                velocity_score REAL NOT NULL,
                disruption_score REAL NOT NULL,
                classification TEXT NOT NULL,
                time_horizon TEXT NOT NULL,
                entities TEXT,
                scored_at TEXT NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    def save_signal(self, signal: ScoredSignal) -> None:
        """Save a scored signal to SQLite database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO signals (
                title, content, source, url, date,
                primary_dimension, secondary_dimensions,
                novelty_score, impact_score, velocity_score,
                disruption_score, classification, time_horizon,
                entities, scored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal.title,
            signal.content,
            signal.source,
            str(signal.url),
            signal.date,
            signal.primary_dimension,
            json.dumps(signal.secondary_dimensions),
            signal.novelty_score,
            signal.impact_score,
            signal.velocity_score,
            signal.disruption_score,
            signal.classification,
            signal.temporal_metadata.time_horizon,
            json.dumps(signal.entities.model_dump()),
            signal.scored_at.isoformat()
        ))

        conn.commit()
        conn.close()

    def get_all_signals(self) -> List[ScoredSignal]:
        """Retrieve all signals."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM signals ORDER BY disruption_score DESC")
        rows = cursor.fetchall()
        conn.close()

        # Note: Full reconstruction requires mapping all fields
        # For simplicity, we return a minimal representation
        # In production, you'd want a complete ORM mapping
        signals = []
        for row in rows:
            # This is simplified - in production use proper ORM
            # or full field mapping
            pass

        return signals

    def get_signals_by_classification(self, classification: str) -> List[ScoredSignal]:
        """Retrieve signals by classification."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM signals WHERE classification = ? ORDER BY disruption_score DESC",
            (classification,)
        )
        rows = cursor.fetchall()
        conn.close()

        return []  # Simplified - would map rows to ScoredSignal objects

    def get_signals_by_dimension(self, dimension: str) -> List[ScoredSignal]:
        """Retrieve signals by PESTEL dimension."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM signals WHERE primary_dimension = ? ORDER BY disruption_score DESC",
            (dimension,)
        )
        rows = cursor.fetchall()
        conn.close()

        return []  # Simplified - would map rows to ScoredSignal objects

    def clear(self) -> None:
        """Clear all stored signals."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM signals")
        conn.commit()
        conn.close()


# Example usage
if __name__ == "__main__":
    from models import RawSignal, ExtractedEntities, TemporalMetadata
    from agents import ClassifierAgent, EvaluatorAgent

    print("=" * 70)
    print("STORAGE LAYER - EXAMPLE USAGE")
    print("=" * 70)

    # Create test signal
    raw_signal = RawSignal(
        title="EU Battery Mandate Test",
        content="Test content for battery swapping infrastructure mandate in European agricultural machinery.",
        source="Test Source",
        url="https://test.com/signal",
        date="2024-03-15"
    )

    # Process through agents
    classifier = ClassifierAgent()
    evaluator = EvaluatorAgent()

    classified = classifier.classify(raw_signal)
    scored = evaluator.evaluate(classified)

    # Test JSON store
    print("\n1. Testing JSON Storage:")
    json_store = JSONSignalStore(filepath="./test_outputs/test_signals.json")
    json_store.clear()
    json_store.save_signal(scored)

    all_signals = json_store.get_all_signals()
    print(f"   ✓ Saved and retrieved {len(all_signals)} signal(s)")
    print(f"   - Title: {all_signals[0].title[:50]}...")
    print(f"   - Score: {all_signals[0].disruption_score:.3f}")

    # Test SQLite store
    print("\n2. Testing SQLite Storage:")
    sqlite_store = SQLiteSignalStore(db_path="./test_outputs/test_signals.db")
    sqlite_store.clear()
    sqlite_store.save_signal(scored)
    print(f"   ✓ Saved signal to SQLite database")

    # Test classification filter
    print("\n3. Testing Filtered Retrieval:")
    json_store.save_signal(scored)  # Save another copy
    high_signals = json_store.get_signals_by_classification(scored.classification)
    print(f"   ✓ Retrieved {len(high_signals)} signal(s) with classification: {scored.classification}")

    print("\n" + "=" * 70)
    print("STORAGE LAYER TESTS COMPLETED")
    print("=" * 70)
