"""Tests for the pure, hand-rolled win-probability model
(analytics/win_probability.py). See docs/win_probability.md for what was
checked against this project's own real data before picking the default
weights, the real APA race-chart verification, and why RaceDifficulty is
a documented v1 gap rather than implemented.
"""

from __future__ import annotations

import math

import pytest

from analytics.win_probability import (
    CLAMP_MAX,
    CLAMP_MIN,
    DEFAULT_WIN_PROBABILITY_WEIGHTS,
    WinProbabilityWeights,
    compute_win_probability,
    race_difficulty,
    sl_delta,
)


class TestSLDelta:
    def test_a_real_skill_level_advantage_is_positive(self):
        assert sl_delta(player_skill_level=6, opponent_skill_level=4) == 2.0

    def test_a_real_skill_level_disadvantage_is_negative(self):
        assert sl_delta(player_skill_level=3, opponent_skill_level=5) == -2.0

    def test_an_even_pairing_is_zero(self):
        assert sl_delta(player_skill_level=5, opponent_skill_level=5) == 0.0

    def test_either_missing_skill_level_is_zero_not_excluded(self):
        assert sl_delta(None, 5) == 0.0
        assert sl_delta(5, None) == 0.0
        assert sl_delta(None, None) == 0.0


class TestRaceDifficultyIsADocumentedGap:
    """RaceDifficulty is NOT implemented in v1 -- see docs/win_probability.md
    ("Race chart verification" + "What's not implemented yet"). Always 0.0,
    a documented gap, never a guessed/fabricated race-chart-derived value."""

    def test_always_returns_zero_regardless_of_input(self):
        assert race_difficulty() == 0.0
        assert race_difficulty(player_skill_level=7, opponent_skill_level=2) == 0.0
        assert race_difficulty(format_name="9-Ball Open") == 0.0


class TestComputeWinProbability:
    def test_all_missing_inputs_land_on_the_pure_intercept(self):
        """z=0 with every input at 0 -- sigmoid(0) = 0.5, clamped."""
        result = compute_win_probability(None, None, None, None)
        assert result == pytest.approx(0.5, abs=1e-6)

    def test_missing_inputs_are_treated_as_zero_not_excluded_and_not_neutral(self):
        """Deliberately different from analytics.lineup_optimizer's
        neutral-0.5-per-missing-input convention: here a missing signal
        contributes nothing to z, not an assumed-average value."""
        only_sl_delta = compute_win_probability(2.0, None, None, None)
        expected_z = DEFAULT_WIN_PROBABILITY_WEIGHTS.sl_delta * 2.0
        expected_p = 1.0 / (1.0 + math.exp(-DEFAULT_WIN_PROBABILITY_WEIGHTS.logistic_scale * expected_z))
        assert only_sl_delta == pytest.approx(round(expected_p, 6))

    def test_a_real_favorable_pairing_scores_above_half(self):
        result = compute_win_probability(sl_delta=2.0, wr_sl=0.7, wr_h2h=0.8, volatility=0.1)
        assert result > 0.5

    def test_a_real_unfavorable_pairing_scores_below_half(self):
        result = compute_win_probability(sl_delta=-2.0, wr_sl=0.3, wr_h2h=0.2, volatility=0.1)
        assert result < 0.5

    def test_higher_volatility_alone_lowers_the_probability(self):
        calm = compute_win_probability(sl_delta=1.0, wr_sl=0.5, wr_h2h=0.5, volatility=0.1)
        volatile = compute_win_probability(sl_delta=1.0, wr_sl=0.5, wr_h2h=0.5, volatility=0.9)
        assert volatile < calm

    def test_matches_the_real_logistic_formula_exactly(self):
        weights = DEFAULT_WIN_PROBABILITY_WEIGHTS
        z = weights.sl_delta * 1.5 + weights.wr_sl * 0.6 + weights.wr_h2h * 0.7 - weights.volatility * 0.3
        expected = round(1.0 / (1.0 + math.exp(-weights.logistic_scale * z)), 6)
        assert compute_win_probability(1.5, 0.6, 0.7, 0.3) == expected

    def test_config_driven_weights_change_the_result(self):
        heavy_sl = WinProbabilityWeights(sl_delta=5.0, wr_sl=0.0, wr_h2h=0.0, volatility=0.0)
        light_sl = WinProbabilityWeights(sl_delta=0.01, wr_sl=0.0, wr_h2h=0.0, volatility=0.0)
        heavy_result = compute_win_probability(2.0, 0.5, 0.5, 0.5, weights=heavy_sl)
        light_result = compute_win_probability(2.0, 0.5, 0.5, 0.5, weights=light_sl)
        assert heavy_result > light_result
        assert heavy_result == pytest.approx(CLAMP_MAX, abs=1e-6)


class TestClampBehavior:
    def test_an_extreme_favorable_z_is_clamped_not_left_at_a_false_certainty(self):
        extreme_weights = WinProbabilityWeights(sl_delta=100.0, wr_sl=0.0, wr_h2h=0.0, volatility=0.0)
        result = compute_win_probability(10.0, None, None, None, weights=extreme_weights)
        assert result == CLAMP_MAX

    def test_an_extreme_unfavorable_z_is_clamped_not_left_at_a_false_certainty(self):
        extreme_weights = WinProbabilityWeights(sl_delta=100.0, wr_sl=0.0, wr_h2h=0.0, volatility=0.0)
        result = compute_win_probability(-10.0, None, None, None, weights=extreme_weights)
        assert result == CLAMP_MIN

    def test_default_clamp_bounds_match_the_documented_real_values(self):
        assert DEFAULT_WIN_PROBABILITY_WEIGHTS.clamp_min == 0.02
        assert DEFAULT_WIN_PROBABILITY_WEIGHTS.clamp_max == 0.98

    def test_a_configured_clamp_range_is_honored(self):
        tight = WinProbabilityWeights(
            sl_delta=100.0, wr_sl=0.0, wr_h2h=0.0, volatility=0.0,
            clamp_min=0.10, clamp_max=0.90,
        )
        assert compute_win_probability(10.0, None, None, None, weights=tight) == 0.90
        assert compute_win_probability(-10.0, None, None, None, weights=tight) == 0.10

    def test_a_never_overflows_on_a_pathological_configured_weight(self):
        """math.exp itself would raise OverflowError well before this --
        the model must clamp its own exponent, not just its final output."""
        pathological = WinProbabilityWeights(
            sl_delta=1e300, wr_sl=0.0, wr_h2h=0.0, volatility=0.0,
        )
        result = compute_win_probability(1e300, None, None, None, weights=pathological)
        assert result == CLAMP_MAX
