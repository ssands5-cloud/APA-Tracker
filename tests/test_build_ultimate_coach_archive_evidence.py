from scripts.build_ultimate_coach_archive_evidence import add_archive_evidence


def test_archive_adds_verified_games_by_member_id_without_replacing_current_fixtures():
    current = {
        "players": [{"id": 1, "external_id": "member-a", "team_history": [{"is_current": True}]}],
        "match_day": {"fixtures": [{"match_external_id": "refreshed"}]},
        "evidence": [],
        "counts": {"all_games": 0},
        "trust": {"identity_verified_game_count": 0, "total_all_games_rows": 0},
    }
    archive = {
        "players": [
            {"id": 10, "external_id": "member-a"},
            {"id": 1, "external_id": "member-b", "team_history": [{"is_current": True}]},
            {"id": 11, "external_id": "member-c"},
        ],
        "evidence": [
            {"player_id": player, "opponent_id": opponent, "match_external_id": match,
             "match_date": date, "game_key": match, "format": "EIGHT"}
            for player, opponent, match, date in (
                (10, 1, "old", "2025-11-09"),
                (1, 10, "old", "2025-11-09"),
                (10, 1, "refreshed", "2026-11-01"),
                (10, 1, "future", "2027-01-01"),
                (1, 11, "unrelated", "2025-11-09"),
            )
        ],
    }
    assert add_archive_evidence(current, archive, "2026-11-12") == 1
    assert current["players"] == [
        {"id": 1, "external_id": "member-a", "team_history": [{"is_current": True}]},
        {"id": 2, "external_id": "member-b", "team_history": []},
    ]
    assert [(r["player_id"], r["opponent_id"], r["game_key"]) for r in current["evidence"]] == [
        (1, 2, "archive:old"), (2, 1, "archive:old"),
    ]
    assert current["match_day"]["fixtures"] == [{"match_external_id": "refreshed"}]
    assert current["counts"] == {"players": 2, "head_to_head_rows": 2, "all_games": 1}
