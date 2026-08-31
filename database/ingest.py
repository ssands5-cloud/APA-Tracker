"""
Upserts scraped data into the database.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Player, PlayerMatch, StandingsSnapshot, Team

logger = logging.getLogger(__name__)


def ingest_standings(db: Session, standings: list[dict]) -> int:
    """Insert one snapshot row per standings entry, timestamped `now`."""
    now = datetime.utcnow()
    count = 0
    for row in standings:
        db.add(
            StandingsSnapshot(
                captured_at=now,
                team_name=row.get("team_name", ""),
                rank=_to_int(row.get("rank")),
                wins=_to_int(row.get("wins")),
                losses=_to_int(row.get("losses")),
                points=_to_float(row.get("points")),
            )
        )
        count += 1
    db.commit()
    logger.info("Ingested %d standings rows", count)
    return count


def upsert_team(db: Session, external_id: str, name: str) -> Team:
    team = db.query(Team).filter_by(external_id=external_id).one_or_none()
    if team is None:
        team = Team(external_id=external_id, name=name)
        db.add(team)
    else:
        team.name = name
    db.commit()
    return team


def upsert_roster(db: Session, team: Team, roster: list[dict]) -> int:
    count = 0
    for entry in roster:
        external_id = entry.get("player_name", "")  # replace with a real external id once available
        player = db.query(Player).filter_by(external_id=external_id).one_or_none()
        if player is None:
            player = Player(external_id=external_id, name=entry.get("player_name", ""), team=team)
            db.add(player)
        player.skill_level = _to_int(entry.get("skill_level"))
        player.team = team
        count += 1
    db.commit()
    logger.info("Upserted %d roster entries for team %s", count, team.name)
    return count


def ingest_player_matches(db: Session, player: Player, matches: list[dict]) -> int:
    count = 0
    for row in matches:
        exists = (
            db.query(PlayerMatch)
            .filter_by(player_id=player.id, match_date=row.get("match_date"), opponent=row.get("opponent"))
            .one_or_none()
        )
        if exists:
            continue
        db.add(
            PlayerMatch(
                player_id=player.id,
                match_date=row.get("match_date"),
                opponent=row.get("opponent"),
                skill_level=_to_int(row.get("skill_level")),
                points_earned=_to_float(row.get("points_earned")),
                result=row.get("result"),
            )
        )
        count += 1
    db.commit()
    logger.info("Ingested %d new match rows for player %s", count, player.name)
    return count


def _to_int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_float(value) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
