"""Tests for the real APA 23-Rule (analytics/lineup_legality.py) -- the
Team Skill Level Limit, verified against APA's own published rules before
this module was written. See the module's own docstring for the source
and for what was deliberately NOT implemented (an earlier draft's
unverified "no more than two SL6+" / "at least one SL3 or below").
"""

from __future__ import annotations

from analytics.lineup_legality import (
    LINEUP_SIZE,
    TEAM_SKILL_LEVEL_LIMIT_5,
    check_lineup_legality,
)


class TestCheckLineupLegality:
    def test_exactly_at_the_cap_is_legal(self):
        levels = [5, 5, 5, 4, 4]  # sums to 23
        assert sum(levels) == TEAM_SKILL_LEVEL_LIMIT_5
        result = check_lineup_legality(levels)
        assert result.is_legal is True
        assert result.skill_total == 23
        assert result.limit == 23

    def test_one_over_the_cap_is_illegal(self):
        levels = [5, 5, 5, 4, 5]  # sums to 24
        result = check_lineup_legality(levels)
        assert result.is_legal is False
        assert result.skill_total == 24

    def test_well_under_the_cap_is_legal(self):
        result = check_lineup_legality([2, 2, 2, 2, 2])
        assert result.is_legal is True

    def test_fewer_than_five_players_has_no_verdict(self):
        assert check_lineup_legality([5, 5, 5, 4]) is None

    def test_more_than_five_players_has_no_verdict(self):
        assert check_lineup_legality([5, 5, 5, 4, 4, 2]) is None

    def test_a_missing_skill_level_has_no_verdict_not_a_zero(self):
        """A missing SL must never be silently treated as 0 -- that would
        understate the real total and could call an actually-illegal
        lineup legal."""
        assert check_lineup_legality([5, 5, 5, 4, None]) is None

    def test_empty_input_has_no_verdict(self):
        assert check_lineup_legality([]) is None

    def test_lineup_size_constant_matches_a_real_apa_team_match(self):
        assert LINEUP_SIZE == 5
