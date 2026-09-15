"""Opponent Risk Profile: a purely descriptive, whole-opponent ranking for
Captain's Edge.

Derived ONLY from already-validated, real fields -- no new blending, no
categorical danger/favorable flag, no threshold of any kind, and
`analytics.win_probability`'s excluded modeled estimate is never imported
or consulted:

    DIRECT win rate                    analytics.pairing_evidence's own
                                        PairingEvidence.observed_win_rate
    sample size                        PairingEvidence.direct_evidence_count
    reliability-weighted skill-only
    probability                        analytics.head_to_head
                                        .skill_only_win_probability, graded
                                        against 106 recorded outcomes in
                                        docs/prediction_validation.md,
                                        combined with a standard weighted
                                        mean (not a new predictive model)

This module ranks opponents; it does not label them. "Recommended Avoid" /
"Recommended Target" are explicitly NOT produced here -- see
docs/player_vs_player_html_structure.md's own rule (posted to Issue #14):
those flags render "Not available -- threshold not validated" until a
real, sourced, checked threshold exists. Nothing in this module invents
one.

Purely computational, like every other analytics module in this project:
takes already-built PairingEvidenceMatrix objects (one per real opponent
scope) and computes. Queries nothing itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from analytics.head_to_head import skill_only_win_probability
from analytics.pairing_evidence import EvidenceLabel, PairingEvidenceMatrix

# A standard weighted-mean weight, not a new statistical model: an
# INDIRECT/UNKNOWN pairing (no real head-to-head history) gets the
# baseline weight of 1; a DIRECT pairing's weight grows with its own real
# distinct-match count, so a well-established real record counts for more
# than a single game or a skill-only estimate, without ever reaching zero
# (which would make an opponent with no DIRECT history at all silently
# drop out of the weighted average).
def _pairing_weight(direct_evidence_count: int) -> int:
    return 1 + direct_evidence_count


@dataclass(frozen=True)
class OpponentRiskEntry:
    """One real opponent team's descriptive profile -- a ranking input,
    never a categorical verdict."""

    opponent_team_external_id: str
    opponent_team_name: str
    total_pairings: int
    direct_pairing_count: int
    direct_win_rate: Optional[float]
    sample_size: int
    reliability_weighted_skill_probability: Optional[float]


def _direct_win_rate(matrix: PairingEvidenceMatrix) -> Optional[float]:
    """Unweighted mean of each DIRECT pairing's own observed_win_rate --
    deliberately not a total-wins/total-games reconstruction, which would
    require inferring integer win/loss counts back out of a rounded
    percentage and risk a fabricated precision that was never really
    there."""
    rates = [
        p.observed_win_rate
        for p in matrix.pairings
        if p.evidence_label is EvidenceLabel.DIRECT and p.observed_win_rate is not None
    ]
    return round(sum(rates) / len(rates), 4) if rates else None


def _sample_size(matrix: PairingEvidenceMatrix) -> int:
    return sum(
        p.direct_evidence_count
        for p in matrix.pairings
        if p.evidence_label is EvidenceLabel.DIRECT
    )


def _reliability_weighted_skill_probability(matrix: PairingEvidenceMatrix) -> Optional[float]:
    weighted_sum = 0.0
    total_weight = 0
    for p in matrix.pairings:
        probability = skill_only_win_probability(p.player_skill_level, p.opponent_skill_level)
        if probability is None:
            continue
        weight = _pairing_weight(
            p.direct_evidence_count if p.evidence_label is EvidenceLabel.DIRECT else 0
        )
        weighted_sum += weight * probability
        total_weight += weight
    return round(weighted_sum / total_weight, 4) if total_weight else None


def profile_for(
    opponent_team_external_id: str, opponent_team_name: str, matrix: PairingEvidenceMatrix
) -> OpponentRiskEntry:
    """One real opponent's descriptive profile from one real, already-
    classified matrix."""
    direct_count = sum(1 for p in matrix.pairings if p.evidence_label is EvidenceLabel.DIRECT)
    return OpponentRiskEntry(
        opponent_team_external_id=opponent_team_external_id,
        opponent_team_name=opponent_team_name,
        total_pairings=len(matrix.pairings),
        direct_pairing_count=direct_count,
        direct_win_rate=_direct_win_rate(matrix),
        sample_size=_sample_size(matrix),
        reliability_weighted_skill_probability=_reliability_weighted_skill_probability(matrix),
    )


def build_profile(
    matrices: Sequence[tuple[str, str, PairingEvidenceMatrix]]
) -> tuple[OpponentRiskEntry, ...]:
    """Every real opponent's descriptive profile, sorted lowest
    reliability-weighted skill probability first (our toughest matchups by
    this one real, validated signal, shown first) -- purely descriptive
    ordering, never a categorical cutoff. An opponent with no scoreable
    signal at all (``None``) sorts last, never assumed average.
    """
    entries = [profile_for(team_id, name, matrix) for team_id, name, matrix in matrices]
    return tuple(sorted(
        entries,
        key=lambda e: (
            e.reliability_weighted_skill_probability is None,
            e.reliability_weighted_skill_probability
            if e.reliability_weighted_skill_probability is not None else 0.0,
            e.opponent_team_name.lower(),
        ),
    ))
