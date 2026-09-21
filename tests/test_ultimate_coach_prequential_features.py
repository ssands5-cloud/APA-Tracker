from analytics.ultimate_coach_prequential_features import build_prequential_feature_rows


def game(key, date, a, b, winner, fmt="EIGHT", status="VERIFIED_UNIQUE"):
    loser = b if winner == a else a
    return {
        "game_key": key,
        "match_date": date,
        "format": fmt,
        "mirror_status": status,
        "participant_a_id": a,
        "participant_b_id": b,
        "winner_id": winner,
        "loser_id": loser,
    }


def by_key(result, key):
    return next(row for row in result["feature_rows"] if row["target_game_key"] == key)


def test_future_games_never_enter_prior_features():
    games = [
        game("future", "2026-03-01T19:00:00Z", 1, 2, 2),
        game("first", "2026-01-01T19:00:00Z", 1, 3, 1),
        game("target", "2026-02-01T19:00:00Z", 1, 2, 1),
    ]
    result = build_prequential_feature_rows(games, "EIGHT")
    target = by_key(result, "target")
    assert target["prior_game_keys"] == ["first"]
    assert "future" not in target["prior_game_keys"]
    assert target["participant_a_prior_games"] == 1
    assert target["participant_b_prior_games"] == 0
    assert target["probability_publication"] == "FORBIDDEN"


def test_same_timestamp_games_cannot_leak_into_each_other():
    games = [
        game("prior", "2026-01-01T00:00:00Z", 1, 3, 1),
        game("same-a", "2026-02-01T00:00:00Z", 1, 2, 1),
        game("same-b", "2026-02-01T00:00:00Z", 1, 4, 4),
    ]
    result = build_prequential_feature_rows(games, "EIGHT")
    assert by_key(result, "same-a")["prior_game_keys"] == ["prior"]
    assert by_key(result, "same-b")["prior_game_keys"] == ["prior"]


def test_format_and_evidence_quality_are_isolated():
    games = [
        game("8-good", "2026-01-01T00:00:00Z", 1, 3, 1),
        game("9-good", "2026-01-02T00:00:00Z", 1, 4, 4, fmt="NINE"),
        game("8-unsafe", "2026-01-03T00:00:00Z", 1, 5, 1, status="VERIFIED_COUNT_ONLY"),
        game("8-target", "2026-02-01T00:00:00Z", 1, 2, 2),
    ]
    result = build_prequential_feature_rows(games, "EIGHT")
    target = by_key(result, "8-target")
    assert target["prior_game_keys"] == ["8-good"]
    assert result["excluded"] == {"UNVERIFIED_EVIDENCE": 1}


def test_direct_and_shared_opponents_use_prior_games_only():
    games = [
        game("a-v-b", "2026-01-01T00:00:00Z", 1, 2, 1),
        game("a-v-c", "2026-01-02T00:00:00Z", 1, 3, 3),
        game("b-v-c", "2026-01-03T00:00:00Z", 2, 3, 2),
        game("target", "2026-02-01T00:00:00Z", 1, 2, 2),
    ]
    target = by_key(build_prequential_feature_rows(games, "EIGHT"), "target")
    assert target["direct_prior_game_keys"] == ["a-v-b"]
    assert target["direct_a_prior_wins"] == 1
    assert target["direct_a_prior_losses"] == 0
    assert target["shared_opponent_ids"] == [3]
    assert target["shared_opponent_count"] == 1


def test_invalid_format_rejected_and_no_probability_field_exists():
    try:
        build_prequential_feature_rows([], "TEN")
        assert False
    except ValueError:
        pass
    result = build_prequential_feature_rows([], "EIGHT")
    assert result["probability_publication"] == "FORBIDDEN"
    assert all("probability" not in key.lower() for row in result["feature_rows"] for key in row if key != "probability_publication")
