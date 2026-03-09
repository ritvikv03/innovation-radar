"""
Unit tests for database.py - SQLite signal storage and temporal velocity calculation.

Tests verify:
1. Signal insertion and retrieval
2. Temporal velocity calculation using historical data
3. Database statistics and queries
"""

import unittest
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add q2_solution to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'q2_solution'))

from database import SignalDatabase


class TestSignalDatabase(unittest.TestCase):
    """Test suite for SignalDatabase class."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db = SignalDatabase(db_path=self.temp_db.name)

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_database_initialization(self):
        """Test that database and tables are created successfully."""
        self.assertTrue(os.path.exists(self.temp_db.name))

        # Verify table exists
        stats = self.db.get_database_stats()
        self.assertEqual(stats['total_signals'], 0)
        self.assertEqual(stats['signals_per_dimension'], {})

    def test_insert_signal(self):
        """Test inserting a signal into the database."""
        signal_id = self.db.insert_signal(
            title="Test Signal: EU Nitrogen Limits",
            content="The EU has proposed new nitrogen fertilizer limits...",
            source="EUR-Lex",
            url="https://eur-lex.europa.eu/test",
            date_ingested="2026-03-01",
            primary_dimension="LEGAL",
            novelty_score=0.75,
            impact_score=0.68,
            velocity_score=0.55,
            disruption_classification="HIGH",
            entities=["nitrogen", "fertilizer", "limits"],
            themes=["LEGAL", "ENVIRONMENTAL"]
        )

        self.assertIsInstance(signal_id, int)
        self.assertGreater(signal_id, 0)

        # Verify signal was inserted
        stats = self.db.get_database_stats()
        self.assertEqual(stats['total_signals'], 1)
        self.assertEqual(stats['signals_per_dimension']['LEGAL'], 1)

    def test_retrieve_signal(self):
        """Test retrieving a signal by ID."""
        # Insert a signal
        signal_id = self.db.insert_signal(
            title="Test Retrieval Signal",
            content="Testing signal retrieval functionality",
            source="Test Source",
            url="https://test.example.com",
            date_ingested="2026-03-01",
            primary_dimension="TECHNOLOGICAL",
            entities=["AI", "robotics"],
            themes=["TECHNOLOGICAL"]
        )

        # Retrieve the signal
        signal = self.db.get_signal_by_id(signal_id)

        self.assertIsNotNone(signal)
        self.assertEqual(signal['title'], "Test Retrieval Signal")
        self.assertEqual(signal['primary_dimension'], "TECHNOLOGICAL")
        self.assertEqual(signal['entities'], ["AI", "robotics"])
        self.assertEqual(signal['themes'], ["TECHNOLOGICAL"])

    def test_calculate_temporal_velocity_no_history(self):
        """Test velocity calculation when there's no historical data."""
        velocity, metadata = self.db.calculate_temporal_velocity(
            entities=["nitrogen", "fertilizer"],
            themes=["LEGAL"],
            reference_date="2026-03-15"
        )

        # With no historical data, velocity should be based on recent count only
        self.assertGreaterEqual(velocity, 0.0)
        self.assertLessEqual(velocity, 1.0)
        self.assertEqual(metadata['recent_count'], 0)
        self.assertEqual(metadata['historical_count'], 0)

    def test_calculate_temporal_velocity_with_history(self):
        """
        Test velocity calculation with historical data.

        This is the KEY test for Phase 2: velocity is calculated from
        actual signal frequency, not keywords.
        """
        # Insert historical signals (30-180 days ago)
        base_date = datetime(2026, 3, 15)

        # Historical period (30-180 days ago): 2 signals
        for days_ago in [45, 90]:
            date = (base_date - timedelta(days=days_ago)).date().isoformat()
            self.db.insert_signal(
                title=f"Historical Signal {days_ago} days ago",
                content="Nitrogen fertilizer regulations discussed",
                source="Test",
                url=f"https://test.example.com/hist-{days_ago}",
                date_ingested=date,
                primary_dimension="LEGAL",
                entities=["nitrogen", "fertilizer"],
                themes=["LEGAL"]
            )

        # Recent period (last 30 days): 5 signals (acceleration!)
        for days_ago in [5, 10, 15, 20, 25]:
            date = (base_date - timedelta(days=days_ago)).date().isoformat()
            self.db.insert_signal(
                title=f"Recent Signal {days_ago} days ago",
                content="Nitrogen fertilizer limits tightening",
                source="Test",
                url=f"https://test.example.com/recent-{days_ago}",
                date_ingested=date,
                primary_dimension="LEGAL",
                entities=["nitrogen", "fertilizer"],
                themes=["LEGAL"]
            )

        # Calculate velocity
        velocity, metadata = self.db.calculate_temporal_velocity(
            entities=["nitrogen", "fertilizer"],
            themes=["LEGAL"],
            reference_date=base_date.date().isoformat()
        )

        # Verify velocity calculation
        self.assertGreater(velocity, 0.5,
                          "Velocity should be HIGH: 5 recent signals vs 2 historical (acceleration)")
        self.assertEqual(metadata['recent_count'], 5)
        self.assertEqual(metadata['historical_count'], 2)

        # Historical average should be 2 signals / 5 periods = 0.4 signals per 30-day period
        self.assertAlmostEqual(metadata['historical_avg'], 2/5, places=1)

        print(f"\n✅ Velocity Test Results:")
        print(f"   Recent signals (30 days): {metadata['recent_count']}")
        print(f"   Historical signals (30-180 days): {metadata['historical_count']}")
        print(f"   Historical average per period: {metadata['historical_avg']:.2f}")
        print(f"   Calculated velocity: {velocity:.3f}")
        print(f"   Interpretation: {'HIGH' if velocity > 0.7 else 'MODERATE' if velocity > 0.4 else 'LOW'} momentum")

    def test_date_range_query(self):
        """Test querying signals by date range."""
        # Insert signals with different dates
        dates = ["2026-01-15", "2026-02-15", "2026-03-15"]
        for date in dates:
            self.db.insert_signal(
                title=f"Signal from {date}",
                content="Test content",
                source="Test",
                url=f"https://test.example.com/{date}",
                date_ingested=date,
                primary_dimension="ECONOMIC"
            )

        # Query signals in February
        signals = self.db.get_signals_by_date_range(
            start_date="2026-02-01",
            end_date="2026-02-28"
        )

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]['title'], "Signal from 2026-02-15")

    def test_dimension_filtering(self):
        """Test filtering signals by PESTEL dimension."""
        # Insert signals across different dimensions
        dimensions = ["LEGAL", "ECONOMIC", "TECHNOLOGICAL"]
        for dim in dimensions:
            self.db.insert_signal(
                title=f"{dim} Signal",
                content="Test content",
                source="Test",
                url=f"https://test.example.com/{dim}",
                date_ingested="2026-03-01",
                primary_dimension=dim
            )

        # Query only LEGAL signals
        signals = self.db.get_signals_by_date_range(
            start_date="2026-02-01",
            end_date="2026-03-31",
            dimension="LEGAL"
        )

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]['primary_dimension'], "LEGAL")

    def test_database_statistics(self):
        """Test database statistics aggregation."""
        # Insert multiple signals
        for i in range(3):
            self.db.insert_signal(
                title=f"Legal Signal {i}",
                content="Legal content",
                source="Test",
                url=f"https://test.example.com/legal-{i}",
                date_ingested="2026-03-01",
                primary_dimension="LEGAL"
            )

        for i in range(2):
            self.db.insert_signal(
                title=f"Tech Signal {i}",
                content="Tech content",
                source="Test",
                url=f"https://test.example.com/tech-{i}",
                date_ingested="2026-03-01",
                primary_dimension="TECHNOLOGICAL"
            )

        stats = self.db.get_database_stats()

        self.assertEqual(stats['total_signals'], 5)
        self.assertEqual(stats['signals_per_dimension']['LEGAL'], 3)
        self.assertEqual(stats['signals_per_dimension']['TECHNOLOGICAL'], 2)
        self.assertIsNotNone(stats['date_range'])


