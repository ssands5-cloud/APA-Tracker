"""
Scrapes an individual player's match history / stats page.
"""

from __future__ import annotations

import logging

import requests

from parser.apa_page_map import PLAYER_PAGE
from parser.html_parser import parse_summary_block, parse_table

logger = logging.getLogger(__name__)


def fetch_player_stats(session: requests.Session, config: dict, player_id: str) -> dict:
    site = config["site"]
    url = site["base_url"].rstrip("/") + site["player_path_template"].format(player_id=player_id)
    timeout = config.get("session", {}).get("timeout_seconds", 15)

    logger.info("Fetching player page: %s", url)
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()

    summary = parse_summary_block(resp.text, PLAYER_PAGE["summary_selector"])
    matches = parse_table(
        resp.text,
        PLAYER_PAGE["stats_table_selector"],
        PLAYER_PAGE["stats_row_selector"],
        PLAYER_PAGE["stats_columns"],
    )
    logger.info("Parsed %d match rows for player %s", len(matches), player_id)
    return {"player_id": player_id, "summary": summary, "matches": matches}
