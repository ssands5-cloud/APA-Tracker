"""Team Matchup Engine (Coach Mode): a purely descriptive, whole-team
comparison for a coach preparing for one real scheduled match.

Like ``analytics.opponent_risk_profile`` (which this module mirrors at
player-within-one-matchup granularity instead of that module's
cross-division team granularity), this is a REPORTER: it takes an
already-built ``analytics.pairing_evidence.PairingEvidenceMatrix`` and an
already-computed ``analytics.lineup_lab.LineupLabResult`` (or its real
error) and aggregates them. It queries nothing itself and recomputes no
probability -- every number traces to Stage 1's classifier
(``pairing_evidence``) or Stage 3's approved lineup solver (``lineup_lab``).

"Danger players" / "weak spots" are ranked, never labeled: the same
purely-descriptive convention ``analytics.opponent_risk_profile`` already
uses ("this module ranks opponents; it does not label them"), because this
project has repeatedly had to fail-close invented, unfitted categorical
danger thresholds (docs/captain_first_edge_experience.md §13). A coach
reads the ranking and applies their own judgment; this module supplies the
real, validated signal, not a verdict.

"Board" in this module's output means "this one scope's own computed
Lineup Lab slot," numbered for display only -- this project's data model
has no persisted, stable per-player board/position identity
(``matchPositionNumber`` is a transient per-scoresheet field, paired once
in ``scraper/graphql_scraper.py::head_to_head_rows()`` and never stored as
an ongoing player attribute). A claim like "favored on board 2" would
otherwise imply a fixed board assignment that doesn't exist in the real
data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from analytics.head_to_head import skill_only_win_probability
from analytics.lineup_lab import LineupLabResult
from analytics.pairing_evidence import EvidenceLabel, PairingEvidenceMatrix
from analytics.player_matchup_engine import SkillTrendInfo, NO_SKILL_TREND


def _pairing_weight(direct_evidence_count: int) -> int:
    """Same standard weighted-mean weight as
    ``analytics.opponent_risk_profile._pairing_weight``: a pairing with no
    DIRECT history still counts (weight 1), one with real DIRECT games
    counts more, and no pairing ever reaches zero weight."""
    return 1 + direct_evidence_count


@dataclass(frozen=True)
class RosterEntry:
    """One real current-roster player, from the matrix's own already-
    resolved identity -- never re-queried."""

    player_id: int
    player_external_id: str
    player_name: str
    skill_level: Optional[int]
    trend: SkillTrendInfo


@dataclass(frozen=True)
class RankedOpponent:
    """One real opponent player's descriptive ranking signal within this
    one team matchup -- a ranking input, never a categorical verdict (see
    module docstring)."""

    opponent_id: int
    opponent_external_id: str
    opponent_name: str
    opponent_skill_level: Optional[int]
    direct_win_rate: Optional[float]
    direct_sample_size: int
    reliability_weighted_skill_probability: Optional[float]


def _direct_win_rate_and_sample(
    matrix: PairingEvidenceMatrix, opponent_id: int
) -> tuple[Optional[float], int]:
    """Unweighted mean of this opponent's own DIRECT observed_win_rate
    across whichever of our players have DIRECT history against them --
    deliberately not a total-wins/total-games reconstruction, matching
    ``analytics.opponent_risk_profile._direct_win_rate``'s own reasoning:
    that would require inferring integer win/loss counts back out of a
    rounded percentage."""
    rates = [
        p.observed_win_rate
        for p in matrix.pairings
        if p.opponent_id == opponent_id
        and p.evidence_label is EvidenceLabel.DIRECT
        and p.observed_win_rate is not None
    ]
    sample = sum(
        p.direct_evidence_count
        for p in matrix.pairings
        if p.opponent_id == opponent_id and p.evidence_label is EvidenceLabel.DIRECT
    )
    return (round(sum(rates) / len(rates), 4) if rates else None), sample


def _reliability_weighted_skill_probability_for(
    matrix: PairingEvidenceMatrix, opponent_id: int
) -> Optional[float]:
    weighted_sum = 0.0
    total_weight = 0
    for p in matrix.pairings:
        if p.opponent_id != opponent_id:
            continue
        probability = skill_only_win_probability(p.player_skill_level, p.opponent_skill_level)
        if probability is None:
            continue
        weight = _pairing_weight(
            p.direct_evidence_count if p.evidence_label is EvidenceLabel.DIRECT else 0
        )
        weighted_sum += weight * probability
        total_weight += weight
    return round(weighted_sum / total_weight, 4) if total_weight else None


def build_ranked_opponents(matrix: PairingEvidenceMatrix) -> tuple[RankedOpponent, ...]:
    """Every real opponent player in this matrix, sorted lowest
    reliability-weighted skill probability first -- our toughest real
    matchups by this one validated signal, shown first. An opponent with no
    scoreable signal at all sorts last, never assumed average. Read the
    list from either end: lowest-first for "danger players," reversed for
    "weak spots" -- both are the same real ranking, not two different
    computations.
    """
    by_opponent: dict[int, tuple[str, str, Optional[int]]] = {}
    for p in matrix.pairings:
        by_opponent.setdefault(
            p.opponent_id, (p.opponent_external_id, p.opponent_name, p.opponent_skill_level)
        )

    entries = []
    for opponent_id, (external_id, name, skill_level) in by_opponent.items():
        direct_rate, direct_sample = _direct_win_rate_and_sample(matrix, opponent_id)
        entries.append(
            RankedOpponent(
                opponent_id=opponent_id,
                opponent_external_id=external_id,
                opponent_name=name,
                opponent_skill_level=skill_level,
                direct_win_rate=direct_rate,
                direct_sample_size=direct_sample,
                reliability_weighted_skill_probability=_reliability_weighted_skill_probability_for(
                    matrix, opponent_id
                ),
            )
        )
    return tuple(sorted(
        entries,
        key=lambda e: (
            e.reliability_weighted_skill_probability is None,
            e.reliability_weighted_skill_probability
            if e.reliability_weighted_skill_probability is not None else 0.0,
            e.opponent_name.lower(),
        ),
    ))


def _roster_from_matrix(matrix: PairingEvidenceMatrix, side: str, trends: dict[int, SkillTrendInfo]) -> tuple[RosterEntry, ...]:
    """One roster side's entries, deduplicated from the matrix's own
    already-resolved per-pairing identity -- never re-queried. ``side`` is
    "our" or "opponent"."""
    seen: dict[int, RosterEntry] = {}
    for p in matrix.pairings:
        if side == "our":
            player_id, external_id, name, skill = (
                p.player_id, p.player_external_id, p.player_name, p.player_skill_level,
            )
        else:
            player_id, external_id, name, skill = (
                p.opponent_id, p.opponent_external_id, p.opponent_name, p.opponent_skill_level,
            )
        if player_id in seen:
            continue
        seen[player_id] = RosterEntry(
            player_id=player_id,
            player_external_id=external_id,
            player_name=name,
            skill_level=skill,
            trend=trends.get(player_id, NO_SKILL_TREND),
        )
    return tuple(sorted(seen.values(), key=lambda r: r.player_name.lower()))


def _summary_for(
    matrix: PairingEvidenceMatrix,
    ranked_opponents: tuple[RankedOpponent, ...],
    lineup_result: Optional[LineupLabResult],
    lineup_error: Optional[str],
) -> str:
    """Plain-language, strictly descriptive summary -- states real counts
    and the real ranking, never a "your team is favored" verdict a
    threshold hasn't been checked to support (see module docstring)."""
    counts = matrix.counts
    total = counts.get("total_feasible_pairings", 0)
    parts = [
        f"{counts.get('DIRECT', 0)} direct, {counts.get('INDIRECT', 0)} indirect, "
        f"{counts.get('UNKNOWN', 0)} unknown pairing(s) out of {total} feasible."
    ]
    scored = [e for e in ranked_opponents if e.reliability_weighted_skill_probability is not None]
    if scored:
        toughest = scored[0]
        easiest = scored[-1]
        parts.append(
            f"Toughest real matchup: {toughest.opponent_name} "
            f"({toughest.reliability_weighted_skill_probability:.0%} estimate for us)."
        )
        if easiest.opponent_id != toughest.opponent_id:
            parts.append(
                f"Most favorable real matchup: {easiest.opponent_name} "
                f"({easiest.reliability_weighted_skill_probability:.0%} estimate for us)."
            )
    if lineup_result is not None and lineup_result.assignments:
        parts.append(f"Approved lineup fills {len(lineup_result.assignments)} board(s).")
    elif lineup_error is not None:
        parts.append(f"No approved lineup: {lineup_error}")
    return " ".join(parts)


