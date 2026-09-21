import pytest

from analytics.ultimate_coach_identity_namespace_audit import audit_identity_namespace


def contract(*, players=None, history=None, games=None, team_matches=None):
    return {
        "schema": "ultimate-coach-data-contract-v1",
        "tables": {
            "players": players or [],
            "team_history": history or [],
            "all_games": games or [],
            "team_matches": team_matches or [],
        },
    }


def player(pid=1, member="1001", name="Alpha"):
    return {
        "player_id": pid,
        "member_external_id": member,
        "player_name": name,
    }


def history(pid=1, member="1001", team="TA", session="Fall 2026", division="D1"):
    return {
        "player_id": pid,
        "member_external_id": member,
        "player_name": "Display Metadata",
        "team_external_id": team,
        "team_name": f"Team {team}",
        "division_id": division,
        "session_name": session,
        "is_current": False,
        "is_tournament": False,
        "skill_level": 4,
    }


def team_match(match_id=10, home="TA", away="TB"):
    return {
        "match_id": match_id,
        "home_team_id": home,
        "away_team_id": away,
    }


def game(
    key="g1",
    *,
    match_id=10,
    session="Fall 2026",
    a=1,
    a_ext="1001",
    a_team="TA",
    a_name="Alpha",
    b=2,
    b_ext="1002",
    b_team="TB",
    b_name="Bravo",
    mirror="VERIFIED_UNIQUE",
):
    return {
        "game_key": key,
        "match_id": match_id,
        "session_name": session,
        "mirror_status": mirror,
        "participant_a_id": a,
        "participant_a_external_id": a_ext,
        "participant_a_team_id": a_team,
        "participant_a_name": a_name,
        "participant_b_id": b,
        "participant_b_external_id": b_ext,
        "participant_b_team_id": b_team,
        "participant_b_name": b_name,
    }


def verified_contract(games=None, team_matches=None):
    return contract(
        players=[player(1, "1001", "Alpha"), player(2, "1002", "Bravo")],
        history=[
            history(1, "1001", "TA"),
            history(2, "1002", "TB", division="D2"),
        ],
        games=games or [game()],
        team_matches=team_matches or [team_match()],
    )


def test_exact_member_team_session_reconciliation_verifies_game():
    out = audit_identity_namespace(verified_contract())
    assert out["counts"]["identity_verified_games"] == 1
    assert out["identity_verified_game_keys"] == ["g1"]
    assert out["counts"]["suspect_participants"] == 0
    assert out["participant_status_counts"] == {"EXACT_ROSTER_SCOPE": 2}
    assert out["database_mutated"] is False
    assert out["name_matching_used"] is False


def test_display_names_are_irrelevant_to_identity_audit():
    c = verified_contract(
        games=[game(a_name="Totally Different Text", b_name="Another Spelling")]
    )
    out = audit_identity_namespace(c)
    assert out["identity_verified_game_keys"] == ["g1"]
    assert out["name_matching_used"] is False


def test_external_member_id_mismatch_is_suspect_and_quarantined():
    c = verified_contract(games=[game(a_ext="9999")])
    out = audit_identity_namespace(c)
    assert out["identity_verified_game_keys"] == []
    assert out["quarantined_game_keys"] == ["g1"]
    suspect = out["suspect_participants"][0]
    assert suspect["side"] == "A"
    assert suspect["reason"] == "EXTERNAL_ID_MISMATCH"
    assert suspect["canonical_member_external_id"] == "1001"


def test_same_session_wrong_team_is_suspect_not_auto_repaired():
    c = verified_contract(
        games=[game(a_team="TX")],
        team_matches=[team_match(home="TX", away="TB")],
    )
    out = audit_identity_namespace(c)
    suspect = next(row for row in out["suspect_participants"] if row["side"] == "A")
    assert suspect["reason"] == "TEAM_MISMATCH_WITHIN_ROSTERED_SESSION"
    assert suspect["rostered_teams_for_session"] == ["TA"]
    assert out["quarantined_game_keys"] == ["g1"]


def test_missing_historical_session_provenance_is_suspect_but_not_declared_collision():
    c = verified_contract(games=[game(session="Spring 2024")])
    out = audit_identity_namespace(c)
    reasons = {row["reason"] for row in out["suspect_participants"]}
    assert reasons == {"NO_ROSTER_PROVENANCE_FOR_GAME_SESSION"}
    assert "does not by itself prove" in out["interpretation"]


def test_missing_game_team_is_indeterminate_not_zero_or_guessed():
    c = verified_contract(games=[game(a_team="")])
    out = audit_identity_namespace(c)
    row = next(row for row in out["indeterminate_participants"] if row["side"] == "A")
    assert row["reason"] == "MISSING_GAME_TEAM_OR_SESSION_SCOPE"
    assert row["team_id"] is None
    assert out["counts"]["identity_verified_games"] == 0


