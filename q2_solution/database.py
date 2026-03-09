"""
SQLite Database for Signal Storage and Temporal Tracking
=========================================================

Provides stateful persistence for disruption signals with temporal analysis capabilities.
Tracks signal evolution over time to calculate mathematical momentum and velocity.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager


class SignalDatabase:
    """
    SQLite database for storing and querying disruption signals.

    Features:
    - Temporal tracking: Analyze signal frequency over time windows
    - Entity deduplication: Track similar themes/entities
    - Velocity calculation: Mathematical momentum based on historical data
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Defaults to q2_solution/data/signals.db
        """
        if db_path is None:
            db_dir = Path(__file__).parent / "data"
            db_dir.mkdir(exist_ok=True)
            db_path = str(db_dir / "signals.db")

        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Create signals table if it doesn't exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    url TEXT NOT NULL,
                    date_ingested TEXT NOT NULL,
                    primary_dimension TEXT NOT NULL,
                    novelty_score REAL,
                    impact_score REAL,
                    velocity_score REAL,
                    disruption_classification TEXT,
                    entities TEXT,
                    themes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for temporal queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_date_ingested
                ON signals(date_ingested)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_primary_dimension
                ON signals(primary_dimension)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_entities
                ON signals(entities)
            """)

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def insert_signal(
        self,
        title: str,
        content: str,
        source: str,
        url: str,
        date_ingested: str,
        primary_dimension: str,
        novelty_score: Optional[float] = None,
        impact_score: Optional[float] = None,
        velocity_score: Optional[float] = None,
        disruption_classification: Optional[str] = None,
        entities: Optional[List[str]] = None,
        themes: Optional[List[str]] = None
    ) -> int:
        """
        Insert a new signal into the database.

        Args:
            title: Signal title
            content: Signal content
            source: Source name
            url: Source URL
            date_ingested: ISO 8601 date string
            primary_dimension: PESTEL dimension (POLITICAL, ECONOMIC, etc.)
            novelty_score: Novelty score (0.0-1.0)
            impact_score: Impact score (0.0-1.0)
            velocity_score: Velocity score (0.0-1.0)
            disruption_classification: Classification (WEAK_SIGNAL, EMERGING_TREND, etc.)
            entities: List of extracted entities
            themes: List of extracted themes

        Returns:
            ID of inserted signal
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO signals (
                    title, content, source, url, date_ingested,
                    primary_dimension, novelty_score, impact_score,
                    velocity_score, disruption_classification,
                    entities, themes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, content, source, url, date_ingested,
                primary_dimension, novelty_score, impact_score,
                velocity_score, disruption_classification,
                json.dumps(entities) if entities else None,
                json.dumps(themes) if themes else None
            ))
            conn.commit()
            return cursor.lastrowid

    def get_signal_by_id(self, signal_id: int) -> Optional[Dict]:
        """
        Retrieve a signal by ID.

        Args:
            signal_id: Signal ID

        Returns:
            Signal dict or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM signals WHERE id = ?
            """, (signal_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_dict(row)
            return None

    def get_signals_by_date_range(
        self,
        start_date: str,
        end_date: str,
        dimension: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve signals within a date range.

        Args:
            start_date: ISO 8601 start date
            end_date: ISO 8601 end date
            dimension: Optional filter by PESTEL dimension

        Returns:
            List of signal dicts
        """
        with self._get_connection() as conn:
            if dimension:
                cursor = conn.execute("""
                    SELECT * FROM signals
                    WHERE date_ingested >= ? AND date_ingested <= ?
                    AND primary_dimension = ?
                    ORDER BY date_ingested DESC
                """, (start_date, end_date, dimension))
            else:
                cursor = conn.execute("""
                    SELECT * FROM signals
                    WHERE date_ingested >= ? AND date_ingested <= ?
                    ORDER BY date_ingested DESC
                """, (start_date, end_date))

            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def calculate_temporal_velocity(
        self,
        entities: List[str],
        themes: List[str],
        reference_date: Optional[str] = None
    ) -> Tuple[float, Dict]:
        """
        Calculate velocity based on temporal signal frequency.

        This is the key innovation: velocity is NOT based on keywords like "urgent",
        but on ACTUAL mathematical momentum - how many times similar entities/themes
        have appeared recently vs. historically.

        Formula:
        - Recent window: Last 30 days
        - Historical window: 30-180 days ago (6 months)
        - Velocity = (recent_count - historical_avg) / (historical_avg + 1)
        - Normalized to 0.0-1.0 scale

        Args:
            entities: List of entities to search for
            themes: List of themes to search for
            reference_date: Reference date (defaults to today)

        Returns:
            Tuple of (velocity_score, metadata_dict)
        """
        if reference_date is None:
            reference_date = datetime.now().date().isoformat()

        ref_date = datetime.fromisoformat(reference_date).date()

        # Define time windows
        recent_start = (ref_date - timedelta(days=30)).isoformat()
        recent_end = ref_date.isoformat()

        historical_start = (ref_date - timedelta(days=180)).isoformat()
        historical_end = (ref_date - timedelta(days=30)).isoformat()

        # Search for matching signals
        search_terms = entities + themes

        recent_count = self._count_signals_with_terms(
            search_terms, recent_start, recent_end
        )

        historical_count = self._count_signals_with_terms(
            search_terms, historical_start, historical_end
        )

        # Calculate historical average (per 30-day period)
        historical_avg = historical_count / 5.0  # 150 days / 30 days = 5 periods

        # Calculate velocity
        if historical_avg == 0:
            # No historical data: high velocity if recent activity
            velocity = min(recent_count / 10.0, 1.0)
        else:
            # Calculate momentum
            momentum = (recent_count - historical_avg) / (historical_avg + 1)
            # Normalize to 0.0-1.0
            velocity = max(0.0, min(1.0, (momentum + 1) / 2))

        metadata = {
            "recent_count": recent_count,
            "historical_count": historical_count,
            "historical_avg": historical_avg,
            "recent_window": f"{recent_start} to {recent_end}",
            "historical_window": f"{historical_start} to {historical_end}",
            "search_terms": search_terms
        }

        return velocity, metadata

    def _count_signals_with_terms(
        self,
        search_terms: List[str],
        start_date: str,
        end_date: str
    ) -> int:
        """
        Count signals containing any of the search terms in the date range.

        Args:
            search_terms: List of terms to search for
            start_date: ISO 8601 start date
            end_date: ISO 8601 end date

        Returns:
            Count of matching signals
        """
        if not search_terms:
            return 0

        with self._get_connection() as conn:
            # Build query with OR conditions for each term
            conditions = " OR ".join(["entities LIKE ? OR themes LIKE ?" for _ in search_terms])

            query = f"""
                SELECT COUNT(DISTINCT id) as count
                FROM signals
                WHERE date_ingested >= ? AND date_ingested <= ?
                AND ({conditions})
            """

            # Prepare parameters: date range + term wildcards
            params = [start_date, end_date]
            for term in search_terms:
                params.extend([f"%{term}%", f"%{term}%"])

            cursor = conn.execute(query, params)
            result = cursor.fetchone()
            return result['count'] if result else 0

    def get_all_signals(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Retrieve all signals, optionally limited.

        Args:
            limit: Maximum number of signals to return

        Returns:
            List of signal dicts
        """
        with self._get_connection() as conn:
            if limit:
                cursor = conn.execute("""
                    SELECT * FROM signals
                    ORDER BY date_ingested DESC
                    LIMIT ?
                """, (limit,))
            else:
                cursor = conn.execute("""
                    SELECT * FROM signals
                    ORDER BY date_ingested DESC
                """)

            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """Convert SQLite row to dict, parsing JSON fields."""
        result = dict(row)

        # Parse JSON fields
        if result.get('entities'):
            result['entities'] = json.loads(result['entities'])
        if result.get('themes'):
            result['themes'] = json.loads(result['themes'])

        return result

    def clear_all_signals(self):
        """Clear all signals from database. Use with caution!"""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM signals")
            conn.commit()

    def get_database_stats(self) -> Dict:
        """
        Get database statistics.

        Returns:
            Dict with stats (total_signals, dimensions, date_range)
        """
        with self._get_connection() as conn:
            # Total signals
            total = conn.execute("SELECT COUNT(*) as count FROM signals").fetchone()['count']

            # Signals per dimension
            dimensions = {}
            cursor = conn.execute("""
                SELECT primary_dimension, COUNT(*) as count
                FROM signals
                GROUP BY primary_dimension
            """)
            for row in cursor:
                dimensions[row['primary_dimension']] = row['count']

            # Date range
            date_range = conn.execute("""
                SELECT
                    MIN(date_ingested) as earliest,
                    MAX(date_ingested) as latest
                FROM signals
            """).fetchone()

            return {
                "total_signals": total,
                "signals_per_dimension": dimensions,
                "date_range": {
                    "earliest": date_range['earliest'],
                    "latest": date_range['latest']
                } if date_range['earliest'] else None
            }


# Convenience function for common use case
def get_database(db_path: Optional[str] = None) -> SignalDatabase:
    """
    Get a SignalDatabase instance.

    Args:
        db_path: Optional path to database file

    Returns:
        SignalDatabase instance
    """
    return SignalDatabase(db_path)
