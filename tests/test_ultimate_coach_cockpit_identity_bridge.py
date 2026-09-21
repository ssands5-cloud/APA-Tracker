"""Adversarial tests for the canonical cockpit identity bridge.

Only the DB-read boundary (analytics.ultimate_coach_data_contract.build_contract)
is monkeypatched. The real analytics.ultimate_coach_identity_manifest,
analytics.ultimate_coach_identity_namespace_audit, and
analytics.ultimate_coach_cockpit_identity_bridge code runs unmodified against
hand-crafted contract fixtures -- this genuinely exercises the production
wiring end-to-end, not a re-derivation of logic already covered by those
modules' own dedicated test suites.
"""

from __future__ import annotations

from typing import Any

import pytest

from analytics import ultimate_coach_cockpit_identity_bridge as bridge
from ui.ultimate_coach import render

CONTRACT_SCHEMA = "ultimate-coach-data-contract-v1"


def _player_row(player_id: Any, external_id: str, name: str) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "member_external_id": external_id,
        "player_name": name,
        "current_skill_level": 5,
        "current_matches_won": None,
        "current_matches_played": None,
    }


def _history_row(
    player_id: int, team_id: str, session_name: str, *, member_external_id: str, division_id: str = "D1"
) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "member_external_id": member_external_id,
        "team_external_id": team_id,
        "team_name": f"Team {team_id}",
        "division_id": division_id,
        "session_name": session_name,
        "is_current": True,
        "is_tournament": False,
        "skill_level": 5,
        "rank": None,
        "matches_won": None,
        "matches_played": None,
    }


def _game_row(
    game_key: str,
    a_id: Any,
    b_id: Any,
    *,
    a_team: str,
    b_team: str,
    session_name: str = "Fall 2026",
    fmt: str = "EIGHT",
    mirror_status: str = "VERIFIED_UNIQUE",
    match_id: int = 900,
    a_external_id: str = "",
    b_external_id: str = "",
    a_name: str = "",
    b_name: str = "",
) -> dict[str, Any]:
    return {
        "game_key": game_key,
        "match_id": match_id,
        "match_external_id": str(match_id),
        "match_date": "2026-09-01T19:00:00-06:00",
        "session_name": session_name,
        "format": fmt,
        "participant_a_id": a_id,
        "participant_a_external_id": a_external_id,
        "participant_a_name": a_name,
        "participant_a_team_id": a_team,
        "participant_a_team_name": f"Team {a_team}",
        "participant_a_skill_level": 5,
        "participant_a_result": "W",
        "participant_a_points_earned": 3,
        "participant_a_nine_ball_points": None,
        "participant_b_id": b_id,
        "participant_b_external_id": b_external_id,
        "participant_b_name": b_name,
        "participant_b_team_id": b_team,
        "participant_b_team_name": f"Team {b_team}",
        "participant_b_skill_level": 4,
        "winner_id": a_id,
        "winner_name": a_name,
        "loser_id": b_id,
        "loser_name": b_name,
        "mirror_status": mirror_status,
    }


