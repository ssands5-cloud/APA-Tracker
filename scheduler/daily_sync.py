"""
Daily sync job: pull the latest team data and ingest it.

Two modes, chosen by whether an APA access token is available:

  live GraphQL  when APA_ACCESS_TOKEN is set. Team, roster, schedule and a
                standings snapshot come from the API, then the workbook is
                refreshed. This is the only mode that can see the team pages,
                which are a client-side app with no HTML to scrape.
  HTML scrape   otherwise. Logs in with a cached cookie session and scrapes
                the pages that are still server-rendered, including per-player
                match history, which the captured GraphQL queries do not cover.

Run manually with `python -m scheduler.daily_sync`, or wire it up to
Windows Task Scheduler / cron using the hour in apa_config.yaml
(scheduler.daily_sync_hour).
"""

from __future__ import annotations

import logging
import os

import yaml
from sqlalchemy.orm import Session

from auth.session_manager import SessionManager
from database.engine import create_db_engine
from database.ingest import ingest_player_matches, ingest_standings, upsert_roster, upsert_team
from scraper.league_scraper import fetch_standings
from scraper.player_scraper import fetch_player_stats
from scraper.team_scraper import fetch_roster
from ui.export_excel import export_to_excel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def load_config(path: str = "apa_config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _has_access_token(config: dict) -> bool:
    return bool(
        (config.get("apa") or {}).get("access_token") or os.environ.get("APA_ACCESS_TOKEN")
    )


def run(config_path: str = "apa_config.yaml") -> None:
    config = load_config(config_path)

    if _has_access_token(config):
        # Delegated rather than reimplemented. A second copy of the live path
        # lived here and had already drifted: it skipped the standings
        # snapshot entirely and called schedule_rows twice.
        from scheduler.graphql_sync import run as run_live

        logger.info("APA_ACCESS_TOKEN found -- running the live GraphQL sync")
        run_live(config_path, export=True)
        logger.info("Daily sync complete (live GraphQL)")
        return

    logger.info("No APA_ACCESS_TOKEN -- falling back to the HTML scrape path")
    engine = create_db_engine(config)

    with Session(engine) as db:
        session_mgr = SessionManager(config)
        http_session = session_mgr.get_session()

        standings = fetch_standings(http_session, config)
        ingest_standings(db, standings)

        team_cfg = config.get("team", {})
        team = upsert_team(db, team_cfg.get("team_id", ""), team_cfg.get("team_name", ""))

        roster = fetch_roster(http_session, config)
        upsert_roster(db, team, roster)

        for player in team.players:
            try:
                stats = fetch_player_stats(http_session, config, player.external_id)
            except Exception:
                logger.exception("Failed to fetch stats for player %s", player.name)
                continue
            ingest_player_matches(db, player, stats["matches"])

        # Previously missing: the job ingested everything and then ended
        # without refreshing the workbook, so the Excel file only ever
        # updated on the weekly run.
        export_to_excel(db, config)

    logger.info("Daily sync complete (HTML scrape)")


if __name__ == "__main__":
    run()
