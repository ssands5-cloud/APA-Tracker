from analytics.ultimate_coach_evaluation_plan import build_evaluation_plan


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


def ready_kwargs():
    return {
        "min_targets": 4,
        "min_players": 2,
        "min_prior_supported": 3,
        "min_direct_supported": 2,
    }


def test_expanding_fold_is_strictly_chronological_and_traceable():
    rows = [
        game(f"g{i}", f"2026-01-0{i}T19:00:00Z", 1, 2, 1 if i % 2 else 2)
        for i in range(1, 7)
    ]
    plan = build_evaluation_plan(
        rows, "EIGHT", min_train_targets=3, holdout_instants=2,
        readiness_kwargs=ready_kwargs(),
    )
    assert plan["status"] == "PLAN_READY"
    assert plan["probability_publication"] == "FORBIDDEN"
    assert plan["evaluation_executed"] is False
    assert plan["folds"][0]["train_game_keys"] == ["g1", "g2", "g3", "g4"]
    assert plan["folds"][0]["holdout_game_keys"] == ["g5", "g6"]
    assert plan["folds"][0]["train_end_time"] < plan["folds"][0]["holdout_start_time"]


def test_same_instant_batch_is_never_split_between_train_and_holdout():
    rows = [
        game("g1", "2026-01-01T19:00:00Z", 1, 2, 1),
        game("g2", "2026-01-02T19:00:00Z", 1, 2, 2),
        game("g3a", "2026-01-03T19:00:00-07:00", 1, 2, 1),
        game("g3b", "2026-01-04T02:00:00+00:00", 1, 2, 2),
        game("g4", "2026-01-05T19:00:00Z", 1, 2, 1),
    ]
    plan = build_evaluation_plan(
        rows, "EIGHT", min_train_targets=2, holdout_instants=1,
        readiness_kwargs={"min_targets": 5, "min_players": 2, "min_prior_supported": 4, "min_direct_supported": 4},
    )
    for fold in plan["folds"]:
        train = set(fold["train_game_keys"])
        holdout = set(fold["holdout_game_keys"])
        assert not ({"g3a", "g3b"} & train and {"g3a", "g3b"} & holdout)


def test_wrong_format_and_unverified_rows_never_enter_folds():
    rows = [
        game("g1", "2026-01-01T19:00:00Z", 1, 2, 1),
        game("g2", "2026-01-02T19:00:00Z", 1, 2, 2),
        game("g3", "2026-01-03T19:00:00Z", 1, 2, 1),
        game("unsafe", "2026-01-04T19:00:00Z", 1, 2, 2, status="MIRROR_MISMATCH"),
        game("nine", "2026-01-05T19:00:00Z", 1, 2, 1, fmt="NINE"),
    ]
    plan = build_evaluation_plan(
        rows, "EIGHT", min_train_targets=1, holdout_instants=1,
        readiness_kwargs={"min_targets": 3, "min_players": 2, "min_prior_supported": 2, "min_direct_supported": 2},
    )
    used = {key for fold in plan["folds"] for key in fold["train_game_keys"] + fold["holdout_game_keys"]}
    assert "unsafe" not in used
    assert "nine" not in used


def test_readiness_failure_keeps_plan_closed_even_if_a_fold_can_be_formed():
    rows = [
        game("g1", "2026-01-01T19:00:00Z", 1, 2, 1),
        game("g2", "2026-01-02T19:00:00Z", 1, 2, 2),
        game("g3", "2026-01-03T19:00:00Z", 1, 2, 1),
    ]
    plan = build_evaluation_plan(rows, "EIGHT", min_train_targets=1, holdout_instants=1)
    assert plan["folds"]
    assert plan["status"] == "PLAN_NOT_READY"
    assert "BACKTEST_READINESS_NOT_MET" in plan["failures"]
    assert plan["probability_publication"] == "FORBIDDEN"


def test_invalid_fold_policy_fails_closed():
    for kwargs in ({"min_train_targets": 0}, {"holdout_instants": 0}):
        try:
            build_evaluation_plan([], "EIGHT", **kwargs)
        except ValueError as exc:
            assert "positive integer" in str(exc)
        else:
            raise AssertionError("invalid evaluation policy must fail closed")
