"""Live sync job: pull team data from the APA GraphQL API and ingest it.

This is the GraphQL counterpart to `daily_sync`, which scrapes HTML pages.
The team, roster and schedule pages on league.poolplayers.com are a
client-side app with no server-rendered HTML, so the data behind them is
only reachable this way.

Run manually with::

    python -m scheduler.graphql_sync

It needs a short-lived access token from your own logged-in session, read
from the environment only::

    $env:APA_ACCESS_TOKEN = "<token>"

The token is never written to disk, never logged, and never belongs in
apa_config.yaml.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from typing import Optional

import yaml
from sqlalchemy.orm import Session

from analytics.matchup_builder import build_matchups
from database.engine import create_db_engine
from database.ingest import (
    ingest_eight_ball_stats,
    ingest_head_to_head,
    ingest_match,
    ingest_match_scores,
    ingest_player_team_history,
    ingest_standings,
    upsert_player,
    upsert_roster,
    upsert_team,
)
from database.models import Match, Player, PlayerMatch
from database.queries import resolve_roster_identity
from scraper.graphql_scraper import (
    AccessTokenExpired,
    AccessTokenMissing,
    alias_id_for_league,
    dashboard_teams_rows,
    division_roster_team_rows,
    division_schedule_rows,
    division_standings_rows,
    eight_ball_stats_row,
    fetch_dashboard_teams,
    fetch_division_rosters,
    fetch_division_schedule,
    fetch_division_standings,
    fetch_eight_ball_stats,
    fetch_formats_by_member_id,
    fetch_match_detail,
    fetch_matches_by_viewer,
    fetch_team_data,
    fetch_team_stat,
    head_to_head_rows,
    match_player_scores,
    roster_rows,
    schedule_rows,
    standings_rows,
    team_row,
    team_stat_rows,
    viewer_matches_rows,
)
from ui.export_excel import export_to_excel
from ui.export_json import export_to_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def load_config(path: str = "apa_config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def ingest_team_data(db: Session, data: dict) -> dict[str, int]:
    """Map fetched GraphQL data onto the existing ingestion functions."""
    identity = team_row(data)
    team = upsert_team(
        db,
        identity["team_id"] or str((data.get("team") or {}).get("id") or ""),
        identity["team_name"],
    )

    roster = roster_rows(data)
    upsert_roster(db, team, roster)

    # Prefer the real division table when we have it: every team's rank and
    # points, as the API reports them. standings_rows is the fallback for a
    # config with no division id, and covers our team alone.
    division = data.get("division") or {}
    standings = division_standings_rows(division) if division.get("teams") else standings_rows(data)
    if standings:
        ingest_standings(db, standings)

    matches = schedule_rows(data)
    created = 0
    updated = 0
    for row in matches:
        if not row["match_id"]:
            logger.warning("Skipping a schedule entry with no match id: week %s", row.get("week"))
            continue
        # Byes are recorded too -- a missing week reads as lost data later.
        _, was_created = ingest_match(
            db,
            match_id=row["match_id"],
            home_team_id=row["home_team_id"],
            away_team_id=row["away_team_id"],
            home_team_name=row["home_team_name"],
            away_team_name="BYE" if row["is_bye"] else row["away_team_name"],
            location=row["location"],
            match_date=row["date"],
            status=row["status"],
            home_score=row["home_score"],
            away_score=row["away_score"],
            week=row["week"],
            is_bye=row["is_bye"],
            is_scored=row["is_scored"],
            is_finalized=row["is_finalized"],
            format=identity["format"],
            session_name=identity["session_name"],
        )
        created += was_created
        updated += not was_created

    return {
        "roster": len(roster),
        "standings": len(standings),
        "matches_seen": len(matches),
        "matches_new": created,
        "matches_updated": updated,
        "byes": sum(1 for row in matches if row["is_bye"]),
        "unscored": sum(1 for row in matches if not row["is_scored"]),
    }


def ingest_viewer_data(db: Session, viewer_teams: dict, viewer_matches: dict) -> dict[str, int]:
    """Ingest every team the account plays on, plus every match for all of
    them, from the two viewer-scoped queries -- no team_id configured
    anywhere. Standings are NOT fetched here: each team's own division
    standings needs a separate call per division id (see run_all_teams()),
    which touches the network and so is not exercised by this function --
    kept out on purpose so this stays fixture-testable.
    """
    team_rows = dashboard_teams_rows(viewer_teams)
    for row in team_rows:
        upsert_team(db, row["team_id"], row["team_name"])

    # P1-4: dashboardTeams already carries each team's division format
    # (division_type) and session_name -- MatchPage/the schedule itself
    # doesn't, so this is threaded in from the match's OWN team_id here,
    # at the one point both are in scope together, rather than guessed at
    # anywhere downstream.
    team_context = {row["team_id"]: row for row in team_rows}

    match_rows = viewer_matches_rows(viewer_matches)
    created = updated = 0
    for row in match_rows:
        if not row["match_id"]:
            logger.warning(
                "Skipping a viewer match entry with no match id: team %s week %s",
                row["team_id"], row.get("week"),
            )
            continue
        context = team_context.get(row["team_id"], {})
        _, was_created = ingest_match(
            db,
            match_id=row["match_id"],
            home_team_id=row["home_team_id"],
            away_team_id=row["away_team_id"],
            home_team_name=row["home_team_name"],
            away_team_name="BYE" if row["is_bye"] else row["away_team_name"],
            match_date=row["date"],
            status=row["status"],
            home_score=row["home_score"],
            away_score=row["away_score"],
            week=row["week"],
            is_bye=row["is_bye"],
            is_scored=row["is_scored"],
            is_finalized=row["is_finalized"],
            format=context.get("division_type"),
            session_name=context.get("session_name"),
        )
        created += was_created
        updated += not was_created

    return {
        "teams": len(team_rows),
        "matches_seen": len(match_rows),
        "matches_new": created,
        "matches_updated": updated,
        "byes": sum(1 for r in match_rows if r["is_bye"]),
        "unscored": sum(1 for r in match_rows if not r["is_scored"]),
    }


def match_already_has_scoresheet(db: Session, match_external_id) -> bool:
    """Whether match_external_id already has real per-player scoresheet
    rows ingested -- the checkpoint signal a resumed acquisition uses to
    skip the one expensive call (fetch_match_detail) it needs to skip.

    A real match whose CURRENT authoritative scoresheet has zero valid
    pairings (every position vacated/forfeited) also has no PlayerMatch
    rows, so it reads as "not yet fetched" and is refetched on every
    resume -- harmless (the same real, idempotent empty result each time),
    just not free. A real per-attempt ledger would avoid that at the cost
    of a new table; this project already accepts a slightly wider
    idempotent retry elsewhere (see database.ingest.ingest_head_to_head's
    delete-then-insert) rather than add state for a rare case.
    """
    match = db.query(Match).filter_by(external_id=str(match_external_id)).one_or_none()
    if match is None:
        return False
    return db.query(PlayerMatch).filter_by(match_id=match.id).first() is not None


def resolve_scoresheet_identities(
    db: Session, session_name: str, scores: list[dict], *, current_only: bool = True
) -> tuple[dict[str, str], int, int]:
    """Map each scoresheet row's own per-position alias player id to its
    real canonical-roster external id, via database.queries.
    resolve_roster_identity scoped to that row's own real team id and this
    session -- see that function's docstring for why the alias id is not a
    stable identity by itself.

    ``scores`` is match_player_scores()'s own output, the only mapper that
    carries a real team_id per row; head_to_head_rows()'s rows do not, but
    are derived from the SAME match detail and therefore share the SAME
    alias ids, so this one mapping covers both once built.

    Returns (alias_to_real_external_id, resolved_count, unresolved_count).
    An alias id absent from the mapping was not uniquely resolvable -- a
    caller must leave it exactly as the scoresheet reported it, never guess.
    """
    mapping: dict[str, str] = {}
    resolved = 0
    unresolved = 0
    seen: set[str] = set()
    for entry in scores:
        alias_id = entry.get("player_id")
        if not alias_id or alias_id in seen:
            continue
        seen.add(alias_id)
        team_id = entry.get("team_id")
        name = entry.get("player_name")
        if not team_id or not name:
            unresolved += 1
            continue
        real_player = resolve_roster_identity(
            db, team_id, session_name, name, current_only=current_only
        )
        if real_player is not None:
            mapping[alias_id] = real_player.external_id
            resolved += 1
        else:
            unresolved += 1
    return mapping, resolved, unresolved


def apply_identity_mapping(rows: list[dict], mapping: dict[str, str], keys: tuple[str, ...]) -> list[dict]:
    """A new list of rows with the given id keys rewritten through mapping.
    A key whose value has no entry in mapping is left exactly as-is."""
    rewritten = []
    for row in rows:
        new_row = dict(row)
        for key in keys:
            alias_id = new_row.get(key)
            if alias_id in mapping:
                new_row[key] = mapping[alias_id]
        rewritten.append(new_row)
    return rewritten


def run_all_teams(
    config_path: str = "apa_config.yaml", export: bool = True, db_path: Optional[str] = None,
    resume: bool = False,
) -> dict[str, int]:
    """Sync every team the account plays on, not just the one configured in
    apa_config.yaml's team.team_id.

    Added after the 2026-09-03 real capture proved a single hardcoded
    team_id cannot express reality: that account played on 4 teams across 4
    DIFFERENT divisions, which a single configured division_id could not
    have covered either -- so standings are fetched per division actually
    found on the account's own teams, not from config at all.

    ``db_path``, when given, overrides apa_config.yaml's own
    database.path -- the staging-database callers (a full production demo
    build) need every write to land in a scratch file, never in the
    configured real production database, until a separate, explicit
    promotion step decides otherwise.

    ``resume=True`` skips fetch_match_detail (the expensive, one-call-per-
    match step) for any scored match that already has real scoresheet rows
    from an earlier, interrupted run against this SAME database -- a real
    APA access token is short-lived and a full sync can outlast it. Cheap,
    idempotent calls (roster, schedule, standings) are always redone
    regardless, so a resumed run still discovers anything genuinely new.
    """
    config = load_config(config_path)
    if db_path:
        config.setdefault("database", {})["path"] = db_path

    try:
        viewer_teams = fetch_dashboard_teams(config)
        viewer_matches = fetch_matches_by_viewer(config)
    except (AccessTokenMissing, AccessTokenExpired) as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc

    team_rows = dashboard_teams_rows(viewer_teams)
    logger.info(
        "Found %d team(s) for this account: %s",
        len(team_rows), ", ".join(r["team_name"] for r in team_rows) or "(none)",
    )
    # Scoresheet identity resolution is scoped to (team, session): a real
    # session name per team id, read once here rather than per match below.
    session_by_team_id = {row["team_id"]: row["session_name"] for row in team_rows}

    engine = create_db_engine(config)
    with Session(engine) as db:
        counts = ingest_viewer_data(db, viewer_teams, viewer_matches)

        # One division standings fetch per DISTINCT division actually found
        # on the account's own teams -- not from config, and not one fetch
        # per team, since two teams can share a division.
        #
        # One shared timestamp for every division in THIS run: ingest_standings
        # defaults to datetime.utcnow() per call, and latest_standings() (what
        # the Excel/JSON exports read) filters to the single MAX captured_at --
        # so without a shared timestamp, only the last division processed ever
        # showed up in an export. Confirmed against a real 4-division account:
        # the Standings sheet had 10 rows instead of 40, silently.
        standings_count = 0
        synced_at = datetime.utcnow()
        for division_id in {row["division_id"] for row in team_rows if row["division_id"]}:
            try:
                division = fetch_division_standings(config, division_id=division_id)
            except (AccessTokenMissing, AccessTokenExpired):
                raise
            except Exception as exc:
                logger.warning(
                    "Could not fetch standings for division %s (%s: %s); skipping just that one.",
                    division_id, type(exc).__name__, exc,
                )
                continue
            rows = division_standings_rows(division)
            if rows:
                ingest_standings(db, rows, captured_at=synced_at)
                standings_count += len(rows)
        counts["standings"] = standings_count

        # Roster for every team found above -- fetch_team_data's team_id
        # override (added alongside this) means this is a flat loop over
        # team_rows, not a single hardcoded team.team_id from config.
        roster_count = 0
        for row in team_rows:
            try:
                data = fetch_team_data(config, team_id=row["team_id"])
            except (AccessTokenMissing, AccessTokenExpired):
                raise
            except Exception as exc:
                logger.warning(
                    "Could not fetch roster for team %s (%s: %s); skipping just that one.",
                    row["team_name"], type(exc).__name__, exc,
                )
                continue
            roster = roster_rows(data)
            if roster:
                team = upsert_team(db, row["team_id"], row["team_name"])
                upsert_roster(db, team, roster)
                roster_count += len(roster)
        counts["roster"] = roster_count

        # Per-player scoresheet for every match that's actually been played.
        # fetch_match_detail is the one query with real per-player stats
        # (skill level, win/loss, points earned) -- the schedule/team
        # queries above only carry the team-level score. One call per
        # SCORED match id already known from viewer_matches_rows -- no
        # per-week or per-team navigation, just a flat loop over match ids
        # the account's own dashboard already reported.
        scoresheet_count = 0
        head_to_head_count = 0
        identity_resolved_count = 0
        identity_unresolved_count = 0
        for row in viewer_matches_rows(viewer_matches):
            if not row["match_id"] or not row["is_scored"]:
                continue
            if resume and match_already_has_scoresheet(db, row["match_id"]):
                # Both ingest_match_scores and ingest_head_to_head already
                # completed for this match in an earlier, interrupted run
                # against this same database -- they run back-to-back with
                # no yield point between them, so PlayerMatch rows existing
                # proves both finished for this match specifically.
                continue
            try:
                match = fetch_match_detail(config, int(row["match_id"]))
            except (AccessTokenMissing, AccessTokenExpired):
                raise
            except Exception as exc:
                logger.warning(
                    "Could not fetch match detail for match %s (%s: %s); skipping just that one.",
                    row["match_id"], type(exc).__name__, exc,
                )
                continue
            scores = match_player_scores(match)
            # Resolve each scoresheet alias id to its real canonical-roster
            # identity BEFORE ingesting -- see resolve_scoresheet_identities'
            # docstring for why the scoresheet's own id is not stable.
            session_name = session_by_team_id.get(row["team_id"], "")
            identity_map, resolved_n, unresolved_n = resolve_scoresheet_identities(
                db, session_name, scores
            )
            identity_resolved_count += resolved_n
            identity_unresolved_count += unresolved_n
            scores = apply_identity_mapping(scores, identity_map, ("player_id",))
            if scores:
                created, updated = ingest_match_scores(db, row["match_id"], scores)
                scoresheet_count += created + updated
            # Called for EVERY scored match, not only when head_to_head_rows()
            # is truthy (P1-7): a match whose corrected scoresheet now has
            # ZERO valid pairings must still reconcile away its old ones --
            # skipping the call here entirely would leave those stale
            # forever, since ingest_head_to_head has no other way to learn
            # this match_id needs reconciling.
            h2h_rows = apply_identity_mapping(
                head_to_head_rows(match), identity_map, ("player_id", "opponent_id")
            )
            head_to_head_count += ingest_head_to_head(db, row["match_id"], h2h_rows)
        counts["scoresheet_rows"] = scoresheet_count
        counts["head_to_head_rows"] = head_to_head_count
        counts["identity_resolved"] = identity_resolved_count
        counts["identity_unresolved"] = identity_unresolved_count

        # Career stats (getEightBallStats) and cross-season team history
        # (TeamStat) for the ACCOUNT'S OWN member -- HANDOFF.md item 2,
        # confirmed 2026-09-03 against a real account. The alias id these
        # two queries need is neither a roster entry's own id nor
        # roster[].member.id; it's reached via fetch_formats_by_member_id,
        # one alias per (member, league). One fetch for the member's alias
        # list, then one alias_id per DISTINCT (league, format) actually
        # found on the account's own teams -- the same "found on the
        # account, not from config" principle as the standings loop above.
        #
        # Requires the viewer's own Player row (from the roster loop above,
        # keyed on member id) to already exist -- upsert_player() would
        # otherwise create a nameless placeholder here, and it should
        # already exist unless roster ingestion for every one of the
        # account's own teams somehow failed.
        career_stats_count = team_history_count = 0
        member_id = viewer_teams.get("id")
        viewer_player = db.query(Player).filter_by(external_id=str(member_id)).one_or_none() if member_id else None
        if member_id and viewer_player is None:
            logger.warning(
                "Viewer's own Player row (member id %s) not found -- skipping career "
                "stats/team history this run.", member_id,
            )
        elif member_id:
            try:
                member = fetch_formats_by_member_id(config, member_id)
            except (AccessTokenMissing, AccessTokenExpired):
                raise
            except Exception as exc:
                logger.warning(
                    "Could not fetch member aliases (%s: %s); skipping career stats/team history.",
                    type(exc).__name__, exc,
                )
                member = {}

            seen_alias_ids: set[int] = set()
            for row in team_rows:
                alias_id = alias_id_for_league(member, row["league_id"], format_=row["division_type"])
                if not alias_id or alias_id in seen_alias_ids:
                    continue
                seen_alias_ids.add(alias_id)
                try:
                    stats = fetch_eight_ball_stats(config, alias_id)
                    team_stat = fetch_team_stat(config, alias_id)
                except (AccessTokenMissing, AccessTokenExpired):
                    raise
                except Exception as exc:
                    logger.warning(
                        "Could not fetch stats for alias %s (%s: %s); skipping just that one.",
                        alias_id, type(exc).__name__, exc,
                    )
                    continue
                career_stats_count += ingest_eight_ball_stats(db, viewer_player, eight_ball_stats_row(stats))
                team_history_count += ingest_player_team_history(db, viewer_player, team_stat_rows(team_stat))
        counts["career_stats"] = career_stats_count
        counts["team_history"] = team_history_count

        # Matchup Advantage Engine -- aggregates the head-to-head rows just
        # ingested above (in the scoreboard loop) into player_matchups.
        # Must run after that ingestion and before export, or the Excel/
        # JSON "Matchups" sheet/key would always be empty on a real sync:
        # scripts/build_matchups.py existing as a separate, manually-run
        # script was the actual gap -- nothing wired this into the live
        # sync itself.
        matchup_rows = build_matchups(db)
        counts["matchups"] = len(matchup_rows)

        if export:
            path = export_to_excel(db, config)
            logger.info("Excel export written to %s", path)
            json_path = export_to_json(db, config)
            logger.info("JSON export written to %s", json_path)

    logger.info(
        "All-teams sync complete: %d team(s), %d roster entries, %d standings row(s) "
        "across their divisions, %d/%d matches new (%d byes, %d not yet scored), "
        "%d player scoresheet row(s) across every scored match, %d career stat "
        "format(s), %d team-history row(s), %d matchup(s) computed",
        counts["teams"], counts["roster"], counts["standings"], counts["matches_new"],
        counts["matches_seen"], counts["byes"], counts["unscored"], counts["scoresheet_rows"],
        counts["career_stats"], counts["team_history"], counts["matchups"],
    )
    return counts


def _division_context(config: dict, team_rows: list[dict]) -> dict[str, dict]:
    """One real (format, session_name) per distinct division found on the
    account's own teams.

    Neither DIVISION_ROSTERS_QUERY nor DIVISION_SCHEDULE_QUERY carries a
    human-readable format string or a session name -- only TEAM_PAGE_QUERY
    does. One representative viewer-owned team per division is enough to
    read both, since a division has exactly one format and one session by
    construction; querying it once per division rather than once per team
    is deliberate.
    """
    context: dict[str, dict] = {}
    for row in team_rows:
        division_id = row["division_id"]
        if not division_id or division_id in context:
            continue
        try:
            data = fetch_team_data(config, team_id=row["team_id"])
        except (AccessTokenMissing, AccessTokenExpired):
            raise
        except Exception as exc:
            logger.warning(
                "Could not fetch format/session context for division %s (%s: %s); "
                "skipping that division's whole-division sync.",
                division_id, type(exc).__name__, exc,
            )
            continue
        info = team_row(data)
        context[division_id] = {
            "format": info["format"],
            "session_name": info["session_name"],
        }
    return context


def sync_division_wide(
    config: dict,
    db: Session,
    division_id: str,
    division_format: str,
    division_session_name: str,
    resume: bool = False,
    *,
    roster_is_current: bool = True,
    identity_current_only: bool = True,
) -> dict[str, int]:
    """Every accessible team's current roster and every scheduled/completed
    match in ONE division -- not only the account's own teams.

    Each roster player's membership is written to PlayerTeamHistory via the
    same ingest_player_team_history() upsert run_all_teams already uses.
    Current live syncs keep roster_is_current=True. Career backfill passes
    False for old divisions so historical memberships can support identity
    resolution without ever masquerading as today's roster. In that mode
    identity_current_only=False resolves within the exact historical
    team+session membership instead of requiring a current-row flag.

    ``resume=True`` skips fetch_match_detail for a scored match that already
    has real scoresheet rows from an earlier, interrupted run against this
    SAME database -- see match_already_has_scoresheet(). Roster and schedule
    fetches are always redone regardless: they are one cheap call per
    division each, not one call per match, so resuming gains nothing by
    skipping them and could miss something genuinely new.

    Returns both DISCOVERED and INGESTED counts so a caller can prove
    complete coverage rather than trusting that nothing silently dropped.
    """
    counts = {
        "teams_discovered": 0, "teams_ingested": 0,
        "roster_players_discovered": 0, "roster_players_ingested": 0,
        "matches_discovered": 0, "matches_ingested": 0,
        "scored_matches_discovered": 0, "scored_matches_with_scoresheet": 0,
        "head_to_head_rows": 0,
        "identity_resolved": 0, "identity_unresolved": 0,
    }

    try:
        rosters = fetch_division_rosters(config, division_id)
    except (AccessTokenMissing, AccessTokenExpired):
        raise
    except Exception as exc:
        logger.warning(
            "Could not fetch division rosters for division %s (%s: %s); "
            "this division's coverage will be reported incomplete.",
            division_id, type(exc).__name__, exc,
        )
        rosters = {}

    for team in division_roster_team_rows(rosters):
        counts["teams_discovered"] += 1
        team_obj = upsert_team(db, team["team_id"], team["team_name"])
        counts["teams_ingested"] += 1
        for entry in team["roster"]:
            counts["roster_players_discovered"] += 1
            if not entry["player_id"]:
                continue  # a vacant slot names no real player to upsert
            player = upsert_player(db, entry["player_id"], entry["player_name"], team_obj)
            written = ingest_player_team_history(db, player, [{
                "team_id": team["team_id"], "team_name": team["team_name"],
                "division_id": division_id, "session_name": division_session_name,
                "is_current": roster_is_current, "skill_level": entry["skill_level"],
                "matches_won": entry["matches_won"], "matches_played": entry["matches_played"],
            }])
            counts["roster_players_ingested"] += written

    try:
        schedule = fetch_division_schedule(config, division_id)
    except (AccessTokenMissing, AccessTokenExpired):
        raise
    except Exception as exc:
        logger.warning(
            "Could not fetch division schedule for division %s (%s: %s); "
            "this division's coverage will be reported incomplete.",
            division_id, type(exc).__name__, exc,
        )
        schedule = {}

    for match in division_schedule_rows(schedule):
        if match["is_bye"]:
            continue
        counts["matches_discovered"] += 1
        ingest_match(
            db, match_id=match["match_id"],
            home_team_id=match["home_team_id"], away_team_id=match["away_team_id"],
            home_team_name=match["home_team_name"], away_team_name=match["away_team_name"],
            match_date=match["date"], status=match["status"],
            home_score=match["home_score"], away_score=match["away_score"],
            week=match["week"], is_bye=False,
            is_scored=match["is_scored"], is_finalized=match["is_finalized"],
            format=division_format, session_name=division_session_name,
        )
        counts["matches_ingested"] += 1

        if not match["is_scored"]:
            continue
        counts["scored_matches_discovered"] += 1

        if resume and match_already_has_scoresheet(db, match["match_id"]):
            # Already fetched and ingested (scores + head-to-head both,
            # same back-to-back-calls guarantee as run_all_teams's loop) in
            # an earlier, interrupted run against this same database.
            counts["scored_matches_with_scoresheet"] += 1
            continue

        try:
            detail = fetch_match_detail(config, int(match["match_id"]))
        except (AccessTokenMissing, AccessTokenExpired):
            raise
        except Exception as exc:
            logger.warning(
                "Could not fetch scoresheet for match %s (%s: %s); skipping just that one.",
                match["match_id"], type(exc).__name__, exc,
            )
            continue
        scores = match_player_scores(detail)
        # Resolve each scoresheet alias id to its real canonical-roster
        # identity BEFORE ingesting -- see resolve_scoresheet_identities'
        # docstring for why the scoresheet's own id is not stable.
        identity_map, resolved_n, unresolved_n = resolve_scoresheet_identities(
            db, division_session_name, scores, current_only=identity_current_only
        )
        counts["identity_resolved"] += resolved_n
        counts["identity_unresolved"] += unresolved_n
        scores = apply_identity_mapping(scores, identity_map, ("player_id",))
        if scores:
            created, updated = ingest_match_scores(db, match["match_id"], scores)
            # A non-empty `scores` list only proves APA returned scoresheet
            # rows to fetch -- it does not prove any were persisted.
            # ingest_match_scores() silently skips every entry with a blank
            # player_id (vacant/forfeited/malformed rows), and can legally
            # return (0, 0) even though `scores` itself was truthy. Counting
            # coverage on `scores` alone let reconcile_division_wide_coverage()
            # -- the actual promotion gate -- report a division complete while
            # some of its matches had zero real PlayerMatch rows. Count only
            # matches that actually got at least one persisted row.
            if created or updated:
                counts["scored_matches_with_scoresheet"] += 1
        h2h_rows = apply_identity_mapping(
            head_to_head_rows(detail), identity_map, ("player_id", "opponent_id")
        )
        counts["head_to_head_rows"] += ingest_head_to_head(db, match["match_id"], h2h_rows)

    return counts


def reconcile_division_wide_coverage(totals: dict[str, int]) -> list[str]:
    """Every discovered team/match/scored-match must have been ingested.

    Returns the list of coverage gaps found -- empty means complete. This is
    a promotion gate, not a log line: a caller with a non-empty result must
    refuse to promote the staging database, never merely warn.
    """
    problems = []
    if totals["teams_ingested"] < totals["teams_discovered"]:
        problems.append(
            f"{totals['teams_discovered'] - totals['teams_ingested']} discovered "
            f"team(s) were not ingested"
        )
    if totals["roster_players_ingested"] < totals["roster_players_discovered"]:
        problems.append(
            f"{totals['roster_players_discovered'] - totals['roster_players_ingested']} "
            f"discovered roster player(s) were not ingested"
        )
    if totals["matches_ingested"] < totals["matches_discovered"]:
        problems.append(
            f"{totals['matches_discovered'] - totals['matches_ingested']} discovered "
            f"scheduled match(es) were not ingested"
        )
    if totals["scored_matches_with_scoresheet"] < totals["scored_matches_discovered"]:
        problems.append(
            f"{totals['scored_matches_discovered'] - totals['scored_matches_with_scoresheet']} "
            f"completed match(es) have no scoresheet"
        )
    return problems


def run_division_wide(
    config_path: str = "apa_config.yaml", export: bool = False, db_path: Optional[str] = None,
    resume: bool = False,
) -> dict:
    """Every accessible team, current roster, scheduled match, and completed
    scoresheet in each division the account's own teams belong to.

    Layered on top of run_all_teams() rather than duplicating it: that call
    ingests everything for the account's OWN teams and is independently
    tested. This adds every OTHER team in each of those same divisions --
    their current rosters, their scheduled matches, and their completed
    scoresheets -- which no existing entry point covers.

    ``db_path`` overrides apa_config.yaml's own database.path for BOTH the
    run_all_teams() call below and this function's own writes -- a staging
    build must never touch the configured real production database.

    ``resume=True`` is for a caller that deliberately did NOT delete an
    existing staging database from an earlier, interrupted run (a real APA
    access token is short-lived and a full division-wide sync can outlast
    it): every already-fetched scoresheet is skipped, so only what a fresh
    token still needs to cover actually gets fetched.

    Returns {"own_teams": <run_all_teams' counts>, "division_wide": <summed
    sync_division_wide counts>, "coverage_gaps": <reconcile_division_wide_
    coverage's result>}. A non-empty "coverage_gaps" means this run must not
    be promoted.
    """
    own_counts = run_all_teams(config_path, export=False, db_path=db_path, resume=resume)

    config = load_config(config_path)
    if db_path:
        config.setdefault("database", {})["path"] = db_path
    try:
        viewer_teams = fetch_dashboard_teams(config)
    except (AccessTokenMissing, AccessTokenExpired) as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc
    team_rows = dashboard_teams_rows(viewer_teams)
    division_ids = sorted({row["division_id"] for row in team_rows if row["division_id"]})

    engine = create_db_engine(config)
    totals = {
        "teams_discovered": 0, "teams_ingested": 0,
        "roster_players_discovered": 0, "roster_players_ingested": 0,
        "matches_discovered": 0, "matches_ingested": 0,
        "scored_matches_discovered": 0, "scored_matches_with_scoresheet": 0,
        "head_to_head_rows": 0,
        "identity_resolved": 0, "identity_unresolved": 0,
    }
    with Session(engine) as db:
        context = _division_context(config, team_rows)
        for division_id in division_ids:
            info = context.get(division_id)
            if not info:
                logger.warning(
                    "No format/session context for division %s -- its whole-division "
                    "coverage will be reported incomplete.", division_id,
                )
                continue
            counts = sync_division_wide(
                config, db, division_id, info["format"], info["session_name"], resume=resume,
            )
            for key in totals:
                totals[key] += counts[key]

        matchup_rows = build_matchups(db)
        totals["matchups"] = len(matchup_rows)

        if export:
            export_to_excel(db, config)
            export_to_json(db, config)

    coverage_gaps = reconcile_division_wide_coverage(totals)
    identity_total = totals["identity_resolved"] + totals["identity_unresolved"]
    identity_rate = (
        round(totals["identity_resolved"] / identity_total, 4) if identity_total else None
    )
    logger.info(
        "Division-wide sync complete: %d division(s), %d team(s) discovered "
        "(%d ingested), %d roster player(s) discovered (%d ingested), %d match(es) "
        "discovered (%d ingested), %d scored match(es) discovered (%d with a "
        "scoresheet). Scoresheet identity: %d resolved to canonical roster, %d "
        "unresolved (rate %s). Coverage gaps: %s",
        len(division_ids), totals["teams_discovered"], totals["teams_ingested"],
        totals["roster_players_discovered"], totals["roster_players_ingested"],
        totals["matches_discovered"], totals["matches_ingested"],
        totals["scored_matches_discovered"], totals["scored_matches_with_scoresheet"],
        totals["identity_resolved"], totals["identity_unresolved"],
        "n/a" if identity_rate is None else f"{identity_rate * 100:.1f}%",
        "none" if not coverage_gaps else "; ".join(coverage_gaps),
    )
    return {
        "own_teams": own_counts, "division_wide": totals, "coverage_gaps": coverage_gaps,
        "identity_resolution_rate": identity_rate,
    }


def run(config_path: str = "apa_config.yaml", export: bool = True) -> dict[str, int]:
    config = load_config(config_path)

    try:
        data = fetch_team_data(config)
    except (AccessTokenMissing, AccessTokenExpired) as exc:
        # These are the user's to fix, and the traceback adds nothing.
        logger.error("%s", exc)
        raise SystemExit(1) from exc

    identity = team_row(data)
    logger.info(
        "Fetched %s (#%s) -- %s, %s, standing %s",
        identity["team_name"] or "(unnamed team)",
        identity["team_number"],
        identity["division_name"] or "(no division)",
        identity["session_name"] or "(no session)",
        identity["standing"],
    )

    # The division table is a separate query on a separate id, and it is a
    # bonus rather than the point of the run: a failure here (a wrong division
    # id, say) must not throw away the team data already fetched. An expired
    # token is the exception -- that means nothing else will work either.
    try:
        data["division"] = fetch_division_standings(config)
        team_count = len((data["division"] or {}).get("teams") or [])
        if team_count:
            logger.info("Fetched division standings for %d teams", team_count)
    except (AccessTokenMissing, AccessTokenExpired):
        raise
    except Exception as exc:
        logger.warning(
            "Could not fetch division standings (%s: %s). Continuing with this "
            "team's own standing only.", type(exc).__name__, exc,
        )
        data["division"] = {}

    engine = create_db_engine(config)

    with Session(engine) as db:
        counts = ingest_team_data(db, data)
        if export:
            path = export_to_excel(db, config)
            logger.info("Excel export written to %s", path)
            json_path = export_to_json(db, config)
            logger.info("JSON export written to %s", json_path)

    logger.info(
        "Sync complete: %d roster entries, %d/%d matches new (%d byes, %d not yet scored)",
        counts["roster"],
        counts["matches_new"],
        counts["matches_seen"],
        counts["byes"],
        counts["unscored"],
    )
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="apa_config.yaml")
    parser.add_argument("--no-export", action="store_true", help="Skip the Excel export")
    parser.add_argument(
        "--single-team", action="store_true",
        help="Sync only apa_config.yaml's configured team.team_id (the original, "
             "narrower path). Default is every team the account plays on, "
             "discovered from the account itself -- see run_all_teams().",
    )
    args = parser.parse_args()
    if args.single_team:
        run(args.config, export=not args.no_export)
    else:
        run_all_teams(args.config, export=not args.no_export)
