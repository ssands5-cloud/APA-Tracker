"""Tests for the pure Opponent Scouting aggregation module
(analytics/opponent_scouting.py)."""

from __future__ import annotations

import pytest

from analytics.opponent_scouting import (
    DEFAULT_OPPONENT_SCOUTING_THRESHOLDS,
    OpponentScoutingThresholds,
    summarize_opponent,
    summarize_opponents,
)


def row(opponent_pk=1, opponent_id="O1", opponent_name="Bob", opponent_team_pk=10,
        opponent_team_name="Corner Pockets", matchup_score=50, win_probability=0.5,
        format="8-Ball Open", session_name="Fall 2026"):
    return {
        "opponent_pk": opponent_pk, "opponent_id": opponent_id, "opponent_name": opponent_name,
        "opponent_team_pk": opponent_team_pk, "opponent_team_name": opponent_team_name,
        "matchup_score": matchup_score, "win_probability": win_probability,
        "format": format, "session_name": session_name,
    }


class TestSummarizeOpponent:
    def test_an_empty_rows_list_raises_a_clear_error_not_an_indexerror(self):
        with pytest.raises(ValueError, match="at least one"):
            summarize_opponent([], opponent_volatility=None)

    def test_averages_real_matchup_score_and_win_probability(self):
        rows = [
            row(matchup_score=80, win_probability=0.8),
            row(matchup_score=60, win_probability=0.6),
        ]
        entry = summarize_opponent(rows, opponent_volatility=None)
        assert entry.times_faced == 2
        assert entry.avg_matchup_score == pytest.approx(70)
        assert entry.avg_win_probability == pytest.approx(0.7)

    def test_a_missing_signal_on_one_row_is_excluded_not_treated_as_zero(self):
        rows = [
            row(matchup_score=80, win_probability=0.8),
            row(matchup_score=None, win_probability=None),
        ]
        entry = summarize_opponent(rows, opponent_volatility=None)
        assert entry.avg_matchup_score == pytest.approx(80)
        assert entry.avg_win_probability == pytest.approx(0.8)

    def test_no_usable_signal_at_all_is_none_not_zero(self):
        rows = [row(matchup_score=None, win_probability=None)]
        entry = summarize_opponent(rows, opponent_volatility=None)
        assert entry.avg_matchup_score is None
        assert entry.avg_win_probability is None

    def test_carries_real_identity_from_the_first_row(self):
        rows = [row(opponent_id="O9", opponent_name="Carol", opponent_team_name="Felt up Crew")]
        entry = summarize_opponent(rows, opponent_volatility=None)
        assert entry.opponent_id == "O9"
        assert entry.opponent_name == "Carol"
        assert entry.opponent_team_name == "Felt up Crew"

    def test_low_win_probability_flags_a_danger_matchup_with_a_real_reason(self):
        rows = [row(win_probability=0.20)]
        entry = summarize_opponent(rows, opponent_volatility=None)
        assert entry.is_danger_matchup is True
        assert any("win probability" in reason for reason in entry.danger_reasons)

    def test_high_opponent_volatility_flags_a_danger_matchup_with_a_real_reason(self):
        rows = [row(win_probability=0.8)]
        entry = summarize_opponent(rows, opponent_volatility=0.9)
        assert entry.is_danger_matchup is True
        assert any("volatility" in reason for reason in entry.danger_reasons)

    def test_a_safe_opponent_is_not_flagged(self):
        rows = [row(win_probability=0.8)]
        entry = summarize_opponent(rows, opponent_volatility=0.1)
        assert entry.is_danger_matchup is False
        assert entry.danger_reasons == []

    def test_missing_win_probability_and_volatility_is_never_flagged_as_danger(self):
        """No evidence is not the same as dangerous -- an opponent with no
        real signal at all must never be flagged."""
        rows = [row(matchup_score=None, win_probability=None)]
        entry = summarize_opponent(rows, opponent_volatility=None)
        assert entry.is_danger_matchup is False

    def test_custom_thresholds_change_the_flag(self):
        rows = [row(win_probability=0.45)]
        lenient = OpponentScoutingThresholds(win_probability_danger=0.30)
        strict = OpponentScoutingThresholds(win_probability_danger=0.50)
        assert summarize_opponent(rows, None, thresholds=lenient).is_danger_matchup is False
        assert summarize_opponent(rows, None, thresholds=strict).is_danger_matchup is True


class TestSummarizeOpponents:
    def test_groups_rows_by_real_opponent_identity(self):
        rows = [
            row(opponent_pk=1, opponent_name="Bob", win_probability=0.6),
            row(opponent_pk=1, opponent_name="Bob", win_probability=0.4),
            row(opponent_pk=2, opponent_name="Carol", win_probability=0.9),
        ]
        entries = summarize_opponents(rows, trends={})
        assert len(entries) == 2
        bob = next(e for e in entries if e.opponent_name == "Bob")
        assert bob.times_faced == 2
        assert bob.avg_win_probability == pytest.approx(0.5)

    def test_looks_up_the_opponents_own_volatility_in_the_rows_real_format_session_context(self):
        rows = [row(opponent_pk=1, format="8-Ball Open", session_name="Fall 2026")]
        trends = {(1, "8-ball", "Fall 2026"): {"volatility": 0.77}}
        [entry] = summarize_opponents(rows, trends)
        assert entry.opponent_volatility == pytest.approx(0.77)

    def test_a_context_mismatch_leaves_volatility_absent_not_a_wrong_value(self):
        rows = [row(opponent_pk=1, format="9-Ball Open", session_name="Fall 2026")]
        trends = {(1, "8-ball", "Fall 2026"): {"volatility": 0.77}}
        [entry] = summarize_opponents(rows, trends)
        assert entry.opponent_volatility is None

    def test_sorted_by_team_then_name_for_deterministic_output(self):
        rows = [
            row(opponent_pk=1, opponent_name="Zoe", opponent_team_name="Z Team"),
            row(opponent_pk=2, opponent_name="Adam", opponent_team_name="A Team"),
        ]
        entries = summarize_opponents(rows, trends={})
        assert [e.opponent_name for e in entries] == ["Adam", "Zoe"]

    def test_empty_input_is_an_empty_list(self):
        assert summarize_opponents([], trends={}) == []

    def test_default_thresholds_match_the_documented_real_values(self):
        assert DEFAULT_OPPONENT_SCOUTING_THRESHOLDS.win_probability_danger == 0.40
        assert DEFAULT_OPPONENT_SCOUTING_THRESHOLDS.volatility_danger == 0.50