def _base_fixture() -> dict[str, Any]:
    """Two fully roster-verified players (1, 2) on teams T1/T2 in the same
    session, one player (3) with zero team history (unverifiable), one
    player (4) verified but never appearing in any game (no-history case),
    and one malformed row with a bool player_id (case 2)."""
    players = [
        _player_row(1, "1001", "Ann Fixture"),
        _player_row(2, "1002", "Bob Sample"),
        _player_row(3, "1003", "Cid Stranger"),  # no team history -> unverifiable
        _player_row(4, "1004", "Dee Quiet"),  # verified but no games at all
        _player_row(True, "1005", "Bool Id"),  # invalid internal id -- must never be selectable
    ]
    history = [
        _history_row(1, "T1", "Fall 2026", member_external_id="1001"),
        _history_row(2, "T2", "Fall 2026", member_external_id="1002"),
        _history_row(4, "T4", "Fall 2026", member_external_id="1004"),
        # player 3 intentionally has NO history rows at all.
    ]
    team_matches = [
        {"match_id": 900, "home_team_id": "T1", "away_team_id": "T2"},
    ]
    all_games = [
        # Clean, identity-verified, mirror-safe game -- must appear as evidence.
        _game_row("G-EIGHT-CLEAN", 1, 2, a_team="T1", b_team="T2", fmt="EIGHT",
                   a_external_id="1001", b_external_id="1002", a_name="Ann Fixture", b_name="Bob Sample"),
        # Case 7: same two players, NINE format -- must appear as ITS OWN
        # evidence entry and never leak into the EIGHT-ball comparison.
        _game_row("G-NINE-1", 1, 2, a_team="T1", b_team="T2", fmt="NINE",
                   a_external_id="1001", b_external_id="1002", a_name="Ann Fixture", b_name="Bob Sample"),
        # Case 3: mirror-verified but one participant (3) has no roster
        # provenance at all -- must be excluded from evidence even though
        # the mirror itself is clean.
        _game_row("G-INDETERMINATE-1", 1, 3, a_team="T1", b_team="XX",
                   a_external_id="1001", b_external_id="1003", a_name="Ann Fixture", b_name="Cid Stranger"),
        # Case 4: player 1 reported on a team they were never rostered on
        # this session -- SUSPECT (TEAM_MISMATCH_WITHIN_ROSTERED_SESSION) ->
        # must be quarantined, never evidence.
        _game_row("G-WRONGTEAM-1", 1, 2, a_team="WRONG_TEAM", b_team="T2",
                   a_external_id="1001", b_external_id="1002", a_name="Ann Fixture", b_name="Bob Sample"),
        # Case 5: duplicate game_key (two DIFFERENT games sharing one key,
        # deliberately separate from the clean baseline above) -- both
        # copies must be quarantined/excluded, never just one arbitrarily
        # kept, and must not affect the unrelated clean game.
        _game_row("G-EIGHT-DUP", 1, 2, a_team="T1", b_team="T2", fmt="EIGHT",
                   a_external_id="1001", b_external_id="1002", a_name="Ann Fixture", b_name="Bob Sample",
                   match_id=901),
        _game_row("G-EIGHT-DUP", 1, 2, a_team="T1", b_team="T2", fmt="EIGHT",
                   a_external_id="1001", b_external_id="1002", a_name="Ann Fixture", b_name="Bob Sample",
                   match_id=902),
        # Case 6: self-pairing -- must be excluded.
        _game_row("G-SELF-1", 1, 1, a_team="T1", b_team="T1",
                   a_external_id="1001", b_external_id="1001", a_name="Ann Fixture", b_name="Ann Fixture"),
    ]
    return {
        "schema": CONTRACT_SCHEMA,
        "tables": {
            "players": players,
            "team_matches": team_matches,
            "player_match_stats": [],
            "raw_h2h_evidence": [],
            "all_games": all_games,
            "career_stats": [],
            "team_history": history,
            "coverage_issues": [{"category": "X", "detail": "one pre-existing source coverage issue"}],
        },
        "counts": {
            "players": len(players),
            "team_matches": len(team_matches),
            "all_games": len(all_games),
            "coverage_issues": 1,
        },
        "notes": {},
    }


@pytest.fixture
def payload(monkeypatch):
    monkeypatch.setattr(bridge, "build_contract", lambda db: _base_fixture())
    return bridge.build_verified_cockpit_payload(db=None)


