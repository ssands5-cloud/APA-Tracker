"""Tests for ui/tabs/tonights_match.py (Stage 2 rendering).

This module is a REPORTER over analytics.pairing_evidence's own output --
these tests build PairingEvidence/PairingEvidenceMatrix objects directly
(the same real dataclasses Stage 1 produces) and assert the rendered page
never recomputes a label or a rate, always shows "No data" for a missing
one, and never hides an UNKNOWN pairing.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix
from ui.tabs.tonights_match import MatchScope, render


def _pairing(
    player_id=1, opponent_id=10, label=EvidenceLabel.DIRECT,
    observed_win_rate=1.0, direct_evidence_count=1,
    modeled_win_probability=None, model_source=None,
    player_skill_level=5, opponent_skill_level=4,
):
    return PairingEvidence(
        player_id=player_id,
        player_external_id=f"P-{player_id}",
        player_name=f"Player {player_id}",
        player_skill_level=player_skill_level,
        opponent_id=opponent_id,
        opponent_external_id=f"OPP-{opponent_id}",
        opponent_name=f"Opponent {opponent_id}",
        opponent_skill_level=opponent_skill_level,
        format="8-Ball Open",
        session_name="Fall 2026",
        evidence_label=label,
        observed_win_rate=observed_win_rate,
        direct_evidence_count=direct_evidence_count,
        modeled_win_probability=modeled_win_probability,
        model_source=model_source,
    )


def _matrix(pairings, *, our_roster_available=True, opponent_roster_available=True):
    counts = {label.value: 0 for label in EvidenceLabel}
    for p in pairings:
        counts[p.evidence_label.value] += 1
    counts["total_feasible_pairings"] = len(pairings)
    return PairingEvidenceMatrix(
        our_team_external_id="OUR",
        opponent_team_external_id="THEIRS",
        format="8-Ball Open",
        session_name="Fall 2026",
        expected_pairings=tuple((p.player_id, p.opponent_id) for p in pairings),
        pairings=tuple(pairings),
        counts=counts,
        our_roster_available=our_roster_available,
        opponent_roster_available=opponent_roster_available,
    )


class TestEmptyState:
    def test_no_scopes_is_an_honest_empty_page_not_a_guess(self):
        html = render([], "Chalk It Up")
        assert "No real scheduled match was found" in html
        assert "<html>" in html


class TestNoExternalResources:
    def test_a_real_page_carries_no_external_resources(self):
        matrix = _matrix([_pairing()])
        scope = MatchScope("Fall 2026", "THEIRS", "Corner Pockets", "8-Ball Open", matrix)
        html = render([scope], "Chalk It Up")
        assert "http://" not in html
        assert "https://" not in html


class TestPayloadFidelity:
    def test_every_evidence_label_is_present_in_the_embedded_payload(self):
        pairings = [
            _pairing(1, 10, EvidenceLabel.DIRECT, observed_win_rate=1.0, direct_evidence_count=1),
            _pairing(2, 10, EvidenceLabel.INDIRECT, observed_win_rate=None,
                     direct_evidence_count=0, modeled_win_probability=0.62,
                     model_source="analytics.head_to_head:validated-skill-only"),
            _pairing(3, 10, EvidenceLabel.UNKNOWN, observed_win_rate=None,
                     direct_evidence_count=0, player_skill_level=None),
        ]
        matrix = _matrix(pairings)
        scope = MatchScope("Fall 2026", "THEIRS", "Corner Pockets", "8-Ball Open", matrix)
        html = render([scope], "Chalk It Up")

        start = html.index("var TM_PAYLOAD = ") + len("var TM_PAYLOAD = ")
        end = html.index(";\n", start)
        payload = json.loads(html[start:end])
        rows = list(payload.values())[0]["pairings"]

        labels = {row["player_id"]: row["evidence_label"] for row in rows}
        assert labels == {1: "DIRECT", 2: "INDIRECT", 3: "UNKNOWN"}

        unknown_row = next(r for r in rows if r["player_id"] == 3)
        assert unknown_row["observed_win_rate"] is None
        assert unknown_row["modeled_win_probability"] is None
        assert unknown_row["player_skill_level"] is None

    def test_no_pairing_is_dropped_from_the_embedded_payload(self):
        pairings = [_pairing(i, 10, EvidenceLabel.UNKNOWN, observed_win_rate=None,
                              direct_evidence_count=0) for i in range(5)]
        matrix = _matrix(pairings)
        scope = MatchScope("Fall 2026", "THEIRS", "Corner Pockets", "8-Ball Open", matrix)
        html = render([scope], "Chalk It Up")

        start = html.index("var TM_PAYLOAD = ") + len("var TM_PAYLOAD = ")
        end = html.index(";\n", start)
        payload = json.loads(html[start:end])
        rows = list(payload.values())[0]["pairings"]
        assert len(rows) == 5


class TestUnavailableScope:
    def test_an_unresolvable_scope_is_still_a_real_option_with_its_reason(self):
        scope = MatchScope(
            "Fall 2026", "THEIRS", "Corner Pockets", "8-Ball Open",
            matrix=None, unavailable_reason="Multiple current roster rows exist",
        )
        html = render([scope], "Chalk It Up")

        start = html.index("var TM_OPTIONS = ") + len("var TM_OPTIONS = ")
        end = html.index(";\n", start)
        options = json.loads(html[start:end])
        [option] = options
        assert option["available"] is False
        assert option["unavailable_reason"] == "Multiple current roster rows exist"

    def test_scope_requires_exactly_one_result_or_reason(self):
        matrix = _matrix([_pairing()])
        with pytest.raises(ValueError, match="exactly one"):
            MatchScope("Fall 2026", "THEIRS", "Corner Pockets", "8-Ball Open", None)
        with pytest.raises(ValueError, match="exactly one"):
            MatchScope(
                "Fall 2026",
                "THEIRS",
                "Corner Pockets",
                "8-Ball Open",
                matrix,
                unavailable_reason="contradictory",
            )


class TestUntrustedText:
    def test_database_text_cannot_end_script_or_inject_inner_html(self):
        hostile = '</script><img src=x onerror="alert(1)">'
        pairing = replace(
            _pairing(),
            player_name=hostile,
            opponent_name="<b>Opponent</b>",
            model_source=hostile,
        )
        scope = MatchScope("Fall 2026", "THEIRS", hostile, "8-Ball Open", _matrix([pairing]))

        html = render([scope], hostile, our_team_external_id="OUR")

        assert hostile not in html
        assert "\\u003c/script\\u003e" in html
        assert "function tmEsc(value)" in html

        start = html.index("var TM_PAYLOAD = ") + len("var TM_PAYLOAD = ")
        end = html.index(";\n", start)
        payload = json.loads(html[start:end])
        row = list(payload.values())[0]["pairings"][0]
        assert row["player_name"] == hostile


class TestRosterAvailability:
    def test_missing_rosters_are_explicit_instead_of_looking_like_zero_players(self):
        matrix = _matrix(
            [],
            our_roster_available=False,
            opponent_roster_available=False,
        )
        scope = MatchScope("Fall 2026", "THEIRS", "Corner Pockets", "8-Ball Open", matrix)

        html = render([scope], "Chalk It Up")

        assert '"our_roster_available": false' in html
        assert '"opponent_roster_available": false' in html
        assert "Our canonical current roster is unavailable" in html
        assert "The opponent canonical current roster is unavailable" in html


class TestControlsArePresent:
    def test_all_five_real_controls_render(self):
        matrix = _matrix([_pairing()])
        scope = MatchScope("Fall 2026", "THEIRS", "Corner Pockets", "8-Ball Open", matrix)
        html = render([scope], "Chalk It Up", our_team_external_id="OUR")
        assert 'id="tm-team"' in html
        assert '<option value="OUR">Chalk It Up</option>' in html
        assert 'id="tm-session"' in html
        assert '<option value="">Select session&hellip;</option>' in html
        assert 'id="tm-opponent"' in html
        assert 'id="tm-format"' in html
        assert 'tm-avail' in html
        assert "Chalk It Up" in html

    def test_availability_toggle_is_safe_before_a_matrix_is_selected(self):
        matrix = _matrix([_pairing()])
        scope = MatchScope("Fall 2026", "THEIRS", "Corner Pockets", "8-Ball Open", matrix)

        html = render([scope], "Chalk It Up")

        assert 'if (countTarget) {' in html
