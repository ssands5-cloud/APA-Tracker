"""
Common read queries used by the analytics and UI modules.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Match, Player, PlayerCareerStats, PlayerMatch, PlayerTeamHistory, StandingsSnapshot, Team


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
