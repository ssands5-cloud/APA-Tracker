"""
Daily sync job: log in, pull the latest standings and any new match
results for the configured team's roster, and ingest them.

Run manually with `python -m scheduler.daily_sync`, or wire it up to
Windows Task Scheduler / cron using the hour in apa_config.yaml
(scheduler.daily_sync_hour).
"""

from __future__ import annotations

import logging

import yaml
from sqlalchemy.orm import Session

from auth.session_manager import SessionManager
from database.ingest import ingest_player_matches, ingest_standings, upsert_roster, upsert_team
from database.engine import create_db_engine
from scraper.league_scraper import fetch_standings
from scraper.player_scraper import fetch_player_stats
from scraper.team_scraper import fetch_roster

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def load_config(path: str = "apa_config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run(config_path: str = "apa_config.yaml") -> None:
    config = load_config(config_path)

    engine = create_db_engine(config)

    session_mgr = SessionManager(config)
    http_session = session_mgr.get_session()

    with Session(engine) as db:
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

    logger.info("Daily sync complete")


if __name__ == "__main__":
    run()
