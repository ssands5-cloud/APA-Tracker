"""Tests for ui/export_html_player_matchup_engine.py."""

from __future__ import annotations

from analytics.pairing_evidence import EvidenceLabel, PairingEvidence
from analytics.player_matchup_engine import build_player_matchup_report
from ui.export_html_player_matchup_engine import render


def _pairing(**overrides) -> PairingEvidence:
    base = dict(
        player_id=1, player_external_id="P1", player_name="Ann", player_skill_level=5,
        opponent_id=2, opponent_external_id="P2", opponent_name="Bob", opponent_skill_level=4,
        format="8-Ball Open", session_name="Fall 2026",
        evidence_label=EvidenceLabel.DIRECT, observed_win_rate=0.75, direct_evidence_count=4,
        modeled_win_probability=0.7, model_source="analytics.head_to_head",
    )
    base.update(overrides)
    return PairingEvidence(**base)


class TestRender:
    def test_a_self_contained_page_with_no_external_resources(self):
        html = render([build_player_matchup_report(_pairing())])
        assert "<html" in html
        assert "http://" not in html
        assert "https://" not in html

    def test_the_pairing_selector_lists_every_real_pairing(self):
        html = render([
            build_player_matchup_report(_pairing()),
            build_player_matchup_report(_pairing(player_id=3, player_name="Carol", opponent_id=4, opponent_name="Dave")),
        ])
        assert "Ann vs Bob" in html
        assert "Carol vs Dave" in html

    def test_a_name_containing_a_script_close_tag_cannot_break_out(self):
        html = render([build_player_matchup_report(_pairing(player_name="</script><script>alert(1)</script>"))])
        assert "<script>alert(1)</script>" not in html

    def test_the_embedded_json_is_valid_and_matches_the_report(self):
        import json

        report = build_player_matchup_report(_pairing())
        html = render([report])
        start = html.index('id="pme-data">') + len('id="pme-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        key = f"{report.player_id}:{report.opponent_id}"
        assert payload[key]["evidence_label"] == "DIRECT"
