"""Captain's Edge Summary -- a real rollup over data this project has
already computed. No new database query, no new per-pairing or
per-lineup computation: every number here already exists somewhere in
the real lineup document scripts.build_lineups writes
(analytics.lineup_optimizer's pairings, analytics.lineup_risk's per-lineup
blocks, analytics.opponent_scouting's per-opponent profiles). This module
only selects and ranks.

Purely derived and purely computational, the same split every other
analytics module in this project uses: it takes the already-built lineup
document (or its real sub-lists) as input and queries nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_TOP_N = 5


@dataclass(frozen=True)
class StrongestPairing:
    player_name: str
    opponent_name: str
    matchup_score: float


@dataclass(frozen=True)
class AnchorCandidate:
    player_name: str
    team_name: str
    opponent_team_name: str
    anchor_stability_score: float


@dataclass(frozen=True)
class HighRiskLineup:
    team_name: str
    opponent_team_name: str
    lineup_risk_score: float
    anchor_player_name: str


@dataclass(frozen=True)
class CaptainsEdgeSummary:
    top_strongest_pairings: list[StrongestPairing] = field(default_factory=list)
    top_danger_matchups: list[dict[str, Any]] = field(default_factory=list)
    best_anchor_candidates: list[AnchorCandidate] = field(default_factory=list)
    highest_risk_lineups: list[HighRiskLineup] = field(default_factory=list)


def top_strongest_pairings(
    pairing_rows: list[dict[str, Any]], n: int = DEFAULT_TOP_N
) -> list[StrongestPairing]:
    """The N real pairings with the highest real matchup_score. A row
    missing matchup_score is excluded entirely -- never ranked as if it
    scored 0, which would misrepresent a real absence of evidence as a
    real weak matchup."""
    scored = [row for row in pairing_rows if row.get("matchup_score") is not None]
    scored.sort(key=lambda row: row["matchup_score"], reverse=True)
    return [
        StrongestPairing(
            player_name=row.get("player_name") or "",
            opponent_name=row.get("opponent_name") or "",
            matchup_score=row["matchup_score"],
        )
        for row in scored[:n]
    ]


def top_danger_matchups(
    opponent_scouting_entries: list[dict[str, Any]], n: int = DEFAULT_TOP_N
) -> list[dict[str, Any]]:
    """The N real opponents already flagged `is_danger_matchup` by
    analytics.opponent_scouting, ranked by the lowest real
    avg_win_probability first (ties: highest real opponent_volatility) --
    the most dangerous real opponents first. An opponent scored `None`
    for avg_win_probability was flagged (if at all) purely on volatility;
    it sorts after every opponent with a real probability, never assumed
    to be worse or better than one that has real evidence.
    """
    danger = [e for e in opponent_scouting_entries if e.get("is_danger_matchup")]
    danger.sort(key=lambda e: (
        e.get("avg_win_probability") is None,
        e.get("avg_win_probability") if e.get("avg_win_probability") is not None else 0.0,
        -(e.get("opponent_volatility") or 0.0),
    ))
    return danger[:n]


def best_anchor_candidates(
    lineups: list[dict[str, Any]], n: int = DEFAULT_TOP_N
) -> list[AnchorCandidate]:
    """The N real lineups' anchors with the highest real
    anchor_stability_score, across every real solved lineup -- reusing
    analytics.lineup_risk's own anchor selection per lineup, never
    re-deriving a different notion of "best" anchor here. A lineup with no
    real anchor (anchor_stability_score is None -- an empty lineup) is
    excluded, never ranked as a 0.
    """
    candidates = []
    for lineup in lineups:
        risk = lineup.get("lineup_risk") or {}
        score = risk.get("anchor_stability_score")
        name = risk.get("anchor_player_name")
        if score is None or name is None:
            continue
        candidates.append(AnchorCandidate(
            player_name=name,
            team_name=lineup.get("team_name") or "",
            opponent_team_name=lineup.get("opponent_team_name") or "",
            anchor_stability_score=score,
        ))
    candidates.sort(key=lambda c: c.anchor_stability_score, reverse=True)
    return candidates[:n]


def highest_risk_lineups(
    lineups: list[dict[str, Any]], n: int = DEFAULT_TOP_N
) -> list[HighRiskLineup]:
    """The N real lineups with the highest real lineup_risk_score, reusing
    analytics.lineup_risk's own combined score -- never a re-derived
    ranking. A lineup with no real risk block at all (an older document)
    is excluded, never ranked as a 0."""
    scored = []
    for lineup in lineups:
        risk = lineup.get("lineup_risk")
        if not risk or risk.get("lineup_risk_score") is None:
            continue
        scored.append(HighRiskLineup(
            team_name=lineup.get("team_name") or "",
            opponent_team_name=lineup.get("opponent_team_name") or "",
            lineup_risk_score=risk["lineup_risk_score"],
            anchor_player_name=risk.get("anchor_player_name") or "",
        ))
    scored.sort(key=lambda l: l.lineup_risk_score, reverse=True)
    return scored[:n]


def build_captains_edge_summary(
    document: dict[str, Any], n: int = DEFAULT_TOP_N
) -> CaptainsEdgeSummary:
    """Build the complete real summary from an already-built lineup
    document (the same real dict scripts.build_lineups.build_payload
    returns / exports/lineups.json contains)."""
    return CaptainsEdgeSummary(
        top_strongest_pairings=top_strongest_pairings(document.get("pairings") or [], n),
        top_danger_matchups=top_danger_matchups(document.get("opponent_scouting") or [], n),
        best_anchor_candidates=best_anchor_candidates(document.get("lineups") or [], n),
        highest_risk_lineups=highest_risk_lineups(document.get("lineups") or [], n),
    )
