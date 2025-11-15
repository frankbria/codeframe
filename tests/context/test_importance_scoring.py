"""Tests for importance scoring algorithm (T027).

Tests the core importance scoring formula:
    score = 0.4 × type_weight + 0.4 × age_decay + 0.2 × access_boost

Components:
- Type weight: TASK (1.0) > CODE (0.8) > ERROR (0.7) > TEST_RESULT (0.6) > PRD_SECTION (0.5)
- Age decay: Exponential decay over time (e^(-0.5 × days))
- Access boost: Log-normalized access frequency (log(count + 1) / 10)

Part of 007-context-management Phase 4 (US2 - Importance Scoring).
"""

import pytest
from datetime import datetime, timedelta, UTC
from codeframe.lib.importance_scorer import (
    calculate_importance_score,
    calculate_age_decay,
    calculate_access_boost,
    ITEM_TYPE_WEIGHTS,
)
from codeframe.core.models import ContextItemType


class TestImportanceScoring:
    """Test importance scoring algorithm."""

    def test_calculate_importance_for_new_task(self):
        """Test that fresh TASK item gets high score (>0.8)."""
        # ARRANGE: New task created now
        created_at = datetime.now(UTC)
        item_type = ContextItemType.TASK
        access_count = 0

        # ACT: Calculate importance score
        score = calculate_importance_score(
            item_type=item_type.value,
            created_at=created_at,
            access_count=access_count,
            last_accessed=created_at,
        )

        # ASSERT: New TASK has high score
        # Type weight: 1.0 (40%) = 0.4
        # Age decay: 1.0 (40%) = 0.4 (just created)
        # Access boost: 0.0 (20%) = 0.0 (no accesses)
        # Expected: 0.4 + 0.4 + 0.0 = 0.8
        assert score == pytest.approx(0.8, abs=0.01)  # Allow small floating point error
        assert score <= 1.0

    def test_calculate_importance_with_age_decay(self):
        """Test that 7-day-old item has lower score."""
        # ARRANGE: Item created 7 days ago
        created_at = datetime.now(UTC) - timedelta(days=7)
        item_type = ContextItemType.CODE
        access_count = 0

        # ACT: Calculate importance score
        score = calculate_importance_score(
            item_type=item_type.value,
            created_at=created_at,
            access_count=access_count,
            last_accessed=created_at,
        )

        # ASSERT: 7-day-old item has decayed score
        # Age decay for 7 days: e^(-0.5 × 7) = e^(-3.5) ≈ 0.03
        # Expected: 0.4 × 0.8 + 0.4 × 0.03 + 0.0 ≈ 0.33
        assert score < 0.5  # Significantly decayed
        assert score > 0.0

    def test_calculate_importance_with_access_boost(self):
        """Test that high access_count increases score."""
        # ARRANGE: Frequently accessed item
        created_at = datetime.now(UTC) - timedelta(days=1)
        item_type = ContextItemType.CODE
        access_count = 100  # Accessed 100 times

        # ACT: Calculate importance score
        score = calculate_importance_score(
            item_type=item_type.value,
            created_at=created_at,
            access_count=access_count,
            last_accessed=datetime.now(UTC),
        )

        # ASSERT: High access count boosts score
        # Access boost: log(101) / 10 ≈ 0.46 (capped at 1.0 → weighted at 0.2)
        # Age decay for 1 day: e^(-0.5) ≈ 0.606
        # Expected: 0.4 × 0.8 + 0.4 × 0.606 + 0.2 × 0.46 ≈ 0.64
        assert score >= 0.6
        assert score <= 1.0

    def test_importance_type_weights(self):
        """Test type weights: TASK > CODE > ERROR > TEST_RESULT > PRD_SECTION."""
        # ARRANGE: Same age and access count for all types
        created_at = datetime.now(UTC)
        access_count = 0

        # ACT: Calculate scores for each type
        scores = {}
        for item_type in ContextItemType:
            scores[item_type] = calculate_importance_score(
                item_type=item_type.value,
                created_at=created_at,
                access_count=access_count,
                last_accessed=created_at,
            )

        # ASSERT: Scores ordered by type weight
        assert scores[ContextItemType.TASK] > scores[ContextItemType.CODE]
        assert scores[ContextItemType.CODE] > scores[ContextItemType.ERROR]
        assert scores[ContextItemType.ERROR] > scores[ContextItemType.TEST_RESULT]
        assert scores[ContextItemType.TEST_RESULT] > scores[ContextItemType.PRD_SECTION]

    def test_importance_score_clamped_to_range(self):
        """Test that result always in [0.0, 1.0]."""
        # ARRANGE: Extreme cases
        test_cases = [
            # Very old item
            (datetime.now(UTC) - timedelta(days=365), 0),
            # Very new item with high access
            (datetime.now(UTC), 1000),
            # New item
            (datetime.now(UTC), 0),
        ]

        for created_at, access_count in test_cases:
            # ACT
            score = calculate_importance_score(
                item_type=ContextItemType.TASK.value,
                created_at=created_at,
                access_count=access_count,
                last_accessed=datetime.now(UTC),
            )

            # ASSERT: Always within range
            assert 0.0 <= score <= 1.0

    def test_importance_formula_components(self):
        """Test that formula uses correct weights: 40% type + 40% age + 20% access."""
        # ARRANGE: New TASK with no accesses
        created_at = datetime.now(UTC)
        item_type = ContextItemType.TASK
        access_count = 0

        # ACT: Calculate score and components
        score = calculate_importance_score(
            item_type=item_type.value,
            created_at=created_at,
            access_count=access_count,
            last_accessed=created_at,
        )

        # ASSERT: Verify formula
        # Type: 1.0 × 0.4 = 0.4
        # Age: 1.0 × 0.4 = 0.4 (just created)
        # Access: 0.0 × 0.2 = 0.0 (no accesses)
        # Expected: 0.8
        assert abs(score - 0.8) < 0.01  # Allow small floating point error


