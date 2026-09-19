import pytest

from analytics.ultimate_coach_evidence_quality import direct_evidence, shared_opponent_evidence


def game(key, a, b, result="W", fmt="EIGHT", status="VERIFIED_UNIQUE"):
    return {
        "game_key": key,
        "participant_a_id": a,
        "participant_b_id": b,
        "participant_a_result": result,
        "format": fmt,
        "mirror_status": status,
    }


def test_direct_record_is_perspective_correct_and_traceable():
    games = [game("g1", 1, 2, "W"), game("g2", 2, 1, "W")]
    row = direct_evidence(games, 1, 2, "EIGHT")
    assert row["status"] == "VERIFIED"
    assert (row["wins"], row["losses"]) == (1, 1)
    assert row["game_keys"] == ["g1", "g2"]
    assert row["probability_publication"] == "FORBIDDEN"


def test_direct_record_keeps_formats_strictly_separate():
    games = [game("eight", 1, 2, "W", "EIGHT"), game("nine", 1, 2, "L", "NINE")]
    assert direct_evidence(games, 1, 2, "EIGHT")["game_keys"] == ["eight"]
    assert direct_evidence(games, 1, 2, "NINE")["game_keys"] == ["nine"]


def test_unverified_game_fails_closed_instead_of_counting_record():
    row = direct_evidence([game("g1", 1, 2, status="VERIFIED_COUNT_ONLY")], 1, 2, "EIGHT")
    assert row["status"] == "INSUFFICIENT_EVIDENCE"
    assert row["wins"] is None and row["losses"] is None
    assert row["unsafe_game_keys"] == ["g1"]


def test_no_history_is_explicit_not_neutral_or_predicted():
    row = direct_evidence([], 1, 2, "EIGHT")
    assert row["status"] == "NO_RECORDED_HISTORY"
    assert row["games"] == 0
    assert row["wins"] == 0 and row["losses"] == 0
    assert row["probability_publication"] == "FORBIDDEN"


def test_direct_record_rejects_blank_and_duplicate_provenance():
    blank = direct_evidence([game("", 1, 2)], 1, 2, "EIGHT")
    assert blank["status"] == "INSUFFICIENT_EVIDENCE"
    assert blank["reason"] == "MISSING_GAME_KEY"
    duplicate = direct_evidence([game("dup", 1, 2), game("dup", 2, 1)], 1, 2, "EIGHT")
    assert duplicate["status"] == "INSUFFICIENT_EVIDENCE"
    assert duplicate["reason"] == "DUPLICATE_GAME_KEY"
    assert duplicate["wins"] is None and duplicate["losses"] is None


def test_invalid_format_and_ambiguous_identity_fail_closed():
    with pytest.raises(ValueError):
        direct_evidence([], 1, 2, "TEN")
    with pytest.raises(ValueError):
        direct_evidence([], 1, 1, "EIGHT")
    with pytest.raises(ValueError):
        shared_opponent_evidence([], 1, 1, "NINE")


def test_shared_opponent_returns_exact_supporting_keys():
    games = [game("a-c", 1, 3, "W"), game("b-c", 2, 3, "L")]
    result = shared_opponent_evidence(games, 1, 2, "EIGHT")
    assert result["count"] == 1
    assert result["probability_publication"] == "FORBIDDEN"
    row = result["shared_opponents"][0]
    assert row["opponent_id"] == 3
    assert row["status"] == "VERIFIED"
    assert row["player_a_record"] == {"wins": 1, "losses": 0}
    assert row["player_b_record"] == {"wins": 0, "losses": 1}
    assert row["player_a_game_keys"] == ["a-c"]
    assert row["player_b_game_keys"] == ["b-c"]


def test_shared_opponent_fails_only_unsafe_opponent_comparison_closed():
    games = [
        game("a-c", 1, 3, "W"),
        game("b-c", 2, 3, "W", status="MIRROR_MISMATCH"),
        game("a-d", 1, 4, "W"),
        game("b-d", 2, 4, "L"),
    ]
    rows = {r["opponent_id"]: r for r in shared_opponent_evidence(games, 1, 2, "EIGHT")["shared_opponents"]}
    assert rows[3]["status"] == "INSUFFICIENT_EVIDENCE"
    assert rows[3]["unsafe_game_keys"] == ["b-c"]
    assert rows[4]["status"] == "VERIFIED"


def test_shared_opponent_duplicate_provenance_fails_that_comparison_closed():
    games = [
        game("dup", 1, 3, "W"),
        game("dup", 2, 3, "L"),
        game("a-d", 1, 4, "W"),
        game("b-d", 2, 4, "L"),
    ]
    rows = {r["opponent_id"]: r for r in shared_opponent_evidence(games, 1, 2, "EIGHT")["shared_opponents"]}
    assert rows[3]["status"] == "INSUFFICIENT_EVIDENCE"
    assert rows[3]["reason"] == "DUPLICATE_GAME_KEY"
    assert rows[3]["player_a_record"] is None
    assert rows[4]["status"] == "VERIFIED"
