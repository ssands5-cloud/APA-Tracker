"""
Weekly refresh job: full re-pull of standings and the team's roster, plus a
fresh Excel export. Meant to catch anything the lighter daily_sync misses
(new players, corrected results, schedule changes), and forces a fresh
login rather than reusing a cached session.

Run manually with `python -m scheduler.weekly_refresh`, or schedule it
for the day/hour in apa_config.yaml (scheduler.weekly_refresh_day/hour).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from auth.session_manager import SessionManager
from database.ingest import ingest_standings, upsert_roster, upsert_team
from database.engine import create_db_engine
from scheduler.daily_sync import load_config
from scraper.league_scraper import fetch_standings
from scraper.team_scraper import fetch_roster
from ui.export_excel import export_to_excel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def run(config_path: str = "apa_config.yaml") -> None:
    config = load_config(config_path)

    engine = create_db_engine(config)

    session_mgr = SessionManager(config)
    http_session = session_mgr.get_session(force_relogin=True)

    with Session(engine) as db:
        standings = fetch_standings(http_session, config)
        ingest_standings(db, standings)

        team_cfg = config.get("team", {})
        team = upsert_team(db, team_cfg.get("team_id", ""), team_cfg.get("team_name", ""))

        roster = fetch_roster(http_session, config)
        upsert_roster(db, team, roster)

        export_to_excel(db, config)

    logger.info("Weekly refresh complete")


if __name__ == "__main__":
    run()
