"""Tests for ui/tabs/data_coverage.py."""

from __future__ import annotations

from analytics.data_coverage import build_report
from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix
from ui.tabs.data_coverage import render


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


class TestRender:
    def test_evidence_coverage_counts_and_percentages_appear(self):
        report = build_report(_matrix([
            _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1),
            _pairing(2, 11, EvidenceLabel.UNKNOWN, player_skill_level=None),
        ]))
        html = render(report, "Chalk It Up", "Corner Pockets")

        assert "50.0%" in html
        assert "Chalk It Up" in html
        assert "Corner Pockets" in html

    def test_missing_skill_levels_are_named_individually(self):
        report = build_report(_matrix([
            _pairing(1, 10, EvidenceLabel.UNKNOWN, player_skill_level=None, player_name="Bob"),
        ]))
        html = render(report, "Us", "Them")

        assert "Bob" in html
        assert "Our" in html

    def test_no_missing_skill_levels_says_so_honestly(self):
        report = build_report(_matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1)]))
        html = render(report, "Us", "Them")

        assert "every player in this matrix has a real posted skill level" in html

    def test_missing_refresh_timestamp_shows_no_data_not_a_guess(self):
        report = build_report(_matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1)]))
        html = render(report, "Us", "Them")

        assert "No data" in html

    def test_unavailable_fields_are_always_listed(self):
        report = build_report(_matrix([]))
        html = render(report, "Us", "Them")

        assert "innings" in html.lower()
        assert "defensive-shot" in html.lower()

    def test_no_external_resources(self):
        report = build_report(_matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1)]))
        html = render(report, "Us", "Them")

        assert "http://" not in html
        assert "https://" not in html