def test_player_without_roster_verified_identity_is_indeterminate():
    c = verified_contract(
        games=[game(b=3, b_ext="3003", b_team="TC", b_name="Unknown")]
    )
    out = audit_identity_namespace(c)
    row = next(row for row in out["indeterminate_participants"] if row["side"] == "B")
    assert row["reason"] == "PLAYER_NOT_ROSTER_VERIFIED"
    assert out["counts"]["identity_verified_games"] == 0


def test_participant_team_not_in_team_match_is_suspect_even_with_roster_scope():
    c = verified_contract(team_matches=[team_match(home="TC", away="TB")])
    out = audit_identity_namespace(c)
    row = next(row for row in out["suspect_participants"] if row["side"] == "A")
    assert row["reason"] == "PARTICIPANT_TEAM_NOT_IN_TEAM_MATCH"
    assert row["team_match_teams"] == ["TB", "TC"]


def test_unverified_mirror_does_not_enter_identity_verified_game_set():
    c = verified_contract(games=[game(mirror="MIRROR_MISMATCH")])
    out = audit_identity_namespace(c)
    assert out["counts"]["exact_roster_scope_participants"] == 2
    assert out["counts"]["identity_verified_games"] == 0
    assert out["quarantined_game_keys"] == []


def test_duplicate_game_key_is_structural_quarantine_and_not_audited_twice():
    g1 = game(key="dup")
    g2 = game(key="dup", match_id=11)
    c = verified_contract(
        games=[g1, g2],
        team_matches=[team_match(10), team_match(11)],
    )
    out = audit_identity_namespace(c)
    assert out["participant_audits"] == []
    assert out["quarantined_game_keys"] == ["dup"]
    assert len(out["structural_issues"]) == 2
    assert {row["reason"] for row in out["structural_issues"]} == {"DUPLICATE_GAME_KEY"}


def test_self_pairing_is_structural_quarantine():
    c = verified_contract(
        games=[game(a=1, a_ext="1001", a_team="TA", b=1, b_ext="1001", b_team="TA")]
    )
    out = audit_identity_namespace(c)
    assert out["participant_audits"] == []
    assert out["quarantined_game_keys"] == ["g1"]
    assert out["structural_issues"][0]["reason"] == "SELF_PAIRING"


@pytest.mark.parametrize("bad_id", [True, False, "1", 1.0, None])
def test_invalid_internal_player_id_is_indeterminate(bad_id):
    c = verified_contract(games=[game(a=bad_id)])
    out = audit_identity_namespace(c)
    row = next(row for row in out["indeterminate_participants"] if row["side"] == "A")
    assert row["reason"] == "INVALID_INTERNAL_PLAYER_ID"


def test_explicit_invalid_manifest_is_rejected_instead_of_silently_rebuilt():
    with pytest.raises(ValueError, match="unsupported identity-manifest schema"):
        audit_identity_namespace(verified_contract(), manifest={})


def test_duplicate_manifest_player_id_fails_closed():
    manifest = {
        "schema": "ultimate-coach-identity-manifest-v1",
        "source_contract_schema": "ultimate-coach-data-contract-v1",
        "identities": [
            {
                "player_id": 1,
                "member_external_id": "1001",
                "roster_provenance_scopes": [
                    {"team_external_id": "TA", "division_id": "D1", "session_name": "Fall 2026"}
                ],
            },
            {
                "player_id": 1,
                "member_external_id": "1001",
                "roster_provenance_scopes": [
                    {"team_external_id": "TA", "division_id": "D1", "session_name": "Fall 2026"}
                ],
            },
            {
                "player_id": 2,
                "member_external_id": "1002",
                "roster_provenance_scopes": [
                    {"team_external_id": "TB", "division_id": "D2", "session_name": "Fall 2026"}
                ],
            },
        ],
    }
    out = audit_identity_namespace(verified_contract(), manifest=manifest)
    row = next(row for row in out["indeterminate_participants"] if row["side"] == "A")
    assert row["reason"] == "DUPLICATE_IDENTITY_MANIFEST_PLAYER_ID"
    assert out["counts"]["duplicate_manifest_player_ids"] == 1


def test_output_is_deterministic_for_equivalent_input_order():
    games = [
        game(key="g2", match_id=11),
        game(key="g1", match_id=10),
    ]
    matches = [team_match(11), team_match(10)]
    c1 = verified_contract(games=games, team_matches=matches)
    c2 = verified_contract(games=list(reversed(games)), team_matches=list(reversed(matches)))
    assert audit_identity_namespace(c1) == audit_identity_namespace(c2)


def test_probability_and_live_login_remain_forbidden():
    out = audit_identity_namespace(verified_contract())
    assert out["matchup_probability"] is None
    assert out["probability_publication"] == "FORBIDDEN"
    assert out["requires_live_apa_login"] is False
