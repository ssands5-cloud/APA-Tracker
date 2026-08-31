"""
Scrapes a single team's roster and match schedule.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from parser.apa_page_map import TEAM_PAGE
from parser.html_parser import parse_table

logger = logging.getLogger(__name__)


def fetch_team_page(session: requests.Session, config: dict, team_id: Optional[str] = None) -> str:
    site = config["site"]
    team_id = team_id or config.get("team", {}).get("team_id")
    url = site["base_url"].rstrip("/") + site["team_path_template"].format(team_id=team_id)
    timeout = config.get("session", {}).get("timeout_seconds", 15)

    logger.info("Fetching team page: %s", url)
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_roster(session: requests.Session, config: dict, team_id: Optional[str] = None) -> list[dict]:
    html = fetch_team_page(session, config, team_id)
    roster = parse_table(
        html,
        TEAM_PAGE["roster_table_selector"],
        TEAM_PAGE["roster_row_selector"],
        TEAM_PAGE["roster_columns"],
    )
    logger.info("Parsed %d roster entries", len(roster))
    return roster


def fetch_schedule(session: requests.Session, config: dict, team_id: Optional[str] = None) -> list[dict]:
    html = fetch_team_page(session, config, team_id)
    schedule = parse_table(
        html,
        TEAM_PAGE["schedule_table_selector"],
        TEAM_PAGE["schedule_row_selector"],
        TEAM_PAGE["schedule_columns"],
    )
    logger.info("Parsed %d schedule entries", len(schedule))
    return schedule