@dataclass(frozen=True)
class TeamMatchupReport:
    """One real scheduled match's full Coach Mode team comparison."""

    our_team_external_id: str
    our_team_name: str
    opponent_team_external_id: str
    opponent_team_name: str
    format: str
    session_name: str
    our_roster: tuple[RosterEntry, ...]
    opponent_roster: tuple[RosterEntry, ...]
    evidence_counts: dict
    ranked_opponents: tuple[RankedOpponent, ...]
    lineup_result: Optional[LineupLabResult]
    lineup_error: Optional[str]
    summary: str


def build_team_matchup_report(
    matrix: PairingEvidenceMatrix,
    our_team_name: str,
    opponent_team_name: str,
    lineup_result: Optional[LineupLabResult] = None,
    lineup_error: Optional[str] = None,
    our_trends: Optional[dict[int, SkillTrendInfo]] = None,
    opponent_trends: Optional[dict[int, SkillTrendInfo]] = None,
) -> TeamMatchupReport:
    """Build one Coach Mode team report from an already-classified matrix
    and an already-computed (or already-failed) Lineup Lab result. Exactly
    one of ``lineup_result``/``lineup_error`` is expected to be set,
    mirroring ``scripts/build_captain_first_edge.py``'s own convention --
    not enforced here since a caller may legitimately have neither yet.
    """
    our_trends = our_trends or {}
    opponent_trends = opponent_trends or {}
    ranked_opponents = build_ranked_opponents(matrix)
    return TeamMatchupReport(
        our_team_external_id=matrix.our_team_external_id,
        our_team_name=our_team_name,
        opponent_team_external_id=matrix.opponent_team_external_id,
        opponent_team_name=opponent_team_name,
        format=matrix.format,
        session_name=matrix.session_name,
        our_roster=_roster_from_matrix(matrix, "our", our_trends),
        opponent_roster=_roster_from_matrix(matrix, "opponent", opponent_trends),
        evidence_counts=dict(matrix.counts),
        ranked_opponents=ranked_opponents,
        lineup_result=lineup_result,
        lineup_error=lineup_error,
        summary=_summary_for(matrix, ranked_opponents, lineup_result, lineup_error),
    )
