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

import yaml
from sqlalchemy.orm import Session

from database.engine import create_db_engine
from database.ingest import ingest_match, ingest_standings, upsert_roster, upsert_team
from scraper.graphql_scraper import (
    AccessTokenExpired,
    AccessTokenMissing,
    division_standings_rows,
    fetch_division_standings,
    fetch_team_data,
    roster_rows,
    schedule_rows,
    standings_rows,
    team_row,
)
from ui.export_excel import export_to_excel

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
    args = parser.parse_args()
    run(args.config, export=not args.no_export)
