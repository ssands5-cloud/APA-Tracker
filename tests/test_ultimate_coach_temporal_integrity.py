from analytics.ultimate_coach_prequential_features import build_prequential_feature_rows


def game(key, date, a=1, b=2, winner=1, *, fmt="EIGHT", status="VERIFIED_UNIQUE", loser=None):
    return {
        "game_key": key,
        "match_date": date,
        "format": fmt,
        "mirror_status": status,
        "participant_a_id": a,
        "participant_b_id": b,
        "winner_id": winner,
        "loser_id": (b if winner == a else a) if loser is None else loser,
    }


def test_timezone_naive_timestamp_fails_closed_not_assumed_local_or_utc():
    rows = [
        game("naive", "2026-01-01T19:00:00"),
        game("aware", "2026-02-01T19:00:00-07:00"),
    ]
    result = build_prequential_feature_rows(rows, "EIGHT")
    assert [r["target_game_key"] for r in result["feature_rows"]] == ["aware"]
    assert result["excluded"] == {"MISSING_INVALID_OR_NAIVE_TIME": 1}


def test_equivalent_instants_with_different_offsets_cannot_see_each_other():
    rows = [
        game("denver", "2026-01-01T19:00:00-07:00", a=1, b=2, winner=1),
        game("utc", "2026-01-02T02:00:00+00:00", a=1, b=3, winner=3),
    ]
    result = build_prequential_feature_rows(rows, "EIGHT")
    assert len(result["feature_rows"]) == 2
    assert all(row["prior_game_keys"] == [] for row in result["feature_rows"])


def test_duplicate_game_key_quarantines_every_copy():
    rows = [
        game("dup", "2026-01-01T19:00:00-07:00", a=1, b=2, winner=1),
        game("dup", "2026-01-02T19:00:00-07:00", a=1, b=3, winner=3),
        game("target", "2026-02-01T19:00:00-07:00", a=1, b=4, winner=1),
    ]
    result = build_prequential_feature_rows(rows, "EIGHT")
    assert [r["target_game_key"] for r in result["feature_rows"]] == ["target"]
    assert result["feature_rows"][0]["prior_game_keys"] == []
    assert result["excluded"] == {"DUPLICATE_GAME_KEY": 2}


def test_blank_game_key_is_not_admitted_to_provenance():
    result = build_prequential_feature_rows(
        [game("", "2026-01-01T19:00:00Z")], "EIGHT"
    )
    assert result["feature_rows"] == []
    assert result["excluded"] == {"MISSING_GAME_KEY": 1}


def test_self_pairing_fails_closed():
    result = build_prequential_feature_rows(
        [game("self", "2026-01-01T19:00:00Z", a=1, b=1, winner=1, loser=1)],
        "EIGHT",
    )
    assert result["feature_rows"] == []
    assert result["excluded"] == {"INCOMPLETE_OR_INCONSISTENT_TARGET": 1}


def test_winner_outside_participants_fails_closed():
    result = build_prequential_feature_rows(
        [game("bad-winner", "2026-01-01T19:00:00Z", a=1, b=2, winner=99, loser=2)],
        "EIGHT",
    )
    assert result["feature_rows"] == []
    assert result["excluded"] == {"INCOMPLETE_OR_INCONSISTENT_TARGET": 1}


def test_winner_and_loser_cannot_be_same_participant():
    result = build_prequential_feature_rows(
        [game("bad-outcome", "2026-01-01T19:00:00Z", a=1, b=2, winner=1, loser=1)],
        "EIGHT",
    )
    assert result["feature_rows"] == []
    assert result["excluded"] == {"INCOMPLETE_OR_INCONSISTENT_TARGET": 1}


def test_format_scope_keeps_duplicate_key_detection_independent():
    rows = [
        game("same-key", "2026-01-01T19:00:00Z", fmt="EIGHT"),
        game("same-key", "2026-01-01T19:00:00Z", fmt="NINE"),
    ]
    eight = build_prequential_feature_rows(rows, "EIGHT")
    nine = build_prequential_feature_rows(rows, "NINE")
    assert len(eight["feature_rows"]) == 1
    assert len(nine["feature_rows"]) == 1
    assert eight["excluded"] == {}
    assert nine["excluded"] == {}
    assert eight["probability_publication"] == "FORBIDDEN"
    assert nine["probability_publication"] == "FORBIDDEN"
