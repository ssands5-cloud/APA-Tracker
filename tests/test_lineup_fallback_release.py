"""Release-gate coverage for the verified APA 4-player/19 fallback."""

from analytics.lineup_legality import (
    FALLBACK_LINEUP_SIZE,
    LINEUP_SIZE,
    TEAM_SKILL_LEVEL_LIMIT_4,
    TEAM_SKILL_LEVEL_LIMIT_5,
    assess_completion_options,
)


def test_standard_five_player_path_is_preferred_when_available():
    result = assess_completion_options([], [2, 2, 2, 2, 2])
    assert result is not None
    assert result.standard_five_possible is True
    assert result.four_player_fallback_possible is True
    assert result.preferred_lineup_size == LINEUP_SIZE
    assert result.skill_limit == TEAM_SKILL_LEVEL_LIMIT_5
    assert result.requires_forfeit is False


def test_four_player_fallback_is_selected_only_when_five_is_impossible():
    result = assess_completion_options([], [5, 5, 5, 4])
    assert result is not None
    assert result.standard_five_possible is False
    assert result.four_player_fallback_possible is True
    assert result.preferred_lineup_size == FALLBACK_LINEUP_SIZE
    assert result.skill_limit == TEAM_SKILL_LEVEL_LIMIT_4
    assert result.requires_forfeit is True


def test_four_player_total_over_nineteen_is_not_legal_fallback():
    result = assess_completion_options([], [5, 5, 5, 5])
    assert result is not None
    assert result.standard_five_possible is False
    assert result.four_player_fallback_possible is False
    assert result.preferred_lineup_size is None
    assert result.requires_forfeit is False


def test_four_committed_at_nineteen_can_finish_via_fallback():
    result = assess_completion_options([5, 5, 5, 4], [])
    assert result is not None
    assert result.standard_five_possible is False
    assert result.four_player_fallback_possible is True
    assert result.preferred_lineup_size == FALLBACK_LINEUP_SIZE
    assert result.skill_limit == TEAM_SKILL_LEVEL_LIMIT_4
    assert result.requires_forfeit is True


def test_four_committed_at_twenty_cannot_use_fallback():
    result = assess_completion_options([5, 5, 5, 5], [])
    assert result is not None
    assert result.standard_five_possible is False
    assert result.four_player_fallback_possible is False
    assert result.preferred_lineup_size is None


def test_unknown_available_skill_keeps_five_player_path_unresolved_and_never_forces_forfeit():
    # Four known SL4 players make the 4-player fallback legal, but a fifth
    # available player exists whose skill is unknown. The standard path is
    # therefore unresolved, not proven impossible. Never recommend a
    # forfeit while a legal 5-player lineup might still exist.
    result = assess_completion_options([], [4, 4, 4, 4, None])
    assert result is not None
    assert result.standard_five_possible is None
    assert result.four_player_fallback_possible is True
    assert result.preferred_lineup_size is None
    assert result.requires_forfeit is False


def test_unknown_committed_skill_has_no_honest_assessment():
    assert assess_completion_options([5, None], [2, 2, 2, 2]) is None


def test_more_than_five_committed_slots_is_malformed():
    assert assess_completion_options([2, 2, 2, 2, 2, 2], []) is None


def test_high_skill_roster_fails_both_paths():
    result = assess_completion_options([], [9, 9, 9, 9, 9])
    assert result is not None
    assert result.standard_five_possible is False
    assert result.four_player_fallback_possible is False
    assert result.preferred_lineup_size is None
