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
    _is_win,
    average_opponent_skill_level,
    average_points_earned,
    average_skill_level_delta,
    confidence_score,
    head_to_head_win_rate,
    matchup_score,
    opponent_skill_modifier,
    recognized_results,
    reliability_weight,
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


class TestResultValidation:
    """P1-6: an unrecognized result must not silently count as a loss, and
    must not count as a game at all for win-rate/sample-size purposes."""

    def test_a_real_win_is_recognized(self):
        assert _is_win("W") is True

    def test_a_real_loss_is_recognized(self):
        assert _is_win("L") is False

    def test_lowercase_still_counts(self):
        assert _is_win("w") is True
        assert _is_win("l") is False

    def test_surrounding_whitespace_is_tolerated(self):
        assert _is_win("  W  ") is True

    def test_none_is_unrecognized(self):
        assert _is_win(None) is None

    def test_blank_string_is_unrecognized(self):
        assert _is_win("") is None
        assert _is_win("   ") is None

    def test_unknown_is_unrecognized_not_a_loss(self):
        assert _is_win("UNKNOWN") is None

    def test_an_unrelated_value_is_unrecognized(self):
        assert _is_win("T") is None  # a hypothetical tie code, not documented anywhere
        assert _is_win("garbage") is None

    def test_recognized_results_drops_unrecognized_rows(self):
        rows = [_game("W"), _game(None), _game("UNKNOWN"), _game("L"), _game("")]
        assert [r.result for r in recognized_results(rows)] == ["W", "L"]

    def test_win_rate_excludes_unrecognized_rows_from_both_numerator_and_denominator(self):
        """The regression this closes: an unrecognized result used to
        silently count as a loss (denominator went up, numerator didn't).
        3 wins and 2 unrecognized rows must read as 100%, not 60%."""
        rows = [_game("W"), _game("W"), _game("W"), _game(None), _game("UNKNOWN")]
        assert head_to_head_win_rate(rows) == 1.0

    def test_all_unrecognized_rows_is_zero_not_a_crash(self):
        rows = [_game(None), _game("UNKNOWN"), _game("")]
        assert head_to_head_win_rate(rows) == 0.0
        assert weighted_win_rate(rows) == 0.0

    def test_matchup_score_treats_all_unrecognized_rows_as_no_history(self):
        """Rows exist, but none have a usable outcome -- same neutral 50
        as genuinely no history at all, not a guess in either direction."""
        rows = [_game("UNKNOWN"), _game(None)]
        assert matchup_score(rows, "stable", 0) == 50

    def test_confidence_score_sample_size_excludes_unrecognized_rows(self):
        """A full sample of games with unrecognized results must not read
        as high confidence -- there's no real outcome evidence in it."""
        garbage = [_game("UNKNOWN")] * FULL_CONFIDENCE_GAMES
        real = [_game("W")] * FULL_CONFIDENCE_GAMES
        assert confidence_score(garbage, "stable", 0) < confidence_score(real, "stable", 0)

    def test_opponent_skill_modifier_ignores_a_win_with_an_unrecognized_result(self):
        """Can't happen from real ingested data (a row either has a
        recognized result or none), but a directly-built row with a
        malformed result and skill levels set must still not count."""
        row = _game("UNKNOWN", opponent_skill_level=9, own_skill_level=1)
        assert opponent_skill_modifier([row]) == 0.0


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


class TestAverageSkillLevelDelta:
    """P2: unweighted (opponent - own) skill gap across ALL games, wins and
    losses alike -- descriptive context, distinct from the win-scoped,
    score-weighted opponent_skill_modifier tested below."""

    def test_no_rows_is_none(self):
        assert average_skill_level_delta([]) is None

    def test_rows_missing_either_skill_level_are_skipped(self):
        rows = [_game("W", opponent_skill_level=7, own_skill_level=None)]
        assert average_skill_level_delta(rows) is None

    def test_losses_count_too_unlike_the_win_scoped_modifier(self):
        """The whole point of this metric: a losing record against tougher
        opponents still shows a real positive delta here, even though
        opponent_skill_modifier would report 0 (no wins to score)."""
        rows = [_game("L", opponent_skill_level=8, own_skill_level=5)]
        assert average_skill_level_delta(rows) == 3.0
        assert opponent_skill_modifier(rows) == 0.0

    def test_averages_across_wins_and_losses(self):
        rows = [
            _game("W", opponent_skill_level=7, own_skill_level=5),  # +2
            _game("L", opponent_skill_level=3, own_skill_level=5),  # -2
        ]
        assert average_skill_level_delta(rows) == 0.0

    def test_a_lower_skill_opponent_is_a_negative_delta(self):
        rows = [_game("W", opponent_skill_level=3, own_skill_level=6)]
        assert average_skill_level_delta(rows) == -3.0


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


class TestReliabilityWeight:
    """P2: n / (n + 3), applied only to the H2H win-rate swing -- distinct
    from sample_size_weight, which still governs the opponent-skill swing
    and confidence_score's sample component (see TestSampleSizeWeight)."""

    def test_no_games_is_zero_weight(self):
        assert reliability_weight(0) == 0.0

    def test_matches_the_n_over_n_plus_three_formula(self):
        assert reliability_weight(3) == 0.5
        assert reliability_weight(7) == 0.7

    def test_never_fully_reaches_one_unlike_sample_size_weight(self):
        """Distinguishes this from sample_size_weight, which hard-caps at
        1.0 at FULL_CONFIDENCE_GAMES -- reliability keeps approaching 1.0
        but never gets there, however large n gets."""
        assert reliability_weight(1000) < 1.0
        assert reliability_weight(FULL_CONFIDENCE_GAMES) != sample_size_weight(FULL_CONFIDENCE_GAMES)


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
        """50 + reliability_weight(10)*40 = 50 + (10/13)*40 = 80.77 -> 81.
        Was a clean 90 before P2's reliability_weight replaced
        sample_size_weight for the win-rate swing specifically -- see
        TestReliabilityWeight for why the two aren't interchangeable."""
        rows = [_game("W")] * FULL_CONFIDENCE_GAMES
        assert matchup_score(rows, "stable", 0) == 81

    def test_a_full_sample_winless_record_with_no_other_modifiers(self):
        """50 - reliability_weight(10)*40 = 50 - (10/13)*40 = 19.23 -> 19."""
        rows = [_game("L")] * FULL_CONFIDENCE_GAMES
        assert matchup_score(rows, "stable", 0) == 19

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
        """Needs more than FULL_CONFIDENCE_GAMES now: reliability_weight
        never fully reaches 1.0 the way sample_size_weight does, so
        FULL_CONFIDENCE_GAMES games alone (reliability ~0.77) isn't enough
        win-rate swing to hit the ceiling on its own -- 30 games
        (reliability ~0.91) is."""
        rows = [_game("W", opponent_skill_level=9, own_skill_level=1)] * 30
        assert matchup_score(rows, "up", 0) == 100
