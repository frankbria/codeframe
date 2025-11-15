"""Tests for score decay over time (T028).

Tests exponential decay formula: e^(-0.5 × age_days)

Part of 007-context-management Phase 4 (US2 - Importance Scoring).
"""

import pytest
import math
from datetime import datetime, timedelta, UTC
from codeframe.lib.importance_scorer import calculate_age_decay


class TestScoreDecay:
    """Test exponential decay over time."""

    def test_exponential_decay_over_time(self):
        """Verify e^(-0.5 × days) formula with multiple time points."""
        test_cases = [
            (0, 1.0),  # t=0: No decay
            (1, math.exp(-0.5)),  # t=1 day: e^(-0.5) ≈ 0.606
            (2, math.exp(-1.0)),  # t=2 days: e^(-1) ≈ 0.368
            (3, math.exp(-1.5)),  # t=3 days: e^(-1.5) ≈ 0.223
            (7, math.exp(-3.5)),  # t=7 days: e^(-3.5) ≈ 0.030
            (14, math.exp(-7.0)),  # t=14 days: e^(-7) ≈ 0.0009
            (30, math.exp(-15.0)),  # t=30 days: e^(-15) ≈ 3e-7
        ]

        for age_days, expected_decay in test_cases:
            # ARRANGE
            created_at = datetime.now(UTC) - timedelta(days=age_days)

            # ACT
            actual_decay = calculate_age_decay(created_at)

            # ASSERT
            assert actual_decay == pytest.approx(expected_decay, rel=1e-3)

    def test_zero_age_gives_max_decay(self):
        """New item (age=0): age_decay = 1.0."""
        # ARRANGE: Item created right now (age = 0)
        created_at = datetime.now(UTC)

        # ACT
        decay = calculate_age_decay(created_at)

        # ASSERT: Maximum decay value
        assert decay == pytest.approx(1.0, abs=0.001)

    def test_old_items_approach_zero(self):
        """30-day-old item: age_decay < 0.1."""
        # ARRANGE: Item created 30 days ago
        created_at = datetime.now(UTC) - timedelta(days=30)

        # ACT
        decay = calculate_age_decay(created_at)

        # ASSERT: Very small decay (approaching zero)
        assert decay < 0.1
        assert decay > 0.0  # But never exactly zero

    def test_decay_decreases_monotonically(self):
        """Verify that decay decreases as age increases."""
        # ARRANGE: Items of increasing age
        ages = [0, 1, 2, 5, 10, 20, 30]
        decays = []

        for age_days in ages:
            created_at = datetime.now(UTC) - timedelta(days=age_days)
            decay = calculate_age_decay(created_at)
            decays.append(decay)

        # ASSERT: Each decay smaller than previous
        for i in range(len(decays) - 1):
            assert decays[i] > decays[i + 1]

    def test_half_life_approximately_1_4_days(self):
        """Verify half-life is approximately 1.4 days for λ=0.5."""
        # For exponential decay e^(-λt), half-life = ln(2) / λ
        # With λ=0.5: half-life ≈ 1.386 days

        # ARRANGE: Item at half-life age
        half_life_days = math.log(2) / 0.5  # ≈ 1.386 days
        created_at = datetime.now(UTC) - timedelta(days=half_life_days)

        # ACT
        decay = calculate_age_decay(created_at)

        # ASSERT: Decay should be approximately 0.5
        assert decay == pytest.approx(0.5, rel=0.01)

    def test_decay_with_fractional_days(self):
        """Test decay calculation with fractional days (hours)."""
        # ARRANGE: Item created 12 hours ago (0.5 days)
        created_at = datetime.now(UTC) - timedelta(hours=12)

        # ACT
        decay = calculate_age_decay(created_at)

        # ASSERT: e^(-0.5 × 0.5) = e^(-0.25) ≈ 0.778
        expected = math.exp(-0.5 * 0.5)
        assert decay == pytest.approx(expected, rel=1e-3)

    def test_decay_never_exceeds_one(self):
        """Verify decay value never exceeds 1.0."""
        # ARRANGE: Various ages including negative (future dates, edge case)
        test_ages = [0, 1, 5, 10, 30, 100]

        for age_days in test_ages:
            created_at = datetime.now(UTC) - timedelta(days=age_days)

            # ACT
            decay = calculate_age_decay(created_at)

            # ASSERT: Always <= 1.0
            assert decay <= 1.0
