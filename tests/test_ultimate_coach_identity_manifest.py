from analytics.ultimate_coach_identity_manifest import build_verified_identity_manifest


def contract(players=None, history=None):
    return {
        "schema": "ultimate-coach-data-contract-v1",
        "tables": {
            "players": players or [],
            "team_history": history or [],
        },
    }


def player(pid=1, member="1001", name="Alpha"):
    return {
        "player_id": pid,
        "member_external_id": member,
        "player_name": name,
    }


def hist(
    pid=1,
    member="1001",
    *,
    team="T1",
    division="D1",
    session="Fall 2026",
    name="Alpha",
    current=False,
):
    return {
        "player_id": pid,
        "member_external_id": member,
        "player_name": name,
        "team_external_id": team,
        "team_name": "Team One",
        "division_id": division,
        "session_name": session,
        "is_current": current,
        "is_tournament": False,
        "skill_level": 4,
    }


def test_roster_backed_member_becomes_verified_identity():
    out = build_verified_identity_manifest(contract([player()], [hist()]))
    assert out["identity_count"] == 1
    row = out["identities"][0]
    assert row["player_id"] == 1
    assert row["member_external_id"] == "1001"
    assert row["status"] == "VERIFIED_UNIQUE"
    assert row["verification_basis"] == "ROSTER_BACKED_PLAYER_TEAM_HISTORY"
    assert row["roster_provenance_scope_count"] == 1
    assert row["roster_provenance_scopes"][0]["team_external_id"] == "T1"
    assert out["name_matching_used"] is False


def test_display_name_mismatch_is_not_used_as_identity_key():
    out = build_verified_identity_manifest(
        contract([player(name="Canonical Display")], [hist(name="Scoresheet Spelling")])
    )
    assert out["identity_count"] == 1
    assert out["identities"][0]["player_name"] == "Canonical Display"
    assert out["name_matching_used"] is False


def test_scoresheet_style_player_without_roster_provenance_is_excluded():
    out = build_verified_identity_manifest(contract([player(member="999999")], []))
    assert out["identity_count"] == 0
    assert out["identity_exclusions"][0]["reason"] == "NO_COMPLETE_ROSTER_PROVENANCE"


def test_incomplete_roster_scope_does_not_verify_identity():
    out = build_verified_identity_manifest(
        contract([player()], [hist(team="", division="D1", session="Fall 2026")])
    )
    assert out["identity_count"] == 0
    row = out["identity_exclusions"][0]
    assert row["reason"] == "NO_COMPLETE_ROSTER_PROVENANCE"
    assert row["invalid_scope_rows"] == 1


def test_invalid_internal_player_ids_fail_closed_including_bool_alias():
    out = build_verified_identity_manifest(
        contract(
            [player(pid=True, member="1001"), player(pid="2", member="1002")],
            [],
        )
    )
    assert out["identity_count"] == 0
    assert [row["reason"] for row in out["identity_exclusions"]] == [
        "INVALID_INTERNAL_PLAYER_ID",
        "INVALID_INTERNAL_PLAYER_ID",
    ]


def test_member_id_must_be_numeric_source_string():
    out = build_verified_identity_manifest(
        contract(
            [
                player(pid=1, member=1001),
                player(pid=2, member="alias-x"),
                player(pid=3, member=""),
            ],
            [],
        )
    )
    assert out["identity_count"] == 0
    assert {row["reason"] for row in out["identity_exclusions"]} == {"INVALID_APA_MEMBER_ID"}


def test_duplicate_player_rows_fail_closed():
    out = build_verified_identity_manifest(
        contract(
            [player(pid=1, member="1001"), player(pid=1, member="1001")],
            [hist(pid=1, member="1001")],
        )
    )
    assert out["identity_count"] == 0
    assert out["identity_exclusions"][0]["reason"] == "DUPLICATE_PLAYER_ROW"


def test_same_member_id_mapping_to_two_players_excludes_both():
    out = build_verified_identity_manifest(
        contract(
            [player(pid=1, member="1001"), player(pid=2, member="1001")],
            [hist(pid=1, member="1001"), hist(pid=2, member="1001", team="T2")],
        )
    )
    assert out["identity_count"] == 0
    rows = out["identity_exclusions"]
    assert len(rows) == 2
    assert {row["reason"] for row in rows} == {"APA_MEMBER_ID_MAPS_TO_MULTIPLE_PLAYERS"}
    assert all(row["conflicting_player_ids"] == [1, 2] for row in rows)


def test_team_history_member_id_conflict_fails_player_closed():
    out = build_verified_identity_manifest(
        contract(
            [player(pid=1, member="1001")],
            [
                hist(pid=1, member="1001", team="T1"),
                hist(pid=1, member="2002", team="T2"),
            ],
        )
    )
    assert out["identity_count"] == 0
    row = out["identity_exclusions"][0]
    assert row["reason"] == "TEAM_HISTORY_MEMBER_ID_CONFLICT"
    assert row["conflicting_member_ids"] == ["2002"]


def test_orphan_history_is_reported_not_used_to_create_identity():
    out = build_verified_identity_manifest(
        contract([player(pid=1, member="1001")], [hist(pid=9, member="9009")])
    )
    assert out["identity_count"] == 0
    assert out["counts"]["orphan_team_history_rows"] == 1
    assert out["structural_issues"][0]["reason"] == "ORPHAN_TEAM_HISTORY_PLAYER_ID"


def test_multiple_real_roster_scopes_are_preserved_and_sorted():
    out = build_verified_identity_manifest(
        contract(
            [player()],
            [
                hist(team="T2", division="D2", session="Summer 2026"),
                hist(team="T1", division="D1", session="Spring 2026"),
                hist(team="T3", division="D3", session="Fall 2026", current=True),
            ],
        )
    )
    scopes = out["identities"][0]["roster_provenance_scopes"]
    assert [row["session_name"] for row in scopes] == [
        "Fall 2026",
        "Spring 2026",
        "Summer 2026",
    ]


def test_manifest_is_deterministic_for_equivalent_input_order():
    players = [player(pid=2, member="1002", name="Beta"), player()]
    history = [hist(pid=2, member="1002", team="T2"), hist()]
    a = build_verified_identity_manifest(contract(players, history))
    b = build_verified_identity_manifest(contract(list(reversed(players)), list(reversed(history))))
    assert a == b
    assert [row["player_id"] for row in a["identities"]] == [1, 2]


def test_manifest_remains_offline_and_probability_locked():
    out = build_verified_identity_manifest(contract([player()], [hist()]))
    assert out["requires_live_apa_login"] is False
    assert out["probability_publication"] == "FORBIDDEN"