class TestSelectableIdentities:
    def test_unverified_player_is_absent_from_selectable_players(self, payload):
        """Case 1: player 3 has zero team history -> not roster-verified ->
        must never appear in the player selector."""
        ids = {p["id"] for p in payload["players"]}
        assert 3 not in ids
        names = {p["name"] for p in payload["players"]}
        assert "Cid Stranger" not in names

    def test_bool_player_id_cannot_enter_the_selector(self, payload):
        """Case 2: a players-table row with player_id=True (bool, not a
        real int) must be rejected by the identity manifest and therefore
        absent from the selectable list -- bool is a subclass of int in
        Python and must not be silently accepted as one."""
        ids = [p["id"] for p in payload["players"]]
        # `True in [1, 2, 4]` is True in Python (bool is an int subclass and
        # True == 1) -- an identity/type check is required, not membership.
        assert not any(isinstance(pid, bool) for pid in ids)
        assert all(isinstance(pid, int) and not isinstance(pid, bool) for pid in ids)
        assert "Bool Id" not in {p["name"] for p in payload["players"]}

    def test_no_history_player_remains_selectable(self, payload):
        """Case 8 (payload half): player 4 is fully roster-verified but
        appears in zero games. They must still be selectable -- a real
        player with no recorded history is not the same as an invalid
        identity -- and must contribute zero evidence rows, never a
        fabricated 0-0 entry."""
        ids = {p["id"] for p in payload["players"]}
        assert 4 in ids
        evidence_for_4 = [
            row for row in payload["evidence"]
            if row["player_id"] == 4 or row["opponent_id"] == 4
        ]
        assert evidence_for_4 == []


class TestEvidenceFiltering:
    def test_clean_verified_game_appears_as_evidence(self, payload):
        eight_ball_direct = [
            row for row in payload["evidence"]
            if row["player_id"] == 1 and row["opponent_id"] == 2 and row["format"] == "EIGHT"
        ]
        assert any(row["game_key"] == "G-EIGHT-CLEAN" for row in eight_ball_direct)
        assert all(row["result"] in {"W", "L"} for row in eight_ball_direct)

    def test_mirror_verified_but_namespace_unresolved_participant_excluded(self, payload):
        """Case 3: G-INDETERMINATE-1 has a clean mirror but participant B
        (player 3) has no roster provenance -- must not become evidence for
        either player."""
        for row in payload["evidence"]:
            assert row["game_key"] != "G-INDETERMINATE-1"

    def test_wrong_team_provenance_is_quarantined(self, payload):
        """Case 4: player 1 reported on WRONG_TEAM, a team they were never
        rostered on this session -- SUSPECT, must never reach evidence."""
        for row in payload["evidence"]:
            assert row["game_key"] != "G-WRONGTEAM-1"

    def test_duplicate_game_key_is_excluded_entirely(self, payload):
        """Case 5: two different all_games rows share game_key
        'G-EIGHT-DUP' -- the namespace audit marks the key itself as
        structurally unsafe (DUPLICATE_GAME_KEY) and quarantines it, so
        NEITHER copy may appear as evidence, not even one arbitrarily kept.
        The unrelated clean game (G-EIGHT-CLEAN) must be unaffected."""
        for row in payload["evidence"]:
            assert row["game_key"] != "G-EIGHT-DUP"
        assert any(row["game_key"] == "G-EIGHT-CLEAN" for row in payload["evidence"])

    def test_self_pairing_is_excluded(self, payload):
        """Case 6: a game where participant A and B are the same player."""
        for row in payload["evidence"]:
            assert row["game_key"] != "G-SELF-1"

    def test_cross_format_evidence_never_leaks(self, payload):
        """Case 7: the same two players' NINE-ball game must exist as its
        own evidence entry, tagged NINE, and never appear when filtering
        for EIGHT."""
        nine_ball = [row for row in payload["evidence"] if row["game_key"] == "G-NINE-1"]
        assert nine_ball, "the clean NINE-ball game should be identity-verified evidence"
        assert all(row["format"] == "NINE" for row in nine_ball)
        eight_ball_rows_from_that_game = [
            row for row in payload["evidence"]
            if row["game_key"] == "G-NINE-1" and row["format"] == "EIGHT"
        ]
        assert eight_ball_rows_from_that_game == []


