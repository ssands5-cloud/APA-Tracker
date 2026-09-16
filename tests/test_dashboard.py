"""Tests for ui/dashboard.py, the static Coach Dashboard that replaces
ui/dashboard_stub.py."""

from __future__ import annotations

import json

from analytics.opponent_risk_profile import OpponentRiskEntry
from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix
from analytics.player_matchup_engine import build_player_matchup_report
from analytics.team_matchup_engine import build_team_matchup_report
from ui.dashboard import render


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


def _matrix() -> PairingEvidenceMatrix:
    pairing = _pairing()
    return PairingEvidenceMatrix(
        our_team_external_id="OUR1", opponent_team_external_id="OPP1",
        format="8-Ball Open", session_name="Fall 2026",
        expected_pairings=((1, 2),), pairings=(pairing,),
        counts={"DIRECT": 1, "INDIRECT": 0, "UNKNOWN": 0, "total_feasible_pairings": 1},
        our_roster_available=True, opponent_roster_available=True,
    )


def _player_report(pairing=None, our_team="OUR1", opponent_team="OPP1", **kwargs):
    return build_player_matchup_report(pairing or _pairing(), our_team, opponent_team, **kwargs)


class TestRender:
    def test_a_self_contained_page_with_no_external_resources(self):
        html = render(
            [_player_report()],
            [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")],
            [],
            "Mark It Up",
        )
        assert "<html" in html
        assert "http://" not in html
        assert "https://" not in html

    def test_choosing_a_player_narrows_the_opponent_selector(self):
        report_a = _player_report()
        report_b = _player_report(_pairing(player_id=3, player_name="Carol", opponent_id=4, opponent_name="Dave"))
        html = render([report_a, report_b], [], [], "Mark It Up")

        start = html.index('id="cd-player-opponent-index">') + len('id="cd-player-opponent-index">')
        end = html.index("</script>", start)
        index = json.loads(html[start:end])
        assert [c["label"] for c in index["1"]] == ["Bob — OPP1 (8-Ball Open, Fall 2026)"]
        assert [c["label"] for c in index["3"]] == ["Dave — OPP1 (8-Ball Open, Fall 2026)"]

    def test_opponent_risk_profile_rows_are_purely_descriptive(self):
        entry = OpponentRiskEntry(
            opponent_team_external_id="OPP1", opponent_team_name="Corner Pockets",
            total_pairings=1, direct_pairing_count=1, direct_win_rate=0.75,
            sample_size=4, reliability_weighted_skill_probability=0.7,
        )
        html = render([], [], [entry], "Mark It Up")
        assert "Corner Pockets" in html
        assert "75.0%" in html
        # The page explains, in prose, that it never emits a categorical
        # verdict -- it must not actually emit one for this real entry.
        assert "Corner Pockets</td><td>Danger" not in html
        assert "Corner Pockets</td><td>Favored" not in html

    def test_an_empty_risk_profile_says_no_data_not_a_blank_table(self):
        html = render([], [], [], "Mark It Up")
        assert "No data" in html

    def test_a_name_containing_a_script_close_tag_cannot_break_out(self):
        html = render(
            [_player_report(_pairing(player_name="</script><script>alert(1)</script>"))],
            [], [], "Mark It Up",
        )
        assert "<script>alert(1)</script>" not in html

    def test_both_engines_embedded_json_is_present_and_valid(self):
        player_report = _player_report()
        team_report = build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")
        html = render([player_report], [team_report], [], "Mark It Up")

        for element_id in ("cd-player-data", "cd-player-opponent-index", "cd-team-data"):
            start = html.index(f'id="{element_id}">') + len(f'id="{element_id}">')
            end = html.index("</script>", start)
            json.loads(html[start:end])  # must not raise

    def test_the_opponent_ranking_never_narrates_a_toughest_or_favorable_verdict(self):
        html = " ".join(render(
            [], [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")], [], "Mark It Up",
        ).split())
        assert "experimental" in html.lower()
        # The prose note explaining WHY it's descriptive-only may say
        # "not a tactical verdict"; the generated summary itself must not
        # narrate a specific opponent as toughest/favorable.
        assert "toughest real matchup" not in html.lower()
        assert "most favorable real matchup" not in html.lower()

    def test_opponent_filter_controls_are_present(self):
        """Directive: skill level / streak(trend) / volatility filters on
        the Player vs Player selector."""
        html = render([_player_report()], [], [], "Mark It Up")
        assert 'id="pme-filter-sl-min"' in html
        assert 'id="pme-filter-sl-max"' in html
        assert 'id="pme-filter-vol-min"' in html
        assert 'class="pme-filter-trend"' in html

    def test_captains_edge_card_is_purely_descriptive(self):
        html = " ".join(render(
            [], [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")], [], "Mark It Up",
        ).split())
        assert "Captain's Edge" in html
        assert "Evidence coverage" in html
        # The card may explain, in prose, that it never emits a verdict --
        # it must not actually narrate a specific opponent as one.
        assert "is favored" not in html.lower()
        assert "danger player" not in html.lower()

    def test_lineup_table_carries_score_and_model_basis_context(self):
        """GPT audit P2 / directive: lineup context (score, model basis,
        sample) must be visible on the Coach Dashboard's own lineup table,
        not only in the standalone Team Matchup Engine export."""
        html = render([], [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")], [], "Mark It Up")
        assert "Score" in html
        assert "Model basis" in html
        assert "Sample" in html
