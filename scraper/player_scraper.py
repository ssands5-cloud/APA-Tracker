"""
Scrapes an individual player's match history / stats page.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

from parser.apa_page_map import MATCH_PAGE

logger = logging.getLogger(__name__)

MATCH_TABLE_DATE_HEADERS = frozenset({"date", "match date", "matchdate", "when"})
MATCH_TABLE_OPPONENT_HEADERS = frozenset({"opponent", "opp", "vs", "vs."})


@dataclass
class PlayerStats:
    """Player's lifetime and session statistics."""

    player_id: str
    player_name: str
    lifetime_won: int
    lifetime_played: int
    ppm: float  # Points Per Match
    points_avail_pct: float
    break_and_run: int
    eight_on_break: int
    hackless: int
    total_points: int
    mini_slams: int


def fetch_player_stats(session: requests.Session, config: dict, player_id: str) -> dict:
    site = config["site"]
    url = site["base_url"].rstrip("/") + site["player_path_template"].format(player_id=player_id)
    timeout = config.get("session", {}).get("timeout_seconds", 15)

    logger.info("Fetching player page: %s", url)
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()

    return parse_player_stats(resp.text, player_id)


def parse_player_stats(html: str, player_id: str) -> dict:
    """Parse player profile page and extract stats."""
    soup = BeautifulSoup(html, "html.parser")

    # Extract player name from page header
    player_name = _extract_player_name(soup)

    # Try to extract lifetime stats from the visible metrics
    lifetime_stats = _extract_lifetime_stats(soup)

    return {
        "player_id": player_id,
        "player_name": player_name,
        "lifetime_stats": lifetime_stats,
        "matches": _extract_match_history(soup),
    }


def _extract_player_name(soup) -> str:
    """Extract player name from profile header."""
    # Look for player name in header, badge, or title
    header = soup.select_one("h1, h2, .profile-header")
    if header:
        return header.get_text(strip=True)

    # Fallback: look in meta or other places
    return "Unknown Player"


def _extract_lifetime_stats(soup) -> dict:
    """Extract lifetime stats metrics from the stats section."""
    stats = {
        "won": 0,
        "played": 0,
        "ppm": 0.0,
        "points_avail_pct": 0.0,
        "break_and_run": 0,
        "eight_on_break": 0,
        "hackless": 0,
        "total_points": 0,
        "mini_slams": 0,
    }

    # Look for stat blocks or divs containing numeric values
    # Common structure: stat name followed by number
    stat_labels = {
        "won": ["WON", "Wins"],
        "played": ["PLAYED", "Played"],
        "ppm": ["PPM", "Points Per Match"],
        "points_avail_pct": ["POINTS AVAIL", "% Points Avail", "% Points Available"],
        "break_and_run": ["BREAK-AND-RUN", "Break and Run"],
        "eight_on_break": ["8-ON-THE-BREAK", "8 on the Break"],
        "hackless": ["HACKLESS", "Hackless"],
        "total_points": ["TOTAL POINTS", "Total Points"],
        "mini_slams": ["MINI SLAMS", "Mini Slams"],
    }

    # Find all text nodes and number patterns
    text = soup.get_text()
    for stat_key, labels in stat_labels.items():
        for label in labels:
            if label.lower() in text.lower():
                # Try to find the number following this label
                pattern = re.escape(label) + r"\s*[:\s]*(\d+\.?\d*)"
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = match.group(1)
                    if "pct" in stat_key or "avail" in stat_key.lower():
                        stats[stat_key] = float(value) / 100.0
                    elif "ppm" in stat_key:
                        stats[stat_key] = float(value)
                    else:
                        stats[stat_key] = int(float(value))
                    break

    return stats


def _is_match_history_table(table) -> bool:
    """Return True when a table contains the date/opponent columns for match history."""
    header_text = {
        th.get_text(" ", strip=True).lower()
        for th in table.select("thead th, tr th, th")
        if th.get_text(" ", strip=True)
    }
    return bool(header_text & MATCH_TABLE_DATE_HEADERS) and bool(
        header_text & MATCH_TABLE_OPPONENT_HEADERS
    )


def _extract_match_history(soup) -> list[dict]:
    """Extract match history from the actual match table(s) on the page."""
    matches = []
    qualifying_tables = [table for table in soup.find_all("table") if _is_match_history_table(table)]

    if not qualifying_tables:
        logger.warning("No table on the player page looked like a match-history table")
        logger.info("Extracted %d match entries", len(matches))
        return matches

    for table in qualifying_tables:
        for row in table.select("tr"):
            cells = row.find_all(["td", "th"])
            if not cells or all(cell.name == "th" for cell in cells):
                continue
            if len(cells) < 3:
                continue
            match_entry = _parse_match_row(cells)
            if match_entry:
                matches.append(match_entry)

    logger.info("Extracted %d match entries", len(matches))
    return matches


def _parse_match_row(cells) -> Optional[dict]:
    """Parse a single match row from stats table."""
    if len(cells) < 3:
        return None

    try:
        match_date = cells[0].get_text(strip=True)
        opponent = cells[1].get_text(strip=True)
        result = cells[2].get_text(strip=True)

        # Optional additional columns
        skill_level = cells[3].get_text(strip=True) if len(cells) > 3 else None
        points_earned = cells[4].get_text(strip=True) if len(cells) > 4 else None

        return {
            "match_date": match_date,
            "opponent": opponent,
            "result": result,
            "skill_level": skill_level,
            "points_earned": points_earned,
        }
    except Exception as e:
        logger.debug("Error parsing match row: %s", e)
        return None


def fetch_and_parse_player(session: requests.Session, config: dict, player_id: str) -> dict:
    """High-level function: fetch and parse player profile in one call."""
    return fetch_player_stats(session, config, player_id)
