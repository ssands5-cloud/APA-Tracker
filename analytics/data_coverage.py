"""Data Coverage: docs/captain_first_edge_experience.md §11.

A dedicated view, separate from the matrix, answering "how much of this
can I actually trust right now" -- missing skill levels named
individually, real sample sizes, DIRECT/INDIRECT/UNKNOWN coverage as
counts and percentages, real refresh timestamps, and an explicit list of
what this project cannot honestly provide at all.

Purely computational, like every other analytics module in this project:
takes an already-built ``analytics.pairing_evidence.PairingEvidenceMatrix``
plus already-fetched real refresh timestamps, and computes. Queries
nothing itself -- a builder (e.g. scripts/build_data_coverage.py) is
responsible for fetching the matrix and the two real timestamp signals
(StandingsSnapshot.captured_at, PlayerCareerStats.updated_at) this module
consumes.

Nothing here recomputes an evidence label, a rate, or a probability --
every number is either copied from the matrix's own real fields or a
direct, real count/percentage over them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from analytics.pairing_evidence import EvidenceLabel, PairingEvidenceMatrix

# Real, fixed disclosure text -- these are gaps in what this project's
# captured data can support at all, not something that varies scope to
# scope. See docs/captain_first_edge_experience.md §11's own list and
# docs/matchups.md's "Two things this deliberately doesn't include".
UNAVAILABLE_FIELDS = (
    "Innings (not captured by APA's API at any grain).",
    "Per-opponent defensive-shot average (only a lifetime, career-wide "
    "figure exists: PlayerCareerStats.defensive_shot_avg).",
    "A canonical current-roster signal for any opponent player never "
    "captured by a real roster/TeamStat ingest (see §12 of "
    "docs/captain_first_edge_experience.md) -- such a player is not listed "
    "in this matrix at all, not silently assumed absent.",
    "Per-player sync timestamps finer than the two real signals this "
    "report shows (StandingsSnapshot.captured_at, "
    "PlayerCareerStats.updated_at).",
)


@dataclass(frozen=True)
class MissingSkillLevel:
    """One real player, on one real side of the matrix, with no posted
    skill level -- named individually, not just counted (§11's own
    requirement)."""

    side: str  # "our" or "opponent"
    player_id: int
    player_external_id: str
    player_name: str


@dataclass(frozen=True)
class EvidenceCoverage:
    """Real DIRECT/INDIRECT/UNKNOWN counts and percentages over the total
    feasible pairings -- copied from the matrix's own already-reconciled
    ``counts``, never recomputed."""

    direct_count: int
    indirect_count: int
    unknown_count: int
    total: int
    direct_pct: Optional[float]
    indirect_pct: Optional[float]
    unknown_pct: Optional[float]


@dataclass(frozen=True)
class SampleSize:
    """The real sample size backing one pairing's evidence -- a distinct
    authoritative-match count for DIRECT, or the two real skill inputs and
    model source for INDIRECT. Never a fabricated "games" count for
    INDIRECT, which has no game-count sample at all."""

    player_id: int
    player_name: str
    opponent_id: int
    opponent_name: str
    evidence_label: EvidenceLabel
    direct_matches: Optional[int]
    player_skill_level: Optional[int]
    opponent_skill_level: Optional[int]
    model_source: Optional[str]


@dataclass(frozen=True)
class DataCoverageReport:
    our_team_external_id: str
    opponent_team_external_id: str
    format: str
    session_name: str
    missing_skill_levels: tuple[MissingSkillLevel, ...]
    evidence_coverage: EvidenceCoverage
    sample_sizes: tuple[SampleSize, ...]
    standings_refreshed_at: Optional[str]
    career_stats_refreshed_at: Mapping[str, Optional[str]]
    unavailable_fields: tuple[str, ...] = UNAVAILABLE_FIELDS


def _pct(count: int, total: int) -> Optional[float]:
    return round(count / total, 4) if total else None


def _evidence_coverage(matrix: PairingEvidenceMatrix) -> EvidenceCoverage:
    counts = matrix.counts
    total = counts["total_feasible_pairings"]
    return EvidenceCoverage(
        direct_count=counts["DIRECT"],
        indirect_count=counts["INDIRECT"],
        unknown_count=counts["UNKNOWN"],
        total=total,
        direct_pct=_pct(counts["DIRECT"], total),
        indirect_pct=_pct(counts["INDIRECT"], total),
        unknown_pct=_pct(counts["UNKNOWN"], total),
    )


def _missing_skill_levels(matrix: PairingEvidenceMatrix) -> tuple[MissingSkillLevel, ...]:
    seen: dict[tuple[str, int], MissingSkillLevel] = {}
    for pairing in matrix.pairings:
        if pairing.player_skill_level is None:
            key = ("our", pairing.player_id)
            seen.setdefault(key, MissingSkillLevel(
                "our", pairing.player_id, pairing.player_external_id, pairing.player_name,
            ))
        if pairing.opponent_skill_level is None:
            key = ("opponent", pairing.opponent_id)
            seen.setdefault(key, MissingSkillLevel(
                "opponent", pairing.opponent_id, pairing.opponent_external_id,
                pairing.opponent_name,
            ))
    return tuple(sorted(seen.values(), key=lambda m: (m.side, m.player_name.lower())))


def _sample_sizes(matrix: PairingEvidenceMatrix) -> tuple[SampleSize, ...]:
    return tuple(
        SampleSize(
            player_id=p.player_id, player_name=p.player_name,
            opponent_id=p.opponent_id, opponent_name=p.opponent_name,
            evidence_label=p.evidence_label,
            direct_matches=p.direct_evidence_count if p.evidence_label is EvidenceLabel.DIRECT else None,
            player_skill_level=p.player_skill_level,
            opponent_skill_level=p.opponent_skill_level,
            model_source=p.model_source,
        )
        for p in matrix.pairings
    )


def build_report(
    matrix: PairingEvidenceMatrix,
    *,
    standings_refreshed_at: Optional[str] = None,
    career_stats_refreshed_at: Optional[Mapping[str, Optional[str]]] = None,
) -> DataCoverageReport:
    """Every real coverage fact this project has for one already-classified
    matrix. ``standings_refreshed_at`` and ``career_stats_refreshed_at``
    are the caller's real, already-fetched values (ISO-8601 strings, or
    ``None``/omitted when no real row exists) -- this module does not
    query the database and does not invent a "last updated: today" label
    when neither is supplied.
    """
    return DataCoverageReport(
        our_team_external_id=matrix.our_team_external_id,
        opponent_team_external_id=matrix.opponent_team_external_id,
        format=matrix.format,
        session_name=matrix.session_name,
        missing_skill_levels=_missing_skill_levels(matrix),
        evidence_coverage=_evidence_coverage(matrix),
        sample_sizes=_sample_sizes(matrix),
        standings_refreshed_at=standings_refreshed_at,
        career_stats_refreshed_at=dict(career_stats_refreshed_at or {}),
    )
