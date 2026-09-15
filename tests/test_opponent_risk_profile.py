"""Tests for analytics/opponent_risk_profile.py."""

from __future__ import annotations

from analytics.head_to_head import skill_only_win_probability
from analytics.opponent_risk_profile import build_profile, profile_for
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


class TestDirectWinRate:
    def test_unweighted_mean_of_direct_pairings_only(self):
        matrix = _matrix([
            _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0),
            _pairing(2, 10, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=0.0),
            _pairing(3, 10, EvidenceLabel.INDIRECT, modeled_win_probability=0.6,
                     model_source="analytics.head_to_head:validated-skill-only"),
        ])
        entry = profile_for("T1", "Corner Pockets", matrix)

        assert entry.direct_win_rate == 0.5
        assert entry.direct_pairing_count == 2
        assert entry.sample_size == 2

    def test_no_direct_pairings_is_none_not_zero(self):
        matrix = _matrix([_pairing(1, 10, EvidenceLabel.UNKNOWN, player_skill_level=None)])
        entry = profile_for("T1", "Corner Pockets", matrix)

        assert entry.direct_win_rate is None
        assert entry.sample_size == 0


class TestReliabilityWeightedSkillProbability:
    def test_direct_pairings_are_weighted_more_than_indirect(self):
        # Two pairings with different skill-only values: one DIRECT with a
        # real record (higher weight), one INDIRECT (baseline weight 1).
        direct = _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=5,
                           observed_win_rate=1.0, player_skill_level=6, opponent_skill_level=3)
        indirect = _pairing(2, 10, EvidenceLabel.INDIRECT, modeled_win_probability=0.5,
                             model_source="analytics.head_to_head:validated-skill-only",
                             player_skill_level=4, opponent_skill_level=4)
        matrix = _matrix([direct, indirect])
        entry = profile_for("T1", "Corner Pockets", matrix)

        direct_skill = skill_only_win_probability(6, 3)
        indirect_skill = skill_only_win_probability(4, 4)
        expected = (6 * direct_skill + 1 * indirect_skill) / 7
        assert entry.reliability_weighted_skill_probability == round(expected, 4)

    def test_no_scoreable_pairing_at_all_is_none(self):
        matrix = _matrix([_pairing(1, 10, EvidenceLabel.UNKNOWN, player_skill_level=None)])
        entry = profile_for("T1", "Corner Pockets", matrix)

        assert entry.reliability_weighted_skill_probability is None

    def test_an_opponent_with_only_indirect_pairings_still_gets_a_value(self):
        matrix = _matrix([
            _pairing(1, 10, EvidenceLabel.INDIRECT, modeled_win_probability=0.6,
                     model_source="analytics.head_to_head:validated-skill-only"),
        ])
        entry = profile_for("T1", "Corner Pockets", matrix)

        assert entry.reliability_weighted_skill_probability is not None


class TestBuildProfile:
    def test_sorted_toughest_first_by_skill_probability(self):
        tough = _matrix([_pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1,
                                   observed_win_rate=0.0, player_skill_level=3, opponent_skill_level=6)])
        easy = _matrix([_pairing(2, 11, EvidenceLabel.DIRECT, direct_evidence_count=1,
                                  observed_win_rate=1.0, player_skill_level=6, opponent_skill_level=3)])
        profiles = build_profile([
            ("T-EASY", "Easy Team", easy),
            ("T-TOUGH", "Tough Team", tough),
        ])

        assert [p.opponent_team_name for p in profiles] == ["Tough Team", "Easy Team"]

    def test_an_opponent_with_no_signal_sorts_last(self):
        unknown = _matrix([_pairing(1, 10, EvidenceLabel.UNKNOWN, player_skill_level=None)])
        known = _matrix([_pairing(2, 11, EvidenceLabel.DIRECT, direct_evidence_count=1, observed_win_rate=1.0)])
        profiles = build_profile([
            ("T-UNKNOWN", "Unknown Team", unknown),
            ("T-KNOWN", "Known Team", known),
        ])

        assert profiles[-1].opponent_team_name == "Unknown Team"

    def test_every_real_opponent_is_represented_exactly_once(self):
        matrices = [
            (f"T{i}", f"Team {i}", _matrix([_pairing(1, 10 + i, EvidenceLabel.UNKNOWN, player_skill_level=None)]))
            for i in range(5)
        ]
        profiles = build_profile(matrices)
        assert len(profiles) == 5
