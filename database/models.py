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
    # Real, captured MATCH_DETAIL_QUERY score-row fields (parser/apa_graphql.py)
    # -- not booleans: an APA match is a race across multiple racks, so these
    # are per-match COUNTS (confirmed against a real fixture: eightBallWins=2
    # in one match). Only ingest_match_scores populates these -- the other
    # two ingest paths (ingest_player_matches, ingest_match_roster) have no
    # source for them. Exactly one of the eight_/nine_ pair is ever non-null
    # for a given row, same convention as points_earned above.
    eight_on_break = Column(Integer)
    eight_break_and_run = Column(Integer)
    nine_on_snap = Column(Integer)
    nine_break_and_run = Column(Integer)

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
    # Real, captured GET_EIGHT_BALL_STATS_QUERY fields (parser/apa_graphql.py),
    # from `alias.players` -- a LIST of one entry per (session, format) the
    # alias played, not a single lifetime total the way matchesWon/CLA/etc.
    # above are. scraper.graphql_scraper.eight_ball_stats_row sums this list
    # per format before it reaches here, so what lands in each column IS the
    # lifetime total, just derived rather than a single ready-made API field.
    # on_break_count/break_and_runs/mini_slams are named generically since
    # both formats report an equivalent stat (8-ball's "on break" is
    # 9-ball's "on snap") under this one shared column; rackless is
    # EIGHT-only and skunks is NINE-only -- null on the other format's row,
    # same convention as cla/defensive_shot_avg being format-agnostic names
    # for a per-format-row value.
    on_break_count = Column(Integer)
    break_and_runs = Column(Integer)
    mini_slams = Column(Integer)
    rackless = Column(Integer)
    skunks = Column(Integer)
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
    # NO unique constraint on (player_id, match_id): a player can legitimately
    # play more than one game in a single match, and each game is its own row
    # with its own opponent, result and points. Confirmed against a real
    # scoresheet -- match 51007724, where Rob Stegall lost to Paul Smith and
    # beat Shiloh Schieck in the same match.
    #
    # The constraint was left over from an earlier upsert-by-key design that
    # ingest_head_to_head has since replaced with per-match delete-then-insert
    # (see its docstring), so nothing depends on it any more -- it only
    # rejected real data.

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    opponent_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    own_skill_level = Column(Integer)
    opponent_skill_level = Column(Integer)
    result = Column(String)
    # Real captured field (MATCH_DETAIL_QUERY score row `nineBallPoints`) --
    # the 9-ball BALL count, distinct from points_earned, which carries match
    # points (eightBallMatchPointsEarned / nineBallMatchPointsEarned). NULL on
    # 8-ball rows, where there is no such thing.
    nine_ball_points = Column(Integer)
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
    per-opponent -- there's nothing to average per matchup. Under Option 1,
    both fields are therefore omitted entirely rather than estimated,
    synthesized, or replaced with proxy values. avg_points_earned and
    avg_opponent_skill_level are separate real metrics supported directly
    by the captured data. See docs/matchups.md.

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
    # P2: own average skill level across ALL games in the pairing --
    # descriptive context alongside avg_opponent_skill_level, never
    # weighted into matchup_score. See analytics/matchups.py's
    # average_own_skill_level for the "avg_own_sl" P2 directive item.
    avg_own_skill_level = Column(Float)
    # P2: average (opponent_skill_level - own_skill_level) across ALL
    # games, wins and losses alike -- purely descriptive context, reported
    # alongside matchup_score but NOT folded into it. Different from
    # opponent_skill_modifier (analytics/matchups.py), which is win-scoped
    # and IS weighted into the score: this answers "how has the skill gap
    # looked overall", not "did a skill-gap win earn a bonus".
    sl_delta = Column(Float)
    trend = Column(String)
    volatility = Column(Integer)
    matchup_score = Column(Integer)
    confidence_score = Column(Integer)
    format = Column(String)
    session_name = Column(String)

    player = relationship("Player", foreign_keys=[player_id])
    opponent = relationship("Player", foreign_keys=[opponent_id])


