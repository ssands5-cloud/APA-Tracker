"""
Scrapes league-wide standings.
"""

from __future__ import annotations

import logging

import requests

from parser.apa_page_map import STANDINGS_PAGE
from parser.html_parser import parse_table

logger = logging.getLogger(__name__)


def fetch_standings(session: requests.Session, config: dict) -> list[dict]:
    """Fetch and parse the league standings table."""
    site = config["site"]
    url = site["base_url"].rstrip("/") + site["standings_path"]
    league_id = config.get("league", {}).get("league_id")
    params = {"league_id": league_id} if league_id else {}
    timeout = config.get("session", {}).get("timeout_seconds", 15)

    logger.info("Fetching standings: %s", url)
    resp = session.get(url, params=params, timeout=timeout)
    resp.raise_for_status()

    standings = parse_table(
        resp.text,
        STANDINGS_PAGE["table_selector"],
        STANDINGS_PAGE["row_selector"],
        STANDINGS_PAGE["columns"],
    )
    logger.info("Parsed %d standings rows", len(standings))
    return standings