class TestAgeDecay:
    """Test exponential decay over time (T028)."""

    def test_exponential_decay_over_time(self):
        """Verify e^(-0.5 × days) formula."""
        import math

        # Test specific decay values
        test_cases = [
            (0, 1.0),  # New item: decay = 1.0
            (1, math.exp(-0.5)),  # 1 day: e^(-0.5) ≈ 0.606
            (7, math.exp(-3.5)),  # 7 days: e^(-3.5) ≈ 0.03
            (30, math.exp(-15)),  # 30 days: e^(-15) ≈ 0.000000306
        ]

        for days, expected_decay in test_cases:
            # ARRANGE
            created_at = datetime.now(UTC) - timedelta(days=days)

            # ACT
            decay = calculate_age_decay(created_at)

            # ASSERT
            assert abs(decay - expected_decay) < 0.001  # Allow small error

    def test_zero_age_gives_max_decay(self):
        """New item: age_decay = 1.0."""
        # ARRANGE: Item created right now
        created_at = datetime.now(UTC)

        # ACT
        decay = calculate_age_decay(created_at)

        # ASSERT
        assert decay == pytest.approx(1.0, abs=0.01)

    def test_old_items_approach_zero(self):
        """30-day-old item: age_decay < 0.1."""
        # ARRANGE: Item created 30 days ago
        created_at = datetime.now(UTC) - timedelta(days=30)

        # ACT
        decay = calculate_age_decay(created_at)

        # ASSERT
        assert decay < 0.1
        assert decay > 0.0  # Never exactly zero


class TestAccessBoost:
    """Test access frequency component."""

    def test_access_boost_logarithmic(self):
        """Test log(access_count + 1) / 10 formula."""
        import math

        test_cases = [
            (0, 0.0),  # No access
            (9, math.log(10) / 10),  # log(10) / 10 ≈ 0.23
            (99, math.log(100) / 10),  # log(100) / 10 ≈ 0.46
            (999, math.log(1000) / 10),  # log(1000) / 10 ≈ 0.69
            (10000, math.log(10001) / 10),  # High access
        ]

        for access_count, expected_boost in test_cases:
            # ACT
            boost = calculate_access_boost(access_count)

            # ASSERT
            assert abs(boost - expected_boost) < 0.01

    def test_access_boost_capped_at_one(self):
        """Test that access boost is capped at 1.0."""
        # ARRANGE: Very high access count
        access_count = 1_000_000

        # ACT
        boost = calculate_access_boost(access_count)

        # ASSERT: Capped at 1.0
        assert boost <= 1.0

    def test_type_weights_constant(self):
        """Verify ITEM_TYPE_WEIGHTS constant values."""
        assert ITEM_TYPE_WEIGHTS["TASK"] == 1.0
        assert ITEM_TYPE_WEIGHTS["CODE"] == 0.8
        assert ITEM_TYPE_WEIGHTS["ERROR"] == 0.7
        assert ITEM_TYPE_WEIGHTS["TEST_RESULT"] == 0.6
        assert ITEM_TYPE_WEIGHTS["PRD_SECTION"] == 0.5
