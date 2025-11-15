"""Tests for automatic tier assignment (T037).

Tests the tier assignment logic based on importance scores:
- HOT tier: score >= 0.8 (always loaded, critical recent context)
- WARM tier: 0.4 <= score < 0.8 (on-demand loading)
- COLD tier: score < 0.4 (archived, rarely accessed)

Part of 007-context-management Phase 5 (US3 - Automatic Tier Assignment).
"""

import pytest
from codeframe.lib.importance_scorer import assign_tier


class TestTierAssignment:
    """Test automatic tier assignment based on importance scores."""

    def test_assign_tier_hot_for_high_score(self):
        """Test that score >= 0.8 assigns HOT tier."""
        # ARRANGE: High importance scores
        test_scores = [0.8, 0.85, 0.9, 0.95, 1.0]

        for score in test_scores:
            # ACT
            tier = assign_tier(score)

            # ASSERT: All high scores get HOT tier
            assert tier == "HOT", f"Score {score} should assign HOT tier"

    def test_assign_tier_warm_for_medium_score(self):
        """Test that 0.4 <= score < 0.8 assigns WARM tier."""
        # ARRANGE: Medium importance scores
        test_scores = [0.4, 0.5, 0.6, 0.7, 0.79]

        for score in test_scores:
            # ACT
            tier = assign_tier(score)

            # ASSERT: All medium scores get WARM tier
            assert tier == "WARM", f"Score {score} should assign WARM tier"

    def test_assign_tier_cold_for_low_score(self):
        """Test that score < 0.4 assigns COLD tier."""
        # ARRANGE: Low importance scores
        test_scores = [0.0, 0.1, 0.2, 0.3, 0.39]

        for score in test_scores:
            # ACT
            tier = assign_tier(score)

            # ASSERT: All low scores get COLD tier
            assert tier == "COLD", f"Score {score} should assign COLD tier"

    def test_tier_boundaries(self):
        """Test exact threshold values (0.8 and 0.4)."""
        # ARRANGE: Exact boundary values
        boundaries = [
            (0.8, "HOT"),      # Lower bound of HOT tier
            (0.79999, "WARM"), # Just below HOT threshold
            (0.4, "WARM"),     # Lower bound of WARM tier
            (0.39999, "COLD"), # Just below WARM threshold
        ]

        for score, expected_tier in boundaries:
            # ACT
            tier = assign_tier(score)

            # ASSERT: Boundary values assign correct tier
            assert tier == expected_tier, \
                f"Score {score} should assign {expected_tier} tier, got {tier}"

    def test_tier_reassignment_on_score_change(self):
        """Test that changing score results in tier update."""
        # ARRANGE: Item starts with high score (HOT tier)
        initial_score = 0.9
        initial_tier = assign_tier(initial_score)
        assert initial_tier == "HOT"

        # ACT: Score decays to medium range (should become WARM)
        decayed_score = 0.6
        new_tier = assign_tier(decayed_score)

        # ASSERT: Tier changes to WARM
        assert new_tier == "WARM"
        assert new_tier != initial_tier

        # ACT: Score decays further to low range (should become COLD)
        very_old_score = 0.2
        final_tier = assign_tier(very_old_score)

        # ASSERT: Tier changes to COLD
        assert final_tier == "COLD"
        assert final_tier != new_tier


class TestTierBoundaryEdgeCases:
    """Additional edge case tests for tier boundaries."""

    def test_score_exactly_one(self):
        """Test maximum score (1.0) assigns HOT tier."""
        tier = assign_tier(1.0)
        assert tier == "HOT"

    def test_score_exactly_zero(self):
        """Test minimum score (0.0) assigns COLD tier."""
        tier = assign_tier(0.0)
        assert tier == "COLD"

    def test_score_just_above_hot_threshold(self):
        """Test score just above 0.8 is still HOT."""
        tier = assign_tier(0.800001)
        assert tier == "HOT"

    def test_score_just_below_warm_threshold(self):
        """Test score just below 0.4 is COLD."""
        tier = assign_tier(0.399999)
        assert tier == "COLD"

    def test_invalid_score_below_zero(self):
        """Test that negative scores are handled (should assign COLD)."""
        # This shouldn't happen in practice due to score clamping,
        # but we test defensive behavior
        tier = assign_tier(-0.1)
        assert tier == "COLD"

    def test_invalid_score_above_one(self):
        """Test that scores > 1.0 are handled (should assign HOT)."""
        # This shouldn't happen in practice due to score clamping,
        # but we test defensive behavior
        tier = assign_tier(1.5)
        assert tier == "HOT"
