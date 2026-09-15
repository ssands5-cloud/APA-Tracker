"""Tests for analytics/team_strength.py."""

from __future__ import annotations

import pytest

from analytics.team_strength import FORMULA_VERSION, build_report


def player(external_id, name="P", won=0, played=0, skill=5, player_id=None):
    return {
        "player_id": player_id or hash(external_id) % 1000,
        "player_external_id": external_id, "player_name": name,
        "skill_level": skill, "matches_won": won, "matches_played": played,
    }


def match(match_id, points_for, points_against, is_home=True, **kwargs):
    row = {
        "match_id": match_id, "points_for": points_for, "points_against": points_against,
        "is_home": is_home,
    }
    row.update(kwargs)
    return row


class TestOffenseIndex:
    def test_pooled_win_rate_not_averaged_per_player(self):
        # Player A: 1/1 (100%). Player B: 1/19 (~5%). A simple average of
        # per-player rates would be ~52%; pooling gives the real 2/20=10%.
        players = [player("A", won=1, played=1), player("B", won=1, played=19)]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, [])

        assert report.offense_index == pytest.approx(10.0)
        assert report.offense_wins == 2
        assert report.offense_played == 20

    def test_no_played_matches_is_null_not_zero(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [player("A")], [])
        assert report.offense_index is None
        assert any("Offense" in reason for reason in report.unavailable_reasons)


class TestDefenseIndex:
    def test_containment_proxy_matches_the_documented_formula(self):
        matches = [match("M1", points_for=8, points_against=2), match("M2", points_for=6, points_against=4)]
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], matches)

        # PF=14, PA=6, total=20 -> 100*(1-6/20) = 70
        assert report.defense_index == pytest.approx(70.0)
        assert report.points_for == 14
        assert report.points_against == 6
        assert report.defense_match_count == 2

    def test_no_eligible_matches_is_null(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [])
        assert report.defense_index is None


class TestDepthIndex:
    def test_fifth_highest_rate_with_at_least_five_scoreable(self):
        players = [
            player("A", won=10, played=10),  # 1.00
            player("B", won=8, played=10),   # 0.80
            player("C", won=6, played=10),   # 0.60
            player("D", won=4, played=10),   # 0.40
            player("E", won=2, played=10),   # 0.20 <- fifth
            player("F", won=0, played=10),   # 0.00
        ]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, [])

        assert report.depth_index == pytest.approx(20.0)
        assert report.depth_player_id == "E"
        assert report.scoreable_player_count == 6

    def test_fewer_than_five_scoreable_is_null(self):
        players = [player(f"P{i}", won=1, played=1) for i in range(4)]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, [])

        assert report.depth_index is None
        assert report.depth_player_id is None

    def test_ties_break_on_external_id_ascending(self):
        players = [
            player("Z", won=5, played=10), player("A", won=5, played=10),
            player("M", won=5, played=10), player("B", won=5, played=10),
            player("Y", won=5, played=10),
        ]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, [])
        # All tied at 0.5 -> sorted by external id ascending: A, B, M, Y, Z
        # -> fifth is Z.
        assert report.depth_player_id == "Z"

    def test_depth_order_is_annotated_on_every_scoreable_player(self):
        players = [player("A", won=10, played=10), player("B", won=0, played=10)]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, [])
        rows_by_id = {r.player_external_id: r for r in report.player_rows}
        assert rows_by_id["A"].depth_order == 1
        assert rows_by_id["B"].depth_order == 2

    def test_a_player_with_no_matches_has_no_depth_order(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [player("A")], [])
        assert report.player_rows[0].depth_order is None


class TestTeamStrengthIndex:
    def test_equal_mean_of_all_three_components_when_all_present(self):
        players = [player(f"P{i}", won=5, played=10) for i in range(5)]
        matches = [match("M1", points_for=8, points_against=2)]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, matches)

        assert report.team_strength_index == pytest.approx(
            (report.offense_index + report.defense_index + report.depth_index) / 3
        )

    def test_composite_is_null_when_any_one_component_is_missing(self):
        players = [player(f"P{i}", won=5, played=10) for i in range(5)]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, [])  # no matches -> no defense

        assert report.defense_index is None
        assert report.team_strength_index is None
        # Never renormalized over the available two components:
        assert report.team_strength_index != pytest.approx(
            (report.offense_index + report.depth_index) / 2
        )

    def test_formula_version_is_recorded(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [])
        assert report.formula_version == FORMULA_VERSION == "team-strength-v1-equal-components"


class TestUnavailableReasons:
    def test_missing_standings_is_disclosed(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [], standings_record=None)
        assert any("Standings" in reason for reason in report.unavailable_reasons)

    def test_a_real_standings_record_suppresses_that_disclosure(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [], standings_record="5-2")
        assert not any("Standings" in reason for reason in report.unavailable_reasons)


class TestRowFidelity:
    def test_every_real_match_is_carried_through(self):
        matches = [match("M1", 8, 2, format="8-Ball Open", session_name="Fall 2026", week=5)]
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], matches)
        assert len(report.match_rows) == 1
        assert report.match_rows[0].week == 5

    def test_every_real_player_is_carried_through_even_when_not_scoreable(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [player("A")], [])
        assert len(report.player_rows) == 1
        assert report.player_rows[0].observed_rate is None
