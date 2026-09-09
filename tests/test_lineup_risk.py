"""Tests for the pure Lineup Risk Scoring module (analytics/lineup_risk.py).

Fixtures are lightweight stand-ins with exactly the four real attributes
the module's own RiskAssignment Protocol needs -- the real caller passes
analytics.lineup_optimizer.AssignmentEntry instances, which satisfy the
same shape structurally (see tests/test_build_lineups.py for that real,
end-to-end wiring).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from analytics.lineup_risk import (
    DANGER_THRESHOLD,
    DEFAULT_LINEUP_RISK_WEIGHTS,
    LineupRiskWeights,
    anchor_stability_score,
    compute_lineup_risk,
    danger_matchup_count,
    lineup_volatility_load,
    upset_risk_index,
)


@dataclass
class FakeAssignment:
    player_name: str
    modeled_win_probability: Optional[float] = 0.5
    volatility: Optional[float] = 0.2
    risk_factor: Optional[float] = 0.3


class TestUpsetRiskIndex:
    def test_sums_one_minus_win_probability_times_volatility(self):
        assignments = [
            FakeAssignment("A", modeled_win_probability=0.8, volatility=0.5),
            FakeAssignment("B", modeled_win_probability=0.2, volatility=0.5),
        ]
        # (1-0.8)*0.5 + (1-0.2)*0.5 = 0.1 + 0.4
        assert upset_risk_index(assignments) == pytest.approx(0.5)

    def test_a_calm_favorite_contributes_almost_nothing(self):
        calm = [FakeAssignment("A", modeled_win_probability=0.95, volatility=0.01)]
        swingy = [FakeAssignment("B", modeled_win_probability=0.30, volatility=0.90)]
        assert upset_risk_index(calm) < upset_risk_index(swingy)

    def test_missing_volatility_contributes_zero_not_a_guess(self):
        assignments = [FakeAssignment("A", modeled_win_probability=0.2, volatility=None)]
        assert upset_risk_index(assignments) == 0.0

    def test_an_empty_lineup_is_zero(self):
        assert upset_risk_index([]) == 0.0


class TestAnchorStabilityScore:
    def test_the_anchor_is_the_highest_win_probability_player(self):
        assignments = [
            FakeAssignment("Weak", modeled_win_probability=0.30, volatility=0.10),
            FakeAssignment("Strong", modeled_win_probability=0.90, volatility=0.10),
            FakeAssignment("Middle", modeled_win_probability=0.60, volatility=0.10),
        ]
        score, name = anchor_stability_score(assignments)
        assert name == "Strong"
        assert score == pytest.approx(0.80)  # 0.90 - 0.10

    def test_a_volatile_anchor_scores_lower_than_a_calm_one(self):
        calm = [FakeAssignment("A", modeled_win_probability=0.9, volatility=0.05)]
        volatile = [FakeAssignment("A", modeled_win_probability=0.9, volatility=0.60)]
        assert anchor_stability_score(calm)[0] > anchor_stability_score(volatile)[0]

    def test_ties_break_on_lower_risk_then_name_for_determinism(self):
        assignments = [
            FakeAssignment("Zoe", modeled_win_probability=0.7, risk_factor=0.1),
            FakeAssignment("Adam", modeled_win_probability=0.7, risk_factor=0.9),
        ]
        # Same win probability -- the calmer player (lower risk_factor) anchors.
        assert anchor_stability_score(assignments)[1] == "Zoe"

    def test_a_missing_risk_factor_sorts_last_among_tied_win_probabilities(self):
        assignments = [
            FakeAssignment("NoRiskData", modeled_win_probability=0.7, risk_factor=None),
            FakeAssignment("KnownCalm", modeled_win_probability=0.7, risk_factor=0.2),
        ]
        # A real, known risk_factor beats an unknown one on the same tie --
        # never assumed to be equal to or better than real evidence.
        assert anchor_stability_score(assignments)[1] == "KnownCalm"

    def test_a_full_tie_breaks_lexicographically(self):
        assignments = [
            FakeAssignment("Zoe", modeled_win_probability=0.7, risk_factor=0.5),
            FakeAssignment("Adam", modeled_win_probability=0.7, risk_factor=0.5),
        ]
        assert anchor_stability_score(assignments)[1] == "Adam"

    def test_an_empty_lineup_has_no_anchor_rather_than_a_guessed_one(self):
        assert anchor_stability_score([]) == (None, None)


class TestLineupVolatilityLoad:
    def test_sums_every_players_real_volatility(self):
        assignments = [
            FakeAssignment("A", volatility=0.10),
            FakeAssignment("B", volatility=0.25),
            FakeAssignment("C", volatility=0.05),
        ]
        assert lineup_volatility_load(assignments) == pytest.approx(0.40)

    def test_missing_volatility_contributes_zero(self):
        assignments = [FakeAssignment("A", volatility=None), FakeAssignment("B", volatility=0.3)]
        assert lineup_volatility_load(assignments) == pytest.approx(0.3)

    def test_an_empty_lineup_is_zero(self):
        assert lineup_volatility_load([]) == 0.0


class TestDangerMatchupCount:
    def test_counts_pairings_below_the_threshold(self):
        assignments = [
            FakeAssignment("A", modeled_win_probability=0.10),
            FakeAssignment("B", modeled_win_probability=0.39),
            FakeAssignment("C", modeled_win_probability=0.41),
            FakeAssignment("D", modeled_win_probability=0.90),
        ]
        assert danger_matchup_count(assignments) == 2

    def test_the_threshold_is_strict_not_inclusive(self):
        exactly_at = [FakeAssignment("A", modeled_win_probability=DANGER_THRESHOLD)]
        assert danger_matchup_count(exactly_at) == 0

    def test_a_configured_threshold_is_honored(self):
        assignments = [FakeAssignment("A", modeled_win_probability=0.55)]
        assert danger_matchup_count(assignments, threshold=0.40) == 0
        assert danger_matchup_count(assignments, threshold=0.60) == 1

    def test_an_empty_lineup_is_zero(self):
        assert danger_matchup_count([]) == 0


class TestComputeLineupRisk:
    def test_bundles_every_component_and_the_combined_score(self):
        assignments = [
            FakeAssignment("Strong", modeled_win_probability=0.80, volatility=0.10),
            FakeAssignment("Weak", modeled_win_probability=0.30, volatility=0.40),
        ]
        metrics = compute_lineup_risk(assignments)

        expected_uri = (1 - 0.80) * 0.10 + (1 - 0.30) * 0.40
        expected_lvl = 0.10 + 0.40
        expected_ass = 0.80 - 0.10
        weights = DEFAULT_LINEUP_RISK_WEIGHTS
        expected_lrs = round(
            weights.upset_risk * round(expected_uri, 6)
            + weights.anchor_instability * (1 - round(expected_ass, 6))
            + weights.volatility_load * round(expected_lvl, 6)
            + weights.danger_count * 1,
            6,
        )

        assert metrics.upset_risk_index == pytest.approx(expected_uri)
        assert metrics.lineup_volatility_load == pytest.approx(expected_lvl)
        assert metrics.anchor_stability_score == pytest.approx(expected_ass)
        assert metrics.anchor_player_name == "Strong"
        assert metrics.danger_matchup_count == 1
        assert metrics.lineup_risk_score == pytest.approx(expected_lrs)

    def test_a_dangerous_lineup_scores_higher_than_a_safe_one(self):
        safe = [
            FakeAssignment("A", modeled_win_probability=0.85, volatility=0.05),
            FakeAssignment("B", modeled_win_probability=0.80, volatility=0.05),
        ]
        dangerous = [
            FakeAssignment("C", modeled_win_probability=0.20, volatility=0.70),
            FakeAssignment("D", modeled_win_probability=0.25, volatility=0.65),
        ]
        assert compute_lineup_risk(dangerous).lineup_risk_score > compute_lineup_risk(safe).lineup_risk_score

    def test_custom_weights_change_the_combined_score(self):
        assignments = [FakeAssignment("A", modeled_win_probability=0.3, volatility=0.5)]
        upset_only = LineupRiskWeights(
            upset_risk=1.0, anchor_instability=0.0, volatility_load=0.0, danger_count=0.0,
        )
        danger_only = LineupRiskWeights(
            upset_risk=0.0, anchor_instability=0.0, volatility_load=0.0, danger_count=1.0,
        )
        assert compute_lineup_risk(assignments, weights=upset_only).lineup_risk_score == pytest.approx(0.35)
        assert compute_lineup_risk(assignments, weights=danger_only).lineup_risk_score == pytest.approx(1.0)

    def test_a_configured_danger_threshold_reaches_the_count(self):
        assignments = [FakeAssignment("A", modeled_win_probability=0.5, volatility=0.0)]
        strict = LineupRiskWeights(danger_threshold=0.60)
        assert compute_lineup_risk(assignments).danger_matchup_count == 0
        assert compute_lineup_risk(assignments, weights=strict).danger_matchup_count == 1

    def test_an_empty_lineup_is_all_zero_and_has_no_anchor(self):
        metrics = compute_lineup_risk([])
        assert metrics.upset_risk_index == 0.0
        assert metrics.lineup_volatility_load == 0.0
        assert metrics.danger_matchup_count == 0
        assert metrics.anchor_stability_score is None
        assert metrics.anchor_player_name is None
        # (1 - ASS) can't propagate None through a real scalar; an absent
        # anchor contributes 0 like every other empty-lineup component.
        assert metrics.lineup_risk_score == pytest.approx(
            DEFAULT_LINEUP_RISK_WEIGHTS.anchor_instability
        )
