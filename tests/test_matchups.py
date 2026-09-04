"""Tests for analytics.matchups -- the Matchup Advantage Engine's scoring.

Operates on plain PlayerHeadToHead rows (built directly, not through
ingest -- pure functions over an already-fetched, chronologically ordered
list) so the scoring math is tested independently of the database/scraper
plumbing covered elsewhere (tests/test_graphql_scraper.py::TestHeadToHeadRows,
tests/test_ingest.py::TestIngestHeadToHead).
"""

from __future__ import annotations

from analytics.matchups import (
    FULL_CONFIDENCE_GAMES,
    average_opponent_skill_level,
    average_points_earned,
    confidence_score,
    head_to_head_win_rate,
    matchup_score,
    opponent_skill_modifier,
    sample_size_weight,
    trend_modifier,
    volatility_penalty,
    weighted_win_rate,
)
from database.models import PlayerHeadToHead


def _game(result, points=None, opponent_skill_level=None, own_skill_level=None):
    return PlayerHeadToHead(
        player_id=1, opponent_id=2, match_id=1,
        result=result, points_earned=points,
        opponent_skill_level=opponent_skill_level, own_skill_level=own_skill_level,
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

    def test_is_unweighted_unlike_weighted_win_rate(self):
        """The exported "Win Rate" column stays the plain, real record --
        order doesn't change it, unlike weighted_win_rate()."""
        assert head_to_head_win_rate([_game("W"), _game("L")]) == 0.5
        assert head_to_head_win_rate([_game("L"), _game("W")]) == 0.5


class TestWeightedWinRate:
    """Recency bias: a more recent game counts slightly more than an
    older one. `rows` must be chronological, oldest first."""

    def test_no_history_is_zero(self):
        assert weighted_win_rate([]) == 0.0

    def test_a_single_game_is_unaffected_by_weighting(self):
        assert weighted_win_rate([_game("W")]) == 1.0
        assert weighted_win_rate([_game("L")]) == 0.0

    def test_a_uniform_record_is_unaffected_by_weighting(self):
        """All wins (or all losses) -- recency can't move a rate that's
        already the same in every game."""
        assert weighted_win_rate([_game("W"), _game("W"), _game("W")]) == 1.0

    def test_a_recent_win_after_an_older_loss_scores_above_the_flat_average(self):
        """[loss, win], oldest first -- the win is more recent and counts
        for more, so this must beat the unweighted 0.5 the same two games
        give via head_to_head_win_rate()."""
        rows = [_game("L"), _game("W")]
        assert weighted_win_rate(rows) > head_to_head_win_rate(rows) == 0.5

    def test_a_recent_loss_after_an_older_win_scores_below_the_flat_average(self):
        """[win, loss], oldest first -- the loss is more recent."""
        rate = weighted_win_rate([_game("W"), _game("L")])
        assert rate < 0.5

    def test_order_is_what_distinguishes_the_two_cases(self):
        """Same two games, opposite chronological order -- different
        weighted rates proves this is really reading recency, not just
        counting wins."""
        recent_win = weighted_win_rate([_game("L"), _game("W")])
        recent_loss = weighted_win_rate([_game("W"), _game("L")])
        assert recent_win > recent_loss


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


class TestOpponentSkillModifier:
    """Bonus for wins against higher-skill opponents, penalty for wins
    against lower-skill ones -- scoped to WON games only."""

    def test_no_wins_at_all_is_no_modifier(self):
        rows = [_game("L", opponent_skill_level=7, own_skill_level=5)]
        assert opponent_skill_modifier(rows) == 0.0

    def test_a_win_with_no_skill_levels_recorded_is_no_modifier(self):
        assert opponent_skill_modifier([_game("W")]) == 0.0

    def test_beating_a_higher_skill_opponent_is_a_bonus(self):
        rows = [_game("W", opponent_skill_level=7, own_skill_level=5)]  # +2 gap
        assert opponent_skill_modifier(rows) == 4.0  # 2 * 2

    def test_beating_a_lower_skill_opponent_is_a_penalty(self):
        rows = [_game("W", opponent_skill_level=3, own_skill_level=5)]  # -2 gap
        assert opponent_skill_modifier(rows) == -4.0

    def test_losses_dont_affect_the_modifier_even_with_a_big_skill_gap(self):
        """This feature is explicitly scoped to wins only -- see the
        function's own docstring for why."""
        rows = [_game("L", opponent_skill_level=9, own_skill_level=2)]
        assert opponent_skill_modifier(rows) == 0.0

    def test_is_capped_so_one_lopsided_win_cant_dominate(self):
        rows = [_game("W", opponent_skill_level=9, own_skill_level=1)]  # +8 gap -> would be 16
        assert opponent_skill_modifier(rows) == 10.0

    def test_is_floored_the_same_way_on_the_penalty_side(self):
        rows = [_game("W", opponent_skill_level=1, own_skill_level=9)]  # -8 gap -> would be -16
        assert opponent_skill_modifier(rows) == -10.0

    def test_averages_across_multiple_wins(self):
        rows = [
            _game("W", opponent_skill_level=7, own_skill_level=5),  # +2
            _game("W", opponent_skill_level=5, own_skill_level=5),  # 0
        ]
        assert opponent_skill_modifier(rows) == 2.0  # avg gap 1 * 2


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


class TestSampleSizeWeight:
    def test_no_games_is_zero_weight(self):
        assert sample_size_weight(0) == 0.0

    def test_one_game_is_a_small_fraction_of_full_weight(self):
        assert sample_size_weight(1) == 1 / FULL_CONFIDENCE_GAMES

    def test_full_confidence_games_is_full_weight(self):
        assert sample_size_weight(FULL_CONFIDENCE_GAMES) == 1.0

    def test_more_than_full_confidence_games_is_still_capped_at_one(self):
        assert sample_size_weight(FULL_CONFIDENCE_GAMES * 3) == 1.0

    def test_weight_scales_linearly_below_the_cap(self):
        assert sample_size_weight(FULL_CONFIDENCE_GAMES // 2) == 0.5


class TestConfidenceScore:
    def test_no_history_is_not_automatically_zero(self):
        """Zero games contributes 0 to the sample component, but the
        volatility/stability components are independent of sample size --
        confidence isn't purely about sample size, so this isn't 0."""
        score = confidence_score([], "no data", 0)
        assert score > 0
        assert score < confidence_score([_game("W")] * FULL_CONFIDENCE_GAMES, "stable", 0)

    def test_full_sample_stable_trend_no_volatility_is_high_confidence(self):
        rows = [_game("W")] * FULL_CONFIDENCE_GAMES
        assert confidence_score(rows, "stable", 0) == 100

    def test_a_moving_trend_costs_confidence_even_with_a_full_sample(self):
        rows = [_game("W")] * FULL_CONFIDENCE_GAMES
        stable = confidence_score(rows, "stable", 0)
        moving = confidence_score(rows, "up", 0)
        assert moving < stable

    def test_volatility_costs_confidence(self):
        rows = [_game("W")] * FULL_CONFIDENCE_GAMES
        calm = confidence_score(rows, "stable", 0)
        volatile = confidence_score(rows, "stable", 5)
        assert volatile < calm

    def test_a_small_sample_costs_confidence_even_with_a_stable_trend(self):
        one_game = confidence_score([_game("W")], "stable", 0)
        full_sample = confidence_score([_game("W")] * FULL_CONFIDENCE_GAMES, "stable", 0)
        assert one_game < full_sample


class TestMatchupScore:
    def test_no_history_is_neutral_fifty_not_a_guess(self):
        assert matchup_score([], "no data", 0) == 50

    def test_a_full_sample_perfect_record_with_no_other_modifiers(self):
        rows = [_game("W")] * FULL_CONFIDENCE_GAMES
        assert matchup_score(rows, "stable", 0) == 90

    def test_a_full_sample_winless_record_with_no_other_modifiers(self):
        rows = [_game("L")] * FULL_CONFIDENCE_GAMES
        assert matchup_score(rows, "stable", 0) == 10

    def test_a_one_game_record_is_pulled_toward_neutral_not_to_the_extreme(self):
        """The actual fix for the reported bug: a 1-0 record must NOT
        score the same as a 10-0 one."""
        one_win = matchup_score([_game("W")], "stable", 0)
        ten_wins = matchup_score([_game("W")] * FULL_CONFIDENCE_GAMES, "stable", 0)
        assert one_win != ten_wins
        assert 50 < one_win < ten_wins

    def test_a_one_loss_record_is_pulled_toward_neutral_not_to_the_extreme(self):
        one_loss = matchup_score([_game("L")], "stable", 0)
        ten_losses = matchup_score([_game("L")] * FULL_CONFIDENCE_GAMES, "stable", 0)
        assert one_loss != ten_losses
        assert ten_losses < one_loss < 50

    def test_trend_and_volatility_are_not_damped_by_a_small_sample(self):
        """Trend/volatility describe the player's current form in general,
        not this specific pairing -- a 1-game sample still gets the full
        +/-5 trend modifier and the full volatility penalty."""
        rows = [_game("W"), _game("L")]  # net-neutral win rate contribution
        stable = matchup_score(rows, "stable", 0)
        up = matchup_score(rows, "up", 0)
        down = matchup_score(rows, "down", 0)
        assert up - stable == 5
        assert stable - down == 5

    def test_opponent_skill_modifier_is_damped_by_sample_size_like_win_rate(self):
        """The skill-level bonus IS scoped by sample size, same as the win
        rate swing -- both come from the same small pool of evidence."""
        one_game = [_game("W", opponent_skill_level=9, own_skill_level=1)]  # capped +10
        full_sample = [_game("W", opponent_skill_level=9, own_skill_level=1)] * FULL_CONFIDENCE_GAMES
        assert matchup_score(one_game, "stable", 0) < matchup_score(full_sample, "stable", 0)

    def test_score_is_clamped_at_zero_not_negative(self):
        rows = [_game("L")] * FULL_CONFIDENCE_GAMES
        assert matchup_score(rows, "down", 50) == 0

    def test_score_is_clamped_at_a_hundred_not_above(self):
        rows = [_game("W", opponent_skill_level=9, own_skill_level=1)] * FULL_CONFIDENCE_GAMES
        assert matchup_score(rows, "up", 0) == 100
