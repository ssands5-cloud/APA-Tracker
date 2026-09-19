from analytics.ultimate_coach_all_player_enrichment import build_all_player_enrichment


def game(key, fmt, when, a, b, winner, loser, status="VERIFIED_UNIQUE"):
    return {"game_key": key, "format": fmt, "match_date": when,
            "participant_a_id": a, "participant_b_id": b,
            "winner_id": winner, "loser_id": loser, "mirror_status": status}


def test_profiles_are_format_isolated_and_missing_is_not_zero():
    games = [
        game("e1", "EIGHT", "2026-01-01T18:00:00-07:00", 1, 2, 1, 2),
        game("n1", "NINE", "2026-01-02T18:00:00-07:00", 1, 2, 2, 1),
    ]
    result = build_all_player_enrichment(games, {1: "VERIFIED_UNIQUE", 2: "VERIFIED_UNIQUE", 3: "VERIFIED_UNIQUE"}, "EIGHT")
    profiles = {p["player_id"]: p for p in result["profiles"]}
    assert result["accepted_game_keys"] == ["e1"]
    assert (profiles[1]["wins"], profiles[1]["losses"]) == (1, 0)
    assert profiles[3]["history_status"] == "NO_RECORDED_HISTORY"
    assert profiles[3]["wins"] is None and profiles[3]["losses"] is None
    assert result["probability_publication"] == "FORBIDDEN"


def test_ambiguous_and_non_integer_identities_fail_closed():
    games = [
        game("amb", "EIGHT", "2026-01-01T18:00:00Z", 1, 2, 1, 2),
        game("bool", "EIGHT", "2026-01-02T18:00:00Z", True, 1, 1, True),
    ]
    result = build_all_player_enrichment(games, {1: "VERIFIED_UNIQUE", 2: "AMBIGUOUS", True: "VERIFIED_UNIQUE"}, "EIGHT")
    assert result["accepted_game_keys"] == []
    assert result["excluded"]["AMBIGUOUS_OR_UNVERIFIED_IDENTITY"] == 1
    assert result["excluded"]["INVALID_PARTICIPANT_IDENTITY"] == 1


def test_as_of_is_exclusive_and_offset_equivalent_instants_are_atomic():
    games = [
        game("prior", "EIGHT", "2026-01-01T17:59:59Z", 1, 2, 1, 2),
        game("same-a", "EIGHT", "2026-01-01T18:00:00Z", 1, 2, 1, 2),
        game("same-b", "EIGHT", "2026-01-01T11:00:00-07:00", 1, 2, 2, 1),
    ]
    result = build_all_player_enrichment(games, {1: "VERIFIED_UNIQUE", 2: "VERIFIED_UNIQUE"}, "EIGHT", as_of="2026-01-01T18:00:00+00:00")
    assert result["accepted_game_keys"] == ["prior"]
    assert result["excluded"]["AT_OR_AFTER_AS_OF"] == 2


def test_bad_provenance_time_and_outcome_are_attributably_excluded():
    games = [
        game("", "EIGHT", "2026-01-01T18:00:00Z", 1, 2, 1, 2),
        game("dup", "EIGHT", "2026-01-02T18:00:00Z", 1, 2, 1, 2),
        game("dup", "EIGHT", "2026-01-03T18:00:00Z", 1, 2, 2, 1),
        game("unverified", "EIGHT", "2026-01-04T18:00:00Z", 1, 2, 1, 2, "AMBIGUOUS"),
        game("naive", "EIGHT", "2026-01-05T18:00:00", 1, 2, 1, 2),
        game("bad-outcome", "EIGHT", "2026-01-06T18:00:00Z", 1, 2, 3, 2),
    ]
    result = build_all_player_enrichment(games, {1: "VERIFIED_UNIQUE", 2: "VERIFIED_UNIQUE"}, "EIGHT")
    assert result["accepted_game_keys"] == []
    assert result["excluded"] == {
        "DUPLICATE_GAME_KEY": 2,
        "INCONSISTENT_OUTCOME": 1,
        "MISSING_GAME_KEY": 1,
        "MISSING_INVALID_OR_NAIVE_TIME": 1,
        "UNVERIFIED_GAME_EVIDENCE": 1,
    }


def test_invalid_format_and_naive_as_of_rejected():
    import pytest
    with pytest.raises(ValueError):
        build_all_player_enrichment([], {}, "TEN")
    with pytest.raises(ValueError):
        build_all_player_enrichment([], {}, "EIGHT", as_of="2026-01-01T18:00:00")
