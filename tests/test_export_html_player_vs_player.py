"""Tests for ui/export_html_player_vs_player.py."""

from __future__ import annotations

from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix
from analytics.player_vs_player_matrix import build_matrix_export
from database.models import PlayerHeadToHead
from ui.export_html_player_vs_player import render_export


def _pairing(player_id, opponent_id, label, **kwargs):
    defaults = dict(
        player_external_id=f"P-{player_id}", player_name=f"Player {player_id}",
        player_skill_level=5, opponent_external_id=f"OPP-{opponent_id}",
        opponent_name=f"Opponent {opponent_id}", opponent_skill_level=4,
        format="8-Ball Open", session_name="Fall 2026",
        observed_win_rate=None, direct_evidence_count=0,
        modeled_win_probability=None, model_source=None,
    )
    defaults.update(kwargs)
    return PairingEvidence(player_id=player_id, opponent_id=opponent_id,
                            evidence_label=label, **defaults)


def _matrix(pairings):
    counts = {label.value: 0 for label in EvidenceLabel}
    for p in pairings:
        counts[p.evidence_label.value] += 1
    counts["total_feasible_pairings"] = len(pairings)
    return PairingEvidenceMatrix(
        our_team_external_id="OUR", opponent_team_external_id="THEIRS",
        format="8-Ball Open", session_name="Fall 2026",
        expected_pairings=tuple((p.player_id, p.opponent_id) for p in pairings),
        pairings=tuple(pairings), counts=counts,
        our_roster_available=True, opponent_roster_available=True,
    )


def _game(player_id=1, opponent_id=10, result="W", match_id=1):
    return PlayerHeadToHead(
        player_id=player_id, opponent_id=opponent_id, match_id=match_id, result=result,
        own_skill_level=5, opponent_skill_level=4,
        format="8-Ball Open", session_name="Fall 2026",
    )


class TestEmptyState:
    def test_no_rows_is_an_honest_empty_page(self):
        html = render_export([])
        assert "No feasible pairings" in html


class TestSummaryAndDetail:
    def test_every_row_appears_in_the_summary_and_has_a_detail_section(self):
        rows = build_matrix_export(
            _matrix([
                _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0),
                _pairing(2, 11, EvidenceLabel.UNKNOWN, player_skill_level=None),
            ]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_export(rows)

        assert "evidence-DIRECT" in html
        assert "evidence-UNKNOWN" in html
        assert "Player 1 vs Opponent 10" in html
        assert "Player 2 vs Opponent 11" in html

    def test_unknown_rows_are_never_hidden(self):
        rows = build_matrix_export(
            _matrix([_pairing(1, 10, EvidenceLabel.UNKNOWN, player_skill_level=None)]),
            histories={},
        )
        html = render_export(rows)

        assert "UNKNOWN" in html
        assert "No data" in html

    def test_counts_summary_reflects_the_real_mix(self):
        rows = build_matrix_export(
            _matrix([
                _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0),
                _pairing(1, 11, EvidenceLabel.INDIRECT, modeled_win_probability=0.6,
                         model_source="analytics.head_to_head:validated-skill-only"),
                _pairing(2, 10, EvidenceLabel.UNKNOWN, player_skill_level=None),
            ]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_export(rows)

        assert "1 DIRECT" in html
        assert "1 INDIRECT" in html
        assert "1 UNKNOWN" in html


class TestNoExternalResources:
    def test_carries_no_external_resources(self):
        rows = build_matrix_export(
            _matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0)]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_export(rows)

        assert "http://" not in html
        assert "https://" not in html


class TestUntrustedText:
    def test_a_hostile_player_name_cannot_break_the_page(self):
        hostile = '</script><img src=x onerror="alert(1)">'
        rows = build_matrix_export(
            _matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1,
                               observed_win_rate=1.0, player_name=hostile)]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_export(rows)

        assert hostile not in html
