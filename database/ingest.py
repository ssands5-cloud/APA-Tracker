"""
Upserts scraped data into the database.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Player, PlayerMatch, Match, StandingsSnapshot, Team

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


def upsert_player(db: Session, player_id: str, player_name: str, team: Optional[Team] = None) -> Player:
    """Create or update a player record."""
    player = db.query(Player).filter_by(external_id=player_id).one_or_none()
    if player is None:
        player = Player(external_id=player_id, name=player_name, team=team)
        db.add(player)
    else:
        player.name = player_name
        if team:
            player.team = team
    db.commit()
    return player


def upsert_roster(db: Session, team: Team, roster: list[dict]) -> int:
    """Update team roster with player stats."""
    count = 0
    for entry in roster:
        player_id = entry.get("player_id") or entry.get("player_name", "")
        player_name = entry.get("player_name", "")
        
        player = upsert_player(db, player_id, player_name, team)
        
        # Update player stats from roster entry
        player.skill_level = _to_int(entry.get("skill_level"))
        player.matches_won = _to_int(entry.get("matches_won"))
        player.matches_played = _to_int(entry.get("matches_played"))
        player.win_pct = _to_float(entry.get("win_pct"))
        player.ppm = _to_float(entry.get("ppm"))
        player.pa = _to_float(entry.get("pa"))
        
        count += 1
    db.commit()
    logger.info("Upserted %d roster entries for team %s", count, team.name)
    return count


def ingest_match(
    db: Session,
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    home_team_name: str,
    away_team_name: str,
    location: Optional[str] = None,
    match_date: Optional[str] = None,
    status: Optional[str] = None,
    home_score: Optional[float] = None,
    away_score: Optional[float] = None,
) -> Optional[int]:
    """Create or update a match record."""
    existing = db.query(Match).filter_by(external_id=match_id).one_or_none()
    if existing:
        existing.home_team_id = home_team_id
        existing.away_team_id = away_team_id
        existing.home_team_name = home_team_name
        existing.away_team_name = away_team_name
        existing.location = location
        existing.match_date = match_date
        existing.status = status
        existing.home_score = home_score
        existing.away_score = away_score
        db.commit()
        logger.debug("Updated match %s", match_id)
        return existing.id

    match = Match(
        external_id=match_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        location=location,
        match_date=match_date,
        status=status,
        home_score=home_score,
        away_score=away_score,
    )
    db.add(match)
    db.commit()
    logger.info("Ingested match %s", match_id)
    return match.id


def ingest_match_roster(
    db: Session,
    match_id: int,
    team_id: str,
    team_name: str,
    roster: list[dict],
) -> int:
    """Link players to a match via the roster."""
    count = 0
    for entry in roster:
        player_id = entry.get("player_id") or entry.get("player_name", "")
        player_name = entry.get("player_name", "")
        
        # Ensure player exists
        player = upsert_player(db, player_id, player_name)
        
        # Check if this player-match combo already exists
        existing = (
            db.query(PlayerMatch)
            .filter_by(player_id=player.id, match_id=match_id)
            .one_or_none()
        )
        
        if existing:
            logger.debug("PlayerMatch for player %s in match %d already exists", player_id, match_id)
            continue
        
        # Create PlayerMatch record
        db.add(
            PlayerMatch(
                player_id=player.id,
                match_id=match_id,
                team_id=team_id,
                team_name=team_name,
                skill_level=_to_int(entry.get("skill_level")),
                matches_won=_to_int(entry.get("matches_won")),
                matches_played=_to_int(entry.get("matches_played")),
                win_pct=_to_float(entry.get("win_pct")),
                ppm=_to_float(entry.get("ppm")),
                pa=_to_float(entry.get("pa")),
            )
        )
        count += 1
    
    db.commit()
    logger.info("Ingested %d player-match records for match %d", count, match_id)
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


def _clean_number(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"n/a", "na", "null", "none"}:
        return None
    text = text.replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    return text


def _to_int(value) -> Optional[int]:
    cleaned = _clean_number(value)
    if cleaned is None:
        return None
    try:
        numeric = float(cleaned)
    except (TypeError, ValueError):
        return None
    if numeric.is_integer():
        return int(numeric)
    return None


def _to_float(value) -> Optional[float]:
    cleaned = _clean_number(value)
    if cleaned is None:
        return None
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None
