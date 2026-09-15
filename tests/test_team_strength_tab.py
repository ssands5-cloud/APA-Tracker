"""Tests for ui/tabs/team_strength.py."""

from __future__ import annotations

from analytics.team_strength import build_report
from ui.tabs.team_strength import render


def player(external_id, name="P", won=0, played=0, skill=5, player_id=None):
    return {
        "player_id": player_id or hash(external_id) % 1000,
        "player_external_id": external_id, "player_name": name,
        "skill_level": skill, "matches_won": won, "matches_played": played,
    }


def match(match_id, points_for, points_against, is_home=True, **kwargs):
    row = {"match_id": match_id, "points_for": points_for, "points_against": points_against, "is_home": is_home}
    row.update(kwargs)
    return row


class TestRender:
    def test_all_three_components_and_index_render(self):
        players = [player(f"P{i}", name=f"Player {i}", won=5, played=10) for i in range(5)]
        matches = [match("M1", 8, 2, format="8-Ball Open", session_name="Fall 2026", week=3)]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, matches)

        html = render(report)

        assert "Chalk It Up" in html
        assert "Fall 2026" in html
        assert "team-strength-v1-equal-components" in html

    def test_missing_component_shows_no_data_not_zero(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [])
        html = render(report)
        assert "No data" in html
        assert "team_strength_index" not in html  # never a raw attribute dump

    def test_unavailable_reasons_are_disclosed(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [])
        html = render(report)
        assert "no canonical roster player has a recorded match" in html.lower()
        assert "no eligible finalized match found" in html.lower()

    def test_no_categorical_strength_tier_language(self):
        players = [player(f"P{i}", won=5, played=10) for i in range(5)]
        matches = [match("M1", 8, 2)]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, matches)
        html = render(report)
        assert 'class="ts-strong"' not in html
        assert 'class="ts-weak"' not in html
        assert 'class="ts-tier' not in html

    def test_defense_is_explicitly_labeled_a_proxy(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [match("M1", 8, 2)])
        html = render(report)
        assert "proxy" in html.lower()

    def test_depth_player_id_appears_in_roster_table(self):
        players = [
            player("A", won=10, played=10), player("B", won=8, played=10),
            player("C", won=6, played=10), player("D", won=4, played=10),
            player("E", won=2, played=10),
        ]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, [])
        html = render(report)
        assert report.depth_player_id == "E"
        assert ">E<" in html

    def test_match_evidence_shows_real_points(self):
        report = build_report(
            "T1", "Chalk It Up", "Fall 2026", [],
            [match("M1", 8, 2, week=5, is_home=True)],
        )
        html = render(report)
        assert "Home" in html
        assert ">8<" in html
        assert ">2<" in html

    def test_hostile_text_is_escaped(self):
        players = [player("A", name="<script>alert(1)</script>", won=1, played=1)]
        report = build_report("T1", "Chalk It Up", "Fall 2026", players, [])
        html = render(report)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_no_external_resources(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [])
        html = render(report)
        assert "http://" not in html
        assert "https://" not in html
