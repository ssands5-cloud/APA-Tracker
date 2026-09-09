"""Tests for the pure Season Projection module (analytics/season_projection.py)."""

from __future__ import annotations

import pytest

from analytics.season_projection import (
    log5_win_probability,
    project_remaining_schedule,
    team_volatility_curve,
    upset_likelihood,
    win_rate,
)


class TestWinRate:
    def test_a_real_record_computes_the_real_rate(self):
        assert win_rate(6, 2) == pytest.approx(0.75)

    def test_no_decided_games_is_none_not_zero(self):
        assert win_rate(0, 0) is None

    def test_either_missing_value_is_none(self):
        assert win_rate(None, 2) is None
        assert win_rate(6, None) is None


class TestLog5WinProbability:
    def test_equal_real_win_rates_is_an_even_match(self):
        assert log5_win_probability(0.5, 0.5) == pytest.approx(0.5)

    def test_a_stronger_team_is_favored(self):
        assert log5_win_probability(0.8, 0.3) > 0.5

    def test_a_weaker_team_is_the_underdog(self):
        assert log5_win_probability(0.3, 0.8) < 0.5

    def test_symmetric_for_the_two_sides(self):
        p_a = log5_win_probability(0.7, 0.4)
        p_b = log5_win_probability(0.4, 0.7)
        assert p_a == pytest.approx(1.0 - p_b)

    def test_missing_opponent_rate_falls_back_to_our_own_rate(self):
        assert log5_win_probability(0.65, None) == pytest.approx(0.65)

    def test_missing_our_rate_falls_back_to_one_minus_their_rate(self):
        assert log5_win_probability(None, 0.65) == pytest.approx(0.35)

    def test_both_missing_is_none_not_a_guess(self):
        assert log5_win_probability(None, None) is None

    def test_both_undefeated_is_an_even_half_not_a_crash(self):
        assert log5_win_probability(1.0, 1.0) == pytest.approx(0.5)

    def test_both_winless_is_an_even_half_not_a_crash(self):
        assert log5_win_probability(0.0, 0.0) == pytest.approx(0.5)


class TestUpsetLikelihood:
    def test_an_even_match_has_the_highest_real_upset_likelihood(self):
        assert upset_likelihood(0.5) == pytest.approx(0.5)

    def test_a_heavy_favorite_has_low_upset_likelihood(self):
        assert upset_likelihood(0.95) == pytest.approx(0.05)

    def test_symmetric_regardless_of_which_side_is_favored(self):
        assert upset_likelihood(0.2) == upset_likelihood(0.8)

    def test_missing_probability_is_none(self):
        assert upset_likelihood(None) is None


def remaining_match(match_id="M1", opponent_team_id="T2", opponent_team_name="Corner Pockets", week=5):
    return {
        "match_id": match_id, "opponent_team_id": opponent_team_id,
        "opponent_team_name": opponent_team_name, "week": week,
    }


class TestProjectRemainingSchedule:
    def test_expected_wins_and_losses_sum_the_real_per_match_probabilities(self):
        matches = [remaining_match("M1", "T2"), remaining_match("M2", "T3")]
        projection = project_remaining_schedule(
            matches, our_win_rate=0.6, opponent_win_rates={"T2": 0.4, "T3": 0.6},
        )
        assert len(projection.matches) == 2
        expected_total = sum(p.win_probability for p in projection.matches)
        assert projection.expected_wins == pytest.approx(expected_total)
        assert projection.expected_wins + projection.expected_losses == pytest.approx(2.0)

    def test_an_unknown_opponent_still_gets_a_real_projection_via_our_own_rate(self):
        matches = [remaining_match("M1", "T9")]
        projection = project_remaining_schedule(matches, our_win_rate=0.7, opponent_win_rates={})
        assert projection.matches[0].win_probability == pytest.approx(0.7)

    def test_no_real_win_rate_at_all_still_lists_the_match_but_contributes_nothing(self):
        matches = [remaining_match("M1", "T9")]
        projection = project_remaining_schedule(matches, our_win_rate=None, opponent_win_rates={})
        assert len(projection.matches) == 1
        assert projection.matches[0].win_probability is None
        assert projection.expected_wins == 0.0
        assert projection.expected_losses == 0.0
        assert projection.high_upset_risk_matches == []

    def test_high_upset_risk_matches_are_flagged_by_the_real_threshold(self):
        matches = [remaining_match("M1", "T2"), remaining_match("M2", "T3")]
        projection = project_remaining_schedule(
            matches, our_win_rate=0.5, opponent_win_rates={"T2": 0.5, "T3": 0.95},
            upset_risk_threshold=0.40,
        )
        flagged_ids = {p.match_id for p in projection.high_upset_risk_matches}
        assert "M1" in flagged_ids  # even match -> upset_likelihood 0.5, above threshold
        assert "M2" not in flagged_ids  # lopsided match -> low upset likelihood

    def test_empty_schedule_is_a_real_zero_projection(self):
        projection = project_remaining_schedule([], our_win_rate=0.6, opponent_win_rates={})
        assert projection.matches == []
        assert projection.expected_wins == 0.0
        assert projection.expected_losses == 0.0


class TestTeamVolatilityCurve:
    def test_a_changing_real_record_produces_one_point_per_real_change(self):
        history = [
            {"captured_at": "2026-09-01", "wins": 1, "losses": 0},
            {"captured_at": "2026-09-02", "wins": 1, "losses": 0},  # duplicate, no real change
            {"captured_at": "2026-09-03", "wins": 2, "losses": 0},  # real change
            {"captured_at": "2026-09-04", "wins": 2, "losses": 1},  # real change
        ]
        curve = team_volatility_curve(history)
        assert [p.captured_at for p in curve] == ["2026-09-01", "2026-09-03", "2026-09-04"]
        assert [p.win_rate for p in curve] == [1.0, 1.0, pytest.approx(2 / 3)]

    def test_a_genuinely_flat_real_record_yields_a_single_honest_point(self):
        """Matches this project's own real data: 46 real standings
        captures across 3 real days with zero actual record changes."""
        history = [
            {"captured_at": f"2026-09-0{i}", "wins": 1, "losses": 2} for i in range(1, 6)
        ]
        curve = team_volatility_curve(history)
        assert len(curve) == 1
        assert curve[0].win_rate == pytest.approx(1 / 3)

    def test_empty_history_is_an_empty_curve(self):
        assert team_volatility_curve([]) == []
