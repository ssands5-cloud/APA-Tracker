"""Tests for the real APA 23-Rule (analytics/lineup_legality.py) -- the
Team Skill Level Limit, verified against APA's own published rules before
this module was written. See the module's own docstring for the source
and for what was deliberately NOT implemented (an earlier draft's
unverified "no more than two SL6+" / "at least one SL3 or below").

`check_lineup_legality` takes (player_id, skill_level) pairs, not bare
skill levels -- player identity is required so a lineup naming the same
real player twice can be caught (see the module's own docstring). Tests
below use short string ids ("A", "B", ...) as stand-ins for real player
identifiers; the function never interprets them, only compares them for
equality.
"""

from __future__ import annotations

from analytics.lineup_legality import (
    LINEUP_SIZE,
    TEAM_SKILL_LEVEL_LIMIT_5,
    check_lineup_legality,
)


def lineup(*skill_levels, players=None):
    """(player_id, skill_level) pairs for a lineup -- distinct real players
    "A", "B", "C", ... by default (one per slot), unless `players`
    overrides the ids explicitly (for duplicate-player tests)."""
    ids = players if players is not None else [chr(ord("A") + i) for i in range(len(skill_levels))]
    return list(zip(ids, skill_levels))


class TestCheckLineupLegality:
    def test_exactly_at_the_cap_is_legal(self):
        levels = [5, 5, 5, 4, 4]  # sums to 23
        assert sum(levels) == TEAM_SKILL_LEVEL_LIMIT_5
        result = check_lineup_legality(lineup(*levels))
        assert result.is_legal is True
        assert result.skill_total == 23
        assert result.limit == 23
        assert result.has_duplicate_players is False

    def test_one_over_the_cap_is_illegal(self):
        levels = [5, 5, 5, 4, 5]  # sums to 24
        result = check_lineup_legality(lineup(*levels))
        assert result.is_legal is False
        assert result.skill_total == 24
        assert result.has_duplicate_players is False

    def test_well_under_the_cap_is_legal(self):
        result = check_lineup_legality(lineup(2, 2, 2, 2, 2))
        assert result.is_legal is True

    def test_fewer_than_five_players_has_no_verdict(self):
        assert check_lineup_legality(lineup(5, 5, 5, 4)) is None

    def test_more_than_five_players_has_no_verdict(self):
        assert check_lineup_legality(lineup(5, 5, 5, 4, 4, 2)) is None

    def test_a_missing_skill_level_has_no_verdict_not_a_zero(self):
        """A missing SL must never be silently treated as 0 -- that would
        understate the real total and could call an actually-illegal
        lineup legal."""
        assert check_lineup_legality(lineup(5, 5, 5, 4, None)) is None

    def test_a_missing_player_id_has_no_verdict(self):
        assert check_lineup_legality([("A", 5), ("B", 5), ("C", 5), ("D", 4), (None, 4)]) is None

    def test_empty_input_has_no_verdict(self):
        assert check_lineup_legality([]) is None

    def test_lineup_size_constant_matches_a_real_apa_team_match(self):
        assert LINEUP_SIZE == 5


class TestDuplicatePlayerRejection:
    """A lineup that names the same real player in two slots isn't a real
    lineup at all -- illegal regardless of the skill-level math."""

    def test_a_repeated_player_is_illegal_even_under_the_cap(self):
        result = check_lineup_legality(
            lineup(2, 2, 2, 2, 2, players=["A", "A", "B", "C", "D"])
        )
        assert result is not None
        assert result.has_duplicate_players is True
        assert result.is_legal is False

    def test_a_repeated_player_is_still_illegal_when_reported_alone(self):
        """Even a lineup that would otherwise be well under the cap is
        illegal once a player repeats -- has_duplicate_players alone
        overrides the skill-total math, not just adds to it."""
        result = check_lineup_legality(
            lineup(1, 1, 1, 1, 1, players=["A", "A", "A", "A", "A"])
        )
        assert result.skill_total == 5
        assert result.skill_total <= TEAM_SKILL_LEVEL_LIMIT_5
        assert result.has_duplicate_players is True
        assert result.is_legal is False

    def test_five_distinct_players_never_flags_a_duplicate(self):
        result = check_lineup_legality(lineup(5, 5, 5, 4, 4))
        assert result.has_duplicate_players is False

    def test_a_malformed_selection_with_a_duplicate_still_has_no_verdict(self):
        """Missing data still wins over the duplicate check -- None means
        "not enough real evidence for any verdict", the same rule as
        every other malformed-input case here."""
        assert check_lineup_legality(
            [("A", 5), ("A", 5), ("B", 5), ("C", 4), (None, 4)]
        ) is None
