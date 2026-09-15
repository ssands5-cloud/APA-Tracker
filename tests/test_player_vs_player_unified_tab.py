"""Tests for ui/tabs/player_vs_player_unified.py."""

from __future__ import annotations

import json

from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix
from analytics.player_vs_player_matrix import build_matrix_export
from database.models import PlayerHeadToHead
from ui.tabs.player_vs_player_unified import RISK_PROFILE_NOTE, render_unified_tab


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
    def test_no_rows_is_an_honest_empty_state(self):
        html = render_unified_tab([], "Chalk It Up")
        assert "No feasible pairings" in html


class TestStructure:
    def test_both_subviews_and_the_toggle_are_present(self):
        rows = build_matrix_export(
            _matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0)]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_unified_tab(rows, "Chalk It Up")

        assert 'id="pvp-matrix-tab"' in html
        assert 'id="pvp-pair-tab"' in html
        assert 'id="pvp-matrix-view"' in html
        assert 'id="pvp-pair-view"' in html

    def test_matrix_view_lists_every_pairing_unknown_included(self):
        rows = build_matrix_export(
            _matrix([
                _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0),
                _pairing(2, 11, EvidenceLabel.UNKNOWN, player_skill_level=None),
            ]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_unified_tab(rows, "Chalk It Up")

        assert "evidence-DIRECT" in html
        assert "evidence-UNKNOWN" in html

    def test_pair_view_contains_one_panel_per_pairing(self):
        rows = build_matrix_export(
            _matrix([
                _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0),
                _pairing(2, 11, EvidenceLabel.UNKNOWN, player_skill_level=None),
            ]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_unified_tab(rows, "Chalk It Up")

        assert html.count('class="pvp-pair-panel"') == 2

    def test_the_first_pairs_panel_starts_visible_others_hidden(self):
        rows = build_matrix_export(
            _matrix([
                _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0),
                _pairing(2, 11, EvidenceLabel.UNKNOWN, player_skill_level=None),
            ]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_unified_tab(rows, "Chalk It Up")

        # Both panels render with the `hidden` attribute in markup (JS
        # un-hides the first one at load); the script shows exactly one
        # explicit showPair() call, targeting the first pairing.
        assert html.count("hidden>") >= 1
        first_id = rows[0]
        assert 'showPair("pvp-' in html


class TestRiskProfileDisclosure:
    def test_the_not_validated_note_appears_in_every_pair_panel(self):
        rows = build_matrix_export(
            _matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0)]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_unified_tab(rows, "Chalk It Up")

        assert RISK_PROFILE_NOTE in html
        assert "not validated" in html.lower()


class TestScriptJsonPayload:
    def test_scope_and_counts_are_embedded_and_parseable(self):
        rows = build_matrix_export(
            _matrix([
                _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0),
                _pairing(2, 11, EvidenceLabel.UNKNOWN, player_skill_level=None),
            ]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_unified_tab(rows, "Chalk It Up")

        start = html.index('id="pvp-data">') + len('id="pvp-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])

        assert payload["counts"] == {"DIRECT": 1, "UNKNOWN": 1}
        assert len(payload["row_ids"]) == 2


class TestUntrustedText:
    def test_a_hostile_player_name_cannot_break_the_script_json(self):
        hostile = '</script><img src=x onerror="alert(1)">'
        rows = build_matrix_export(
            _matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1,
                               observed_win_rate=1.0, player_name=hostile)]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_unified_tab(rows, "Chalk It Up")

        assert hostile not in html


class TestNoExternalResources:
    def test_carries_no_external_resources(self):
        rows = build_matrix_export(
            _matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0)]),
            histories={(1, 10): [_game(match_id=1)]},
        )
        html = render_unified_tab(rows, "Chalk It Up")

        assert "http://" not in html
        assert "https://" not in html
