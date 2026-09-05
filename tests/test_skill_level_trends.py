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
    normalized_volatility,
    skill_level_volatility,
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


class TestNormalizedVolatility:
    """P2: the Matchup Advantage Engine's own volatility, normalized to a
    RATE -- changes divided by valid transitions (window_length - 1) over
    the last 5 readings. Deliberately a separate function from
    skill_level_volatility (see its own docstring) rather than a change to
    it, so the unrelated Skill Level History summary (ui/export_json.py)
    keeps its whole-history, uncapped count."""

    def test_no_changes_is_zero(self):
        assert normalized_volatility([_reading(5), _reading(5)]) == 0.0

    def test_a_change_on_every_opportunity_is_one(self):
        """Three readings give two transitions; both moved."""
        assert normalized_volatility([_reading(5), _reading(6), _reading(5)]) == 1.0

    def test_rate_is_changes_over_valid_transitions(self):
        """Five readings, two changes, four transitions -> 0.5."""
        matches = [_reading(5), _reading(5), _reading(6), _reading(6), _reading(5)]
        assert normalized_volatility(matches) == 0.5

    def test_a_single_reading_offers_no_transition_to_measure(self):
        """Absence of evidence, not evidence of stability -- but there is no
        rate to report, and dividing by zero is not an option."""
        assert normalized_volatility([_reading(5)]) == 0.0
        assert normalized_volatility([]) == 0.0

    def test_only_looks_at_the_last_five_readings(self):
        """Six readings with an old change (5->6) followed by five steady
        ones: the old change falls outside the default window of 5, so it
        must not count, unlike skill_level_volatility's whole-history 1."""
        matches = [_reading(5), _reading(6)] + [_reading(6)] * 4
        assert skill_level_volatility(matches) == 1
        assert normalized_volatility(matches) == 0.0

    def test_readings_without_a_skill_level_leave_the_rate_alone(self):
        """A None reading is skipped on BOTH sides of the ratio. Counting it
        in the denominator only would silently dilute a real 1.0 to 0.5."""
        matches = [_reading(5), _reading(None), _reading(6)]
        assert normalized_volatility(matches) == 1.0

    def test_window_is_configurable(self):
        matches = [_reading(5), _reading(6), _reading(5), _reading(6), _reading(5)]
        assert normalized_volatility(matches) == 1.0
        assert normalized_volatility(matches, window=3) == 1.0

    def test_the_rate_is_bounded_at_one_so_no_cap_is_needed(self):
        """The old implementation clamped a raw count at 3. A rate cannot
        exceed 1.0 by construction, which is what retired the cap."""
        matches = [_reading(5), _reading(6), _reading(5), _reading(6), _reading(5)]
        assert skill_level_volatility(matches) == 4
        assert normalized_volatility(matches) == 1.0


class TestSameChangeCountDifferentHistoryLength:
    """P2's headline requirement: an identical raw change count must NOT
    produce an identical volatility once history length differs. This is
    exactly what the old capped-count implementation could not express --
    it reported a flat 2 for both players below."""

    TWO_CHANGES_IN_THREE_READINGS = [_reading(5), _reading(6), _reading(5)]
    TWO_CHANGES_IN_FIVE_READINGS = [
        _reading(5), _reading(5), _reading(6), _reading(6), _reading(5),
    ]

    def test_both_histories_really_do_have_the_same_raw_change_count(self):
        assert skill_level_volatility(self.TWO_CHANGES_IN_THREE_READINGS) == 2
        assert skill_level_volatility(self.TWO_CHANGES_IN_FIVE_READINGS) == 2

    def test_the_same_raw_count_normalizes_to_different_rates(self):
        short = normalized_volatility(self.TWO_CHANGES_IN_THREE_READINGS)
        long = normalized_volatility(self.TWO_CHANGES_IN_FIVE_READINGS)
        assert short == 1.0  # 2 changes / 2 transitions
        assert long == 0.5   # 2 changes / 4 transitions
        assert short != long

    def test_the_shorter_history_is_the_more_volatile_one(self):
        """Two changes across two opportunities is unsettled every time;
        two across four is steadier than not."""
        assert normalized_volatility(self.TWO_CHANGES_IN_THREE_READINGS) > normalized_volatility(
            self.TWO_CHANGES_IN_FIVE_READINGS
        )
