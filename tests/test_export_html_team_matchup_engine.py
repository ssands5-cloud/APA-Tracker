"""Tests for ui/export_html_team_matchup_engine.py."""

from __future__ import annotations

import json

from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix
from analytics.team_matchup_engine import build_team_matchup_report
from ui.export_html_team_matchup_engine import render


def _matrix(opponent_team_external_id="OPP1") -> PairingEvidenceMatrix:
    pairing = PairingEvidence(
        player_id=1, player_external_id="P1", player_name="Ann", player_skill_level=5,
        opponent_id=2, opponent_external_id="P2", opponent_name="Bob", opponent_skill_level=4,
        format="8-Ball Open", session_name="Fall 2026",
        evidence_label=EvidenceLabel.DIRECT, observed_win_rate=0.75, direct_evidence_count=4,
        modeled_win_probability=0.7, model_source="analytics.head_to_head",
    )
    return PairingEvidenceMatrix(
        our_team_external_id="OUR1", opponent_team_external_id=opponent_team_external_id,
        format="8-Ball Open", session_name="Fall 2026",
        expected_pairings=((1, 2),), pairings=(pairing,),
        counts={"DIRECT": 1, "INDIRECT": 0, "UNKNOWN": 0, "total_feasible_pairings": 1},
        our_roster_available=True, opponent_roster_available=True,
    )


class TestRender:
    def test_a_self_contained_page_with_no_external_resources(self):
        report = build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")
        html = render([report])
        assert "<html" in html
        assert "http://" not in html
        assert "https://" not in html

    def test_the_scope_selector_lists_every_real_scope(self):
        r1 = build_team_matchup_report(_matrix("OPP1"), "Mark It Up", "Corner Pockets")
        r2 = build_team_matchup_report(_matrix("OPP2"), "Mark It Up", "Rack Attack")
        html = render([r1, r2])
        assert "Corner Pockets" in html
        assert "Rack Attack" in html

    def test_a_name_containing_a_script_close_tag_cannot_break_out(self):
        report = build_team_matchup_report(_matrix(), "Mark It Up</script><script>alert(1)</script>", "Corner Pockets")
        html = render([report])
        assert "<script>alert(1)</script>" not in html

    def test_the_embedded_json_carries_the_real_summary_and_no_categorical_verdict(self):
        report = build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")
        html = render([report])
        start = html.index('id="tme-data">') + len('id="tme-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        key = f"OPP1|8-Ball Open|Fall 2026"
        assert payload[key]["summary"] == report.summary
        assert "favored" not in report.summary.lower()

    def test_the_opponent_scouting_section_never_narrates_a_verdict(self):
        """GPT audit P1: renamed from "Opponent ranking (toughest real
        matchup first)" to "Opponent Scouting," an explicitly experimental
        ranking with no narrated verdict."""
        report = build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")
        html = " ".join(render([report]).split())
        assert "Opponent Scouting" in html
        assert "experimental" in html.lower()
        assert "toughest real matchup" not in html.lower()
        assert "most favorable real matchup" not in html.lower()
