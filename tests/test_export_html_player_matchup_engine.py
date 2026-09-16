"""Tests for ui/export_html_player_matchup_engine.py."""

from __future__ import annotations

import json

from analytics.pairing_evidence import EvidenceLabel, PairingEvidence
from analytics.player_matchup_engine import build_player_matchup_report
from ui.export_html_player_matchup_engine import _pair_key, render


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


def _build(pairing=None, our_team="OUR1", opponent_team="OPP1", **kwargs):
    return build_player_matchup_report(pairing or _pairing(), our_team, opponent_team, **kwargs)


class TestPairKeyIsScopeSafe:
    def test_two_scopes_with_the_same_players_never_collide(self):
        """GPT audit P1, the load-bearing regression: the same two players
        can face each other under more than one real (opponent, format,
        session) scope in one bundle -- e.g. two different formats against
        the same opponent, same session. Keying on player_id:opponent_id
        alone let the later report silently overwrite the earlier one."""
        report_a = _build(_pairing(format="8-Ball Open"))
        report_b = _build(_pairing(format="9-Ball Open"))

        assert _pair_key(report_a) != _pair_key(report_b)

    def test_two_scopes_against_different_opponent_teams_never_collide(self):
        report_a = _build(_pairing(), opponent_team="OPP1")
        report_b = _build(_pairing(), opponent_team="OPP2")

        assert _pair_key(report_a) != _pair_key(report_b)


class TestRender:
    def test_a_self_contained_page_with_no_external_resources(self):
        html = render([_build()])
        assert "<html" in html
        assert "http://" not in html
        assert "https://" not in html

    def test_choosing_a_player_narrows_the_opponent_options_to_their_real_pairings(self):
        report_a = _build(_pairing())
        report_b = _build(_pairing(player_id=3, player_name="Carol", opponent_id=4, opponent_name="Dave"))
        html = render([report_a, report_b])

        start = html.index('id="pme-opponent-index">') + len('id="pme-opponent-index">')
        end = html.index("</script>", start)
        index = json.loads(html[start:end])

        assert [c["label"] for c in index["1"]] == ["Bob (8-Ball Open, Fall 2026)"]
        assert [c["label"] for c in index["3"]] == ["Dave (8-Ball Open, Fall 2026)"]

    def test_a_name_containing_a_script_close_tag_cannot_break_out(self):
        html = render([_build(_pairing(player_name="</script><script>alert(1)</script>"))])
        assert "<script>alert(1)</script>" not in html

    def test_the_embedded_json_is_valid_and_matches_the_report(self):
        report = _build()
        html = render([report])
        start = html.index('id="pme-data">') + len('id="pme-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        assert payload[_pair_key(report)]["evidence_label"] == "DIRECT"

    def test_win_loss_and_match_wording_are_present(self):
        report = _build()
        html = " ".join(render([report]).split())
        assert "recorded match" in html
        assert "whole captured history" in html
