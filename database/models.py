"""
SQLAlchemy ORM models for the APA Tracker database.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    external_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)

    players = relationship("Player", back_populates="team")


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    external_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    skill_level = Column(Integer)
    team_id = Column(Integer, ForeignKey("teams.id"))
    # Roster-snapshot stats, refreshed on each ingest_roster() run.
    matches_won = Column(Integer)
    matches_played = Column(Integer)
    win_pct = Column(Float)
    ppm = Column(Float)
    pa = Column(Float)

    team = relationship("Team", back_populates="players")
    matches = relationship("PlayerMatch", back_populates="player")


class StandingsSnapshot(Base):
    """One row per team, per scrape run -- lets us track standings over time."""

    __tablename__ = "standings_snapshots"

    id = Column(Integer, primary_key=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    team_name = Column(String, nullable=False)
    rank = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    points = Column(Float)


class Match(Base):
    """A single scheduled/played team match, scraped from the match page.

    Team ids/names are stored denormalized (as scraped) rather than as
    foreign keys to `Team`, matching the existing pattern used by
    `StandingsSnapshot.team_name` -- the scraper only has the portal's
    external team identifiers on hand, not our internal `Team.id`.
    """

    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    external_id = Column(String, unique=True, nullable=False)
    home_team_id = Column(String)
    away_team_id = Column(String)
    home_team_name = Column(String)
    away_team_name = Column(String)
    location = Column(String)
    match_date = Column(String)  # stored as scraped text; normalize later if needed
    status = Column(String)

    roster = relationship("PlayerMatch", back_populates="match")


class PlayerMatch(Base):
    """A row linking a player to a match.

    This table serves two related ingest paths that populate different
    subsets of its columns:

    - `ingest_player_matches()` writes one row per historical result from a
      player's own stats page (`match_date`, `opponent`, `skill_level`,
      `points_earned`, `result`); `match_id` is left null since those rows
      aren't tied to a specific `Match` record.
    - `ingest_match_roster()` writes one row per player on a specific
      `Match`'s roster (`match_id`, `team_id`, `team_name`, and the
      roster-snapshot stat columns); `match_date`/`opponent` are left null
      for those rows.
    """

    __tablename__ = "player_matches"
    __table_args__ = (
        UniqueConstraint("player_id", "match_date", "opponent", name="uq_player_match"),
    )

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"))
    match_date = Column(String)  # stored as scraped text; normalize later if needed
    opponent = Column(String)
    skill_level = Column(Integer)
    points_earned = Column(Float)
    result = Column(String)
    # Roster-snapshot fields, populated by ingest_match_roster().
    team_id = Column(String)
    team_name = Column(String)
    matches_won = Column(Integer)
    matches_played = Column(Integer)
    win_pct = Column(Float)
    ppm = Column(Float)
    pa = Column(Float)

    player = relationship("Player", back_populates="matches")
    match = relationship("Match", back_populates="roster")