class PlayerH2HAdvantage(Base):
    """One row per (player, opponent): the Head-to-Head Advantage Engine's
    output -- record, skill-level context, a trend-adjusted matchup score,
    and three forward-looking estimates (win probability, expected 8-ball
    points, expected 9-ball balls).

    Deliberately SEPARATE from PlayerMatchup rather than an extension of it.
    PlayerMatchup is the Matchup Advantage Engine's aggregate and is read by
    Captain's Edge, the workbook, the demo and the pipeline; this table adds
    the probabilistic layer without disturbing any of that. Both are derived
    from the same PlayerHeadToHead rows, so they cannot disagree about the
    underlying games.

    Two fields the original ask wanted are absent on purpose, not pending:
    APA exposes no per-opponent INNINGS at all, and defensive shots only as a
    lifetime average (PlayerCareerStats.defensive_shot_avg), never per
    opponent. Inventing either would be the one thing this project has
    consistently refused to do. See docs/head_to_head.md, "Unavailable APA
    Fields".

    Upserted in place on (player_id, opponent_id, format, session_name) --
    always-current, like PlayerMatchup, not snapshotted per run.
    """

    __tablename__ = "player_h2h_advantage"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "opponent_id", "format", "session_name",
            name="uq_player_h2h_advantage_pair",
        ),
    )

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    opponent_id = Column(Integer, ForeignKey("players.id"), nullable=False)

    total_matches = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)

    # Mean (opponent_skill_level - own_skill_level): positive means the
    # player has been giving up skill level. Same sign convention as
    # PlayerMatchup.sl_delta.
    sl_delta = Column(Float)
    # The numeric +5 / -5 / 0 from analytics.matchups.trend_modifier, stored
    # so the sheet can show WHY a score moved, not just that it did.
    trend_modifier = Column(Integer)
    matchup_score = Column(Integer)

    # 0.0-1.0. Logistic over skill-level advantage and the observed record,
    # the latter weighted by sample size -- see analytics/head_to_head.py.
    win_probability = Column(Float)
    # Format-specific and mutually exclusive: an 8-ball pairing has no ball
    # count, a 9-ball pairing has no match-point estimate. NULL means "not
    # this format", never "zero".
    expected_points = Column(Float)
    expected_balls = Column(Float)

    format = Column(String)
    session_name = Column(String)

    player = relationship("Player", foreign_keys=[player_id])
    opponent = relationship("Player", foreign_keys=[opponent_id])


class PlayerTrend(Base):
    """One row per (player, format): how a player's SKILL LEVEL has been
    moving lately, per the finalized Player Trend Analyzer spec.

    The subject of the trend metrics is skill level, not points earned:
    volatility is the sample standard deviation (ddof=1) of SL over the last
    20 matches, and trend_slope is a least-squares fit in SL units per match
    over the player's WHOLE history in that format. Those two spans differ
    deliberately -- see docs/player_trends.md.

    avg_points_last_20 is the one points-based figure, kept as descriptive
    context alongside the SL trend rather than as an input to it.

    Every field is derived from real captured data (PlayerMatch.skill_level
    and .points_earned, format from the joined Match). No innings and no
    defensive-shot figures exist in this project (APA does not expose them),
    and none are invented for trends either.

    NULL is meaningful throughout and is never replaced by a fabricated
    zero. Per the spec's minimum-evidence rules:

      * trend_slope        -- NULL below 2 SL observations
      * volatility_last_20 -- NULL below 2 SL observations in the window
      * sl_stability       -- NULL whenever volatility is NULL
      * hot_cold_flag      -- NULL below 5 observations, or without
                              volatility; "neutral" means observed and
                              unremarkable, which is a different fact
      * projected_sl_change_probability -- NULL below 5 observations, or
                              without volatility

    Upserted on (player_id, format): always-current, not snapshotted.
    """

    __tablename__ = "player_trends"
    __table_args__ = (
        UniqueConstraint("player_id", "format", name="uq_player_trends_format"),
    )

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    format = Column(String)

    # SL observations in the volatility window -- not the window SIZE. With a
    # 20-match window and 4 matches played this reads 4, and every gated
    # figure below is only as strong as that number.
    matches_considered = Column(Integer)

    avg_points_last_20 = Column(Float)
    # Sample stddev (ddof=1) of SKILL LEVEL over the last 20 matches.
    volatility_last_20 = Column(Float)
    # Least-squares slope of SL vs match order, SL units per match, over the
    # full history. Positive means the skill level is climbing.
    trend_slope = Column(Float)
    # |tanh(4 * slope)|. The one metric the governing spec does not define --
    # flagged as such in analytics/player_trends.py and the docs.
    trend_strength = Column(Float)
    # 1 / (1 + volatility). 1.0 is perfectly stable, approaching 0.0 as the
    # skill level swings. NOT a variance -- see the spec's §2.
    sl_stability = Column(Float)
    # "hot" / "cold" / "neutral", or NULL for insufficient evidence.
    hot_cold_flag = Column(String)
    # 0.0-1.0 from the spec's documented heuristic. Upward SL pressure only:
    # the clamp floors a downward trend at 0.0, and direction lives in
    # trend_slope. Not a fitted model and not APA's own projection.
    projected_sl_change_probability = Column(Float)

    player = relationship("Player", foreign_keys=[player_id])
