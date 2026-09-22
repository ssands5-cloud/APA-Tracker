"""Derive Excel-ready reference tables from the verified Ultimate Coach
cockpit payload (analytics.ultimate_coach_cockpit_identity_bridge).

Pure transforms only -- no I/O, no openpyxl -- so the shape each sheet is
built from can be unit tested without ever writing a workbook. The Excel
builder (scripts/build_ultimate_coach_excel.py) and the HTML builder
(ui/ultimate_coach.py) both start from the same
build_verified_cockpit_payload() output, so they cannot silently disagree
about who is a verified player or which games count as evidence.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_team_rosters(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per (team, player) current-roster membership, deduped.

    A player can be rostered on a same-named team in two divisions at once
    (e.g. separate 8-ball and 9-ball divisions), so team_history can carry
    two is_current rows for one player on one team -- this was a real bug
    found in the HTML Team vs Team build against real staging data (see
    ui/ultimate_coach.py's TEAM_INDEX comment). Keep only the first
    membership row per (team_name, player_id) pair.
    """
    seen: set[tuple[str, int]] = set()
    rows: list[dict[str, Any]] = []
    for player in payload.get("players") or []:
        pid = player["id"]
        for hist in player.get("team_history") or []:
            if not hist.get("is_current") or not hist.get("team_name"):
                continue
            key = (hist["team_name"], pid)
            if key in seen:
                continue
            seen.add(key)
            live_sl = player.get("current_skill_level")
            skill_level = live_sl if live_sl is not None else hist.get("skill_level")
            rows.append(
                {
                    "team_name": hist["team_name"],
                    "division_id": hist.get("division_id") or "",
                    "session_name": hist.get("session_name") or "",
                    "player_id": pid,
                    "player_name": player["name"],
                    "skill_level": skill_level,
                    "skill_level_is_live": live_sl is not None,
                    "matches_won": hist.get("matches_won"),
                    "matches_played": hist.get("matches_played"),
                }
            )
    rows.sort(key=lambda r: (r["team_name"], r["player_name"]))
    return rows


def build_teams_summary(team_rosters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per current team: roster size and known-skill total."""
    by_team: dict[str, dict[str, Any]] = {}
    for row in team_rosters:
        team = by_team.setdefault(
            row["team_name"],
            {
                "team_name": row["team_name"],
                "division_id": row["division_id"],
                "session_name": row["session_name"],
                "roster_count": 0,
                "known_skill_count": 0,
                "skill_total": 0,
            },
        )
        team["roster_count"] += 1
        if row["skill_level"] is not None:
            team["known_skill_count"] += 1
            team["skill_total"] += row["skill_level"]
    teams = list(by_team.values())
    teams.sort(key=lambda r: r["team_name"])
    return teams


def build_player_vs_player_pairs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per (player, opponent, format) with at least one recorded
    meeting -- aggregated win/loss/games, both perspectives kept (the
    evidence list already carries a row from each player's own point of
    view for every game, so both (A,B) and (B,A) keys appear naturally).
    """
    groups: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("evidence") or []:
        key = (row["player_id"], row["opponent_id"], row.get("format") or "")
        groups[key].append(row)

    players_by_id = {p["id"]: p for p in payload.get("players") or []}
    pairs: list[dict[str, Any]] = []
    for (player_id, opponent_id, fmt), rows in groups.items():
        wins = sum(1 for r in rows if r.get("result") == "W")
        games = len(rows)
        pairs.append(
            {
                "player_id": player_id,
                "player_name": players_by_id.get(player_id, {}).get("name", str(player_id)),
                "opponent_id": opponent_id,
                "opponent_name": players_by_id.get(opponent_id, {}).get("name", str(opponent_id)),
                "format": fmt,
                "wins": wins,
                "losses": games - wins,
                "games": games,
                "win_rate": (wins / games) if games else None,
                "pair_key": f"{player_id}|{fmt}|{opponent_id}",
            }
        )
    pairs.sort(key=lambda r: (r["player_name"], r["format"], -r["games"]))
    return pairs
