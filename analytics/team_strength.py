"""Team Strength Analyzer: docs/team_strength.md.

Three transparent, bounded, DESCRIPTIVE components -- never a fitted
outcome model, a lineup selector, or a strength category:

    offense_index   pooled individual-match win rate ("Roster result rate")
    defense_index   team-score containment PROXY (PF/PA share) -- not a
                    real defensive-shot rate; APA Tracker has no
                    team-level defensive-event feed
    depth_index     the observed result-rate floor at the fifth roster
                    position

``team_strength_index`` is their unweighted mean, equal-weighted by
explicit design choice (not a learned coefficient), and is ``None``
unless all three components are present -- it never renormalizes over a
partial subset, which would make two teams with different missing
components incomparable.

Purely derived and purely computational, the same split every analytics
module in this project uses: takes already-fetched real rows (already
scoped/guarded by the caller -- exact team_external_id/session/is_current,
finalized/scored/non-bye matches) and computes. Queries nothing itself,
imports no UI renderer.

Not a validated predictive signal: "Equal weighting is a design
assumption, not a learned coefficient. Before the index is used
predictively, a separate validation study must freeze historical
training/holdout cohorts and compare it with simpler baselines. Until
then it supports descriptive comparison only" (docs/team_strength.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

FORMULA_VERSION = "team-strength-v1-equal-components"


@dataclass(frozen=True)
class TeamStrengthPlayerRow:
    """One canonical current-roster player's real result record."""

    player_id: int
    player_external_id: str
    player_name: str
    skill_level: Optional[int]
    matches_won: int
    matches_played: int
    observed_rate: Optional[float]
    contributes_to_offense: bool
    scoreable_for_depth: bool
    depth_order: Optional[int]


@dataclass(frozen=True)
class TeamStrengthMatchRow:
    """One real, eligible (finalized, scored, non-bye) match."""

    match_id: str
    match_date: Optional[str]
    week: Optional[int]
    format: Optional[str]
    session_name: Optional[str]
    opponent_team_id: Optional[str]
    opponent_team_name: Optional[str]
    is_home: bool
    points_for: float
    points_against: float


@dataclass(frozen=True)
class TeamStrengthReport:
    team_external_id: str
    team_name: str
    session_name: str
    division_id: Optional[str]
    format: Optional[str]
    source_manifest_id: Optional[str]
    captured_at: Optional[str]
    formula_version: str

    team_strength_index: Optional[float]

    offense_index: Optional[float]
    offense_wins: int
    offense_played: int
    offense_player_count: int

    defense_index: Optional[float]
    points_for: float
    points_against: float
    defense_match_count: int

    depth_index: Optional[float]
    roster_count: int
    scoreable_player_count: int
    depth_player_id: Optional[str]

    player_rows: tuple[TeamStrengthPlayerRow, ...]
    match_rows: tuple[TeamStrengthMatchRow, ...]

    current_rank: Optional[int]
    standings_record: Optional[str]
    unavailable_reasons: tuple[str, ...]


def _compute_offense(
    players: Sequence[dict],
) -> tuple[Optional[float], int, int, int]:
    """Pooled win rate over canonical roster rows with a positive played
    count -- pooling first (sum wins / sum played) so a 1-match player
    never gets equal weight to a 20-match one."""
    eligible = [p for p in players if (p.get("matches_played") or 0) > 0]
    wins = sum(p["matches_won"] for p in eligible)
    played = sum(p["matches_played"] for p in eligible)
    index = round(100 * wins / played, 4) if played > 0 else None
    return index, wins, played, len(eligible)


def _compute_defense(
    matches: Sequence[dict],
) -> tuple[Optional[float], float, float, int]:
    """Team-score containment PROXY: this selected team's share of scored
    match points, from the points-allowed side. Not a defensive-shot
    rate."""
    points_for = sum(m["points_for"] for m in matches)
    points_against = sum(m["points_against"] for m in matches)
    total = points_for + points_against
    index = round(100 * (1 - points_against / total), 4) if total > 0 else None
    return index, points_for, points_against, len(matches)


def _compute_depth(
    players: Sequence[dict],
) -> tuple[Optional[float], int, Optional[str], dict[str, int]]:
    """The observed result-rate floor at the fifth roster position.

    Ranked descending by rate, external id ascending as the tie-break.
    Fewer than five scoreable players (at least one recorded match) means
    no real floor exists yet -- null, never a guess from a shallower
    bench. Returns the index, the scoreable count, the fifth player's
    external id (when one exists), and a {external_id: depth_order} map
    for annotating every scoreable player's rank.
    """
    scoreable = [p for p in players if (p.get("matches_played") or 0) > 0]
    ranked = sorted(
        scoreable,
        key=lambda p: (-(p["matches_won"] / p["matches_played"]), p["player_external_id"]),
    )
    depth_order = {p["player_external_id"]: i + 1 for i, p in enumerate(ranked)}
    if len(ranked) < 5:
        return None, len(scoreable), None, depth_order
    fifth = ranked[4]
    rate = fifth["matches_won"] / fifth["matches_played"]
    return round(100 * rate, 4), len(scoreable), fifth["player_external_id"], depth_order


