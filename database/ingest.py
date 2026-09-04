"""
Upserts scraped data into the database.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

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

logger = logging.getLogger(__name__)


def ingest_standings(db: Session, standings: list[dict], captured_at: Optional[datetime] = None) -> int:
    """Insert one snapshot row per standings entry, timestamped `now`.

    `captured_at` lets a caller ingesting several divisions in one sync run
    (run_all_teams) give every division's rows the SAME timestamp. Real bug
    without it: each division got its own datetime.utcnow() call,
    microseconds apart, and latest_standings()/the Excel and JSON exports
    filter to the single MAX captured_at -- so only the last division
    processed ever showed up; the other three vanished with no error.
    Confirmed against a real 4-division sync: the exported Standings sheet
    had 10 rows instead of 40, one team's division only.
    """
    now = captured_at or datetime.utcnow()
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
    week: Optional[int] = None,
    is_bye: bool = False,
    is_scored: bool = False,
    is_finalized: bool = False,
) -> tuple[Optional[int], bool]:
    """Create or update a match record.

    Returns (match_id, created). A match must be updatable, not skipped: the
    schedule is published before the season, so nearly every match is first
    seen unplayed and only later carries a score. Skipping known matches meant
    a result could never arrive.

    Returns `created` separately because "seen again" and "new this run" are
    different numbers, and an id alone cannot tell them apart.
    """
    fields = {
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "home_team_name": home_team_name,
        "away_team_name": away_team_name,
        "location": location,
        "match_date": match_date,
        "status": status,
        "home_score": home_score,
        "away_score": away_score,
        "week": week,
        "is_bye": is_bye,
        "is_scored": is_scored,
        "is_finalized": is_finalized,
    }

    existing = db.query(Match).filter_by(external_id=match_id).one_or_none()
    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        db.commit()
        logger.debug("Updated match %s", match_id)
        return existing.id, False

    match = Match(external_id=match_id, **fields)
    db.add(match)
    db.commit()
    logger.info("Ingested match %s", match_id)
    return match.id, True


def _resolve_match_pk(db: Session, match_external_id) -> Match:
    """Look up a Match row by APA's own id, not the database's internal one.

    Every caller of ingest_match_roster/ingest_match_scores knows the match
    only by APA's id (the same one ingest_match() was given as `match_id`).
    That id is stored in Match.external_id; Match.id is a separate,
    autoincrement primary key assigned by SQLAlchemy. Storing the external id
    directly onto PlayerMatch.match_id -- which foreign-keys to Match.id --
    silently created an orphaned reference: PlayerMatch.match_id == "555001"
    while the real row's primary key was 1. SQLite does not enforce foreign
    keys by default, so nothing raised; `player_match.match` just resolved to
    None. Confirmed directly: ingest_match() then ingest_match_scores() with
    the same id, then checking `.match` on the result.

    Raises ValueError rather than silently creating the same orphaned
    reference again: a match's row-level scores should never exist before
    the match itself does.
    """
    match = db.query(Match).filter_by(external_id=str(match_external_id)).one_or_none()
    if match is None:
        raise ValueError(
            f"No Match with external_id={match_external_id!r}. Call ingest_match() "
            "for this match before ingesting its roster or scores."
        )
    return match


def ingest_match_roster(
    db: Session,
    match_id,
    team_id: str,
    team_name: str,
    roster: list[dict],
) -> int:
    """Link players to a match via the roster.

    `match_id` is APA's own match id (Match.external_id), the same value
    passed to ingest_match() -- not the database's internal primary key.
    """
    match = _resolve_match_pk(db, match_id)
    count = 0
    for entry in roster:
        player_id = entry.get("player_id") or entry.get("player_name", "")
        player_name = entry.get("player_name", "")

        # A vacant/forfeited roster slot has no real player behind it. Every
        # such slot, across every match, would otherwise share the same
        # blank external_id -- Player.external_id is unique, so they'd all
        # silently collapse into ONE fake "player" accumulating match
        # history that belongs to nobody. Confirmed against real data: an
        # unnamed player with a 0-0 record spanning two different matches.
        if not player_id:
            logger.debug("Skipping a roster entry with no player id for match %s", match_id)
            continue

        # Ensure player exists
        player = upsert_player(db, player_id, player_name)

        # Check if this player-match combo already exists
        existing = (
            db.query(PlayerMatch)
            .filter_by(player_id=player.id, match_id=match.id)
            .one_or_none()
        )

        if existing:
            logger.debug("PlayerMatch for player %s in match %s already exists", player_id, match_id)
            continue

        # Create PlayerMatch record
        db.add(
            PlayerMatch(
                player_id=player.id,
                match_id=match.id,
                match_date=match.match_date,
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
    logger.info("Ingested %d player-match records for match %s", count, match_id)
    return count


def ingest_match_scores(db: Session, match_id, scores: list[dict]) -> tuple[int, int]:
    """Persist one match's per-player scoresheet rows.

    `match_id` is APA's own match id (Match.external_id) -- see
    _resolve_match_pk's docstring for why this isn't just PlayerMatch.match_id
    set directly: that shipped once already as an orphaned foreign key that
    nothing caught, because SQLite does not enforce FKs by default.

    Returns (created, updated). Unlike ingest_match_roster, an existing row is
    UPDATED rather than skipped: match_player_scores() can be re-run against
    the same match after it goes from unfinalized to finalized, and a
    forfeit/incomplete flag or the final result can change between those two
    reads. Deduped the same way, on (player_id, match_id).
    """
    match = _resolve_match_pk(db, match_id)
    created = updated = 0
    for entry in scores:
        player_id = entry.get("player_id") or ""
        player_name = entry.get("player_name") or ""

        # Same reasoning as ingest_match_roster's identical guard: a vacant/
        # forfeited scoresheet slot has no real player behind it, and every
        # such slot sharing a blank external_id would collapse into one
        # fake "player" across every match it happens in. This is the exact
        # bug found in a real export: an unnamed player with a 0-0 record
        # spanning two unrelated matches.
        if not player_id:
            logger.debug("Skipping a scoresheet entry with no player id for match %s", match_id)
            continue

        player = upsert_player(db, player_id, player_name)

        existing = (
            db.query(PlayerMatch)
            .filter_by(player_id=player.id, match_id=match.id)
            .one_or_none()
        )
        # opponent is the OTHER side's name, not this player's own team --
        # analytics.team_stats.head_to_head() filters PlayerMatch.opponent,
        # and without this it silently matched nothing for any row ingested
        # through this path.
        own_team_id = entry.get("team_id")
        if own_team_id == match.home_team_id:
            opponent = match.away_team_name
        elif own_team_id == match.away_team_id:
            opponent = match.home_team_name
        else:
            opponent = None

        fields = {
            "match_date": match.match_date,
            "opponent": opponent,
            "team_id": entry.get("team_id"),
            "team_name": entry.get("team_name"),
            "skill_level": _to_int(entry.get("skill_level")),
            "result": entry.get("result"),
            "points_earned": _to_float(entry.get("points_earned")),
        }
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            updated += 1
        else:
            db.add(PlayerMatch(player_id=player.id, match_id=match.id, **fields))
            created += 1

    db.commit()
    logger.info(
        "Ingested match %s scores: %d new, %d updated player-match row(s)",
        match_id, created, updated,
    )
    return created, updated


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


def ingest_player_career_stats(db: Session, player: Player, stats_row: dict) -> None:
    """Upsert one player's lifetime stats for ONE format (eight_ball_stats_row's
    output has both formats side by side; call this once per format --
    see ingest_eight_ball_stats below for the split).

    Unlike the per-match paths, this always overwrites in place on
    (player_id, format): lifetime totals only ever grow, so there is
    nothing worth keeping a history of the way StandingsSnapshot does.
    """
    format_ = stats_row["format"]
    existing = (
        db.query(PlayerCareerStats)
        .filter_by(player_id=player.id, format=format_)
        .one_or_none()
    )
    fields = {
        "matches_won": _to_int(stats_row.get("matches_won")),
        "matches_played": _to_int(stats_row.get("matches_played")),
        "cla": _to_int(stats_row.get("cla")),
        "defensive_shot_avg": _to_float(stats_row.get("defensive_shot_avg")),
        "match_count_last_two_yrs": _to_int(stats_row.get("match_count_last_two_yrs")),
        "last_played": stats_row.get("last_played"),
    }
    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
    else:
        db.add(PlayerCareerStats(player_id=player.id, format=format_, **fields))
    db.commit()


def ingest_eight_ball_stats(db: Session, player: Player, stats_row: dict) -> int:
    """Split scraper.graphql_scraper.eight_ball_stats_row's combined
    (both formats in one dict) shape into up to two PlayerCareerStats rows
    -- one per format that actually has data. Returns how many formats
    were written (0, 1, or 2).
    """
    written = 0
    if stats_row.get("eight_ball_matches_played") is not None:
        ingest_player_career_stats(db, player, {
            "format": "EIGHT",
            "matches_won": stats_row.get("eight_ball_matches_won"),
            "matches_played": stats_row.get("eight_ball_matches_played"),
            "cla": stats_row.get("eight_ball_cla"),
            "defensive_shot_avg": stats_row.get("eight_ball_defensive_shot_avg"),
            "match_count_last_two_yrs": stats_row.get("eight_ball_match_count_for_last_two_yrs"),
            "last_played": stats_row.get("eight_ball_last_played"),
        })
        written += 1
    if stats_row.get("nine_ball_matches_played") is not None:
        ingest_player_career_stats(db, player, {
            "format": "NINE",
            "matches_won": stats_row.get("nine_ball_matches_won"),
            "matches_played": stats_row.get("nine_ball_matches_played"),
            "cla": stats_row.get("nine_ball_cla"),
            "defensive_shot_avg": stats_row.get("nine_ball_defensive_shot_avg"),
            "match_count_last_two_yrs": stats_row.get("nine_ball_match_count_for_last_two_yrs"),
            "last_played": stats_row.get("nine_ball_last_played"),
        })
        written += 1
    logger.info("Ingested career stats for %s: %d format(s)", player.name, written)
    return written


def ingest_player_team_history(db: Session, player: Player, rows: list[dict]) -> int:
    """Upsert one row per (team, division, session) from TeamStat.

    TeamStat's response is the player's COMPLETE history every time, not
    an incremental diff -- upserting on the natural key means a rerun
    refreshes existing rows (a since-updated matches_won/rank, say)
    instead of accumulating duplicates.
    """
    count = 0
    for row in rows:
        existing = (
            db.query(PlayerTeamHistory)
            .filter_by(
                player_id=player.id,
                team_name=row.get("team_name") or "",
                division_id=row.get("division_id") or "",
                session_name=row.get("session_name") or "",
            )
            .one_or_none()
        )
        fields = {
            "is_current": bool(row.get("is_current")),
            "is_tournament": bool(row.get("is_tournament")),
            "nick_name": row.get("nick_name") or "",
            "skill_level": _to_int(row.get("skill_level")),
            "rank": _to_int(row.get("rank")),
            "matches_won": _to_int(row.get("matches_won")),
            "matches_played": _to_int(row.get("matches_played")),
        }
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
        else:
            db.add(
                PlayerTeamHistory(
                    player_id=player.id,
                    team_name=row.get("team_name") or "",
                    division_id=row.get("division_id") or "",
                    session_name=row.get("session_name") or "",
                    **fields,
                )
            )
        count += 1
    db.commit()
    logger.info("Ingested %d team-history row(s) for %s", count, player.name)
    return count


def ingest_head_to_head(db: Session, rows: list[dict]) -> int:
    """Upsert one PlayerHeadToHead row per (player, match), from
    scraper.graphql_scraper.head_to_head_rows() -- who a player actually
    played against, not just which two teams. head_to_head_rows() already
    returns both directions of a position pairing as separate rows, since
    each carries that player's own result/points/skill level rather than
    one shared symmetric fact.

    Requires the Match to already exist (ingest_match()) -- same
    requirement as ingest_match_scores. A row with no real player/opponent
    id is skipped, not guessed at -- head_to_head_rows() already filters
    these, but this stays defensive against a caller passing raw rows.
    """
    count = 0
    for row in rows:
        player_id = row.get("player_id") or ""
        opponent_id = row.get("opponent_id") or ""
        if not player_id or not opponent_id:
            logger.debug("Skipping a head-to-head row with a missing player/opponent id")
            continue

        match = _resolve_match_pk(db, row.get("match_id"))
        player = upsert_player(db, player_id, row.get("player_name") or "")
        opponent = upsert_player(db, opponent_id, row.get("opponent_name") or "")

        existing = (
            db.query(PlayerHeadToHead)
            .filter_by(player_id=player.id, match_id=match.id)
            .one_or_none()
        )
        fields = {
            "opponent_id": opponent.id,
            "own_skill_level": _to_int(row.get("own_skill_level")),
            "opponent_skill_level": _to_int(row.get("opponent_skill_level")),
            "result": row.get("result"),
            "points_earned": _to_float(row.get("points_earned")),
        }
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
        else:
            db.add(PlayerHeadToHead(player_id=player.id, match_id=match.id, **fields))
        count += 1
    db.commit()
    logger.info("Ingested %d head-to-head row(s)", count)
    return count


def ingest_matchups(db: Session, rows: list[dict]) -> int:
    """Upsert one PlayerMatchup row per (player, opponent) --
    analytics.matchups' computed aggregate, written by
    scripts/build_matchups.py. `rows` are plain dicts keyed by external
    player/opponent id plus the aggregate fields; both Player rows must
    already exist (from ingest_head_to_head) -- an id with no matching
    Player is skipped, not created from nothing.
    """
    count = 0
    for row in rows:
        player = db.query(Player).filter_by(external_id=row.get("player_id") or "").one_or_none()
        opponent = db.query(Player).filter_by(external_id=row.get("opponent_id") or "").one_or_none()
        if player is None or opponent is None:
            logger.debug("Skipping a matchup row for an unknown player/opponent id")
            continue

        existing = (
            db.query(PlayerMatchup)
            .filter_by(player_id=player.id, opponent_id=opponent.id)
            .one_or_none()
        )
        fields = {
            "matches_played": row.get("matches_played"),
            "win_rate": row.get("win_rate"),
            "avg_points_earned": row.get("avg_points_earned"),
            "avg_opponent_skill_level": row.get("avg_opponent_skill_level"),
            "trend": row.get("trend"),
            "volatility": row.get("volatility"),
            "matchup_score": row.get("matchup_score"),
        }
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
        else:
            db.add(PlayerMatchup(player_id=player.id, opponent_id=opponent.id, **fields))
        count += 1
    db.commit()
    logger.info("Ingested %d matchup row(s)", count)
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