class TestVelocityEdgeCases(unittest.TestCase):
    """Test edge cases in velocity calculation."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db = SignalDatabase(db_path=self.temp_db.name)

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_velocity_empty_entities(self):
        """Test velocity calculation with empty entity list."""
        velocity, metadata = self.db.calculate_temporal_velocity(
            entities=[],
            themes=[],
            reference_date="2026-03-15"
        )

        # Should return 0 velocity for empty search
        self.assertEqual(velocity, 0.0)
        self.assertEqual(metadata['recent_count'], 0)

    def test_velocity_deceleration(self):
        """Test velocity calculation when signal frequency is decreasing."""
        base_date = datetime(2026, 3, 15)

        # Historical period: 10 signals (high activity)
        for i in range(10):
            date = (base_date - timedelta(days=45 + i*10)).date().isoformat()
            self.db.insert_signal(
                title=f"Historical Signal {i}",
                content="Hydrogen tractor development",
                source="Test",
                url=f"https://test.example.com/hist-{i}",
                date_ingested=date,
                primary_dimension="TECHNOLOGICAL",
                entities=["hydrogen", "tractor"],
                themes=["TECHNOLOGICAL"]
            )

        # Recent period: 2 signals (activity declining)
        for i in range(2):
            date = (base_date - timedelta(days=5 + i*10)).date().isoformat()
            self.db.insert_signal(
                title=f"Recent Signal {i}",
                content="Hydrogen tractor interest waning",
                source="Test",
                url=f"https://test.example.com/recent-{i}",
                date_ingested=date,
                primary_dimension="TECHNOLOGICAL",
                entities=["hydrogen", "tractor"],
                themes=["TECHNOLOGICAL"]
            )

        velocity, metadata = self.db.calculate_temporal_velocity(
            entities=["hydrogen", "tractor"],
            themes=["TECHNOLOGICAL"],
            reference_date=base_date.date().isoformat()
        )

        # Velocity should be LOW/MODERATE (deceleration)
        # Note: Velocity normalizes to 0-1 range, so even with decline it may be >0
        self.assertLess(velocity, 0.6,
                       "Velocity should be LOW/MODERATE: recent activity declined vs historical")

        print(f"\n✅ Deceleration Test Results:")
        print(f"   Recent: {metadata['recent_count']}, Historical: {metadata['historical_count']}")
        print(f"   Velocity: {velocity:.3f} (deceleration detected)")


def run_tests():
    """Run all tests and print results."""
    print("=" * 70)
    print("DATABASE TEMPORAL VELOCITY TESTS")
    print("=" * 70)
    print("\nTesting Phase 2 Innovation: Mathematical Momentum Calculation\n")

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestSignalDatabase))
    suite.addTests(loader.loadTestsFromTestCase(TestVelocityEdgeCases))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED")
        print(f"   Tests run: {result.testsRun}")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
    else:
        print("❌ SOME TESTS FAILED")
        print(f"   Tests run: {result.testsRun}")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
    print("=" * 70)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
