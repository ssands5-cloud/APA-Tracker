"""
SQLAlchemy ORM models for the APA Tracker database.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
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
    # Current-season roster totals, refreshed on every roster ingest.
    # ingest.upsert_roster() has always assigned these; with no columns behind
    # them they were set as plain Python attributes and silently never saved.
    matches_won = Column(Integer)
    matches_played = Column(Integer)
    win_pct = Column(Float)
    ppm = Column(Float)
    pa = Column(Float)
    team_id = Column(Integer, ForeignKey("teams.id"))

    team = relationship("Team", back_populates="players")
    matches = relationship("PlayerMatch", back_populates="player")


class Match(Base):
    """One scheduled or completed match between two teams.

    Team names are stored next to the team ids rather than resolved through a
    foreign key: the schedule names both sides even for opponents whose roster
    has never been scraped, and a match against an unknown team must still
    record who it was against.
    """

    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    external_id = Column(String, unique=True, nullable=False)
    home_team_id = Column(String)
    away_team_id = Column(String)
    home_team_name = Column(String)
    away_team_name = Column(String)
    location = Column(String)
    # Kept as delivered text, matching PlayerMatch.match_date. Normalising to a
    # real datetime is a separate change: the two ingest paths deliver
    # different formats (scraped portal text vs the API's ISO startTime).
    match_date = Column(String)
    status = Column(String)
    week = Column(Integer)

    # Scores stay NULL until the match is actually scored. NULL and 0 are
    # different facts -- "not played yet" versus "shut out" -- and a match
    # that is scored but not yet finalized can legitimately carry one side's
    # points and not the other's.
    home_score = Column(Float)
    away_score = Column(Float)

    # A bye is a real schedule slot with no opponent, kept so a missing week
    # never reads as lost data. is_finalized marks a result the league has
    # confirmed; is_scored alone can still change.
    is_bye = Column(Boolean, default=False)
    is_scored = Column(Boolean, default=False)
    is_finalized = Column(Boolean, default=False)

    player_matches = relationship("PlayerMatch", back_populates="match")


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


class PlayerMatch(Base):
    """One player's involvement in one match. Two ingest paths write here:

    - ``ingest_player_matches`` fills ``match_date`` / ``opponent`` /
      ``points_earned`` / ``result`` from a player's own match-history page.
    - ``ingest_match_roster`` fills ``match_id`` / ``team_id`` / ``team_name``
      and the roster totals from a specific match's roster tables.

    The two sets barely overlap, which is why almost every column is nullable.
    The unique constraint only guards the first path; the second de-duplicates
    on ``(player_id, match_id)`` in ``ingest_match_roster`` instead, since its
    rows leave ``match_date`` and ``opponent`` NULL.
    """

    __tablename__ = "player_matches"
    __table_args__ = (
        UniqueConstraint("player_id", "match_date", "opponent", name="uq_player_match"),
    )

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"))
    team_id = Column(String)
    team_name = Column(String)
    match_date = Column(String)  # stored as scraped text; normalize later if needed
    opponent = Column(String)
    skill_level = Column(Integer)
    matches_won = Column(Integer)
    matches_played = Column(Integer)
    win_pct = Column(Float)
    ppm = Column(Float)
    pa = Column(Float)
    points_earned = Column(Float)
    result = Column(String)

    player = relationship("Player", back_populates="matches")
    match = relationship("Match", back_populates="player_matches")
