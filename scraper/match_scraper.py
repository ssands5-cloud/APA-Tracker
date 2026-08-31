"""
Scrapes a single match's roster and player stats from both teams.

Parses the match detail page containing home and away team rosters with
individual player statistics: skill level, matches won/played, win %, PPM, PA.
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


@dataclass
class PlayerStats:
    """Individual player's stats within a match roster."""

    player_name: str
    player_id: str
    skill_level: int
    matches_won: int
    matches_played: int
    win_pct: float
    ppm: float
    pa: float  # Points Available


@dataclass
class TeamRoster:
    """A team's roster for a specific match."""

    team_name: str
    team_id: str
    players: list[PlayerStats]


@dataclass
class MatchData:
    """Complete match data with both rosters."""

    match_id: str
    home_team: TeamRoster
    away_team: TeamRoster
    location: Optional[str] = None
    match_date: Optional[str] = None
    status: Optional[str] = None


def fetch_match_page(
    session: requests.Session, config: dict, match_id: str
) -> str:
    """Fetch the raw HTML of a match detail page."""
    site = config["site"]
    url = (
        site["base_url"].rstrip("/")
        + site.get("match_path_template", "/arapahocounty/match/{match_id}").format(
            match_id=match_id
        )
    )
    timeout = config.get("session", {}).get("timeout_seconds", 15)

    logger.info("Fetching match page: %s", url)
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_match(html: str, match_id: str) -> MatchData:
    """Parse match HTML and extract rosters for both teams."""
    soup = BeautifulSoup(html, "html.parser")

    # Find all team roster sections (usually two: home and away)
    team_sections = soup.select(MATCH_PAGE["team_section_selector"])

    if len(team_sections) < 2:
        logger.warning("Expected at least 2 team sections, found %d", len(team_sections))

    # Parse home team (first section)
    home_team = _parse_team_section(
        team_sections[0] if len(team_sections) > 0 else None, "HOME"
    )

    # Parse away team (second section)
    away_team = _parse_team_section(
        team_sections[1] if len(team_sections) > 1 else None, "AWAY"
    )

    # Extract match metadata
    location = _extract_metadata(soup, "location")
    match_date = _extract_metadata(soup, "date_time")
    status = _extract_metadata(soup, "status")

    return MatchData(
        match_id=match_id,
        home_team=home_team,
        away_team=away_team,
        location=location,
        match_date=match_date,
        status=status,
    )


def _parse_team_section(team_elem, team_type: str) -> TeamRoster:
    """Parse a single team's roster section."""
    if not team_elem:
        logger.warning("Team element for %s is None", team_type)
        return TeamRoster(team_name=f"{team_type} Team", team_id="", players=[])

    # Team name: try configured selector, fall back gracefully
    team_name = f"{team_type} Team"
    team_id = ""
    try:
        team_link = team_elem.select_one(MATCH_PAGE["team_name_selector"])
        if team_link:
            team_name = team_link.get_text(strip=True) or team_name
            team_id = _extract_id_from_href(team_link.get("href", ""))
        else:
            logger.debug("No team name element found for %s, using default", team_type)
    except Exception as e:
        logger.warning("Error extracting team name for %s: %s", team_type, e)

    # Find the roster table within this section
    table = team_elem.select_one(MATCH_PAGE["table_selector"])
    if not table:
        logger.warning("No roster table found for team %s", team_name)
        return TeamRoster(team_name=team_name, team_id=team_id, players=[])

    # Parse player rows
    players = _parse_player_rows(table)

    return TeamRoster(team_name=team_name, team_id=team_id, players=players)


def _parse_player_rows(table) -> list[PlayerStats]:
    """Parse all player rows from a roster table."""
    players = []
    rows = table.select(MATCH_PAGE["table_row_selector"])

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 6:
            logger.debug("Row has fewer than 6 cells, skipping")
            continue

        try:
            player = _parse_player_row(cells)
            if player:
                players.append(player)
        except Exception as e:
            logger.warning("Error parsing player row: %s", e)
            continue

    logger.info("Parsed %d players from roster table", len(players))
    return players


def _parse_player_row(cells) -> Optional[PlayerStats]:
    """Parse a single player row from the roster table.

    Real portal structure (validated via DevTools inspection):
      <td>
        <span class="sm-block">Shawna Larsen</span>
        #80200640
      </td>
      <td class="text-center">3</td>           <!-- Skill Level -->
      <td class="text-center">2/3</td>         <!-- Matches Won/Played -->
      <td class="text-center">66.67%</td>      <!-- Win % -->
      <td class="text-center">2.33</td>        <!-- PPM -->
      <td class="text-center">77.78%</td>      <!-- PA -->
    """
    # Cell 0: Player Name in <span class="sm-block">; ID as plain text "#xxxxxxx"
    try:
        name_span = cells[0].select_one(MATCH_PAGE["player_name_selector"])
        if not name_span:
            logger.debug("No span.sm-block found in player row, skipping")
            return None

        player_name = name_span.get_text(strip=True)
        if not player_name:
            logger.debug("Empty player name, skipping row")
            return None

        # Player ID may appear as "#12345678" anywhere in the cell text
        all_text = cells[0].get_text(strip=True)
        id_match = re.search(r"#(\d+)", all_text)
        player_id = id_match.group(1) if id_match else ""
    except Exception as e:
        logger.warning("Error extracting player name/id: %s", e)
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
        "Parsed player: %s (id=%s) sl=%s won=%s/%s win_pct=%s ppm=%s pa=%s",
        player_name, player_id, skill_level, matches_won, matches_played, win_pct, ppm, pa,
    )

    return PlayerStats(
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


def _extract_metadata(soup, key: str) -> Optional[str]:
    """Extract match metadata from page."""
    selectors = MATCH_PAGE.get("match_metadata_selectors", {})
    selector = selectors.get(key)
    if not selector:
        return None

    elem = soup.select_one(selector)
    return elem.get_text(strip=True) if elem else None


def fetch_and_parse_match(
    session: requests.Session, config: dict, match_id: str
) -> MatchData:
    """High-level function: fetch and parse a match in one call."""
    html = fetch_match_page(session, config, match_id)
    return parse_match(html, match_id)