def _team_strength_index(
    offense: Optional[float], defense: Optional[float], depth: Optional[float]
) -> Optional[float]:
    if offense is None or defense is None or depth is None:
        return None
    return round((offense + defense + depth) / 3, 4)


def build_report(
    team_external_id: str,
    team_name: str,
    session_name: str,
    players: Sequence[dict],
    matches: Sequence[dict],
    *,
    division_id: Optional[str] = None,
    format: Optional[str] = None,
    source_manifest_id: Optional[str] = None,
    captured_at: Optional[str] = None,
    current_rank: Optional[int] = None,
    standings_record: Optional[str] = None,
) -> TeamStrengthReport:
    """Every real, already-guarded input this project has for one team's
    descriptive strength report.

    ``players`` -- one dict per canonical current-roster row:
    ``player_id``/``player_external_id``/``player_name``/``skill_level``/
    ``matches_won``/``matches_played``. ``matches`` -- one dict per real,
    eligible (finalized, scored, non-bye) match this team played:
    ``match_id``/``match_date``/``week``/``format``/``session_name``/
    ``opponent_team_id``/``opponent_team_name``/``is_home``/
    ``points_for``/``points_against``. Both are the caller's
    responsibility to scope and guard (§ "Required guard" in
    docs/team_strength.md) -- this module does not query or re-validate
    identity.
    """
    offense_index, offense_wins, offense_played, offense_player_count = _compute_offense(players)
    defense_index, points_for, points_against, defense_match_count = _compute_defense(matches)
    depth_index, scoreable_player_count, depth_player_id, depth_orders = _compute_depth(players)
    strength_index = _team_strength_index(offense_index, defense_index, depth_index)

    player_rows = tuple(
        TeamStrengthPlayerRow(
            player_id=p["player_id"],
            player_external_id=p["player_external_id"],
            player_name=p["player_name"],
            skill_level=p.get("skill_level"),
            matches_won=p["matches_won"],
            matches_played=p["matches_played"],
            observed_rate=(
                round(p["matches_won"] / p["matches_played"], 4)
                if (p.get("matches_played") or 0) > 0 else None
            ),
            contributes_to_offense=(p.get("matches_played") or 0) > 0,
            scoreable_for_depth=(p.get("matches_played") or 0) > 0,
            depth_order=depth_orders.get(p["player_external_id"]),
        )
        for p in players
    )
    match_rows = tuple(
        TeamStrengthMatchRow(
            match_id=m["match_id"], match_date=m.get("match_date"), week=m.get("week"),
            format=m.get("format"), session_name=m.get("session_name"),
            opponent_team_id=m.get("opponent_team_id"), opponent_team_name=m.get("opponent_team_name"),
            is_home=bool(m.get("is_home")), points_for=m["points_for"], points_against=m["points_against"],
        )
        for m in matches
    )

    unavailable: list[str] = []
    if offense_index is None:
        unavailable.append("Offense (Roster result rate): no canonical roster player has a recorded match.")
    if defense_index is None:
        unavailable.append("Defense (team-score containment proxy): no eligible finalized match found.")
    if depth_index is None:
        unavailable.append(
            f"Depth: fewer than five scoreable players ({scoreable_player_count} found)."
        )
    if standings_record is None:
        unavailable.append("Standings: no real StandingsSnapshot resolved for this team.")

    return TeamStrengthReport(
        team_external_id=team_external_id, team_name=team_name, session_name=session_name,
        division_id=division_id, format=format, source_manifest_id=source_manifest_id,
        captured_at=captured_at, formula_version=FORMULA_VERSION,
        team_strength_index=strength_index,
        offense_index=offense_index, offense_wins=offense_wins, offense_played=offense_played,
        offense_player_count=offense_player_count,
        defense_index=defense_index, points_for=points_for, points_against=points_against,
        defense_match_count=defense_match_count,
        depth_index=depth_index, roster_count=len(players), scoreable_player_count=scoreable_player_count,
        depth_player_id=depth_player_id,
        player_rows=player_rows, match_rows=match_rows,
        current_rank=current_rank, standings_record=standings_record,
        unavailable_reasons=tuple(unavailable),
    )
