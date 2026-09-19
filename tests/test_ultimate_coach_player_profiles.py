import pytest

from analytics.ultimate_coach_player_profiles import (
    build_all_player_profiles,
    build_player_profile,
)


def ident(player_id=1, status="VERIFIED_UNIQUE", name="Alpha"):
    return {"player_id": player_id, "status": status, "player_name": name}


def game(
    key,
    a,
    b,
    *,
    when="2026-09-01T19:00:00-06:00",
    fmt="EIGHT",
    result="W",
    mirror="VERIFIED_UNIQUE",
    a_sl=4,
    b_sl=5,
):
    winner = a if result == "W" else b if result == "L" else None
    loser = b if result == "W" else a if result == "L" else None
    return {
        "game_key": key,
        "match_date": when,
        "format": fmt,
        "mirror_status": mirror,
        "participant_a_id": a,
        "participant_b_id": b,
        "participant_a_result": result,
        "participant_a_skill_level": a_sl,
        "participant_b_skill_level": b_sl,
        "winner_id": winner,
        "loser_id": loser,
    }


@pytest.mark.parametrize("bad_id", [True, False, "1", 1.0, None])
def test_profile_rejects_noncanonical_identity_aliases(bad_id):
    with pytest.raises(ValueError, match="integer canonical player identity"):
        build_player_profile([], ident(bad_id), "EIGHT")


@pytest.mark.parametrize("status", ["AMBIGUOUS", "UNRESOLVED", "", None])
def test_profile_rejects_unverified_identity_status(status):
    with pytest.raises(ValueError, match="VERIFIED_UNIQUE"):
        build_player_profile([], ident(1, status=status), "NINE")


def test_format_isolation_and_exact_source_provenance():
    games = [
        game("8-win", 1, 2, fmt="EIGHT", result="W"),
        game("9-loss", 1, 2, fmt="NINE", result="L"),
    ]
    out = build_player_profile(games, ident(1), "8-ball")
    assert out["format"] == "EIGHT"
    assert out["source_game_keys"] == ["8-win"]
    assert out["verified_observed_record"]["wins"] == 1
    assert out["verified_observed_record"]["losses"] == 0
    assert out["opponent_history"][0]["game_keys"] == ["8-win"]
    assert out["opponent_history"][0]["evidence_type"] == "DIRECT_OBSERVED"


def test_blank_duplicate_and_unverified_provenance_are_quarantined():
    games = [
        game("", 1, 2),
        game("dup", 1, 3),
        game("dup", 1, 4),
        game("unsafe", 1, 5, mirror="MIRROR_MISMATCH"),
        game("good", 1, 6),
    ]
    out = build_player_profile(games, ident(1), "EIGHT")
    assert out["evidence_status"] == "PARTIAL"
    assert out["source_game_keys"] == ["good"]
    assert out["exclusions"]["counts"] == {
        "DUPLICATE_GAME_KEY": 2,
        "MISSING_GAME_KEY": 1,
        "UNVERIFIED_GAME_EVIDENCE": 1,
    }
    assert out["verified_observed_record"]["games"] == 1


def test_missing_skill_level_stays_missing_not_zero():
    out = build_player_profile(
        [game("g1", 1, 2, a_sl=None, b_sl=5)],
        ident(1),
        "EIGHT",
    )
    assert out["skill_level_history"][0]["skill_level"] is None
    assert out["skill_level_history"][0]["opponent_skill_level"] == 5


def test_no_recorded_history_is_not_presented_as_zero_record():
    out = build_player_profile([], ident(1), "NINE")
    record = out["verified_observed_record"]
    assert out["evidence_status"] == "NO_RECORDED_EVIDENCE"
    assert record["games"] == 0
    assert record["wins"] is None
    assert record["losses"] is None
    assert record["first_event_time"] is None
    assert out["probability_publication"] == "FORBIDDEN"


