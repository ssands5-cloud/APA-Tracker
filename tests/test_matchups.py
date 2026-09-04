"""Tests for analytics.matchups -- the Matchup Advantage Engine's scoring.

Operates on plain PlayerHeadToHead rows (built directly, not through
ingest -- pure functions over an already-fetched list) so the scoring math
is tested independently of the database/scraper plumbing covered elsewhere
(tests/test_graphql_scraper.py::TestHeadToHeadRows,
tests/test_ingest.py::TestIngestHeadToHead).
"""

from __future__ import annotations

from analytics.matchups import (
    average_opponent_skill_level,
    average_points_earned,
    head_to_head_win_rate,
    matchup_score,
    trend_modifier,
    volatility_penalty,
)
from database.models import PlayerHeadToHead


def _game(result, points=None, opponent_skill_level=None):
    return PlayerHeadToHead(
        player_id=1, opponent_id=2, match_id=1,
        result=result, points_earned=points, opponent_skill_level=opponent_skill_level,
    )


class TestHeadToHeadWinRate:
    def test_no_history_is_zero_not_none(self):
        assert head_to_head_win_rate([]) == 0.0

    def test_a_perfect_record(self):
        assert head_to_head_win_rate([_game("W"), _game("W")]) == 1.0

    def test_a_mixed_record(self):
        assert head_to_head_win_rate([_game("W"), _game("L"), _game("W"), _game("L")]) == 0.5

    def test_lowercase_result_still_counts(self):
        assert head_to_head_win_rate([_game("w")]) == 1.0


class TestAveragePointsEarned:
    def test_no_rows_is_none_not_zero(self):
        """A real 0 must stay distinguishable from "we don't know"."""
        assert average_points_earned([]) is None

    def test_averages_the_real_values(self):
        assert average_points_earned([_game("W", points=6), _game("L", points=3)]) == 4.5

    def test_rows_with_no_points_value_are_skipped_not_zero(self):
        assert average_points_earned([_game("W", points=6), _game("L", points=None)]) == 6.0


class TestAverageOpponentSkillLevel:
    def test_no_rows_is_none(self):
        assert average_opponent_skill_level([]) is None

    def test_averages_the_real_values(self):
        rows = [_game("W", opponent_skill_level=5), _game("L", opponent_skill_level=7)]
        assert average_opponent_skill_level(rows) == 6.0


class TestTrendModifier:
    def test_up_is_positive(self):
        assert trend_modifier("up") == 5

    def test_down_is_negative(self):
        assert trend_modifier("down") == -5

    def test_stable_is_neutral(self):
        assert trend_modifier("stable") == 0

    def test_no_data_is_neutral(self):
        assert trend_modifier("no data") == 0


class TestVolatilityPenalty:
    def test_zero_volatility_is_no_penalty(self):
        assert volatility_penalty(0) == 0

    def test_scales_with_changes(self):
        assert volatility_penalty(2) == 6

    def test_caps_so_one_wild_player_cant_zero_the_score_alone(self):
        assert volatility_penalty(50) == 15


class TestMatchupScore:
    def test_no_history_is_neutral_fifty_not_a_guess(self):
        assert matchup_score([], "no data", 0) == 50

    def test_a_perfect_record_with_no_modifiers(self):
        assert matchup_score([_game("W"), _game("W")], "stable", 0) == 90

    def test_a_winless_record_with_no_modifiers(self):
        assert matchup_score([_game("L"), _game("L")], "stable", 0) == 10

    def test_an_even_record_with_no_modifiers_is_the_fifty_baseline(self):
        assert matchup_score([_game("W"), _game("L")], "stable", 0) == 50

    def test_trend_and_volatility_shift_an_even_record(self):
        rows = [_game("W"), _game("L")]
        assert matchup_score(rows, "up", 0) == 55
        assert matchup_score(rows, "down", 0) == 45
        assert matchup_score(rows, "stable", 2) == 44  # 50 - volatility_penalty(2)

    def test_score_is_clamped_at_zero_not_negative(self):
        """A winless record + a down trend + heavy volatility would go
        negative unclamped (10 - 5 - 15 = -10) -- must floor at 0."""
        rows = [_game("L"), _game("L")]
        assert matchup_score(rows, "down", 50) == 0

    def test_a_perfect_record_with_a_positive_trend_stays_within_bounds(self):
        rows = [_game("W"), _game("W")]
        score = matchup_score(rows, "up", 0)
        assert 0 <= score <= 100
        assert score == 95  # 50 + 40 (win rate) + 5 (trend) - 0 (volatility)
