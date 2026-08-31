"""
Common read queries used by the analytics and UI modules.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Player, PlayerMatch, StandingsSnapshot, Team


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
