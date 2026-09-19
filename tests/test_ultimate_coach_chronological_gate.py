from analytics.ultimate_coach_chronological_gate import chronological_archive_gate


def game(key, date, fmt="EIGHT", status="VERIFIED_UNIQUE", winner=1, loser=2):
    return {
        "game_key": key,
        "match_date": date,
        "format": fmt,
        "mirror_status": status,
        "winner_id": winner,
        "loser_id": loser,
    }


def test_split_is_chronological_not_input_order():
    games = [
        game("late", "2026-03-01T19:00:00-07:00"),
        game("early", "2026-01-01T19:00:00-07:00"),
        game("middle", "2026-02-01T19:00:00-07:00"),
    ]
    row = chronological_archive_gate(games, "EIGHT", holdout_fraction=1/3, min_verified_games=3, min_holdout_games=1)
    assert row["status"] == "READY_FOR_BACKTEST"
    assert row["train_game_keys"] == ["early", "middle"]
    assert row["holdout_game_keys"] == ["late"]
    assert row["chronology_ok"] is True
    assert row["probability_publication"] == "FORBIDDEN"


def test_formats_never_cross_contaminate():
    games = [game("8a", "2026-01-01T00:00:00Z"), game("9a", "2026-01-02T00:00:00Z", "NINE")]
    eight = chronological_archive_gate(games, "EIGHT", min_verified_games=1, min_holdout_games=1)
    nine = chronological_archive_gate(games, "NINE", min_verified_games=1, min_holdout_games=1)
    assert eight["holdout_game_keys"] == ["8a"]
    assert nine["holdout_game_keys"] == ["9a"]


def test_unsafe_invalid_time_and_unknown_outcome_are_excluded():
    games = [
        game("safe", "2026-01-01T00:00:00Z"),
        game("unsafe", "2026-01-02T00:00:00Z", status="VERIFIED_COUNT_ONLY"),
        game("bad-time", "not-a-date"),
        game("unknown", "2026-01-03T00:00:00Z", winner=None, loser=None),
    ]
    row = chronological_archive_gate(games, "EIGHT", min_verified_games=1, min_holdout_games=1)
    assert row["verified_games"] == 1
    assert row["excluded"] == {
        "MISSING_OR_INVALID_TIME": 1,
        "UNKNOWN_OUTCOME": 1,
        "UNVERIFIED_EVIDENCE": 1,
    }


def test_small_archive_fails_closed_even_with_valid_rows():
    games = [game("g1", "2026-01-01T00:00:00Z"), game("g2", "2026-01-02T00:00:00Z")]
    row = chronological_archive_gate(games, "EIGHT", min_verified_games=100, min_holdout_games=20)
    assert row["status"] == "NOT_READY"
    assert "INSUFFICIENT_VERIFIED_GAMES" in row["reasons"]
    assert "INSUFFICIENT_HOLDOUT_GAMES" in row["reasons"]
    assert row["probability_publication"] == "FORBIDDEN"


def test_invalid_format_and_fraction_are_rejected():
    try:
        chronological_archive_gate([], "TEN")
        assert False
    except ValueError:
        pass
    try:
        chronological_archive_gate([], "EIGHT", holdout_fraction=1)
        assert False
    except ValueError:
        pass
