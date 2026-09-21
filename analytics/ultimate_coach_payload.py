"""Build the offline Ultimate Coach scouting payload from the shared data contract."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from analytics.ultimate_coach_data_contract import build_contract


def build_ultimate_coach_payload(db: Session) -> dict[str, Any]:
    """Return Scout & Compare payload from the same contract Excel will use.

    SQLite remains the source of truth. This adapter intentionally performs no
    direct ORM reads of its own, preventing the HTML cockpit from drifting away
    from the workbook/raw-data contract.
    """
    contract = build_contract(db)
    tables = contract["tables"]

    history_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in tables["team_history"]:
        history_by_player[int(row["player_id"])].append(
            {
                "team_external_id": row["team_external_id"],
                "team_name": row["team_name"] or "",
                "division_id": row["division_id"] or "",
                "session_name": row["session_name"] or "",
                "is_current": bool(row["is_current"]),
                "skill_level": row["skill_level"],
                "matches_won": row["matches_won"],
                "matches_played": row["matches_played"],
            }
        )

    career_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in tables["career_stats"]:
        career_by_player[int(row["player_id"])].append(
            {
                "league_id": row["league_id"],
                "league_slug": row["league_slug"] or "",
                "alias_external_id": row["alias_external_id"],
                "format": row["format"],
                "matches_won": row["matches_won"],
                "matches_played": row["matches_played"],
                "defensive_shot_avg": row["defensive_shot_avg"],
                "match_count_last_two_yrs": row["match_count_last_two_yrs"],
                "last_played": row["last_played"],
                "on_break_count": row["on_break_count"],
                "break_and_runs": row["break_and_runs"],
                "mini_slams": row["mini_slams"],
                "rackless": row["rackless"],
                "skunks": row["skunks"],
            }
        )

    player_rows = []
    for row in tables["players"]:
        player_id = int(row["player_id"])
        player_rows.append(
            {
                "id": player_id,
                "external_id": row["member_external_id"],
                "name": row["player_name"],
                "current_skill_level": row["current_skill_level"],
                "current_matches_won": row["current_matches_won"],
                "current_matches_played": row["current_matches_played"],
                "team_history": history_by_player.get(player_id, []),
                "career_stats": career_by_player.get(player_id, []),
            }
        )

    evidence_rows = [
        {
            "player_id": row["player_id"],
            "opponent_id": row["opponent_id"],
            "match_id": row["match_id"],
            "match_external_id": row["match_external_id"],
            "match_date": row["match_date"] or "",
            "session_name": row["session_name"] or "",
            "format": row["format"],
            "result": row["result"],
            "own_skill_level": row["own_skill_level"],
            "opponent_skill_level": row["opponent_skill_level"],
            "points_earned": row["points_earned"],
            "nine_ball_points": row["nine_ball_points"],
        }
        for row in tables["raw_h2h_evidence"]
        if row["result"] in {"W", "L"} and row["format"] in {"EIGHT", "NINE"}
    ]

    return {
        "schema": "ultimate-coach-cockpit-v1",
        "source_contract_schema": contract["schema"],
        "probability_status": "NOT_CALIBRATED",
        "players": player_rows,
        "evidence": evidence_rows,
        "coverage_issue_count": contract["counts"]["coverage_issues"],
        "counts": {
            "players": len(player_rows),
            "head_to_head_rows": len(evidence_rows),
            "all_games": contract["counts"]["all_games"],
        },
    }
