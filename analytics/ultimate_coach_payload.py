"""Build the offline Ultimate Coach scouting payload from verified SQLite rows."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from database.models import (
    Match,
    Player,
    PlayerHeadToHead,
    PlayerLeagueCareerStats,
    PlayerTeamHistory,
)


def build_ultimate_coach_payload(db: Session) -> dict[str, Any]:
    """Return normalized real-source data for offline Scout & Compare.

    The browser computes pair-specific direct/shared-opponent summaries from
    these rows. No model score or probability is embedded here.
    """
    players = db.query(Player).order_by(Player.name, Player.id).all()
    histories = db.query(PlayerTeamHistory).order_by(
        PlayerTeamHistory.player_id,
        PlayerTeamHistory.session_name,
        PlayerTeamHistory.team_name,
    ).all()
    career = db.query(PlayerLeagueCareerStats).order_by(
        PlayerLeagueCareerStats.player_id,
        PlayerLeagueCareerStats.league_id,
        PlayerLeagueCareerStats.format,
    ).all()
    h2h = (
        db.query(PlayerHeadToHead, Match)
        .join(Match, PlayerHeadToHead.match_id == Match.id)
        .filter(PlayerHeadToHead.result.in_(("W", "L")))
        .order_by(Match.match_date, Match.id, PlayerHeadToHead.id)
        .all()
    )

    history_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in histories:
        history_by_player[row.player_id].append(
            {
                "team_external_id": row.team_external_id,
                "team_name": row.team_name or "",
                "division_id": row.division_id or "",
                "session_name": row.session_name or "",
                "is_current": bool(row.is_current),
                "skill_level": row.skill_level,
                "matches_won": row.matches_won,
                "matches_played": row.matches_played,
            }
        )

    career_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in career:
        career_by_player[row.player_id].append(
            {
                "league_id": row.league_id,
                "league_slug": row.league_slug or "",
                "alias_external_id": row.alias_external_id,
                "format": row.format,
                "matches_won": row.matches_won,
                "matches_played": row.matches_played,
                "defensive_shot_avg": row.defensive_shot_avg,
                "match_count_last_two_yrs": row.match_count_last_two_yrs,
                "last_played": row.last_played,
                "on_break_count": row.on_break_count,
                "break_and_runs": row.break_and_runs,
                "mini_slams": row.mini_slams,
                "rackless": row.rackless,
                "skunks": row.skunks,
            }
        )

    player_rows = []
    for player in players:
        player_rows.append(
            {
                "id": player.id,
                "external_id": player.external_id,
                "name": player.name,
                "current_skill_level": player.skill_level,
                "current_matches_won": player.matches_won,
                "current_matches_played": player.matches_played,
                "team_history": history_by_player.get(player.id, []),
                "career_stats": career_by_player.get(player.id, []),
            }
        )

    evidence_rows = []
    for row, match in h2h:
        fmt = str(row.format or match.format or "").upper()
        if "EIGHT" in fmt or fmt in {"8", "8-BALL", "EIGHT_BALL"}:
            fmt = "EIGHT"
        elif "NINE" in fmt or fmt in {"9", "9-BALL", "NINE_BALL"}:
            fmt = "NINE"
        else:
            continue
        evidence_rows.append(
            {
                "player_id": row.player_id,
                "opponent_id": row.opponent_id,
                "match_id": match.id,
                "match_external_id": match.external_id,
                "match_date": match.match_date or "",
                "session_name": row.session_name or match.session_name or "",
                "format": fmt,
                "result": str(row.result).upper(),
                "own_skill_level": row.own_skill_level,
                "opponent_skill_level": row.opponent_skill_level,
                "points_earned": row.points_earned,
                "nine_ball_points": row.nine_ball_points,
            }
        )

    return {
        "schema": "ultimate-coach-cockpit-v1",
        "probability_status": "NOT_CALIBRATED",
        "players": player_rows,
        "evidence": evidence_rows,
        "counts": {
            "players": len(player_rows),
            "head_to_head_rows": len(evidence_rows),
        },
    }
