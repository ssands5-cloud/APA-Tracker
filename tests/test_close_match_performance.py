"""Tests for Close-Match Win Rate -- docs/planned_analytics_design.md.

Fixtures are real, detached PlayerHeadToHead/Match ORM objects, same
convention as tests/test_head_to_head.py's `game()` helper. Every
`Match()` fixture here is scored AND finalized by default -- is_close_match
requires both (see its own docstring) -- and carries an explicit,
distinct `id` per real match, since PlayerHeadToHead.match_id is what
close_match_performance groups by to count DISTINCT matches, not rows.
"""

from __future__ import annotations

import itertools

import pytest

from analytics.close_match_performance import (
    CLOSE_MATCH_MARGIN,
    CLOSE_MATCH_MIN_SAMPLE,
    close_match_performance,
    is_close_match,
)
from analytics.matchups import reliability_weight
from database.models import Match, PlayerHeadToHead

_match_ids = itertools.count(1)


def close_match(home=18, away=16, **overrides):
    fields = {"is_scored": True, "is_finalized": True, "is_bye": False}
    fields.update(overrides)
    return Match(id=next(_match_ids), home_score=home, away_score=away, **fields)


def blowout_match(home=25, away=5, **overrides):
    return close_match(home=home, away=away, **overrides)


def game(result="W", match=None):
    """One head-to-head game, detached, carrying its own real Match. A
    fresh close_match() by default -- callers that need several GAMES in
    the SAME real match pass the same `match` object explicitly."""
    m = match if match is not None else close_match()
    return PlayerHeadToHead(result=result, match=m, match_id=m.id)


class TestIsCloseMatch:
    def test_within_the_margin_is_close(self):
        assert is_close_match(close_match(home=10, away=10 - CLOSE_MATCH_MARGIN))

    def test_beyond_the_margin_is_not_close(self):
        assert not is_close_match(close_match(home=10, away=10 - CLOSE_MATCH_MARGIN - 1))

    def test_an_unscored_match_is_not_close(self):
        assert not is_close_match(Match(id=1, home_score=None, away_score=None,
                                        is_scored=False, is_finalized=False))

    def test_a_scored_but_not_yet_finalized_match_is_not_close(self):
        """is_scored alone can still change (Match's own docstring);
        an unconfirmed score is not decided evidence yet."""
        assert not is_close_match(close_match(is_finalized=False))

    def test_a_missing_match_is_not_close(self):
        assert not is_close_match(None)

    def test_a_bye_is_never_close_even_if_it_somehow_carries_scores(self):
        assert not is_close_match(close_match(is_bye=True))

    def test_a_tie_is_not_a_decided_result_either_way(self):
        assert not is_close_match(close_match(home=10, away=10))

    def test_margin_is_symmetric(self):
        assert is_close_match(close_match(home=5, away=5 + CLOSE_MATCH_MARGIN))


class TestCloseMatchPerformance:
    def test_below_the_minimum_sample_has_no_shrunk_rate(self):
        rows = [game("W", close_match()) for _ in range(CLOSE_MATCH_MIN_SAMPLE - 1)]
        result = close_match_performance(rows)
        assert result.close_matches_played == CLOSE_MATCH_MIN_SAMPLE - 1
        assert result.shrunk_win_rate is None

    def test_meeting_the_minimum_sample_produces_a_real_shrunk_rate(self):
        rows = [game("W", close_match()) for _ in range(CLOSE_MATCH_MIN_SAMPLE)]
        result = close_match_performance(rows)
        assert result.close_matches_played == CLOSE_MATCH_MIN_SAMPLE
        assert result.close_win_rate == 1.0
        assert result.overall_win_rate == 1.0
        assert result.shrunk_win_rate == 1.0  # both signals agree, so shrinkage is moot here

    def test_multiple_games_in_the_SAME_match_count_as_one_match_not_several(self):
        """A player can legitimately play more than one individual game
        within a single real team match (confirmed against a real
        scoresheet -- see PlayerHeadToHead's own docstring in
        database/models.py). Three games inside ONE close match must not
        satisfy the three-DISTINCT-matches minimum sample."""
        one_match = close_match()
        rows = [game("W", one_match) for _ in range(CLOSE_MATCH_MIN_SAMPLE)]
        result = close_match_performance(rows)
        assert result.close_games_played == CLOSE_MATCH_MIN_SAMPLE
        assert result.close_matches_played == 1
        assert result.shrunk_win_rate is None  # only 1 distinct match -- still no real signal

    def test_close_win_rate_is_still_a_real_per_game_rate(self):
        """close_win_rate itself stays game-based (each game is a real,
        independent result) -- only the SAMPLE-SIZE gate needed fixing to
        count distinct matches."""
        one_match = close_match()
        rows = [game("W", one_match), game("L", one_match)]
        result = close_match_performance(rows)
        assert result.close_games_played == 2
        assert result.close_matches_played == 1
        assert result.close_win_rate == 0.5

    def test_shrinkage_pulls_toward_the_overall_rate_not_just_the_close_rate(self):
        """A perfect close-match record alongside a mediocre overall
        record should shrink DOWN from 1.0 -- the whole point of
        shrinkage is that a small close-match sample doesn't get taken at
        face value."""
        close_rows = [game("W", close_match()) for _ in range(CLOSE_MATCH_MIN_SAMPLE)]
        blowout_losses = [game("L", blowout_match()) for _ in range(10)]
        result = close_match_performance(close_rows + blowout_losses)

        assert result.close_win_rate == 1.0
        assert result.overall_win_rate == pytest.approx(3 / 13, abs=0.001)
        assert 0.0 < result.shrunk_win_rate < 1.0

        weight = reliability_weight(CLOSE_MATCH_MIN_SAMPLE)
        expected = round(weight * 1.0 + (1 - weight) * result.overall_win_rate, 3)
        assert result.shrunk_win_rate == expected

    def test_no_recognized_results_at_all_is_none_not_zero(self):
        result = close_match_performance([])
        assert result.overall_win_rate is None
        assert result.close_win_rate is None
        assert result.shrunk_win_rate is None

    def test_unrecognized_results_are_excluded_from_every_count(self):
        rows = [game("?", close_match()) for _ in range(5)]
        result = close_match_performance(rows)
        assert result.overall_matches_played == 0
        assert result.close_matches_played == 0
        assert result.close_games_played == 0

    def test_a_blowout_never_counts_toward_the_close_match_sample(self):
        rows = [game("W", blowout_match()) for _ in range(10)]
        result = close_match_performance(rows)
        assert result.close_matches_played == 0
        assert result.overall_matches_played == 10
        assert result.overall_win_rate == 1.0
        assert result.shrunk_win_rate is None

    def test_a_row_with_no_linked_match_is_never_close(self):
        rows = [PlayerHeadToHead(result="W", match=None) for _ in range(5)]
        result = close_match_performance(rows)
        assert result.close_matches_played == 0
        assert result.overall_matches_played == 5
