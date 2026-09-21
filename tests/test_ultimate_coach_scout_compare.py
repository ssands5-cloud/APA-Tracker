import pytest

from analytics.ultimate_coach_scout_compare import build_scout_compare


def ident(player_id, status="VERIFIED_UNIQUE"):
    return {"player_id": player_id, "status": status}


def game(key, a, b, result="W", fmt="EIGHT", status="VERIFIED_UNIQUE"):
    return {
        "game_key": key,
        "participant_a_id": a,
        "participant_b_id": b,
        "participant_a_result": result,
        "format": fmt,
        "mirror_status": status,
    }


def test_offline_cockpit_keeps_formats_separate_and_never_publishes_odds():
    games = [
        game("8-direct", 1, 2, fmt="EIGHT"),
        game("9-direct", 1, 2, result="L", fmt="NINE"),
        game("8-a-common", 1, 3, fmt="EIGHT"),
        game("8-b-common", 2, 3, result="L", fmt="EIGHT"),
    ]
    out = build_scout_compare(games, ident(1), ident(2), "8-ball")
    assert out["format"] == "EIGHT"
    assert out["direct_history"]["game_keys"] == ["8-direct"]
    assert out["shared_opponent_history"]["count"] == 1
    assert out["matchup_probability"] is None
    assert out["predictive_confidence"] is None
    assert out["probability_publication"] == "FORBIDDEN"
    assert out["requires_live_apa_login"] is False


@pytest.mark.parametrize("status", ["AMBIGUOUS", "UNRESOLVED", "", None])
def test_ambiguous_or_unresolved_identity_fails_closed(status):
    with pytest.raises(ValueError):
        build_scout_compare([], ident(1, status), ident(2), "EIGHT")


def test_same_canonical_player_fails_closed():
    with pytest.raises(ValueError):
        build_scout_compare([], ident(7), ident(7), "NINE")


def test_missing_history_is_not_fabricated_as_neutral_evidence():
    out = build_scout_compare([], ident(1), ident(2), "NINE")
    assert out["evidence_status"] == "NO_RECORDED_EVIDENCE"
    assert out["direct_history"]["status"] == "NO_RECORDED_HISTORY"
    assert out["direct_history"]["games"] == 0
    assert out["shared_opponent_history"]["count"] == 0
    assert out["matchup_probability"] is None


def test_unsafe_direct_provenance_remains_visible_not_zero_filled():
    out = build_scout_compare([game("bad", 1, 2, status="AMBIGUOUS")], ident(1), ident(2), "EIGHT")
    assert out["evidence_status"] == "PARTIAL"
    assert out["direct_history"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert out["direct_history"]["wins"] is None
    assert out["direct_history"]["losses"] is None
    assert "DIRECT:UNVERIFIED_GAME_EVIDENCE" in out["evidence_blockers"]


def test_unsafe_shared_opponent_isolated_and_attributable():
    games = [
        game("a-safe", 1, 3),
        game("b-unsafe", 2, 3, status="AMBIGUOUS"),
        game("a-other", 1, 4),
        game("b-other", 2, 4),
    ]
    out = build_scout_compare(games, ident(1), ident(2), "EIGHT")
    rows = {row["opponent_id"]: row for row in out["shared_opponent_history"]["shared_opponents"]}
    assert rows[3]["status"] == "INSUFFICIENT_EVIDENCE"
    assert rows[3]["player_a_record"] is None
    assert rows[4]["status"] == "VERIFIED"
    assert out["probability_publication"] == "FORBIDDEN"
