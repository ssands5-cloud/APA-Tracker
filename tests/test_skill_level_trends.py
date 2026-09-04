"""Tests for analytics.skill_level_trends.

Operates on plain PlayerMatch rows (built directly, not through ingest --
these are pure functions over an already-ordered list) so the trend math is
tested independently of the database/export plumbing covered elsewhere
(tests/test_export_json.py::TestSkillLevelHistory).
"""

from __future__ import annotations

from analytics.skill_level_trends import (
    SkillLevelChange,
    skill_level_changes,
    skill_level_trend,
    skill_level_volatility,
    windowed_volatility,
)
from database.models import Match, PlayerMatch


def _reading(skill_level, week=None, match_date=None):
    row = PlayerMatch(player_id=1, skill_level=skill_level, match_date=match_date)
    if week is not None:
        row.match = Match(week=week)
    return row


class TestSkillLevelChanges:
    def test_no_readings_means_no_changes(self):
        assert skill_level_changes([]) == []

    def test_one_reading_is_never_a_change(self):
        assert skill_level_changes([_reading(5)]) == []

    def test_a_steady_level_across_several_matches_has_no_changes(self):
        matches = [_reading(5), _reading(5), _reading(5)]
        assert skill_level_changes(matches) == []

    def test_a_move_between_two_matches_is_one_change(self):
        matches = [_reading(5, week=1), _reading(6, week=7)]
        assert skill_level_changes(matches) == [
            SkillLevelChange(from_level=5, to_level=6, match_date=None, week=7)
        ]

    def test_readings_with_no_skill_level_are_skipped_not_treated_as_a_change(self):
        """A match linked to the player (e.g. a bye or an unscored row) with
        no skill_level must not read as a drop to/from None."""
        matches = [_reading(5), _reading(None), _reading(5)]
        assert skill_level_changes(matches) == []

    def test_multiple_changes_are_all_reported_in_order(self):
        matches = [_reading(5, week=1), _reading(6, week=3), _reading(5, week=6)]
        changes = skill_level_changes(matches)
        assert [(c.from_level, c.to_level) for c in changes] == [(5, 6), (6, 5)]


class TestSkillLevelTrend:
    def test_no_readings_at_all(self):
        assert skill_level_trend([]) == "no data"

    def test_ends_higher_than_it_started_is_up(self):
        assert skill_level_trend([_reading(4), _reading(5), _reading(6)]) == "up"

    def test_ends_lower_than_it_started_is_down(self):
        assert skill_level_trend([_reading(6), _reading(5)]) == "down"

    def test_unchanged_is_stable(self):
        assert skill_level_trend([_reading(5), _reading(5)]) == "stable"

    def test_a_dip_that_fully_recovers_reads_stable_not_up_or_down(self):
        """Compares first vs. last reading, not the min/max in between --
        what the player ended the season at, not the roughest patch."""
        assert skill_level_trend([_reading(5), _reading(3), _reading(5)]) == "stable"


class TestSkillLevelVolatility:
    def test_no_changes_is_zero(self):
        assert skill_level_volatility([_reading(5), _reading(5)]) == 0

    def test_counts_every_change_not_just_whether_one_happened(self):
        matches = [_reading(5), _reading(6), _reading(5), _reading(6)]
        assert skill_level_volatility(matches) == 3


class TestWindowedVolatility:
    """P2: the Matchup Advantage Engine's own normalized volatility --
    windowed to the last 5 readings, capped at 3. Deliberately a separate
    function from skill_level_volatility (see its own docstring) rather
    than a change to it, so the unrelated Skill Level History summary
    (ui/export_json.py) keeps its whole-history, uncapped count."""

    def test_no_changes_is_zero(self):
        assert windowed_volatility([_reading(5), _reading(5)]) == 0

    def test_within_the_window_matches_the_plain_count(self):
        matches = [_reading(5), _reading(6), _reading(5)]
        assert windowed_volatility(matches) == 2

    def test_only_looks_at_the_last_five_readings(self):
        """Six readings with an old change (5->6) followed by five steady
        ones: the old change falls outside the default window of 5, so it
        must not count, unlike skill_level_volatility's whole-history 1."""
        matches = [_reading(5), _reading(6)] + [_reading(6)] * 4
        assert skill_level_volatility(matches) == 1
        assert windowed_volatility(matches) == 0

    def test_is_capped_at_three_even_with_more_real_changes_in_the_window(self):
        """Five readings, four consecutive changes (5-6-5-6-5) -- more
        than the cap, so this must clamp to 3 rather than reporting 4."""
        matches = [_reading(5), _reading(6), _reading(5), _reading(6), _reading(5)]
        assert skill_level_volatility(matches) == 4
        assert windowed_volatility(matches) == 3

    def test_window_and_cap_are_configurable(self):
        matches = [_reading(5), _reading(6), _reading(5), _reading(6), _reading(5)]
        assert windowed_volatility(matches, window=3) == 2
        assert windowed_volatility(matches, window=5, cap=2) == 2
