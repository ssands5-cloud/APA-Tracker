"""Unit tests for the pure Excel reference-table transforms."""

from __future__ import annotations

from analytics.ultimate_coach_excel_payload import (
    build_player_vs_player_pairs,
    build_team_rosters,
    build_teams_summary,
)


def _payload():
    return {
        "players": [
            {
                "id": 1,
                "name": "Ann Archer",
                "current_skill_level": 4,
                "team_history": [
                    {"team_name": "Sharks", "division_id": "d1", "session_name": "Spring", "is_current": True, "skill_level": 4, "matches_won": 4, "matches_played": 6},
                ],
            },
            {
                "id": 2,
                "name": "Bea Baker",
                "current_skill_level": None,
                "team_history": [
                    # Same team, two divisions at once -- must dedupe to one row.
                    {"team_name": "Sharks", "division_id": "da", "session_name": "Spring", "is_current": True, "skill_level": 5, "matches_won": 2, "matches_played": 6},
                    {"team_name": "Sharks", "division_id": "db", "session_name": "Spring", "is_current": True, "skill_level": 5, "matches_won": 3, "matches_played": 6},
                    # Stale (not current) membership on a different team -- excluded.
                    {"team_name": "Old Team", "division_id": "d0", "session_name": "Fall 2025", "is_current": False, "skill_level": 5, "matches_won": 1, "matches_played": 2},
                ],
            },
            {
                "id": 3,
                "name": "Cam Cole",
                "current_skill_level": 3,
                "team_history": [
                    {"team_name": "Falcons", "division_id": "d2", "session_name": "Spring", "is_current": True, "skill_level": 3, "matches_won": 1, "matches_played": 4},
                ],
            },
        ],
        "evidence": [
            {"player_id": 1, "opponent_id": 3, "format": "EIGHT", "result": "W"},
            {"player_id": 3, "opponent_id": 1, "format": "EIGHT", "result": "L"},
            {"player_id": 1, "opponent_id": 3, "format": "EIGHT", "result": "L"},
            {"player_id": 3, "opponent_id": 1, "format": "EIGHT", "result": "W"},
        ],
    }


def test_team_rosters_dedupes_multi_division_membership():
    rosters = build_team_rosters(_payload())
    sharks = [r for r in rosters if r["team_name"] == "Sharks"]

    assert len(sharks) == 2
    bea_rows = [r for r in sharks if r["player_name"] == "Bea Baker"]
    assert len(bea_rows) == 1
    # current_skill_level is null for Bea -- must fall back to the
    # division-scoped team_history skill_level rather than showing nothing.
    assert bea_rows[0]["skill_level"] == 5
    assert bea_rows[0]["skill_level_is_live"] is False

    ann_rows = [r for r in sharks if r["player_name"] == "Ann Archer"]
    assert ann_rows[0]["skill_level"] == 4
    assert ann_rows[0]["skill_level_is_live"] is True

    # Stale (non-current) membership must never appear.
    assert not any(r["team_name"] == "Old Team" for r in rosters)


def test_teams_summary_sums_known_skill_only():
    rosters = build_team_rosters(_payload())
    teams = build_teams_summary(rosters)
    sharks = next(t for t in teams if t["team_name"] == "Sharks")

    assert sharks["roster_count"] == 2
    assert sharks["known_skill_count"] == 2
    assert sharks["skill_total"] == 9  # Ann 4 + Bea 5, counted once each


def test_player_vs_player_pairs_aggregate_both_perspectives():
    pairs = build_player_vs_player_pairs(_payload())
    by_key = {p["pair_key"]: p for p in pairs}

    ann_vs_cam = by_key["1|EIGHT|3"]
    assert ann_vs_cam["wins"] == 1
    assert ann_vs_cam["losses"] == 1
    assert ann_vs_cam["games"] == 2
    assert ann_vs_cam["win_rate"] == 0.5
    assert ann_vs_cam["player_name"] == "Ann Archer"
    assert ann_vs_cam["opponent_name"] == "Cam Cole"

    cam_vs_ann = by_key["3|EIGHT|1"]
    assert cam_vs_ann["wins"] == 1
    assert cam_vs_ann["losses"] == 1
