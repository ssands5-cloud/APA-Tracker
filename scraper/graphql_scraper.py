"""Fetch and normalize live team data from the APA GraphQL API.

Every accessor here defends against nulls rather than missing keys. GraphQL
returns the full shape of the query with `null` in any field it could not
resolve, so `payload.get("team", {})` hands back `None` -- not the default --
the moment the server nulls a field, and the next `.get()` raises. `or {}`
after the lookup is therefore load-bearing throughout.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from auth.graphql_client import GraphQLAuthError, execute
from parser.apa_graphql import (
    DIVISION_STANDINGS_QUERY,
    MATCH_DETAIL_QUERY,
    TEAM_PAGE_QUERY,
    TEAM_ROSTER_QUERY,
    TEAM_SCHEDULE_QUERY,
)

logger = logging.getLogger(__name__)


class AccessTokenMissing(RuntimeError):
    """No APA access token was available in the environment."""


class AccessTokenExpired(RuntimeError):
    """The APA access token was rejected. They are short-lived by design."""


def _token(config: dict) -> str:
    token = (config.get("apa") or {}).get("access_token") or os.environ.get("APA_ACCESS_TOKEN")
    if not token:
        raise AccessTokenMissing(
            "No APA access token found. Set it for this shell only, replacing "
            "the whole quoted string with your real token:\n"
            '  $env:APA_ACCESS_TOKEN = "eyJhbGciOi...your token here..."\n'
            "Never put the token in apa_config.yaml, a script, or source control."
        )

    # Caught before the network call because the instructions people copy show
    # a placeholder in angle brackets, and pasting it verbatim otherwise costs
    # a round trip and comes back as the API's opaque "token is no longer
    # valid" -- which reads as an expiry problem, not a paste problem.
    stripped = token.strip()
    if stripped.startswith("<") and stripped.endswith(">"):
        raise AccessTokenMissing(
            f"APA_ACCESS_TOKEN is still the placeholder text {stripped!r}, not a "
            "real token. Replace the whole quoted string, angle brackets and "
            "all, with the token from your logged-in APA session."
        )
    return token


def _team(payload: dict[str, Any]) -> dict[str, Any]:
    """The `team` object from a response, or {} when the server nulled it."""
    return (payload or {}).get("team") or {}


def fetch_team_data(config: dict) -> dict[str, Any]:
    """Fetch team metadata, roster, and schedule in three authenticated calls.

    Raises:
        AccessTokenMissing: No token in config or environment.
        AccessTokenExpired: The token was rejected -- capture a fresh one.
        GraphQLError / GraphQLTransportError: Anything else from the API.
    """
    team_id = int(config["team"]["team_id"])
    token = _token(config)
    timeout = (config.get("session") or {}).get("timeout_seconds", 15)
    retries = (config.get("session") or {}).get("max_retries", 0)

    def run(query: str) -> dict[str, Any]:
        try:
            return execute(query, {"id": team_id}, token, timeout, retries)
        except GraphQLAuthError as exc:
            raise AccessTokenExpired(
                "The APA access token was rejected (it expires quickly). Re-open the "
                "APA site while logged in, capture a fresh token, and set "
                "APA_ACCESS_TOKEN again."
            ) from exc

    schedule_team = _team(run(TEAM_SCHEDULE_QUERY))
    return {
        "team": _team(run(TEAM_PAGE_QUERY)),
        "roster": _team(run(TEAM_ROSTER_QUERY)).get("roster") or [],
        "schedule": schedule_team.get("matches") or [],
        # The schedule query also returns the season point totals at team level.
        "points": {
            key: schedule_team.get(key)
            for key in ("sessionPoints", "sessionBonusPoints", "sessionTotalPoints")
        },
    }


def team_row(data: dict[str, Any]) -> dict[str, Any]:
    """Team identity/metadata, flattened for `upsert_team` and reporting."""
    team = data.get("team") or {}
    division = team.get("division") or {}
    session = team.get("session") or {}
    league = team.get("league") or {}
    location = team.get("location") or {}
    return {
        "team_id": str(team.get("id") or ""),
        "team_name": team.get("name") or "",
        "team_number": team.get("number"),
        "standing": team.get("standing"),
        "is_tied": bool(team.get("isTied")),
        "division_id": str(division.get("id") or ""),
        "division_name": division.get("name") or "",
        "night_of_play": division.get("nightOfPlay"),
        "format": division.get("format"),
        "session_name": session.get("name") or "",
        "league_id": str(league.get("id") or ""),
        "home_location": location.get("name") or "",
    }


def roster_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert API roster objects to the field names `upsert_roster` expects."""
    rows = []
    for player in data.get("roster") or []:
        player = player or {}
        played = player.get("matchesPlayed") or 0
        won = player.get("matchesWon") or 0
        member = player.get("member") or {}
        rows.append(
            {
                "player_id": str(member.get("id") or player.get("id") or ""),
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
    """Convert API match objects to stable, display-ready dictionaries.

    Byes are kept, not dropped: a bye week is part of the schedule and its
    absence would read as a missing week. They are flagged `is_bye` and carry
    no opponent, since there is no opposing team to name.
    """
    rows = []
    for match in data.get("schedule") or []:
        match = match or {}
        home = match.get("home") or {}
        away = match.get("away") or {}
        location = match.get("location") or {}
        scores = {
            "home": None,
            "away": None,
        }
        for result in match.get("results") or []:
            side = str(result.get("homeAway") or "").lower()
            points = (result.get("points") or {}).get("total")
            if side in {"home", "away"}:
                scores[side] = points
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
                "home_score": scores["home"],
                "away_score": scores["away"],
            }
        )
    return rows


