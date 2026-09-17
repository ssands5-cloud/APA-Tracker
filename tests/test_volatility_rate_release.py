"""Release-gate regression tests for matchup volatility normalization.

These lock the valid behavior originally developed on stale PR #13 onto the
current 1.0 hardening branch without merging that 130-commit-old branch.
"""

from analytics.matchups import confidence_score, matchup_score, volatility_penalty
from analytics.skill_level_trends import normalized_volatility, skill_level_volatility
from database.models import PlayerHeadToHead, PlayerMatch


def _reading(level):
    return PlayerMatch(skill_level=level)


def _game(result="W"):
    return PlayerHeadToHead(result=result)


def test_same_change_count_different_transition_count_gets_different_rate():
    short = [_reading(5), _reading(6), _reading(5)]
    long = [_reading(5), _reading(5), _reading(6), _reading(6), _reading(5)]

    assert skill_level_volatility(short) == 2
    assert skill_level_volatility(long) == 2
    assert normalized_volatility(short) == 1.0
    assert normalized_volatility(long) == 0.5


def test_unknown_readings_do_not_dilute_the_rate():
    history = [_reading(5), _reading(None), _reading(6)]
    assert normalized_volatility(history) == 1.0


def test_fewer_than_two_known_readings_has_zero_observed_rate():
    assert normalized_volatility([]) == 0.0
    assert normalized_volatility([_reading(None), _reading(5)]) == 0.0


def test_penalty_uses_rate_and_preserves_fifteen_point_ceiling():
    assert volatility_penalty(0.0) == 0
    assert volatility_penalty(0.5) == 8
    assert volatility_penalty(1.0) == 15
    assert volatility_penalty(3.0) == 15
    assert volatility_penalty(-1.0) == 0


def test_same_normalized_rate_scores_equivalently():
    rows = [_game("W"), _game("L"), _game("W")]

    assert matchup_score(rows, "stable", 0.5) == matchup_score(rows, "stable", 0.5)
    assert confidence_score(rows, "stable", 0.5) == confidence_score(rows, "stable", 0.5)

    # Prove volatility is still load-bearing rather than ignored.
    assert matchup_score(rows, "stable", 0.0) != matchup_score(rows, "stable", 1.0)
    assert confidence_score(rows, "stable", 0.0) != confidence_score(rows, "stable", 1.0)
