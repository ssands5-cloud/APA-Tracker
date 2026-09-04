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
    upsert_roster,
    upsert_team,
)
from database.models import Player
from scraper.graphql_scraper import (
    AccessTokenExpired,
    AccessTokenMissing,
    alias_id_for_league,
    dashboard_teams_rows,
    division_standings_rows,
    eight_ball_stats_row,
    fetch_dashboard_teams,
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

    match_rows = viewer_matches_rows(viewer_matches)
    created = updated = 0
    for row in match_rows:
        if not row["match_id"]:
            logger.warning(
                "Skipping a viewer match entry with no match id: team %s week %s",
                row["team_id"], row.get("week"),
            )
            continue
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


def run_all_teams(config_path: str = "apa_config.yaml", export: bool = True) -> dict[str, int]:
    """Sync every team the account plays on, not just the one configured in
    apa_config.yaml's team.team_id.

    Added after the 2026-09-03 real capture proved a single hardcoded
    team_id cannot express reality: that account played on 4 teams across 4
    DIFFERENT divisions, which a single configured division_id could not
    have covered either -- so standings are fetched per division actually
    found on the account's own teams, not from config at all.
    """
    config = load_config(config_path)

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
        for row in viewer_matches_rows(viewer_matches):
            if not row["match_id"] or not row["is_scored"]:
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
            if scores:
                created, updated = ingest_match_scores(db, row["match_id"], scores)
                scoresheet_count += created + updated
            head_to_head = head_to_head_rows(match)
            if head_to_head:
                head_to_head_count += ingest_head_to_head(db, head_to_head)
        counts["scoresheet_rows"] = scoresheet_count
        counts["head_to_head_rows"] = head_to_head_count

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
