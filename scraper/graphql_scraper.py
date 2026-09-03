"""Fetch and normalize live team data from the APA GraphQL API."""

from __future__ import annotations

import os
from typing import Any

from auth.graphql_client import execute
from parser.apa_graphql import TEAM_PAGE_QUERY, TEAM_ROSTER_QUERY, TEAM_SCHEDULE_QUERY


def _token(config: dict) -> str:
    token = config.get("apa", {}).get("access_token") or os.environ.get("APA_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Set APA_ACCESS_TOKEN in the environment; never put it in apa_config.yaml.")
    return token


def fetch_team_data(config: dict) -> dict[str, Any]:
    """Fetch team metadata, roster, and schedule in three authenticated calls."""
    team_id = int(config["team"]["team_id"])
    token = _token(config)
    timeout = config.get("session", {}).get("timeout_seconds", 15)
    retries = config.get("session", {}).get("max_retries", 0)
    return {
        "team": execute(TEAM_PAGE_QUERY, {"id": team_id}, token, timeout, retries).get("team") or {},
        "roster": (
            execute(TEAM_ROSTER_QUERY, {"id": team_id}, token, timeout, retries)
            .get("team", {})
            .get("roster")
            or []
        ),
        "schedule": (
            execute(TEAM_SCHEDULE_QUERY, {"id": team_id}, token, timeout, retries)
            .get("team", {})
            .get("matches")
            or []
        ),
    }


def roster_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert API roster objects to the existing ingestion field names."""
    rows = []
    for player in data.get("roster", []):
        played = player.get("matchesPlayed") or 0
        won = player.get("matchesWon") or 0
        rows.append(
            {
                "player_id": str(player.get("member", {}).get("id") or player.get("id") or ""),
                "player_name": player.get("displayName") or "",
                "skill_level": player.get("skillLevel"),
                "matches_won": won,
                "matches_played": played,
                "win_pct": won / played if played else 0.0,
                "ppm": player.get("ppm"),
                "pa": player.get("pa"),
            }
        )
    return rows


def schedule_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert API match objects to stable, display-ready dictionaries."""
    rows = []
    for match in data.get("schedule", []):
        home = match.get("home") or {}
        away = match.get("away") or {}
        location = match.get("location") or {}
        rows.append(
            {
                "match_id": str(match.get("id") or ""),
                "week": match.get("week"),
                "date": match.get("startTime"),
                "status": match.get("status"),
                "home_team_id": str(home.get("id") or ""),
                "home_team_name": home.get("name") or "",
                "away_team_id": str(away.get("id") or ""),
                "away_team_name": away.get("name") or "",
                "location": location.get("name"),
                "is_bye": bool(match.get("isBye")),
                "is_scored": bool(match.get("isScored")),
                "is_finalized": bool(match.get("isFinalized")),
                "results": match.get("results") or [],
            }
        )
    return rows
