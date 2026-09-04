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
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
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
    career_stats = relationship("PlayerCareerStats", back_populates="player")
    team_history = relationship("PlayerTeamHistory", back_populates="player")


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
    # Not from the match itself (MatchPage doesn't return division/session
    # info) -- threaded in from the originating team's own context at
    # ingestion (dashboard_teams_rows()'s division_type / session_name, or
    # team_row()'s format / session_name on the single-team path). P1-4:
    # lets head-to-head/matchup grouping distinguish an 8-ball matchup
    # from a 9-ball one, and one session's record from a stale one.
    format = Column(String)
    session_name = Column(String)

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
    """One player's involvement in one match. Three ingest paths write here:

    - ``ingest_player_matches`` fills ``match_date`` / ``opponent`` /
      ``points_earned`` / ``result`` from a player's own match-history page.
      No ``match_id`` -- this path predates the ``Match`` table entirely.
    - ``ingest_match_roster`` fills ``match_id`` / ``team_id`` / ``team_name``
      and the roster totals from a specific match's roster tables. Leaves
      ``opponent`` NULL.
    - ``ingest_match_scores`` fills ``match_id`` plus ``opponent`` (derived
      from the Match itself) and the real per-player scoresheet fields.

    The uniqueness guard below is a PARTIAL index -- (player_id, match_date,
    opponent), but only where match_id IS NULL -- covering ingest_player_matches
    alone. It used to be a blanket table-wide constraint, which broke the
    first time ingest_match_scores ran against a real account: two DIFFERENT
    real matches (different teams, different divisions) landed on the same
    match_date against two different opponents that happened to share a
    name ("Mark It Up"), so the same player's two genuinely different
    match-linked rows collided on (player_id, match_date, opponent) even
    though their match_id differed. The match-linked paths already
    deduplicate correctly in Python on (player_id, match_id) before
    inserting/updating (see ingest_match_roster/ingest_match_scores in
    database/ingest.py) -- the blanket DB constraint was redundant for them
    at best, actively wrong at worst.
    """

    __tablename__ = "player_matches"
    __table_args__ = (
        Index(
            "uq_player_match_history",
            "player_id", "match_date", "opponent",
            unique=True,
            sqlite_where=text("match_id IS NULL"),
        ),
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


class PlayerCareerStats(Base):
    """One row per (player, format) -- lifetime totals from
    getEightBallStats, e.g. "64 won / 129 played, CLA 1, lastPlayed
    2026-08-31" -- as opposed to PlayerMatch, which is per-match or
    per-season. Upserted in place on (player_id, format) rather than
    snapshotted per sync run: these are always-current lifetime totals, not
    a value worth tracking a history of the way StandingsSnapshot is.
    """

    __tablename__ = "player_career_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "format", name="uq_player_career_stats_format"),
    )

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    format = Column(String, nullable=False)  # "EIGHT" or "NINE"
    matches_won = Column(Integer)
    matches_played = Column(Integer)
    cla = Column(Integer)
    defensive_shot_avg = Column(Float)
    match_count_last_two_yrs = Column(Integer)
    last_played = Column(String)  # stored as delivered text, same convention as match_date elsewhere
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    player = relationship("Player", back_populates="career_stats")


class PlayerTeamHistory(Base):
    """One row per team (past or current) a player's alias has played on,
    from TeamStat -- the cross-season history PlayerMatch has no source
    for. Upserted on (player_id, team_name, division_id, session_name):
    TeamStat's response is the complete list every time, not an
    incremental diff, so a rerun should refresh existing rows rather than
    accumulate duplicates.
    """

    __tablename__ = "player_team_history"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "team_name", "division_id", "session_name",
            name="uq_player_team_history",
        ),
    )

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    is_current = Column(Boolean, default=False)
    team_name = Column(String)
    division_id = Column(String)
    is_tournament = Column(Boolean, default=False)
    session_name = Column(String)
    nick_name = Column(String)
    skill_level = Column(Integer)
    rank = Column(Integer)
    matches_won = Column(Integer)
    matches_played = Column(Integer)

    player = relationship("Player", back_populates="team_history")


