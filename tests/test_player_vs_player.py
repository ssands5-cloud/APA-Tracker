"""Tests for analytics/player_vs_player.py.

Real inputs only: PlayerHeadToHead rows built the same way
tests/test_head_to_head.py already does. Every number checked here is
either a direct reuse of an already-tested analytics.head_to_head/
analytics.matchups function, or a real, simple aggregation over it --
this module invents no new formula, so these tests hold it to that, not
to a new spec.
"""

from __future__ import annotations

from analytics.head_to_head import (
    average_skill_level_delta,
    skill_level_trend,
    skill_only_win_probability,
    win_loss,
    win_probability,
)
from analytics.matchups import reliability_weight
from analytics.player_vs_player import DEFAULT_RECENT_GAMES, recent_trend, summarize
from database.models import PlayerHeadToHead


def game(result="W", own=5, opp=4, match_id=1, points=2.0, balls=None,
         fmt="8-Ball Open", session="Fall 2026"):
    return PlayerHeadToHead(
        player_id=1, opponent_id=2, match_id=match_id, result=result,
        own_skill_level=own, opponent_skill_level=opp,
        points_earned=points, nine_ball_points=balls,
        format=fmt, session_name=session,
    )


class TestDirectHistory:
    def test_total_games_wins_and_losses_match_the_real_record(self):
        rows = [game("W", match_id=1), game("W", match_id=2), game("L", match_id=3)]
        summary = summarize(rows, "P1", "P2")

        assert summary.total_games == 3
        assert summary.wins == 2
        assert summary.losses == 1

    def test_an_unrecognized_result_does_not_count_as_a_game(self):
        rows = [game("W", match_id=1), game(None, match_id=2)]
        summary = summarize(rows, "P1", "P2")

        assert summary.total_games == 1
        assert summary.wins == 1
        assert summary.losses == 0

    def test_no_history_at_all_is_an_honest_zero_not_a_guess(self):
        summary = summarize([], "P1", "P2")

        assert summary.total_games == 0
        assert summary.wins == 0
        assert summary.losses == 0
        assert summary.modeled_win_probability is None
        assert summary.skill_only_probability is None
        assert summary.next_match_projection is None
        assert summary.games == ()

    def test_games_are_carried_through_in_the_given_chronological_order(self):
        rows = [game("W", match_id=1), game("L", match_id=2), game("W", match_id=3)]
        summary = summarize(rows, "P1", "P2")

        assert [g.match_id for g in summary.games] == [1, 2, 3]
        assert [g.result for g in summary.games] == ["W", "L", "W"]

    def test_match_dates_are_resolved_from_the_caller_supplied_map(self):
        rows = [game(match_id=1), game(match_id=2)]
        summary = summarize(rows, "P1", "P2", match_dates={1: "2026-08-01", 2: "2026-08-15"})

        assert [g.match_date for g in summary.games] == ["2026-08-01", "2026-08-15"]

    def test_an_unmapped_match_id_is_none_not_a_guessed_date(self):
        rows = [game(match_id=1)]
        summary = summarize(rows, "P1", "P2", match_dates={})

        assert summary.games[0].match_date is None


class TestReliabilityWeighting:
    def test_matches_the_real_shared_curve(self):
        rows = [game("W", match_id=i) for i in range(4)]
        summary = summarize(rows, "P1", "P2")

        assert summary.reliability == reliability_weight(4)

    def test_zero_games_has_zero_reliability(self):
        assert summarize([], "P1", "P2").reliability == reliability_weight(0) == 0.0


class TestSkillGapProbability:
    def test_matches_the_shared_production_function_on_the_last_real_game(self):
        rows = [game(own=5, opp=4, match_id=1), game(own=6, opp=3, match_id=2)]
        summary = summarize(rows, "P1", "P2")

        assert summary.skill_only_probability == skill_only_win_probability(6, 3)

    def test_missing_skill_levels_on_the_last_game_is_unscoreable(self):
        rows = [game(own=None, opp=None, match_id=1)]
        summary = summarize(rows, "P1", "P2")

        assert summary.skill_only_probability is None


class TestModeledWinProbability:
    def test_matches_the_shared_production_function_exactly(self):
        rows = [game("W", match_id=1), game("L", match_id=2), game("W", match_id=3)]
        summary = summarize(rows, "P1", "P2")

        assert summary.modeled_win_probability == win_probability(rows)

    def test_next_match_projection_is_the_same_value_not_a_second_computation(self):
        rows = [game("W", match_id=1)]
        summary = summarize(rows, "P1", "P2")

        assert summary.next_match_projection == summary.modeled_win_probability


class TestTrend:
    def test_trend_matches_the_shared_first_vs_last_function(self):
        rows = [game(own=4, match_id=1), game(own=6, match_id=2)]
        summary = summarize(rows, "P1", "P2")

        assert summary.trend == skill_level_trend(rows)

    def test_recent_trend_is_scoped_to_the_last_k_games_only(self):
        # An early dip that fully recovers within the recent window should
        # read "stable" for the recent window even though the whole-history
        # trend function would see the same first-vs-last shape differently
        # if the early games dominated.
        rows = (
            [game(own=7, match_id=0)]
            + [game(own=4, match_id=i) for i in range(1, 5)]
            + [game(own=4, match_id=5)]
        )
        assert recent_trend(rows, k=2) == "stable"

    def test_default_recent_window_is_five(self):
        assert DEFAULT_RECENT_GAMES == 5

    def test_fewer_games_than_the_window_uses_all_of_them(self):
        rows = [game(own=4, match_id=1), game(own=6, match_id=2)]
        assert recent_trend(rows, k=5) == skill_level_trend(rows)

    def test_no_games_is_no_data(self):
        assert recent_trend([]) == "no data"


class TestSkillLevelDeltaPassthrough:
    def test_matches_the_shared_production_function(self):
        rows = [game(own=5, opp=4, match_id=1), game(own=6, opp=3, match_id=2)]
        summary = summarize(rows, "P1", "P2")

        assert summary.sl_delta == average_skill_level_delta(rows)


class TestFixtureRegression:
    """Pinned against hand-verified real values -- a future accidental
    change to the shared formulas should fail this test even if nothing in
    this module's own logic changed."""

    def test_the_1_0_5v4_example_is_pinned(self):
        summary = summarize([game("W", own=5, opp=4, match_id=1)], "P1", "P2")

        assert round(summary.modeled_win_probability, 3) == 0.639
        assert round(summary.skill_only_probability, 3) == 0.599
        assert summary.wins == 1
        assert summary.losses == 0
        assert summary.reliability == 0.25