class TestProbabilityLocks:
    def test_locks_are_hardcoded_not_derived_from_payload_content(self, payload):
        """Case 9: matchup_probability/predictive_confidence/
        probability_publication must be present, correct, and identical
        regardless of what the underlying evidence contains -- proven here
        against a fixture that deliberately contains quarantined/suspect/
        duplicate/self-paired rows, exactly the kind of input that a buggy
        implementation might accidentally let influence these fields."""
        assert payload["matchup_probability"] is None
        assert payload["predictive_confidence"] is None
        assert payload["probability_publication"] == "FORBIDDEN"
        assert payload["requires_live_apa_login"] is False
        assert payload["database_mutated"] is False

    def test_locks_survive_even_with_zero_evidence(self, monkeypatch):
        empty_fixture = _base_fixture()
        empty_fixture["tables"]["all_games"] = []
        monkeypatch.setattr(bridge, "build_contract", lambda db: empty_fixture)
        empty_payload = bridge.build_verified_cockpit_payload(db=None)
        assert empty_payload["matchup_probability"] is None
        assert empty_payload["probability_publication"] == "FORBIDDEN"


class TestTrustSection:
    def test_trust_counts_reflect_the_fixture(self, payload):
        trust = payload["trust"]
        assert trust["verified_identity_count"] == 3  # players 1, 2, 4 (not 3, not the bool row)
        assert trust["source_coverage_issue_count"] == 1
        # quarantined_game_keys is a SET of keys, not a row count: WRONG_TEAM
        # (1 key), the duplicate pair (1 shared key), self-pair (1 key) = 3.
        assert trust["quarantined_game_count"] == 3
        # identity-verified: G-EIGHT-CLEAN + G-NINE-1. G-INDETERMINATE-1
        # counts toward neither verified nor quarantined (mixed statuses,
        # not a structural issue) -- disclosed instead via
        # indeterminate_participant_count.
        assert trust["identity_verified_game_count"] == 2
        assert trust["indeterminate_participant_count"] >= 1

    def test_quarantined_games_never_silently_vanish_from_the_report(self, payload):
        """Quarantined evidence must be counted, not just dropped with no
        trace -- the whole point of the Data Trust section."""
        assert payload["trust"]["quarantined_game_count"] > 0
        assert payload["trust"]["quarantined_game_keys_sample"]


class TestHtmlScriptBreakoutSafety:
    """Case 10: a malicious/malformed source string must never let embedded
    JSON break out of its <script type="application/json"> element."""

    def test_dangerous_strings_cannot_break_out_of_the_json_script_block(self):
        dangerous_name = (
            'Ann</script><script>alert(1)</script>'
            '&amp;"quoted"<angle>brackets>'
            '\u2028\u2029line-and-paragraph-separators'
        )
        payload = {
            "schema": "ultimate-coach-verified-cockpit-v1",
            "players": [
                {
                    "id": 1,
                    "external_id": "1001",
                    "name": dangerous_name,
                    "current_skill_level": 5,
                    "career_stats": [],
                    "team_history": [],
                }
            ],
            "evidence": [],
            "trust": {},
            "counts": {"players": 1, "head_to_head_rows": 0, "all_games": 0},
            "matchup_probability": None,
            "predictive_confidence": None,
            "probability_publication": "FORBIDDEN",
        }
        html = render(payload, built_at="2026-09-21 03:00 UTC")

        # Exactly the two legitimate closing tags (the JSON data island and
        # the page's own script block) may appear -- the malicious string's
        # own literal "</script>" must never survive verbatim.
        assert html.count("</script>") == 2
        assert "<script>alert(1)</script>" not in html
        assert "\u2028" not in html
        assert "\u2029" not in html
        # The escaped form must still be present and correctly reversible --
        # confirms this is real escaping, not silent deletion of the name.
        assert "\\u003c/script\\u003e" in html or "\\u003cscript\\u003e" in html

    def test_escaped_json_round_trips_to_the_original_string(self):
        import json
        from ui.ultimate_coach import _script_json

        dangerous = '</script><script>&"\u2028\u2029<>'
        encoded = _script_json({"v": dangerous})
        assert "</script>" not in encoded
        decoded = json.loads(encoded)
        assert decoded["v"] == dangerous
