"""Tests for analytics/data_coverage.py (docs/captain_first_edge_experience.md §11)."""

from __future__ import annotations

from analytics.data_coverage import UNAVAILABLE_FIELDS, build_report
from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix


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


class TestMissingSkillLevels:
    def test_named_individually_not_just_counted(self):
        pairings = [
            _pairing(1, 10, EvidenceLabel.UNKNOWN, player_skill_level=None, player_name="Bob"),
            _pairing(2, 11, EvidenceLabel.UNKNOWN, opponent_skill_level=None, opponent_name="Carol"),
        ]
        report = build_report(_matrix(pairings))

        names = {(m.side, m.player_name) for m in report.missing_skill_levels}
        assert names == {("our", "Bob"), ("opponent", "Carol")}

    def test_a_player_missing_on_multiple_pairings_is_listed_once(self):
        pairings = [
            _pairing(1, 10, EvidenceLabel.UNKNOWN, player_skill_level=None, player_name="Bob"),
            _pairing(1, 11, EvidenceLabel.UNKNOWN, player_skill_level=None, player_name="Bob"),
        ]
        report = build_report(_matrix(pairings))

        assert len(report.missing_skill_levels) == 1

    def test_no_missing_skill_levels_is_an_honest_empty_tuple(self):
        pairings = [_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1)]
        report = build_report(_matrix(pairings))

        assert report.missing_skill_levels == ()


class TestEvidenceCoverage:
    def test_counts_and_percentages_match_the_matrix_exactly(self):
        pairings = [
            _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1),
            _pairing(1, 11, EvidenceLabel.INDIRECT, modeled_win_probability=0.6,
                     model_source="analytics.head_to_head:validated-skill-only"),
            _pairing(2, 10, EvidenceLabel.UNKNOWN, player_skill_level=None),
            _pairing(2, 11, EvidenceLabel.UNKNOWN, player_skill_level=None),
        ]
        report = build_report(_matrix(pairings))
        coverage = report.evidence_coverage

        assert coverage.direct_count == 1
        assert coverage.indirect_count == 1
        assert coverage.unknown_count == 2
        assert coverage.total == 4
        assert coverage.direct_pct == 0.25
        assert coverage.unknown_pct == 0.5

    def test_zero_feasible_pairings_gives_none_percentages_not_a_divide_by_zero(self):
        report = build_report(_matrix([]))

        assert report.evidence_coverage.total == 0
        assert report.evidence_coverage.direct_pct is None


class TestSampleSizes:
    def test_direct_carries_a_real_match_count_indirect_does_not(self):
        pairings = [
            _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=3),
            _pairing(1, 11, EvidenceLabel.INDIRECT, modeled_win_probability=0.6,
                     model_source="analytics.head_to_head:validated-skill-only"),
        ]
        report = build_report(_matrix(pairings))
        direct = next(s for s in report.sample_sizes if s.evidence_label is EvidenceLabel.DIRECT)
        indirect = next(s for s in report.sample_sizes if s.evidence_label is EvidenceLabel.INDIRECT)

        assert direct.direct_matches == 3
        assert indirect.direct_matches is None
        assert indirect.model_source == "analytics.head_to_head:validated-skill-only"

    def test_every_pairing_produces_exactly_one_sample_size_row(self):
        pairings = [
            _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1),
            _pairing(2, 11, EvidenceLabel.UNKNOWN, player_skill_level=None),
        ]
        report = build_report(_matrix(pairings))
        assert len(report.sample_sizes) == 2


class TestRefreshTimestamps:
    def test_real_values_are_carried_through_unchanged(self):
        report = build_report(
            _matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1)]),
            standings_refreshed_at="2026-09-09T23:11:36Z",
            career_stats_refreshed_at={"P-1": "2026-09-01T00:00:00Z"},
        )

        assert report.standings_refreshed_at == "2026-09-09T23:11:36Z"
        assert report.career_stats_refreshed_at == {"P-1": "2026-09-01T00:00:00Z"}

    def test_no_real_timestamp_is_none_never_a_synthetic_today_label(self):
        report = build_report(_matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1)]))

        assert report.standings_refreshed_at is None
        assert report.career_stats_refreshed_at == {}


class TestUnavailableFields:
    def test_the_fixed_disclosure_list_is_always_present(self):
        report = build_report(_matrix([]))

        assert report.unavailable_fields == UNAVAILABLE_FIELDS
        assert any("innings" in f.lower() for f in report.unavailable_fields)
        assert any("defensive-shot" in f.lower() for f in report.unavailable_fields)
        assert any("roster" in f.lower() for f in report.unavailable_fields)
