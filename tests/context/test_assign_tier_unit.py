"""Unit tests for assign_tier() function (T046).

Tests the tier assignment function in isolation without database dependencies.
Verifies correct tier mapping based on importance scores.

Part of 007-context-management Phase 5 (US3 - Automatic Tier Assignment).
"""

import pytest
from codeframe.lib.importance_scorer import assign_tier


class TestAssignTierUnit:
    """Unit tests for assign_tier() function."""

    def test_assign_tier_returns_string(self):
        """Test that assign_tier returns a string tier name."""
        result = assign_tier(0.9)
        assert isinstance(result, str)
        assert result in ["HOT", "WARM", "COLD"]

    def test_assign_tier_hot_threshold(self):
        """Test HOT tier assignment at exact threshold (0.8)."""
        assert assign_tier(0.8) == "HOT"

    def test_assign_tier_warm_threshold(self):
        """Test WARM tier assignment at exact lower threshold (0.4)."""
        assert assign_tier(0.4) == "WARM"

    def test_assign_tier_hot_range(self):
        """Test all scores >= 0.8 map to HOT."""
        hot_scores = [0.8, 0.85, 0.9, 0.95, 0.99, 1.0]
        for score in hot_scores:
            assert assign_tier(score) == "HOT", f"Score {score} should be HOT"

    def test_assign_tier_warm_range(self):
        """Test all scores in [0.4, 0.8) map to WARM."""
        warm_scores = [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.79]
        for score in warm_scores:
            assert assign_tier(score) == "WARM", f"Score {score} should be WARM"

    def test_assign_tier_cold_range(self):
        """Test all scores < 0.4 map to COLD."""
        cold_scores = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.39]
        for score in cold_scores:
            assert assign_tier(score) == "COLD", f"Score {score} should be COLD"

    def test_assign_tier_boundary_precision(self):
        """Test tier assignment with high precision near boundaries."""
        # Just below HOT threshold
        assert assign_tier(0.799999) == "WARM"
        assert assign_tier(0.7999999999) == "WARM"

        # Exact HOT threshold
        assert assign_tier(0.8) == "HOT"

        # Just above HOT threshold
        assert assign_tier(0.800001) == "HOT"

        # Just below WARM threshold
        assert assign_tier(0.399999) == "COLD"
        assert assign_tier(0.3999999999) == "COLD"

        # Exact WARM threshold
        assert assign_tier(0.4) == "WARM"

        # Just above WARM threshold
        assert assign_tier(0.400001) == "WARM"

    def test_assign_tier_edge_cases(self):
        """Test edge cases: minimum and maximum scores."""
        # Minimum score
        assert assign_tier(0.0) == "COLD"

        # Maximum score
        assert assign_tier(1.0) == "HOT"

    def test_assign_tier_defensive_bounds(self):
        """Test defensive behavior with out-of-range scores."""
        # These shouldn't happen due to score clamping in calculate_importance_score,
        # but test defensive behavior

        # Negative scores (should treat as COLD)
        assert assign_tier(-0.1) == "COLD"
        assert assign_tier(-1.0) == "COLD"

        # Scores > 1.0 (should treat as HOT)
        assert assign_tier(1.1) == "HOT"
        assert assign_tier(2.0) == "HOT"

    def test_assign_tier_consistency(self):
        """Test that same score always returns same tier."""
        score = 0.65
        first_result = assign_tier(score)
        for _ in range(10):
            assert assign_tier(score) == first_result

    def test_assign_tier_monotonic_ordering(self):
        """Test that higher scores never get lower tiers."""
        tiers_order = {"COLD": 0, "WARM": 1, "HOT": 2}

        # Test that as scores increase, tier never decreases
        prev_score = 0.0
        prev_tier_rank = tiers_order[assign_tier(prev_score)]

        for score in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
            current_tier = assign_tier(score)
            current_tier_rank = tiers_order[current_tier]

            # Higher score should have >= tier rank
            assert current_tier_rank >= prev_tier_rank, \
                f"Score {score} (tier {current_tier}) should not have lower tier than {prev_score} (tier rank {prev_tier_rank})"

            prev_score = score
            prev_tier_rank = current_tier_rank


class TestAssignTierWithCalculatedScores:
    """Test assign_tier with realistic calculated importance scores."""

    def test_new_task_gets_hot_tier(self):
        """Test that fresh TASK (score ~0.8) gets HOT tier."""
        # New TASK: type=1.0, age=1.0, access=0.0
        # Score: 0.4*1.0 + 0.4*1.0 + 0.2*0.0 = 0.8
        score = 0.8
        assert assign_tier(score) == "HOT"

    def test_aged_task_gets_warm_tier(self):
        """Test that 3-day-old TASK gets WARM tier."""
        # 3-day TASK: type=1.0, age≈0.223, access=0
        # Score: 0.4*1.0 + 0.4*0.223 + 0.2*0.0 ≈ 0.49
        score = 0.49
        assert assign_tier(score) == "WARM"

    def test_very_old_item_gets_cold_tier(self):
        """Test that 30-day-old item gets COLD tier."""
        # 30-day item: age≈0, regardless of type
        # Score: < 0.4
        score = 0.3
        assert assign_tier(score) == "COLD"

    def test_frequently_accessed_old_item_stays_warm(self):
        """Test that high access count can keep old item in WARM."""
        # Old item with high access boost
        # Score: 0.4*0.8 + 0.4*0.2 + 0.2*0.46 ≈ 0.51
        score = 0.51
        assert assign_tier(score) == "WARM"
