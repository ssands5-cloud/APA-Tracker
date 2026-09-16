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
    MAX_COMPLETION_ATTEMPTS,
    TEAM_SKILL_LEVEL_LIMIT_5,
    check_lineup_legality,
    legal_completion_exists,
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


class TestLegalCompletionExists:
    """Match Night: can a legal 5-player lineup still be completed given
    who's already committed to a board and who's still available? Distinct
    from check_lineup_legality, which only verifies an already-complete
    selection -- this answers the live-planning question of whether a
    choice made *now* still leaves a legal path for the rest of the match.
    """

    def test_nothing_committed_yet_with_enough_low_skill_players(self):
        # Any 5 of these five 2s sum to 10, well under 23.
        assert legal_completion_exists([], [2, 2, 2, 2, 2]) is True

    def test_nothing_committed_yet_but_only_high_skill_players_available(self):
        # Every 5-of-5 combination sums to 45, over the cap -- no completion.
        assert legal_completion_exists([], [9, 9, 9, 9, 9]) is False

    def test_some_high_skill_players_already_committed_can_still_complete_legally(self):
        # Committed: 9, 9 (=18). Needs 3 more, cap allows 5 more total (23-18).
        # Available has a combo (1, 1, 1) summing to 3, well within budget.
        assert legal_completion_exists([9, 9], [1, 1, 1, 9, 9]) is True

    def test_committed_players_alone_already_exceed_the_cap(self):
        # 9+9+9+9+9 = 45 already committed for all 5 slots -- no room, and
        # nothing left to choose, so no completion can fix it.
        assert legal_completion_exists([9, 9, 9, 9, 9], []) is False

    def test_exactly_at_the_cap_with_nothing_left_to_choose_is_legal(self):
        assert legal_completion_exists([5, 5, 5, 4, 4], []) is True

    def test_fewer_available_players_with_a_known_skill_than_are_still_needed(self):
        # Two committed, three needed, only two real skill levels available.
        assert legal_completion_exists([5, 5], [4, 4]) is None

    def test_missing_skill_levels_are_excluded_not_treated_as_zero(self):
        """A player with no recorded skill level can't be silently assumed
        to cost 0 -- that could call an actually-infeasible completion
        possible. None entries are dropped from the search, not zeroed."""
        # Only two real skill levels (4, 4) remain after dropping the two
        # Nones -- fewer than the three still needed -> None, not a guess.
        assert legal_completion_exists([5, 5], [4, 4, None, None]) is None

    def test_more_than_five_already_committed_has_no_verdict(self):
        assert legal_completion_exists([4, 4, 4, 4, 4, 4], [2, 2, 2, 2, 2]) is None

    def test_a_marginal_case_where_only_one_specific_combo_works(self):
        # Committed: 5+5+5 = 15, need 2 more totalling <= 8. Available: a
        # 9 (too high alone), and a 3+4=7 pair that fits; the search must
        # find that specific legal pair, not just check the first combo.
        assert legal_completion_exists([5, 5, 5], [9, 3, 4]) is True

    def test_a_marginal_case_with_no_working_combo(self):
        # Committed: 15, need 2 more totalling <= 8, but every available
        # pair (9,9)/(9,8)/(9,8) sums well over 8.
        assert legal_completion_exists([5, 5, 5], [9, 9, 8]) is False

    def test_zero_still_needed_checks_only_the_committed_total(self):
        assert legal_completion_exists([5, 5, 5, 4, 4], [1, 1, 1]) is True
        assert legal_completion_exists([5, 5, 5, 5, 5], [1, 1, 1]) is False

    def test_a_completion_search_within_the_real_bound_does_not_raise(self):
        # 20 available players, needing all 5 -- C(20,5) = 15504, well
        # inside MAX_COMPLETION_ATTEMPTS, must not raise.
        assert legal_completion_exists([], [2] * 20) is True

    def test_a_completion_search_over_the_real_bound_raises_rather_than_approximate(self):
        # Force an exact-search size whose C(n, k) exceeds the real bound,
        # rather than ever silently truncating or sampling the search.
        import math
        n = 60
        k = 5
        assert math.comb(n, k) > MAX_COMPLETION_ATTEMPTS
        try:
            legal_completion_exists([], [2] * n)
        except ValueError as exc:
            assert "narrow tonight's availability" in str(exc)
        else:
            raise AssertionError("expected a ValueError for an unbounded search")