def test_historical_as_of_boundary_is_strict_and_same_instant_safe():
    games = [
        game("before", 1, 2, when="2026-09-01T18:59:59-06:00"),
        game("same", 1, 3, when="2026-09-01T19:00:00-06:00"),
        game("after", 1, 4, when="2026-09-01T19:00:01-06:00"),
    ]
    out = build_player_profile(
        games,
        ident(1),
        "EIGHT",
        as_of="2026-09-01T19:00:00-06:00",
    )
    assert out["source_game_keys"] == ["before"]
    assert out["outside_as_of_count"] == 2
    assert out["history_boundary_rule"] == "STRICTLY_BEFORE_AS_OF"


def test_equivalent_instant_different_offset_is_still_same_boundary():
    games = [
        game("same-instant", 1, 2, when="2026-09-02T01:00:00+00:00"),
        game("earlier", 1, 3, when="2026-09-02T00:59:59+00:00"),
    ]
    out = build_player_profile(
        games,
        ident(1),
        "EIGHT",
        as_of="2026-09-01T19:00:00-06:00",
    )
    assert out["source_game_keys"] == ["earlier"]
    assert out["outside_as_of_count"] == 1


@pytest.mark.parametrize("bad_time", ["", "2026-09-01T19:00:00", "not-a-time"])
def test_invalid_or_naive_event_time_is_quarantined(bad_time):
    out = build_player_profile([game("bad-time", 1, 2, when=bad_time)], ident(1), "EIGHT")
    assert out["evidence_status"] == "INSUFFICIENT_EVIDENCE"
    assert out["exclusions"]["counts"]["MISSING_INVALID_OR_NAIVE_TIME"] == 1
    assert out["source_game_keys"] == []


def test_inconsistent_outcome_and_self_pairing_fail_closed():
    inconsistent = game("bad-outcome", 1, 2)
    inconsistent["winner_id"] = 2
    inconsistent["loser_id"] = 1
    self_game = game("self", 1, 1)
    out = build_player_profile([inconsistent, self_game], ident(1), "EIGHT")
    assert out["evidence_status"] == "INSUFFICIENT_EVIDENCE"
    assert out["exclusions"]["counts"]["INCOMPLETE_OR_INCONSISTENT_OUTCOME"] == 1
    assert out["exclusions"]["counts"]["INVALID_OPPONENT_IDENTITY"] == 1


def test_output_is_deterministic_for_identical_verified_input():
    games = [
        game("later", 1, 3, when="2026-09-02T19:00:00-06:00", result="L"),
        game("earlier", 1, 2, when="2026-09-01T19:00:00-06:00", result="W"),
    ]
    a = build_player_profile(games, ident(1), "EIGHT")
    b = build_player_profile(list(reversed(games)), ident(1), "EIGHT")
    assert a == b
    assert a["source_game_keys"] == ["earlier", "later"]


def test_all_player_builder_omits_ambiguous_invalid_and_duplicate_identities():
    identities = [
        ident(1, name="One"),
        ident(2, status="AMBIGUOUS", name="Two"),
        ident(True, name="Bool"),
        ident(3, name="Three"),
        ident(3, name="Three Duplicate"),
    ]
    out = build_all_player_profiles([], identities, "EIGHT")
    assert [row["player_id"] for row in out["profiles"]] == [1]
    assert out["profile_count"] == 1
    assert out["identity_exclusion_count"] == 3
    assert any("duplicate VERIFIED_UNIQUE" in row["reason"] for row in out["identity_exclusions"])
    assert out["probability_publication"] == "FORBIDDEN"
    assert out["requires_live_apa_login"] is False


def test_as_of_must_be_offset_aware():
    with pytest.raises(ValueError, match="offset-aware"):
        build_player_profile([], ident(1), "EIGHT", as_of="2026-09-01T19:00:00")


def test_publication_lock_never_turns_descriptive_profile_into_prediction():
    out = build_player_profile([game("g1", 1, 2)], ident(1), "EIGHT")
    assert out["matchup_probability"] is None
    assert out["predictive_confidence"] is None
    assert out["probability_publication"] == "FORBIDDEN"