def fetch_division_standings(config: dict) -> dict[str, Any]:
    """Fetch the full division standings table -- every team, not just ours.

    Returns {} when no division id is configured, so callers can treat "not
    configured" and "nothing came back" the same way rather than branching on
    which. Raises AccessTokenExpired the same way fetch_team_data does; a
    non-auth GraphQL error (e.g. a bad division id) is the caller's to decide
    whether to fall back on, so it is not swallowed here.
    """
    division_id = (config.get("apa") or {}).get("division_id")
    if not division_id:
        return {}
    token = _token(config)
    timeout = (config.get("session") or {}).get("timeout_seconds", 15)
    retries = (config.get("session") or {}).get("max_retries", 0)
    try:
        payload = execute(DIVISION_STANDINGS_QUERY, {"id": int(division_id)}, token, timeout, retries)
    except GraphQLAuthError as exc:
        raise AccessTokenExpired(
            "The APA access token was rejected (it expires quickly). Re-open the "
            "APA site while logged in, capture a fresh token, and set "
            "APA_ACCESS_TOKEN again."
        ) from exc
    return payload.get("division") or {}


def division_standings_rows(division: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per team in the division, from the real standings query.

    `rank` and `points` come straight from the API. `wins` and `losses` stay
    None: this endpoint does not return them at all -- APA ranks by
    cumulative session points, not a maintained win/loss record -- and a
    guessed count is worse than an honest gap.
    """
    rows = []
    for team in division.get("teams") or []:
        team = team or {}
        rows.append(
            {
                "team_name": team.get("name") or "",
                "rank": team.get("standing"),
                "wins": None,
                "losses": None,
                "points": team.get("sessionTotalPoints"),
            }
        )
    return rows


def standings_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A standings snapshot for OUR team only -- one row, or none.

    Superseded by division_standings_rows() wherever a division id is
    configured: that one returns the full division table, straight from the
    API's own numbers. This is the fallback for when it isn't -- our own rank
    and points, derived from our own schedule, when no other team is visible.

    Rank and points come straight from the API. Wins and losses are derived,
    by comparing the two sides' totals on matches the API marks scored, and
    stay None when nothing is scored yet -- an unplayed season is not 0-0.
    """
    identity = team_row(data)
    if not identity["team_name"]:
        return []

    our_id = identity["team_id"]
    wins = losses = 0
    counted = 0
    for row in schedule_rows(data):
        if row["is_bye"]:
            continue
        home_points, away_points = match_score(row)
        if home_points is None or away_points is None or home_points == away_points:
            continue
        we_are_home = row["home_team_id"] == our_id
        if not we_are_home and row["away_team_id"] != our_id:
            continue
        our_points = home_points if we_are_home else away_points
        their_points = away_points if we_are_home else home_points
        counted += 1
        if our_points > their_points:
            wins += 1
        else:
            losses += 1

    return [
        {
            "team_name": identity["team_name"],
            "rank": identity["standing"],
            "wins": wins if counted else None,
            "losses": losses if counted else None,
            "points": (data.get("points") or {}).get("sessionTotalPoints"),
        }
    ]


def match_score(row: dict[str, Any]) -> tuple[Any, Any]:
    """(home_points, away_points) for a match row, or (None, None).

    A match that has not been scored yet, or has been only partially scored,
    yields None rather than 0 -- "no result yet" and "shut out" are different
    facts and must not collapse into the same number.
    """
    if not row.get("is_scored"):
        return (None, None)

    points: dict[str, Any] = {}
    for result in row.get("results") or []:
        result = result or {}
        side = (result.get("homeAway") or "").lower()
        total = (result.get("points") or {}).get("total")
        if side in ("home", "away") and total is not None:
            points[side] = total

    return (points.get("home"), points.get("away"))


def fetch_match_detail(config: dict, match_id: int) -> dict[str, Any]:
    """Fetch one match's full scoresheet -- both sides, every player's line.

    This is the only source of per-player, per-match statistics (skill level,
    games won, break-and-runs, forfeits, the win/loss call): the schedule and
    team queries carry only the team-level score. Callers walk a division's
    or team's schedule for match ids, then call this once per match that is
    actually scored.

    Raises the same errors as fetch_team_data. Returns {} if the server has
    no match at that id (a nulled `match`), so callers can treat "no such
    match" and "match not found" the same way.
    """
    token = _token(config)
    timeout = (config.get("session") or {}).get("timeout_seconds", 15)
    retries = (config.get("session") or {}).get("max_retries", 0)
    try:
        payload = execute(MATCH_DETAIL_QUERY, {"id": int(match_id)}, token, timeout, retries)
    except GraphQLAuthError as exc:
        raise AccessTokenExpired(
            "The APA access token was rejected (it expires quickly). Re-open the "
            "APA site while logged in, capture a fresh token, and set "
            "APA_ACCESS_TOKEN again."
        ) from exc
    return payload.get("match") or {}


def match_player_scores(match: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per player who played in this match -- the per-game scoresheet.

    A forfeited or incomplete line is still returned, flagged rather than
    dropped: a player who forfeited did participate in the match, and
    silently omitting the row would undercount matches played, not just
    matches won.

    `points_earned` maps 8-ball and 9-ball match points onto one field since
    a division plays one format or the other, never both, so exactly one of
    the two source fields is ever non-null for a given player.
    """
    rows = []
    for result in match.get("results") or []:
        result = result or {}
        side = (result.get("homeAway") or "").lower()
        team = (match.get("home") if side == "home" else match.get("away")) or {}
        for score in result.get("scores") or []:
            score = score or {}
            player = score.get("player") or {}
            points_earned = score.get("eightBallMatchPointsEarned")
            if points_earned is None:
                points_earned = score.get("nineBallMatchPointsEarned")
            rows.append(
                {
                    "match_id": str(match.get("id") or ""),
                    "player_id": str(player.get("id") or ""),
                    "player_name": player.get("displayName") or "",
                    "team_id": str(team.get("id") or ""),
                    "team_name": team.get("name") or "",
                    "skill_level": score.get("skillLevel"),
                    "result": score.get("winLoss"),
                    "points_earned": points_earned,
                    "forfeited": bool(score.get("matchForfeited")),
                    "incomplete": bool(score.get("incompleteMatch")),
                }
            )
    return rows