class PlayerHeadToHead(Base):
    """One row per individual game within a scored match -- who a player
    actually played against, not just which two teams faced off.

    A team match's `results[].scores[]` doesn't name the opposing player
    directly, but each score row carries `matchPositionNumber`/
    `playerPosition`, and standard APA team format plays same-numbered
    positions against each other (position 1 home vs position 1 away, and
    so on) -- see scraper.graphql_scraper.head_to_head_rows(). That's a
    documented field, not a guess at an ambiguous id: unlike the alias-id
    question in HANDOFF.md, matchPositionNumber's meaning is given by its
    name and APA's own published team-match format.

    Raw, per-match facts -- database.queries aggregates these into the
    player_matchups table (PlayerMatchup, below), the same raw/aggregate
    split as PlayerMatch vs Player.matches_won.
    """

    __tablename__ = "player_head_to_head"
    __table_args__ = (
        UniqueConstraint("player_id", "match_id", name="uq_player_head_to_head_match"),
    )

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    opponent_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    own_skill_level = Column(Integer)
    opponent_skill_level = Column(Integer)
    result = Column(String)
    points_earned = Column(Float)
    # Copied from Match.format/Match.session_name at ingestion (P1-4) --
    # not part of the unique constraint above, since a given match_id
    # already implies exactly one format/session; kept here (denormalized)
    # so analytics.matchup_builder can group by them without a join.
    format = Column(String)
    session_name = Column(String)

    player = relationship("Player", foreign_keys=[player_id])
    opponent = relationship("Player", foreign_keys=[opponent_id])
    match = relationship("Match")


class PlayerMatchup(Base):
    """One row per (player, opponent) -- the Matchup Advantage Engine's
    aggregate: win rate, points/skill-level context, and a 0-100
    matchup_score, all derived from PlayerHeadToHead by
    analytics.matchups and written by scripts/build_matchups.py.

    Two real fields the original ask wanted aren't here: "innings" isn't a
    stat this API has ever returned (checked every captured query --
    parser/apa_graphql.py), and "defensive shots" only exists as a
    career-wide average (PlayerCareerStats.defensive_shot_avg), never
    per-opponent -- there's nothing to average per matchup. Rather than
    invent numbers for either, avg_points_earned and
    avg_opponent_skill_level stand in: real, per-opponent, and actually in
    the data. See docs/matchups.md.

    Upserted in place on (player_id, opponent_id), like PlayerCareerStats:
    always-current, not a value worth snapshotting per run.

    confidence_score (added alongside sample-size/opponent-skill-level/
    recency weighting -- see analytics/matchups.py and docs/matchups.md)
    says how much to trust matchup_score itself: a 1-0 matchup and a 10-0
    matchup can now land on similar scores once weighted, and confidence
    is what tells them apart.

    format/session_name (P1-4) split the aggregate by division format and
    session -- a player's 8-ball record against an opponent doesn't
    predict their 9-ball one, and a stale prior session's record isn't
    "current form" the way this session's is. Both are nullable: a pair
    whose head-to-head rows never got a format/session threaded through
    (an older ingest, or a caller that didn't have team context handy)
    still aggregates, just under a NULL/NULL bucket rather than being
    dropped. NULL participates in the uniqueness check as SQL's usual
    "distinct from everything, including another NULL" -- ingest_matchups()
    and prune_matchups_not_in() always look rows up by the full tuple
    rather than relying on the DB constraint alone to prevent duplicates,
    so this doesn't create a real gap in practice.
    """

    __tablename__ = "player_matchups"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "opponent_id", "format", "session_name",
            name="uq_player_matchups_pair",
        ),
    )

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    opponent_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    matches_played = Column(Integer)
    win_rate = Column(Float)
    avg_points_earned = Column(Float)
    avg_opponent_skill_level = Column(Float)
    trend = Column(String)
    volatility = Column(Integer)
    matchup_score = Column(Integer)
    confidence_score = Column(Integer)
    format = Column(String)
    session_name = Column(String)

    player = relationship("Player", foreign_keys=[player_id])
    opponent = relationship("Player", foreign_keys=[opponent_id])
