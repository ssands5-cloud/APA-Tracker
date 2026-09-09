"""Tests for Close-Match Win Rate -- docs/planned_analytics_design.md.

Fixtures are real, detached PlayerHeadToHead/Match ORM objects, same
convention as tests/test_head_to_head.py's `game()` helper.
"""

from __future__ import annotations

import pytest

from analytics.close_match_performance import (
    CLOSE_MATCH_MARGIN,
    CLOSE_MATCH_MIN_SAMPLE,
    close_match_performance,
    is_close_match,
)
from analytics.matchups import reliability_weight
from database.models import Match, PlayerHeadToHead


def close_match(home=18, away=16):
    return Match(home_score=home, away_score=away)


def blowout_match(home=25, away=5):
    return Match(home_score=home, away_score=away)


def game(result="W", match=None):
    """One head-to-head game, detached, carrying its own real Match."""
    return PlayerHeadToHead(result=result, match=match if match is not None else close_match())


class TestIsCloseMatch:
    def test_within_the_margin_is_close(self):
        assert is_close_match(Match(home_score=10, away_score=10 - CLOSE_MATCH_MARGIN))

    def test_beyond_the_margin_is_not_close(self):
        assert not is_close_match(Match(home_score=10, away_score=10 - CLOSE_MATCH_MARGIN - 1))

    def test_an_unscored_match_is_not_close(self):
        assert not is_close_match(Match(home_score=None, away_score=None))

    def test_a_missing_match_is_not_close(self):
        assert not is_close_match(None)

    def test_margin_is_symmetric(self):
        assert is_close_match(Match(home_score=5, away_score=5 + CLOSE_MATCH_MARGIN))


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
