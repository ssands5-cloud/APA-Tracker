"""
Common read queries used by the analytics and UI modules.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import (
    Match,
    Player,
    PlayerCareerStats,
    PlayerHeadToHead,
    PlayerMatch,
    PlayerMatchup,
    PlayerTeamHistory,
    StandingsSnapshot,
    Team,
)


def all_teams(db: Session) -> list[Team]:
    return db.query(Team).order_by(Team.name).all()


def all_matches(db: Session) -> list[Match]:
    return db.query(Match).order_by(Match.week, Match.id).all()


def latest_standings(db: Session) -> list[StandingsSnapshot]:
    latest_ts = db.query(func.max(StandingsSnapshot.captured_at)).scalar()
    if latest_ts is None:
        return []
    return (
        db.query(StandingsSnapshot)
        .filter(StandingsSnapshot.captured_at == latest_ts)
        .order_by(StandingsSnapshot.rank)
        .all()
    )


def standings_history(db: Session, team_name: str) -> list[StandingsSnapshot]:
    return (
        db.query(StandingsSnapshot)
        .filter(StandingsSnapshot.team_name == team_name)
        .order_by(StandingsSnapshot.captured_at)
        .all()
    )


def team_roster(db: Session, team_external_id: str) -> list[Player]:
    team = db.query(Team).filter_by(external_id=team_external_id).one_or_none()
    return team.players if team else []


def player_match_history(db: Session, player_external_id: str) -> list[PlayerMatch]:
    player = db.query(Player).filter_by(external_id=player_external_id).one_or_none()
    if player is None:
        return []
    return (
        db.query(PlayerMatch)
        .filter_by(player_id=player.id)
        .order_by(PlayerMatch.match_date)
        .all()
    )


def all_players(db: Session) -> list[Player]:
    return db.query(Player).order_by(Player.name).all()


def match_scores(db: Session) -> list[PlayerMatch]:
    """Every PlayerMatch row tied to a specific match (match_id set) -- the
    per-match scoresheet path (ingest_match_scores/ingest_match_roster), as
    opposed to player_match_history's per-player result-history path
    (ingest_player_matches), which leaves match_id null. The two ingest
    paths write disjoint columns onto the same table -- see PlayerMatch's
    own docstring -- so filtering on match_id is what actually separates
    them, not filtering on which columns happen to be set.
    """
    return (
        db.query(PlayerMatch)
        .filter(PlayerMatch.match_id.isnot(None))
        .order_by(PlayerMatch.match_id, PlayerMatch.id)
        .all()
    )


def career_stats(db: Session) -> list[PlayerCareerStats]:
    """Every player's lifetime stats, one row per (player, format) --
    from getEightBallStats, HANDOFF.md item 2."""
    return db.query(PlayerCareerStats).order_by(PlayerCareerStats.player_id, PlayerCareerStats.format).all()


def team_history(db: Session) -> list[PlayerTeamHistory]:
    """Every player's cross-season team history -- from TeamStat,
    HANDOFF.md item 2."""
    return (
        db.query(PlayerTeamHistory)
        .order_by(PlayerTeamHistory.player_id, PlayerTeamHistory.is_current.desc())
        .all()
    )


def skill_level_history(db: Session) -> list[PlayerMatch]:
    """Every match-linked PlayerMatch row that carries a skill level,
    ordered so a player's skill level can be read match-by-match across a
    season -- not just the single current snapshot on Player.skill_level.

    No new ingestion or table needed: both ingest_match_roster and
    ingest_match_scores already write PlayerMatch.skill_level per match:
    this just reads that column back out (join Player for name, .match for
    week -- see PlayerMatch/Match relationships in database/models.py).

    Deliberately NOT deduplicated to one row per (player, week): a player
    can have more than one match in the same week number (a doubleheader,
    a makeup match), and each is a real, distinct skill-level reading --
    collapsing them on (player, week) would silently discard one.
    player_match_history()'s per-player-history rows (match_id IS NULL) are
    excluded since that path never populates skill_level.
    """
    return (
        db.query(PlayerMatch)
        .join(Player, PlayerMatch.player_id == Player.id)
        .filter(PlayerMatch.match_id.isnot(None))
        .filter(PlayerMatch.skill_level.isnot(None))
        .order_by(Player.name, PlayerMatch.match_date, PlayerMatch.id)
        .all()
    )


def all_head_to_head(db: Session) -> list[PlayerHeadToHead]:
    """Every raw per-match head-to-head row -- scripts/build_matchups.py
    groups these by (player_id, opponent_id) to compute player_matchups.
    Ordered by player then opponent so rows for one pair are contiguous,
    and chronologically WITHIN each pair (oldest first) -- required by
    analytics.matchups.weighted_win_rate's recency weighting. Match.match_date
    is stored as delivered text (see Match's own docstring), not a real
    datetime, but the live GraphQL source is ISO 8601, which sorts
    correctly as plain text; PlayerHeadToHead.id breaks a tie (same date,
    or both missing one)."""
    return (
        db.query(PlayerHeadToHead)
        .join(Match, PlayerHeadToHead.match_id == Match.id)
        .order_by(
            PlayerHeadToHead.player_id, PlayerHeadToHead.opponent_id,
            Match.match_date, PlayerHeadToHead.id,
        )
        .all()
    )


def head_to_head_history(db: Session, player_id: int, opponent_id: int) -> list[PlayerHeadToHead]:
    """Every game a specific player has played against a specific
    opponent, chronologically (oldest first) -- see all_head_to_head()'s
    docstring for why this ordering matters and how it's derived."""
    return (
        db.query(PlayerHeadToHead)
        .join(Match, PlayerHeadToHead.match_id == Match.id)
        .filter(PlayerHeadToHead.player_id == player_id, PlayerHeadToHead.opponent_id == opponent_id)
        .order_by(Match.match_date, PlayerHeadToHead.id)
        .all()
    )


def all_matchups(db: Session) -> list[PlayerMatchup]:
    """Every computed (player, opponent) matchup, best score first."""
    return db.query(PlayerMatchup).order_by(PlayerMatchup.matchup_score.desc()).all()


def matchups_with_neutral_fill(db: Session) -> list[dict]:
    """Every computed PlayerMatchup row, PLUS a neutral-50 placeholder row
    for every (subject, opponent) pair with no computed matchup between
    them yet, in any format/session -- P1-8: a player who's simply never
    faced a specific opponent shows up as "no history yet, neutral" in the
    output rather than being silently absent.

    Subjects = roster players (Player.team_id IS NOT NULL -- someone
    actually rostered on a team, including a brand-new player with zero
    games played) UNION players who've appeared in real head-to-head
    history (PlayerHeadToHead, as either side). Opponents = known
    head-to-head players only -- a roster player with zero games isn't a
    plausible OPPONENT to pad every other row with, but they ARE a real
    subject a captain wants to see a placeholder row for against players
    who ARE known. A career-stats-only "shadow" player with no roster slot
    and no scoresheet history at all is neither a subject nor an opponent
    -- there's no real candidate matchup to speculate about.

    Real rows always win: this only ever ADDS a synthetic row for a pair
    with zero PlayerMatchup rows across every format/session -- never
    duplicates or overrides real computed data. A pair covered in ONE
    format/session is not padded with a second "no history" row for a
    different one; this fills gaps at the pair level, not per format.

    Returns plain dicts (not ORM rows) with the same keys for both real
    and synthetic rows, plus `has_history` so a caller (ui.export_excel,
    ui.export_json, the demo) can render the two differently -- this is
    an OUTPUT-layer fill: player_head_to_head/player_matchups themselves
    are untouched.
    """
    real_rows = all_matchups(db)
    covered_pairs = {(row.player_id, row.opponent_id) for row in real_rows}

    known_opponent_ids: set[int] = set()
    for player_id, opponent_id in db.query(PlayerHeadToHead.player_id, PlayerHeadToHead.opponent_id).distinct():
        known_opponent_ids.add(player_id)
        known_opponent_ids.add(opponent_id)

    roster_player_ids = {
        p.id for p in db.query(Player.id).filter(Player.team_id.isnot(None))
    }
    subject_ids = known_opponent_ids | roster_player_ids

    players_by_id = (
        {p.id: p for p in db.query(Player).filter(Player.id.in_(subject_ids | known_opponent_ids)).all()}
        if (subject_ids or known_opponent_ids)
        else {}
    )

    rows = [
        {
            "player": r.player.name if r.player else "",
            "player_id": r.player.external_id if r.player else "",
            "opponent": r.opponent.name if r.opponent else "",
            "opponent_id": r.opponent.external_id if r.opponent else "",
            "matches_played": r.matches_played,
            "win_rate": r.win_rate,
            "avg_points_earned": r.avg_points_earned,
            "avg_opponent_skill_level": r.avg_opponent_skill_level,
            "sl_delta": r.sl_delta,
            "trend": r.trend,
            "volatility": r.volatility,
            "matchup_score": r.matchup_score,
            "confidence_score": r.confidence_score,
            "format": r.format,
            "session_name": r.session_name,
            "has_history": True,
        }
        for r in real_rows
    ]

    for player_id in subject_ids:
        for opponent_id in known_opponent_ids:
            if player_id == opponent_id or (player_id, opponent_id) in covered_pairs:
                continue
            player = players_by_id.get(player_id)
            opponent = players_by_id.get(opponent_id)
            if not player or not opponent:
                continue
            rows.append(
                {
                    "player": player.name, "player_id": player.external_id,
                    "opponent": opponent.name, "opponent_id": opponent.external_id,
                    "matches_played": 0, "win_rate": None, "avg_points_earned": None,
                    "avg_opponent_skill_level": None, "sl_delta": None, "trend": "no data", "volatility": 0,
                    "matchup_score": 50, "confidence_score": 0,
                    "format": None, "session_name": None, "has_history": False,
                }
            )
    return rows
