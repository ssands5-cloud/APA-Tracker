"""
Scrapes a single team's roster and match schedule.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

from parser.apa_page_map import TEAM_PAGE, MATCH_PAGE

logger = logging.getLogger(__name__)


@dataclass
class TeamMember:
    """A player on a team's roster."""

    player_name: str
    player_id: str
    skill_level: int
    matches_won: int
    matches_played: int
    win_pct: float
    ppm: float
    pa: float  # Points Available


@dataclass
class TeamRosterData:
    """Complete team roster data."""

    team_id: str
    team_name: str
    members: list[TeamMember]


def fetch_team_page(session: requests.Session, config: dict, team_id: Optional[str] = None) -> str:
    site = config["site"]
    team_id = team_id or config.get("team", {}).get("team_id")
    url = site["base_url"].rstrip("/") + site["team_path_template"].format(team_id=team_id)
    timeout = config.get("session", {}).get("timeout_seconds", 15)

    logger.info("Fetching team page: %s", url)
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_team_roster(html: str, team_id: str) -> TeamRosterData:
    """Parse team HTML and extract roster."""
    soup = BeautifulSoup(html, "html.parser")

    # Extract team name (best-effort; selector may not always match)
    team_name = f"Team {team_id}"
    try:
        team_link = soup.select_one(MATCH_PAGE["team_name_selector"])
        if team_link:
            team_name = team_link.get_text(strip=True) or team_name
    except Exception as e:
        logger.warning("Error extracting team name for %s: %s", team_id, e)

    # Find roster table
    table = soup.select_one(MATCH_PAGE["table_selector"])
    if not table:
        logger.warning("No roster table found for team %s", team_name)
        return TeamRosterData(team_id=team_id, team_name=team_name, members=[])

    # Parse player rows
    members = _parse_roster_rows(table)
    logger.info("Parsed %d members for team %s", len(members), team_name)

    return TeamRosterData(team_id=team_id, team_name=team_name, members=members)


def _parse_roster_rows(table) -> list[TeamMember]:
    """Parse all player rows from a roster table."""
    members = []
    rows = table.select(MATCH_PAGE["table_row_selector"])

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 6:
            logger.debug("Row has fewer than 6 cells, skipping")
            continue

        try:
            member = _parse_roster_row(cells)
            if member:
                members.append(member)
        except Exception as e:
            logger.warning("Error parsing roster row: %s", e)
            continue

    return members


def _parse_roster_row(cells) -> Optional[TeamMember]:
    """Parse a single player row from the roster table.

    Real portal structure (validated via DevTools inspection):
      <td>
        <span class="sm-block">Player Name</span>
        #80200640
      </td>
      <td class="text-center">3</td>   <!-- Skill Level -->
      ...
    """
    # Cell 0: Player Name in <span class="sm-block">; ID as plain text "#xxxxxxx"
    try:
        name_span = cells[0].select_one(MATCH_PAGE["player_name_selector"])
        if not name_span:
            logger.debug("No span.sm-block found in roster row, skipping")
            return None

        player_name = name_span.get_text(strip=True)
        if not player_name:
            logger.debug("Empty player name in roster row, skipping")
            return None

        all_text = cells[0].get_text(strip=True)
        id_match = re.search(r"#(\d+)", all_text)
        player_id = id_match.group(1) if id_match else ""
    except Exception as e:
        logger.warning("Error extracting player name/id from roster row: %s", e)
        return None

    # Extract numeric columns with individual fallbacks
    try:
        skill_level = _parse_int(cells[MATCH_PAGE["skill_level_col"]].get_text(strip=True))
    except Exception as e:
        logger.warning("Error parsing skill_level for %s: %s", player_name, e)
        skill_level = None

    try:
        matches_won_played = _parse_matches_won_lost(
            cells[MATCH_PAGE["matches_won_lost_col"]].get_text(strip=True)
        )
    except Exception as e:
        logger.warning("Error parsing matches_won_played for %s: %s", player_name, e)
        matches_won_played = None

    try:
        win_pct = _parse_percentage(
            cells[MATCH_PAGE["win_pct_col"]].get_text(strip=True)
        )
    except Exception as e:
        logger.warning("Error parsing win_pct for %s: %s", player_name, e)
        win_pct = None

    try:
        ppm = _parse_float(cells[MATCH_PAGE["ppm_col"]].get_text(strip=True))
    except Exception as e:
        logger.warning("Error parsing ppm for %s: %s", player_name, e)
        ppm = None

    try:
        pa = _parse_percentage(cells[MATCH_PAGE["pa_col"]].get_text(strip=True))
    except Exception as e:
        logger.warning("Error parsing pa for %s: %s", player_name, e)
        pa = None

    matches_won = matches_won_played.get("won", 0) if matches_won_played else 0
    matches_played = matches_won_played.get("played", 0) if matches_won_played else 0

    logger.debug(
        "Parsed roster member: %s (id=%s) sl=%s won=%s/%s",
        player_name, player_id, skill_level, matches_won, matches_played,
    )

    return TeamMember(
        player_name=player_name,
        player_id=player_id,
        skill_level=skill_level or 0,
        matches_won=matches_won,
        matches_played=matches_played,
        win_pct=win_pct or 0.0,
        ppm=ppm or 0.0,
        pa=pa or 0.0,
    )


def _extract_id_from_href(href: str) -> str:
    """Extract numeric ID from href like /arapahocounty/member/1349374."""
    match = re.search(r"/(\d+)(?:/|$)", href)
    return match.group(1) if match else ""


def _parse_int(value: str) -> Optional[int]:
    """Parse integer, returning None if not a valid number."""
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


def _parse_float(value: str) -> Optional[float]:
    """Parse float, returning None if not a valid number."""
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return None


def _parse_percentage(value: str) -> Optional[float]:
    """Parse percentage string (e.g., '50%') to float (0.5)."""
    try:
        clean = value.strip().rstrip("%")
        return float(clean) / 100.0
    except (TypeError, ValueError):
        return None


def _parse_matches_won_lost(value: str) -> Optional[dict]:
    """Parse matches string like '2/4' into {'won': 2, 'played': 4}."""
    try:
        parts = value.strip().split("/")
        if len(parts) == 2:
            return {"won": int(parts[0]), "played": int(parts[1])}
    except (TypeError, ValueError):
        pass
    return None


def fetch_roster(session: requests.Session, config: dict, team_id: Optional[str] = None) -> list[dict]:
    """Fetch and parse team roster, returning as list of dicts for compatibility."""
    html = fetch_team_page(session, config, team_id)
    team_id = team_id or config.get("team", {}).get("team_id")
    roster_data = parse_team_roster(html, team_id)

    # Convert to dict format for compatibility with ingest.py
    return [
        {
            "player_id": m.player_id,
            "player_name": m.player_name,
            "skill_level": m.skill_level,
            "matches_won": m.matches_won,
            "matches_played": m.matches_played,
            "win_pct": m.win_pct,
            "ppm": m.ppm,
            "pa": m.pa,
        }
        for m in roster_data.members
    ]


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


def parse_table(html: str, table_selector: str, row_selector: str, columns: list[str]) -> list[dict]:
    """Generic table parser for schedule and other tables."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(table_selector)
    if not table:
        logger.warning("Table not found with selector: %s", table_selector)
        return []

    rows = table.select(row_selector)
    result = []
    for row in rows:
        cells = row.find_all("td")
        row_data = {}
        for i, col_name in enumerate(columns):
            if i < len(cells):
                row_data[col_name] = cells[i].get_text(strip=True)
        result.append(row_data)
    return result
