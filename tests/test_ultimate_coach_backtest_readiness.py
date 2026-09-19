from analytics.ultimate_coach_backtest_readiness import build_backtest_readiness


def game(key, date, a, b, winner, *, fmt="EIGHT", status="VERIFIED_UNIQUE"):
    return {
        "game_key": key,
        "match_date": date,
        "format": fmt,
        "mirror_status": status,
        "participant_a_id": a,
        "participant_b_id": b,
        "winner_id": winner,
        "loser_id": b if winner == a else a,
    }


def test_small_archive_fails_closed_and_never_unlocks_probability():
    result = build_backtest_readiness(
        [game("g1", "2026-01-01T19:00:00Z", 1, 2, 1)], "EIGHT"
    )
    assert result["status"] == "NOT_READY"
    assert result["probability_publication"] == "FORBIDDEN"
    assert result["model_training_performed"] is False
    assert result["calibration_performed"] is False
    assert "INSUFFICIENT_TARGET_GAMES" in result["failures"]


def test_threshold_ready_means_evaluation_design_only_not_model_approval():
    rows = [
        game("g1", "2026-01-01T19:00:00Z", 1, 2, 1),
        game("g2", "2026-01-02T19:00:00Z", 1, 2, 2),
        game("g3", "2026-01-03T19:00:00Z", 3, 4, 3),
    ]
    result = build_backtest_readiness(
        rows, "EIGHT", min_targets=3, min_players=4,
        min_prior_supported=2, min_direct_supported=1,
    )
    assert result["status"] == "READY_FOR_EVALUATION_DESIGN"
    assert result["probability_publication"] == "FORBIDDEN"
    assert result["calibration_performed"] is False
    assert result["target_game_keys"] == ["g1", "g2", "g3"]


def test_unsafe_and_wrong_format_rows_cannot_satisfy_thresholds():
    rows = [
        game("safe", "2026-01-01T19:00:00Z", 1, 2, 1),
        game("unsafe", "2026-01-02T19:00:00Z", 3, 4, 3, status="MIRROR_MISMATCH"),
        game("nine", "2026-01-03T19:00:00Z", 5, 6, 5, fmt="NINE"),
    ]
    result = build_backtest_readiness(
        rows, "EIGHT", min_targets=2, min_players=2,
        min_prior_supported=1, min_direct_supported=1,
    )
    assert result["counts"]["eligible_targets"] == 1
    assert result["status"] == "NOT_READY"
    assert result["excluded_source_rows"] == {"UNVERIFIED_EVIDENCE": 1}


def test_same_timestamp_games_do_not_create_prior_support():
    rows = [
        game("a", "2026-01-01T19:00:00-07:00", 1, 2, 1),
        game("b", "2026-01-02T02:00:00+00:00", 1, 2, 2),
    ]
    result = build_backtest_readiness(
        rows, "EIGHT", min_targets=2, min_players=2,
        min_prior_supported=1, min_direct_supported=1,
    )
    assert result["counts"]["targets_with_any_prior_history"] == 0
    assert result["counts"]["targets_with_direct_prior_history"] == 0
    assert result["status"] == "NOT_READY"


def test_positive_integer_thresholds_are_required():
    try:
        build_backtest_readiness([], "EIGHT", min_targets=0)
    except ValueError as exc:
        assert "positive integers" in str(exc)
    else:
        raise AssertionError("zero threshold must fail closed")
