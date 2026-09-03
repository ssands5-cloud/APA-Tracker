"""
Daily sync job: log in, pull the latest standings and any new match
results for the configured team's roster, and ingest them.

Run manually with `python -m scheduler.daily_sync`, or wire it up to
Windows Task Scheduler / cron using the hour in apa_config.yaml
(scheduler.daily_sync_hour).
"""

from __future__ import annotations

import logging
import os

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auth.session_manager import SessionManager
from database.ingest import ingest_match, ingest_player_matches, ingest_standings, upsert_roster, upsert_team
from database.models import Base
from scraper.league_scraper import fetch_standings
from scraper.player_scraper import fetch_player_stats
from scraper.team_scraper import fetch_roster
from scraper.graphql_scraper import fetch_team_data, roster_rows, schedule_rows
from ui.export_excel import export_to_excel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def load_config(path: str = "apa_config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run(config_path: str = "apa_config.yaml") -> None:
    config = load_config(config_path)

    engine = create_engine(f"sqlite:///{config['database']['path']}")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        if config.get("apa", {}).get("access_token") or os.environ.get("APA_ACCESS_TOKEN"):
            live = fetch_team_data(config)
            team_data = live["team"]
            team = upsert_team(db, str(team_data.get("id") or config["team"]["team_id"]), team_data.get("name") or config["team"].get("team_name", ""))
            upsert_roster(db, team, roster_rows(live))
            for match in schedule_rows(live):
                if match["match_id"]:
                    ingest_match(
                        db,
                        match["match_id"],
                        match["home_team_id"],
                        match["away_team_id"],
                        match["home_team_name"],
                        match["away_team_name"],
                        match["location"],
                        match["date"],
                        match["status"],
                        match["home_score"],
                        match["away_score"],
                    )
            export_to_excel(db, config)
            logger.info("Fetched %d live matches and exported workbook", len(schedule_rows(live)))
        else:
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

    logger.info("Daily sync complete")


if __name__ == "__main__":
    run()
