"""Real-browser interaction test for the offline Ultimate Coach cockpit."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from analytics.ultimate_coach_match_day import build_match_day_section
from ui.ultimate_coach import _browser_payload, render


def _payload():
    return {
        "schema": "ultimate-coach-cockpit-v1",
        "probability_status": "NOT_CALIBRATED",
        "players": [
            {"id": 1, "external_id": "1", "name": "Alpha Adams", "current_skill_level": 4, "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": []},
            {"id": 2, "external_id": "2", "name": "Bravo Brown", "current_skill_level": 5, "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": []},
            {"id": 3, "external_id": "3", "name": "Charlie Clark", "current_skill_level": 4, "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": []},
            {"id": 4, "external_id": "4", "name": "Delta Dunn", "current_skill_level": 3, "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": []},
        ],
        "evidence": [
            {"player_id": 1, "opponent_id": 2, "match_id": 10, "match_external_id": "10", "match_date": "2026-01-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "W", "own_skill_level": 4, "opponent_skill_level": 5, "points_earned": 3, "nine_ball_points": None},
            {"player_id": 1, "opponent_id": 3, "match_id": 11, "match_external_id": "11", "match_date": "2026-02-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "W", "own_skill_level": 4, "opponent_skill_level": 4, "points_earned": 3, "nine_ball_points": None},
            {"player_id": 2, "opponent_id": 3, "match_id": 12, "match_external_id": "12", "match_date": "2026-03-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "L", "own_skill_level": 5, "opponent_skill_level": 4, "points_earned": 0, "nine_ball_points": None},
        ],
        "counts": {"players": 4, "head_to_head_rows": 3},
    }


def test_search_compare_and_format_switch_work_in_real_browser(tmp_path: Path):
    path = tmp_path / "ultimate_coach.html"
    path.write_text(render(_payload(), built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            page.select_option("#player-a", "1")
            assert page.locator("#player-b option").count() == 3
            assert "2 recorded opponents for Alpha Adams in 8-Ball" in page.locator("#search-status-b").inner_text()
            assert "Delta Dunn" not in page.locator("#player-b").inner_text()

            page.select_option("#player-b", "2")
            assert "1-0" in page.locator("#direct").inner_text()
            assert "Charlie Clark" in page.locator("#shared").inner_text()
            assert "1 recorded direct meeting" in page.locator("#summary").inner_text()
            assert "1 recorded opponent" in page.locator("#summary").inner_text()
            assert "NOT CALIBRATED" in page.locator("#status").inner_text()

            page.fill("#search-b", "Charlie")
            page.wait_for_timeout(400)
            assert page.locator("#player-b option").count() == 2
            assert page.locator("#player-b").input_value() == ""
            assert "Charlie Clark" in page.locator("#player-b option").nth(1).inner_text()
            assert "1 meeting" in page.locator("#player-b option").nth(1).inner_text()

            page.select_option("#format", "NINE")
            # Played-opponents mode is the default. With no NINE-ball history
            # for Alpha, Player B must become empty instead of retaining stale
            # EIGHT-ball choices/results.
            assert page.locator("#player-b option").count() == 1
            assert page.locator("#player-b").input_value() == ""
            assert "No recorded opponents for Alpha Adams in 9-Ball" in page.locator("#search-status-b").inner_text()
            assert "Switch Player B to" in page.locator("#summary").inner_text()
            assert page.locator("#direct").inner_text() == ""

            # All-player scouting remains available for never-played matchups
            # and must still disclose zero direct evidence honestly.
            page.select_option("#player-b-scope", "all")
            assert page.locator("#player-b option").count() == 4
            assert "Delta Dunn" in page.locator("#player-b").inner_text()
            page.select_option("#player-b", "2")
            assert "No recorded evidence" in page.locator("#direct").inner_text()
            assert "0-0" not in page.locator("#direct").inner_text()
            assert "No recorded shared opponents" in page.locator("#shared").inner_text()
        finally:
            browser.close()



def test_format_switch_reaches_non_eight_nine_evidence_in_real_browser(tmp_path: Path):
    payload = _payload()
    payload["players"].append(
        {"id": 5, "external_id": "5", "name": "Echo Evans", "current_skill_level": 6, "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": []}
    )
    # Alpha and Echo have no 8-Ball/9-Ball history together -- only this one
    # real, distinct APA format (see scraper.graphql_scraper._VALID_FORMATS).
    # Before this fix, the Format <select> only ever offered EIGHT/NINE, so
    # this real recorded meeting was permanently unreachable through the UI
    # and the tool would falsely read as "no recorded direct meeting".
    payload["evidence"].append(
        {"player_id": 1, "opponent_id": 5, "match_id": 20, "match_external_id": "20", "match_date": "2026-04-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "MASTERS ALT", "result": "W", "own_skill_level": 4, "opponent_skill_level": 6, "points_earned": 3, "nine_ball_points": None},
    )
    payload["counts"]["players"] = 5
    payload["counts"]["head_to_head_rows"] = 4

    path = tmp_path / "ultimate_coach_masters_alt.html"
    path.write_text(render(payload, built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            page.select_option("#player-a", "1")
            page.select_option("#player-b-scope", "all")
            page.select_option("#player-b", "5")
            assert "No recorded direct meeting" in page.locator("#summary").inner_text()

            # select_option raises if "MASTERS ALT" is not an actual <option>
            # on this <select> -- the real regression guard. No re-selection
            # of Player B here: "all players" mode must keep it selected
            # across the format switch (see the dedicated preservation test
            # below), so if that broke this assertion would fail too.
            page.select_option("#format", "MASTERS ALT")
            assert "1 recorded direct meeting" in page.locator("#summary").inner_text()
            assert "1-0" in page.locator("#direct").inner_text()

            # Same real option must exist on the Team vs Team format select.
            page.select_option("#team-format", "MASTERS ALT")
        finally:
            browser.close()


def test_format_switch_preserves_player_b_and_search_in_all_players_mode(tmp_path: Path):
    payload = _payload()
    payload["players"].append(
        {"id": 5, "external_id": "5", "name": "Echo Evans", "current_skill_level": 6, "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": []}
    )
    # Echo has no EIGHT evidence vs Alpha at all -- only this one MASTERS ALT
    # meeting. "All players" mode's candidate pool never depended on format,
    # so switching format while Echo is selected must keep both the
    # selection and the typed search text, and simply refresh the
    # comparison -- not silently reset Player B back to "Select a player...".
    payload["evidence"].append(
        {"player_id": 1, "opponent_id": 5, "match_id": 20, "match_external_id": "20", "match_date": "2026-04-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "MASTERS ALT", "result": "W", "own_skill_level": 4, "opponent_skill_level": 6, "points_earned": 3, "nine_ball_points": None},
    )
    payload["counts"]["players"] = 5
    payload["counts"]["head_to_head_rows"] = 4

    path = tmp_path / "ultimate_coach_format_switch_preserve.html"
    path.write_text(render(payload, built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            page.select_option("#player-a", "1")
            page.select_option("#player-b-scope", "all")
            page.fill("#search-b", "Echo")
            page.wait_for_timeout(400)
            page.select_option("#player-b", "5")
            assert "No recorded direct meeting" in page.locator("#summary").inner_text()

            page.select_option("#format", "MASTERS ALT")

            assert page.locator("#search-b").input_value() == "Echo"
            assert page.locator("#player-b").input_value() == "5"
            assert "1 recorded direct meeting" in page.locator("#summary").inner_text()
            assert "1-0" in page.locator("#direct").inner_text()

            # "Played opponents" mode is unaffected by this fix: its pool is
            # format-dependent, so the prior selection/search must still
            # clear when it's the active mode.
            page.select_option("#player-b-scope", "played")
            page.fill("#search-b", "Echo")
            page.wait_for_timeout(400)
            page.select_option("#format", "EIGHT")
            assert page.locator("#search-b").input_value() == ""
            assert page.locator("#player-b").input_value() == ""
        finally:
            browser.close()


def test_typing_only_filters_and_never_runs_matchup_until_selection(tmp_path: Path):
    path = tmp_path / "ultimate_coach_search_idle.html"
    path.write_text(render(_payload(), built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            page.select_option("#player-a", "1")
            page.select_option("#player-b", "2")
            before_summary = page.locator("#summary").inner_text()
            before_direct = page.locator("#direct").inner_text()

            # Typing narrows the UI only. It must not silently select Charlie,
            # rebuild the matchup, or render a new comparison.
            page.fill("#search-b", "Charlie")
            page.wait_for_timeout(400)
            assert page.locator("#player-b").input_value() == ""
            assert page.locator("#summary").inner_text() == before_summary
            assert page.locator("#direct").inner_text() == before_direct

            # The expensive comparison happens only after an explicit choice.
            page.select_option("#player-b", "3")
            assert "Alpha Adams and Charlie Clark" in page.locator("#summary").inner_text()

            # Same rule for Player A search: typing may clear the visible
            # selection but must not rebuild Player B or run a comparison.
            page.fill("#search-a", "Bravo")
            page.wait_for_timeout(400)
            assert page.locator("#player-a").input_value() == ""
            assert "Alpha Adams and Charlie Clark" in page.locator("#summary").inner_text()
        finally:
            browser.close()


def test_profile_history_dedupes_repeated_display_rows(tmp_path: Path):
    payload = _payload()
    repeated = {
        "team_external_id": "mark-it-up",
        "team_name": "Mark It Up",
        "division_id": "d1",
        "session_name": "Summer 2026",
        "is_current": True,
        "skill_level": 4,
        "matches_won": 1,
        "matches_played": 2,
    }
    payload["players"][0]["team_history"] = [dict(repeated), dict(repeated), dict(repeated)]

    path = tmp_path / "ultimate_coach_profile_history.html"
    path.write_text(render(payload, built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            page.select_option("#player-a", "1")
            profile = page.locator("#profile-a").inner_text()
            assert profile.count("Summer 2026 · Mark It Up · SL 4") == 1
        finally:
            browser.close()


def _rehydrate(compact: dict) -> dict:
    """Faithful Python port of the browser's rehydrate step.

    Kept deliberately close to the JS in ui/ultimate_coach.py so a change to
    one that is not mirrored in the other shows up as a failing round-trip.
    """
    import copy

    out = copy.deepcopy(compact)
    table = out.get("strings")
    if table is None:
        return out
    deref = lambda v: table[v] if isinstance(v, int) and not isinstance(v, bool) else v

    positions = out.get("evidence_interned_positions") or []
    for rows in (out.get("evidence_index") or {}).values():
        for row in rows:
            for position in positions:
                row[position] = deref(row[position])

    fields = out.get("team_history_fields")
    if fields:
        interned = set(out.get("team_history_interned_positions") or [])
        for player in out.get("players") or []:
            rows = player.get("team_history")
            if not rows:
                continue
            player["team_history"] = [
                {
                    name: (deref(row[i]) if i in interned else row[i])
                    for i, name in enumerate(fields)
                }
                if isinstance(row, list)
                else row
                for row in rows
            ]
    return out


def test_browser_payload_compacts_and_preindexes_evidence():
    payload = _payload()
    compact = _rehydrate(_browser_payload(payload))

    assert "evidence" not in compact
    assert compact["counts"] == payload["counts"]

    fields = compact["evidence_row_fields"]
    opponent_i = fields.index("opponent_id")
    result_i = fields.index("result")

    player_one = compact["evidence_index"]["1|EIGHT"]
    assert len(player_one) == 2
    assert player_one[0][opponent_i] == 2
    assert player_one[0][result_i] == "W"


def test_browser_payload_declares_the_compact_v2_schema():
    compact = _browser_payload(_payload())

    assert compact["browser_payload_schema"] == "ultimate-coach-browser-compact-v2"
    assert compact["team_history_fields"][0] == "team_external_id"
    assert isinstance(compact["strings"], list)


def test_interning_is_lossless_for_evidence_and_team_history():
    """Every recorded value must survive the round trip byte for byte.

    This is the guard on the ~50MB size reduction: the payload may shrink
    only by removing duplication, never by dropping or altering a row.
    """
    payload = _payload()
    payload["players"][0]["team_history"] = [
        {
            "team_external_id": "t-1",
            "team_name": "Team One",
            "division_id": "d1",
            "session_name": "Summer 2026",
            "format": "EIGHT",
            "is_current": True,
            "skill_level": 4,
            "matches_won": 1,
            "matches_played": 2,
        },
        {
            "team_external_id": "t-1",
            "team_name": "Team One",
            "division_id": "d1",
            "session_name": "Summer 2026",
            "format": "NINE",
            "is_current": False,
            "skill_level": None,
            "matches_won": 0,
            "matches_played": 0,
        },
    ]
    expected_history = [dict(entry) for entry in payload["players"][0]["team_history"]]
    expected_rows = {
        key: [list(row) for row in rows]
        for key, rows in _browser_payload(payload)["evidence_index"].items()
    }

    compact = _browser_payload(payload)
    restored = _rehydrate(compact)

    assert restored["players"][0]["team_history"] == expected_history
    # a repeated string is stored once and referenced twice
    assert compact["players"][0]["team_history"][0][1] == (
        compact["players"][0]["team_history"][1][1]
    )
    assert len(compact["strings"]) == len(set(compact["strings"]))
    for key, rows in restored["evidence_index"].items():
        assert len(rows) == len(expected_rows[key])


def test_interning_refuses_an_ambiguous_non_string_value():
    """A number in an interned field would be unrecoverable, so the build fails.

    The browser rehydrates by replacing numbers with table entries, so a real
    number arriving here could not be told apart from an index. Refusing beats
    silently corrupting a recorded session name.
    """
    from ui.ultimate_coach import BrowserPayloadEncodingError

    payload = _payload()
    payload["players"][0]["team_history"] = [
        {
            "team_external_id": "t-1",
            "team_name": 12345,
            "division_id": "d1",
            "session_name": "Summer 2026",
            "format": "EIGHT",
            "is_current": True,
            "skill_level": 4,
            "matches_won": 1,
            "matches_played": 2,
        }
    ]

    with pytest.raises(BrowserPayloadEncodingError) as excinfo:
        _browser_payload(payload)

    assert "team_name" in str(excinfo.value)



def test_production_render_can_drain_raw_evidence_after_compaction():
    payload = _payload()
    original_rows = len(payload["evidence"])
    html = render(payload, built_at="test", consume_evidence=True)

    assert original_rows == 3
    assert payload["evidence"] == []
    assert "evidence_index" in html
    assert "Alpha Adams" in html


def test_rendered_browser_never_scans_full_evidence_array_per_compare():
    html = render(_payload(), built_at="test")

    assert "DATA.evidence.filter" not in html
    assert "EVIDENCE_INDEX[String(pid)+\"|\"+fmt]" in html
    assert "evidence_index" in html


def test_search_is_bounded_for_large_player_lists(tmp_path: Path):
    payload = _payload()
    payload["players"] = [
        {
            "id": i,
            "external_id": str(i),
            "name": f"Player {i:04d}",
            "current_skill_level": 4,
            "current_matches_won": None,
            "current_matches_played": None,
            "team_history": [],
            "career_stats": [],
        }
        for i in range(1, 601)
    ]
    payload["counts"]["players"] = len(payload["players"])

    path = tmp_path / "ultimate_coach_large.html"
    path.write_text(render(payload, built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            assert page.locator("#player-a option").count() == 76
            assert "Showing first 75 of 600" in page.locator("#search-status-a").inner_text()

            page.fill("#search-a", "Player 0599")
            page.wait_for_timeout(400)
            assert page.locator("#player-a option").count() == 2
            assert page.locator("#player-a").input_value() == ""
            assert page.locator("#player-a option").nth(1).inner_text() == "Player 0599 · APA record ID 599"
        finally:
            browser.close()


def _team_payload():
    def hist(team, sl):
        return [{"team_external_id": team, "team_name": team, "division_id": "d1", "session_name": "Spring 2026", "is_current": True, "skill_level": sl, "matches_won": sl, "matches_played": sl + 2}]

    return {
        "schema": "ultimate-coach-cockpit-v1",
        "probability_status": "NOT_CALIBRATED",
        "players": [
            {"id": 1, "external_id": "1", "name": "Ann Archer", "current_skill_level": 4, "current_matches_won": 4, "current_matches_played": 6, "team_history": hist("Sharks", 4), "career_stats": []},
            {"id": 2, "external_id": "2", "name": "Bea Baker", "current_skill_level": 5, "current_matches_won": 5, "current_matches_played": 7, "team_history": hist("Sharks", 5), "career_stats": []},
            {"id": 3, "external_id": "3", "name": "Cam Cole", "current_skill_level": 3, "current_matches_won": 3, "current_matches_played": 5, "team_history": hist("Falcons", 3), "career_stats": []},
            {"id": 4, "external_id": "4", "name": "Drew Diaz", "current_skill_level": 6, "current_matches_won": 6, "current_matches_played": 8, "team_history": hist("Falcons", 6), "career_stats": []},
            {"id": 5, "external_id": "5", "name": "Finn Frost", "current_skill_level": 4, "current_matches_won": 4, "current_matches_played": 6, "team_history": hist("Falcons", 4), "career_stats": []},
            {"id": 6, "external_id": "6", "name": "Evan Ellis", "current_skill_level": 4, "current_matches_won": 4, "current_matches_played": 6, "team_history": [], "career_stats": []},
        ],
        "evidence": [
            # Ann beats Cam twice -- direct evidence for the Cam matchup.
            {"player_id": 1, "opponent_id": 3, "match_id": 20, "match_external_id": "20", "match_date": "2026-01-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "W", "own_skill_level": 4, "opponent_skill_level": 3, "points_earned": 3, "nine_ball_points": None},
            {"player_id": 3, "opponent_id": 1, "match_id": 20, "match_external_id": "20", "match_date": "2026-01-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "L", "own_skill_level": 3, "opponent_skill_level": 4, "points_earned": None, "nine_ball_points": None},
            {"player_id": 1, "opponent_id": 3, "match_id": 21, "match_external_id": "21", "match_date": "2026-02-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "W", "own_skill_level": 4, "opponent_skill_level": 3, "points_earned": 3, "nine_ball_points": None},
            {"player_id": 3, "opponent_id": 1, "match_id": 21, "match_external_id": "21", "match_date": "2026-02-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "L", "own_skill_level": 3, "opponent_skill_level": 4, "points_earned": None, "nine_ball_points": None},
            # Bea and Drew never met directly, but both have faced Evan --
            # shared-opponent evidence for the Drew matchup.
            {"player_id": 2, "opponent_id": 6, "match_id": 22, "match_external_id": "22", "match_date": "2026-01-15T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "W", "own_skill_level": 5, "opponent_skill_level": 4, "points_earned": 3, "nine_ball_points": None},
            {"player_id": 6, "opponent_id": 2, "match_id": 22, "match_external_id": "22", "match_date": "2026-01-15T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "L", "own_skill_level": 4, "opponent_skill_level": 5, "points_earned": None, "nine_ball_points": None},
            {"player_id": 4, "opponent_id": 6, "match_id": 23, "match_external_id": "23", "match_date": "2026-01-20T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "L", "own_skill_level": 6, "opponent_skill_level": 4, "points_earned": None, "nine_ball_points": None},
            {"player_id": 6, "opponent_id": 4, "match_id": 23, "match_external_id": "23", "match_date": "2026-01-20T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "W", "own_skill_level": 4, "opponent_skill_level": 6, "points_earned": 3, "nine_ball_points": None},
        ],
        "counts": {"players": 6, "head_to_head_rows": 8},
    }


def test_team_vs_team_recommends_direct_then_shared_then_no_evidence(tmp_path: Path):
    path = tmp_path / "ultimate_coach_teams.html"
    path.write_text(render(_team_payload(), built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            page.select_option("#team-a", "Sharks|d1|Spring 2026")
            page.select_option("#team-b", "Falcons|d1|Spring 2026")

            rosters = page.locator("#team-rosters").inner_text()
            assert "Sharks" in rosters and "2 rostered" in rosters
            assert "Falcons" in rosters and "3 rostered" in rosters
            assert "Ann Archer" in rosters and "Bea Baker" in rosters
            assert "Cam Cole" in rosters and "Drew Diaz" in rosters and "Finn Frost" in rosters

            matchups = page.locator("#team-matchups").inner_text()
            # Cam: Ann has 2 direct wins, must be the strongest-evidence pick.
            assert ("Ann Archer (APA record ID 1) — ranks first on direct evidence: 2-0 direct (2 meetings) "
                    "vs Cam Cole (APA record ID 3)") in matchups
            # Drew: no direct history for anyone, but Bea shares Evan with Drew.
            # Indirect-only evidence is never given a "first" (GPT audit, PR #85).
            assert ("None of our roster has met Drew Diaz (APA record ID 4) directly. 1 player has shared-opponent "
                    "evidence only — not ranked against each other; compare ours vs theirs in the matrix.") in matchups
            # Finn: nobody on our roster has any direct or shared evidence at all.
            assert "No direct or shared-opponent evidence for any of our roster against Finn Frost (APA record ID 5)" in matchups

            assert "FORBIDDEN" in matchups

            # Opponent roster labels must show the real skill level from
            # their team_history row (the roster-member object's own
            # "skill_level" field), never "undefined" -- a real bug found
            # against real staging data where the opponent-row template
            # read a "current_skill_level" field roster-member objects
            # never carry (only "skill_level" does).
            assert "Cam Cole (SL 3)" in matchups
            assert "APA record ID 3" in matchups
            assert "Drew Diaz (SL 6)" in matchups
            assert "undefined" not in matchups
        finally:
            browser.close()


def test_team_dropdown_filters_same_named_scopes_by_selected_format(tmp_path: Path):
    payload = _team_payload()
    payload["players"].append(
        {
            "id": 7,
            "external_id": "7",
            "name": "Nina Nine",
            "current_skill_level": 4,
            "current_matches_won": 1,
            "current_matches_played": 2,
            "team_history": [
                {
                    "team_external_id": "Sharks-NINE",
                    "team_name": "Sharks",
                    "division_id": "d9",
                    "session_name": "Spring 2026",
                    "format": "NINE",
                    "is_current": True,
                    "skill_level": 4,
                    "matches_won": 1,
                    "matches_played": 2,
                }
            ],
            "career_stats": [],
        }
    )
    for player in payload["players"]:
        for hist in player.get("team_history") or []:
            hist.setdefault("format", "EIGHT")

    path = tmp_path / "ultimate_coach_team_format_filter.html"
    path.write_text(render(payload, built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            page.fill("#search-team-a", "Sharks")
            page.wait_for_timeout(400)
            options = page.locator("#team-a option").all_inner_texts()
            assert any("8-Ball" in text and "Div d1" in text for text in options)
            assert not any("9-Ball" in text or "Div d9" in text for text in options)

            page.select_option("#team-format", "NINE")
            page.wait_for_timeout(50)
            options = page.locator("#team-a option").all_inner_texts()
            assert any("9-Ball" in text and "Div d9" in text for text in options)
            assert not any("8-Ball" in text or "Div d1" in text for text in options)
        finally:
            browser.close()


def test_team_format_search_explains_zero_current_teams(tmp_path: Path):
    payload = _team_payload()
    for player in payload["players"]:
        for hist in player.get("team_history") or []:
            hist["format"] = "EIGHT"
    # No team in this fixture ever plays Masters Alt -- but a real recorded
    # meeting under that format must still exist so "Masters Alt" is a real
    # offered <option> (reachable for Player A/B scouting), exercising the
    # exact real-world shape: a format with real evidence but zero current
    # team rosters, not an absent/fabricated option.
    payload["evidence"].append(
        {"player_id": 1, "opponent_id": 3, "match_id": 99, "match_external_id": "99", "match_date": "2026-05-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "MASTERS ALT", "result": "W", "own_skill_level": 4, "opponent_skill_level": 3, "points_earned": 3, "nine_ball_points": None},
    )

    path = tmp_path / "ultimate_coach_team_format_empty_state.html"
    path.write_text(render(payload, built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            # Baseline under 8-Ball (the default): real teams exist, plain
            # count (2 current scopes: Sharks, Falcons -- Evan has no team).
            assert page.locator("#search-status-team-a").inner_text() == "2 matching teams."

            page.select_option("#team-format", "MASTERS ALT")
            # select_option itself raises if "MASTERS ALT" is not a real
            # <option> -- the regression guard for evidence staying
            # reachable even though no team plays this format.
            assert page.locator("#search-status-team-a").inner_text() == (
                "No currently-rostered team plays Masters Alt right now."
            )
            assert page.locator("#search-status-team-b").inner_text() == (
                "No currently-rostered team plays Masters Alt right now."
            )
            # Only the "Select a team..." placeholder -- never a stale list
            # left over from the previous format.
            assert page.locator("#team-a option").count() == 1

            # Must not be confused with a plain search-text miss: typing a
            # non-matching term under a format that DOES have teams stays
            # the ordinary zero-count message, not the format-availability one.
            page.select_option("#team-format", "EIGHT")
            page.fill("#search-team-a", "zzz-no-such-team")
            page.wait_for_timeout(400)
            assert page.locator("#search-status-team-a").inner_text() == "0 matching teams."
        finally:
            browser.close()


def test_team_search_only_filters_until_explicit_selection(tmp_path: Path):
    path = tmp_path / "ultimate_coach_teams_search.html"
    path.write_text(render(_team_payload(), built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            page.select_option("#team-a", "Sharks|d1|Spring 2026")
            page.select_option("#team-b", "Falcons|d1|Spring 2026")
            before = page.locator("#team-matchups").inner_text()

            # Typing narrows the team list only -- it must not clear the
            # rendered matchup or silently reselect a different team. The
            # current selection is preserved when it still matches the filter.
            page.fill("#search-team-b", "Fal")
            page.wait_for_timeout(400)
            assert page.locator("#team-b").input_value() == "Falcons|d1|Spring 2026"
            assert page.locator("#team-matchups").inner_text() == before

            # A filter that excludes the current selection clears the visible
            # dropdown value (same contract as Player A/B search) but still
            # must not itself trigger a matchup rebuild -- only an explicit
            # change event does that.
            page.fill("#search-team-b", "Sha")
            page.wait_for_timeout(400)
            assert page.locator("#team-b").input_value() == ""
            assert page.locator("#team-matchups").inner_text() == before

            # Switching teams must clear the stale matchup rather than
            # leaving the old opponent's recommendations on screen.
            page.fill("#search-team-b", "")
            page.wait_for_timeout(400)
            page.select_option("#team-b", "")
            assert "Choose both teams" in page.locator("#team-matchups").inner_text()
        finally:
            browser.close()


def test_same_named_teams_in_different_divisions_never_merge_rosters(tmp_path: Path):
    # Real UAT surfaced impossible 16/21-player "teams" because the browser
    # keyed TEAM_INDEX by display name alone. Same-named teams in different
    # divisions/sessions are distinct roster scopes and must stay separate.
    payload = _team_payload()
    payload["players"].append(
        {
            "id": 7,
            "external_id": "7",
            "name": "Gale Grant",
            "current_skill_level": None,
            "current_matches_won": None,
            "current_matches_played": None,
            "team_history": [
                {"team_external_id": "sharks-div-a", "team_name": "Sharks", "division_id": "da", "session_name": "Spring 2026", "is_current": True, "skill_level": 5, "matches_won": 2, "matches_played": 6},
                {"team_external_id": "sharks-div-b", "team_name": "Sharks", "division_id": "db", "session_name": "Spring 2026", "is_current": True, "skill_level": 5, "matches_won": 3, "matches_played": 6},
            ],
            "career_stats": [],
        }
    )

    path = tmp_path / "ultimate_coach_team_scopes.html"
    path.write_text(render(payload, built_at="test"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            page.select_option("#team-a", "Sharks|d1|Spring 2026")
            base_roster = page.locator("#team-rosters").inner_text()
            assert "2 rostered" in base_roster
            assert "Ann Archer" in base_roster and "Bea Baker" in base_roster
            assert "Gale Grant" not in base_roster

            page.select_option("#team-a", "sharks-div-a|da|Spring 2026")
            roster_a = page.locator("#team-rosters").inner_text()
            assert roster_a.count("Gale Grant") == 1
            assert "1 rostered" in roster_a
            assert "full-roster skill total 5" in roster_a
            assert "Gale Grant	7	5	" in roster_a  # this team's format-specific SL, no live-SL asterisk

            page.select_option("#team-a", "sharks-div-b|db|Spring 2026")
            roster_b = page.locator("#team-rosters").inner_text()
            assert roster_b.count("Gale Grant") == 1
            assert "1 rostered" in roster_b
        finally:
            browser.close()


def _team_match(**overrides):
    """One analytics.ultimate_coach_data_contract team_matches row."""
    row = {
        "match_id": 100, "match_external_id": "100", "match_date": "2026-10-11T11:00:00-06:00",
        "format": "EIGHT", "format_raw": "8-Ball Open", "session_name": "Spring 2026", "week": 7,
        "status": "UNPLAYED", "location": None, "home_team_id": "Sharks", "home_team_name": "Sharks",
        "away_team_id": "Falcons", "away_team_name": "Falcons", "home_score": None,
        "away_score": None, "is_bye": False, "is_scored": False, "is_finalized": False,
    }
    row.update(overrides)
    return row


def _match_day_page(tmp_path: Path, name: str, team_matches, *, viewer=None, payload=None, card=None):
    payload = payload or _team_payload()
    payload["match_day"] = build_match_day_section(team_matches, payload["players"])
    path = tmp_path / name
    path.write_text(
        render(payload, built_at="test", viewer_member_external_id=viewer, viewer_card_number=card),
        encoding="utf-8",
    )
    return path


def _open(browser, path: Path, **context_kwargs):
    page = browser.new_context(**context_kwargs).new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(path.as_uri())
    page.wait_for_load_state("load")
    return page, errors


def test_match_day_without_configured_viewer_offers_explicit_identity_choice(tmp_path: Path):
    path = _match_day_page(tmp_path, "md_unconfigured.html", [_team_match()])
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _open(browser, path)
            assert page.locator("#md-team").is_disabled()
            assert "No viewer identity configured" in page.locator("#md-status").inner_text()
            assert "Nothing is guessed" in page.locator("#md-viewer-status").inner_text()
            assert page.locator("#md-viewer").input_value() == ""

            page.select_option("#md-viewer", "1")
            assert not page.locator("#md-team").is_disabled()
            assert "APA record ID 1" in page.locator("#md-viewer-status").inner_text()
            assert "Sharks" in page.locator("#md-team").inner_text()
            assert errors == []
        finally:
            browser.close()


def test_match_day_configured_viewer_with_no_current_team_is_disclosed(tmp_path: Path):
    payload = _team_payload()
    payload["players"].append(
        {"id": 8, "external_id": "9999", "name": "Teamless Viewer", "current_skill_level": 4,
         "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": []}
    )
    path = _match_day_page(tmp_path, "md_teamless.html", [], viewer="9999", payload=payload)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            assert page.locator("#md-team").is_disabled()
            assert "No current team found for Teamless Viewer" in page.locator("#md-status").inner_text()
        finally:
            browser.close()


def test_match_day_unresolved_configured_viewer_is_disclosed_not_guessed(tmp_path: Path):
    path = _match_day_page(tmp_path, "md_unresolved.html", [_team_match()], viewer="424242")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            assert page.locator("#md-viewer").input_value() == ""
            assert "424242" in page.locator("#md-viewer-status").inner_text()
            assert "not found" in page.locator("#md-status").inner_text()
        finally:
            browser.close()


def test_match_day_finds_fixture_and_applies_it_to_team_vs_team(tmp_path: Path):
    # Ann Archer (external_id "1") is on Sharks -- see _team_payload().
    path = _match_day_page(tmp_path, "md_find.html", [_team_match()], viewer="1", card="80000001")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _open(browser, path)
            assert page.locator("#md-team option").count() == 1
            assert "Sharks" in page.locator("#md-team").inner_text()
            viewer_status = page.locator("#md-viewer-status").inner_text()
            assert "APA record ID 1" in viewer_status
            assert "card #80000001" in viewer_status and "not used as identity" in viewer_status

            # The team's real scheduled date is offered as a quick pick.
            assert page.locator("#md-team-dates button[data-date='2026-10-11']").count() == 1
            page.fill("#md-date", "2026-10-11")
            assert "1 scheduled match" in page.locator("#md-status").inner_text()
            fixture_text = page.locator("#md-fixtures").inner_text()
            assert "Falcons" in fixture_text
            assert "8-Ball Open" in fixture_text
            assert "Home" in fixture_text
            assert "Sun Oct 11, 2026 · 11:00 AM MDT" in fixture_text
            assert "2026-10-11T11:00:00-06:00" in fixture_text  # raw source kept
            assert "No data" in fixture_text  # venue is unrecorded

            page.click("#md-compare-0")
            page.wait_for_timeout(100)
            assert page.locator("#team-a").input_value() == "Sharks|d1|Spring 2026"
            assert page.locator("#team-b").input_value() == "Falcons|d1|Spring 2026"
            assert page.locator("#team-format").input_value() == "EIGHT"
            assert "Loaded from Match Day" in page.locator("#search-status-team-b").inner_text()
            rosters = page.locator("#team-rosters").inner_text()
            assert "Ann Archer" in rosters and "Cam Cole" in rosters
            assert errors == []
        finally:
            browser.close()


def test_match_day_uses_display_timezone_for_a_utc_midnight_crossing(tmp_path: Path):
    # Real shape (match 51545390): 01:00Z on Aug 30 is 7:00 PM Saturday Aug 29
    # in America/Denver -- it must be found on the 29th, never the 30th.
    path = _match_day_page(
        tmp_path, "md_utc_crossing.html",
        [_team_match(match_date="2026-08-30T01:00:00Z")], viewer="1",
    )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            page.fill("#md-date", "2026-08-30")
            assert "No scheduled match found" in page.locator("#md-status").inner_text()
            page.fill("#md-date", "2026-08-29")
            assert "1 scheduled match" in page.locator("#md-status").inner_text()
            text = page.locator("#md-fixtures").inner_text()
            assert "Sat Aug 29, 2026 · 7:00 PM MDT" in text
            assert "2026-08-30T01:00:00Z" in text
            assert "America/Denver" in page.locator("#md-tz").inner_text()
        finally:
            browser.close()


def test_match_day_never_auto_applies_when_multiple_fixtures_exist(tmp_path: Path):
    path = _match_day_page(tmp_path, "md_multi.html", [
        _team_match(match_id=101, match_external_id="101", match_date="2026-10-11T19:00:00-06:00"),
        _team_match(match_id=102, match_external_id="102", match_date="2026-10-11T11:00:00-06:00"),
    ], viewer="1")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            page.fill("#md-date", "2026-10-11")
            assert "2 scheduled matches" in page.locator("#md-status").inner_text()
            assert "none is applied automatically" in page.locator("#md-status").inner_text()
            assert page.locator("[id^='md-compare-']").count() == 2
            whens = page.locator(".fixture-when").all_inner_texts()
            assert "11:00 AM" in whens[0] and "7:00 PM" in whens[1]  # kickoff order
            assert page.locator("#team-a").input_value() == ""
            assert page.locator("#team-b").input_value() == ""
        finally:
            browser.close()


def test_match_day_bye_says_no_opponent_and_offers_no_roster_lookup(tmp_path: Path):
    # Real bye rows carry placeholder names ("BYE") on a real team id; only
    # is_bye is trustworthy, and the placeholder must never read as a team.
    path = _match_day_page(tmp_path, "md_bye.html", [
        _team_match(is_bye=True, away_team_id="13082714", away_team_name="BYE"),
    ], viewer="1")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            page.fill("#md-date", "2026-10-11")
            text = page.locator("#md-fixtures").inner_text()
            assert "Bye — no opponent" in text
            assert "Bye week" in text
            assert "vs BYE" not in text and "at BYE" not in text
            assert page.locator("[id^='md-compare-']").count() == 0
        finally:
            browser.close()


def test_match_day_opponent_without_current_roster_or_ambiguous_scope_is_disclosed(tmp_path: Path):
    payload = _team_payload()
    # Two current roster scopes share opponent id "Owls" + session -> ambiguous.
    for pid, div in ((9, "d1"), (10, "d2")):
        payload["players"].append({
            "id": pid, "external_id": str(pid), "name": f"Owl {pid}", "current_skill_level": 4,
            "current_matches_won": None, "current_matches_played": None, "career_stats": [],
            "team_history": [{"team_external_id": "Owls", "team_name": "Owls", "division_id": div,
                              "session_name": "Spring 2026", "is_current": True, "skill_level": 4,
                              "matches_won": 1, "matches_played": 2}],
        })
    path = _match_day_page(tmp_path, "md_opp_states.html", [
        _team_match(match_id=1, match_external_id="1", away_team_id="Ghosts", away_team_name="Ghosts"),
        _team_match(match_id=2, match_external_id="2", away_team_id="Owls", away_team_name="Owls",
                    match_date="2026-10-11T19:00:00-06:00"),
    ], viewer="1", payload=payload)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            page.fill("#md-date", "2026-10-11")
            text = page.locator("#md-fixtures").inner_text()
            assert "No current roster is captured for Ghosts" in text
            assert "Opponent roster is ambiguous: 2 current roster scopes" in text
            assert "None is picked automatically" in text
            assert page.locator("[id^='md-compare-']").count() == 0
        finally:
            browser.close()


def test_match_day_no_fixture_on_chosen_date_is_disclosed_clearly(tmp_path: Path):
    path = _match_day_page(tmp_path, "md_empty.html", [_team_match()], viewer="1")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            page.fill("#md-date", "2026-10-18")
            assert "No scheduled match found for Sharks" in page.locator("#md-status").inner_text()
            assert page.locator("#md-fixtures").inner_text() == ""
        finally:
            browser.close()


def test_match_day_missing_and_unparseable_dates_are_counted_not_hidden(tmp_path: Path):
    path = _match_day_page(tmp_path, "md_undated.html", [
        _team_match(match_id=1, match_external_id="1", match_date="not-a-real-timestamp"),
        _team_match(match_id=2, match_external_id="2", match_date=None),
    ], viewer="1")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            assert "2 fixtures have a missing or unparseable date" in page.locator("#md-status").inner_text()
            page.fill("#md-date", "2026-10-11")
            assert "No scheduled match found" in page.locator("#md-status").inner_text()
        finally:
            browser.close()


def test_match_day_format_filter_defaults_to_all_eight_and_nine_variants(tmp_path: Path):
    path = _match_day_page(tmp_path, "md_format.html", [
        _team_match(match_id=103, match_external_id="103", format="EIGHT", format_raw="8-Ball Doubles"),
        _team_match(match_id=104, match_external_id="104", format="MASTERS ALT", format_raw="Masters Alt",
                    match_date="2026-10-11T19:00:00-06:00"),
    ], viewer="1")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            assert page.locator("#md-format").input_value() == ""
            page.fill("#md-date", "2026-10-11")
            assert "1 scheduled match" in page.locator("#md-status").inner_text()
            assert "8-Ball Doubles" in page.locator("#md-fixtures").inner_text()

            page.select_option("#md-format", "Masters Alt")
            assert "1 scheduled match" in page.locator("#md-status").inner_text()
            assert "Masters Alt" in page.locator("#md-fixtures").inner_text()

            page.select_option("#md-format", "*")
            assert "2 scheduled matches" in page.locator("#md-status").inner_text()
        finally:
            browser.close()


def test_match_day_lists_every_current_scope_separately_and_all_teams_view(tmp_path: Path):
    payload = _team_payload()
    # Ann is also on a second division of the same team name.
    payload["players"][0]["team_history"].append(
        {"team_external_id": "Sharks9", "team_name": "Sharks", "division_id": "d9", "session_name": "Spring 2026",
         "is_current": True, "skill_level": 4, "matches_won": 1, "matches_played": 2}
    )
    path = _match_day_page(tmp_path, "md_scopes.html", [
        _team_match(match_id=1, match_external_id="1"),
        _team_match(match_id=2, match_external_id="2", home_team_id="Sharks9", match_date="2026-10-11T19:00:00-06:00"),
    ], viewer="1", payload=payload)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            options = page.locator("#md-team option").all_inner_texts()
            assert options[0] == "All my current teams (2)"
            assert any("Div d1" in o for o in options) and any("Div d9" in o for o in options)
            assert "2 current team scopes" in page.locator("#md-viewer-status").inner_text()
            # Default team = the team of the next fixture (earliest kickoff), same rule as Excel.
            assert page.input_value("#md-team") == "Sharks|d1|Spring 2026"
            page.select_option("#md-team", "__all__")
            page.fill("#md-date", "2026-10-11")
            assert "2 scheduled matches" in page.locator("#md-status").inner_text()
            assert "none is applied automatically" in page.locator("#md-status").inner_text()
            page.select_option("#md-team", "Sharks9|d9|Spring 2026")
            assert "1 scheduled match" in page.locator("#md-status").inner_text()
        finally:
            browser.close()


def test_match_day_identity_selector_distinguishes_duplicate_names_and_remembers_choice(tmp_path: Path):
    payload = _team_payload()
    payload["players"].append({
        "id": 11, "external_id": "777", "name": "Ann Archer", "current_skill_level": 3,
        "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": [],
    })
    path = _match_day_page(tmp_path, "md_dupes.html", [_team_match()], payload=payload)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(path.as_uri())
            page.fill("#md-viewer-search", "ann archer")
            page.wait_for_timeout(400)
            labels = page.locator("#md-viewer option").all_inner_texts()[1:]
            assert len(labels) == 2
            assert all("2 players share this name" in label for label in labels)
            assert any("APA record ID 1 · Sharks" in label for label in labels)
            assert any("APA record ID 777 · no current team" in label for label in labels)

            page.select_option("#md-viewer", "1")
            page.reload()
            page.wait_for_load_state("load")
            assert page.locator("#md-viewer").input_value() == "1"
            assert "saved choice" in page.locator("#md-viewer-status").inner_text()
        finally:
            browser.close()


def test_match_day_page_has_no_horizontal_scroll_on_a_phone(tmp_path: Path):
    path = _match_day_page(tmp_path, "md_phone.html", [_team_match()], viewer="1")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _open(browser, path, viewport={"width": 375, "height": 812})
            page.fill("#md-date", "2026-10-11")
            page.click("#md-compare-0")
            page.wait_for_timeout(100)
            overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            assert overflow <= 0
            assert errors == []
        finally:
            browser.close()


def test_player_selectors_show_record_ids_and_keep_duplicate_names_distinct(tmp_path: Path):
    payload = _payload()
    payload["players"].append({"id": 5, "external_id": "5005", "name": "Alpha Adams", "current_skill_level": 6,
                               "current_matches_won": None, "current_matches_played": None, "team_history": [],
                               "career_stats": []})
    payload["counts"]["players"] = 5
    path = tmp_path / "uc_names.html"
    path.write_text(render(payload, built_at="test"), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            labels = page.locator("#player-a option").all_inner_texts()[1:]
            assert "Alpha Adams · APA record ID 1" in labels
            assert "Alpha Adams · APA record ID 5005" in labels
            # Searching by record ID finds exactly that identity.
            page.fill("#search-a", "5005")
            page.wait_for_timeout(400)
            assert page.locator("#player-a option").all_inner_texts()[1:] == ["Alpha Adams · APA record ID 5005"]
            page.select_option("#player-a", "5")
            profile = page.locator("#profile-a").inner_text()
            assert "Alpha Adams" in profile and "APA record ID 5005" in profile
            # The other Alpha (record 1) keeps her own evidence -- selection is by id, never by name.
            page.fill("#search-a", "")
            page.wait_for_timeout(400)
            page.select_option("#player-a", "1")
            assert "APA record ID 1" in page.locator("#profile-a").inner_text()
            assert "Bravo Brown · APA record ID 2 · 1 meeting" in page.locator("#player-b").inner_text()
            page.select_option("#player-b", "2")
            assert "Charlie Clark · APA record ID 3" in page.locator("#shared").inner_text()
        finally:
            browser.close()


def test_team_rosters_are_labeled_and_list_record_ids(tmp_path: Path):
    payload = _team_payload()
    payload["players"].append({"id": 7, "external_id": "7007", "name": "Nia Null", "current_skill_level": None,
                               "current_matches_won": None, "current_matches_played": None, "career_stats": [],
                               "team_history": [{"team_external_id": "Falcons", "team_name": "Falcons", "division_id": "d1",
                                                 "session_name": "Spring 2026", "is_current": True, "skill_level": None,
                                                 "matches_won": None, "matches_played": None}]})
    path = tmp_path / "uc_rosters.html"
    path.write_text(render(payload, built_at="test"), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.select_option("#team-a", "Sharks|d1|Spring 2026")
            page.select_option("#team-b", "Falcons|d1|Spring 2026")
            cards = page.locator("#team-rosters > .card")
            ours, theirs = cards.nth(0).inner_text(), cards.nth(1).inner_text()
            assert ours.startswith("OUR TEAM") and "Sharks" in ours
            assert theirs.startswith("OPPONENT") and "Falcons" in theirs
            headers = cards.nth(1).locator("th").all_inner_texts()
            assert [h.upper() for h in headers][:5] == ["#", "PLAYER", "APA RECORD ID", "SL (THIS FORMAT)", "TEAM W-L"]
            nia = [r for r in cards.nth(1).locator("tbody tr").all_inner_texts() if "Nia Null" in r][0]
            assert "7007" in nia and nia.count("—") == 2  # missing SL and W-L are disclosed, never 0
            assert "Drew Diaz\t4" in theirs  # name next to its record ID
            head = page.locator("#matchup-head").inner_text()
            assert "Teams chosen manually" in head
            notes = page.locator("#matchup-notes").inner_text()
            assert "— = not captured in the source data." in notes
            assert "never counted as 0" in notes and "NOT CALIBRATED" in notes
            assert "Players are identified by APA record ID" in notes
        finally:
            browser.close()


def test_focused_printable_matchup_shows_fixture_and_both_labeled_rosters_only(tmp_path: Path):
    path = _match_day_page(tmp_path, "md_print.html", [_team_match()], viewer="1")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _open(browser, path)
            page.fill("#md-date", "2026-10-11")
            page.click("#md-compare-0")
            page.wait_for_timeout(100)
            head = page.locator("#matchup-head").inner_text()
            assert "Sun Oct 11, 2026 · 11:00 AM MDT" in head and "America/Denver" in head
            assert "OUR TEAM" in head.upper() and "OPPONENT" in head.upper()
            assert "Sharks · Spring 2026 · Div d1" in head and "Falcons · Spring 2026 · Div d1" in head
            assert "Home" in head and "Away" in head
            assert "2026-10-11T11:00:00-06:00" in head and "No data" in head  # source time + missing venue
            ours = page.locator("#team-rosters > .card").nth(0).inner_text()
            assert "Home" in ours and "Ann Archer" in ours and "\t1\t" in ours

            page.evaluate("window.print = () => { window.__printed = true; }")
            page.click("#print-matchup")
            assert page.evaluate("window.__printed === true")
            assert page.evaluate("document.body.classList.contains('print-matchup')")
            page.emulate_media(media="print")
            visible = lambda sel: page.locator(sel).first.is_visible()
            assert visible("#matchup-head") and visible("#team-rosters") and visible("#matchup-notes")
            assert visible("#team-comparison") and visible("#team-matchups")  # comparison + ranking are printed
            # Captain Packet: page 1 = fixture, both rosters, best sends, top risks; detail starts on page 2.
            for shown in ("#wr-opportunities", "#wr-risks", "#wr-matrix", "#lineup-lab", "#scouting-cards", "#wr-meetings"):
                assert visible(shown), shown
            assert page.evaluate("getComputedStyle(document.getElementById('wr-matrix')).breakBefore") == "page"
            # Planning inputs print as plain text, never as form controls.
            assert not page.locator("#lineup-lab select.plan").first.is_visible()
            assert page.locator("#lineup-lab .print-only").first.is_visible()
            for hidden in ("#match-day-card", "#player-section", "#trust-section", "header.hero",
                           "#team-section", "#print-matchup"):
                assert not visible(hidden), hidden
            # Leaving print mode restores the normal page.
            page.evaluate("window.dispatchEvent(new Event('afterprint'))")
            assert not page.evaluate("document.body.classList.contains('print-matchup')")
            assert errors == []
        finally:
            browser.close()


def test_changing_teams_by_hand_drops_the_fixture_context(tmp_path: Path):
    path = _match_day_page(tmp_path, "md_ctx.html", [_team_match()], viewer="1")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            page.fill("#md-date", "2026-10-11")
            page.click("#md-compare-0")
            assert "11:00 AM MDT" in page.locator("#matchup-head").inner_text()
            page.select_option("#team-format", "NINE")  # same teams: context kept
            assert "11:00 AM MDT" in page.locator("#matchup-head").inner_text()
            page.fill("#search-team-b", "")
            page.wait_for_timeout(400)
            page.select_option("#team-b", "")
            head = page.locator("#matchup-head").inner_text()
            assert "11:00 AM MDT" not in head and "Teams chosen manually" in head
        finally:
            browser.close()



def test_focused_print_of_full_rosters_keeps_matchup_on_page_one_and_ranking_compact(tmp_path: Path):
    payload = _team_payload()
    # Real rosters top out at 9 players: Sharks 2 + 7 = 9, Falcons 3 + 5 = 8.
    for team, extra in (("Sharks", 7), ("Falcons", 5)):
        for n in range(extra):
            pid = 100 + len(payload["players"])
            payload["players"].append({
                "id": pid, "external_id": str(3000000 + pid), "name": f"Longname Player-{team}-{n} Hyphenated",
                "current_skill_level": (n % 7) + 1, "current_matches_won": 3, "current_matches_played": 5,
                "career_stats": [],
                "team_history": [{"team_external_id": team, "team_name": team, "division_id": "d1",
                                  "session_name": "Spring 2026", "is_current": True, "skill_level": (n % 7) + 1,
                                  "matches_won": 3, "matches_played": 5}],
            })
    path = _match_day_page(tmp_path, "md_print_pages.html", [_team_match()], viewer="1", payload=payload)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, _ = _open(browser, path)
            page.fill("#md-date", "2026-10-11")
            page.click("#md-compare-0")
            page.evaluate("document.body.classList.add('print-matchup')")
            page.emulate_media(media="print")
            # Landscape Letter less 10 mm margins at 96 dpi: ~980 x 740 CSS px. Page 1 must hold the
            # fixture header, both 9-player rosters, best sends and top risks.
            page.set_viewport_size({"width": 980, "height": 740})
            page_one = page.evaluate("""() => {
                const top = document.getElementById('matchup-head').getBoundingClientRect().top;
                return document.getElementById('wr-risks').getBoundingClientRect().bottom - top; }""")
            assert page_one <= 740, page_one
            pdf = page.pdf(prefer_css_page_size=True, print_background=True)
            pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf))
            assert 2 <= pages <= 9, pages  # then matrix, Lineup Lab, comparison, ranking, scouting cards, meetings
        finally:
            browser.close()


def _ranking_rows(page, block_index):
    rows = page.locator(f"#rank-block-{block_index} tbody tr").all_inner_texts()
    return [r.split("\t") for r in rows]


def test_match_night_ranks_our_players_against_each_opponent_with_evidence(tmp_path: Path):
    path = tmp_path / "uc_rank.html"
    path.write_text(render(_team_payload(), built_at="test"), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.select_option("#team-a", "Sharks|d1|Spring 2026")
            page.select_option("#team-b", "Falcons|d1|Spring 2026")
            heads = page.locator(".rank-block h3").all_inner_texts()
            # Opponents in roster order (SL high to low): Drew 6, Finn 4, Cam 3.
            assert heads == [
                "vs Drew Diaz (APA record ID 4) · SL 6 · 1 recorded game in 8-Ball",
                "vs Finn Frost (APA record ID 5) · SL 4 · 0 recorded games in 8-Ball",
                "vs Cam Cole (APA record ID 3) · SL 3 · 2 recorded games in 8-Ball",
            ]
            assert _ranking_rows(page, 0) == [
                ["≈", "Bea Baker (APA record ID 2)", "5", "No verified direct meetings in this snapshot",
                 "1 shared opponent · ours 1-0 (1 game) · theirs 0-1 (1 game)",
                 "Shared-opponent results only (no direct meetings) — not ordered against other indirect candidates; "
                 "compare ours vs theirs"],
                ["—", "Ann Archer (APA record ID 1)", "4", "No verified direct meetings in this snapshot", "No shared opponents",
                 "No direct or shared-opponent evidence"],
            ]
            notes = page.locator(".rank-block p.muted").all_inner_texts()
            assert notes[0] == "1 of 2 of our players have direct or shared-opponent evidence against this opponent."
            assert notes[1] == "No recorded 8-Ball games for this opponent in the verified evidence — nothing to rank on."
            assert _ranking_rows(page, 2)[0] == ["1", "Ann Archer (APA record ID 1)", "4", "2-0 (2 meetings)",
                                                "No shared opponents", "Direct record"]
            text = page.locator("#team-matchups").inner_text()
            assert "not a win probability" in text and "not a guaranteed or optimal lineup" in text
            assert "ranks ahead of shared-opponent results even when it is small or a loss" in text
            assert "%" not in text  # records and sample counts only -- no odds-like percentages
            comparison = page.locator("#team-comparison").inner_text()
            assert "Players rostered\t2\t3" in comparison
            assert "Skill total (captured SLs only)\t9\t13" in comparison
            assert "Recorded 8-Ball games (all opponents)\t3\t3" in comparison
            assert "Players with no recorded 8-Ball games\t0\t1" in comparison
            assert "2 games · our players 2-0" in comparison
            assert "1 of 3" in comparison
            assert "1 direct · 1 shared-opponent only · 4 no evidence (6 total)" in comparison
        finally:
            browser.close()


def _tie_payload():
    payload = _team_payload()
    # Gia joins Sharks with the same 2-0 direct record against Cam as Ann.
    payload["players"].append({"id": 9, "external_id": "9", "name": "Gia Green", "current_skill_level": 4,
                               "current_matches_won": 1, "current_matches_played": 2, "career_stats": [],
                               "team_history": [{"team_external_id": "Sharks", "team_name": "Sharks", "division_id": "d1",
                                                 "session_name": "Spring 2026", "is_current": True, "skill_level": 4,
                                                 "matches_won": 1, "matches_played": 2}]})
    for match_id in (30, 31):
        payload["evidence"] += [
            {"player_id": 9, "opponent_id": 3, "match_id": match_id, "match_external_id": str(match_id),
             "match_date": "2026-03-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "W",
             "own_skill_level": 4, "opponent_skill_level": 3, "points_earned": 3, "nine_ball_points": None},
            {"player_id": 3, "opponent_id": 9, "match_id": match_id, "match_external_id": str(match_id),
             "match_date": "2026-03-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "L",
             "own_skill_level": 3, "opponent_skill_level": 4, "points_earned": None, "nine_ball_points": None},
        ]
    return payload


def test_ties_are_marked_and_explained_never_broken_silently(tmp_path: Path):
    path = tmp_path / "uc_tie.html"
    path.write_text(render(_tie_payload(), built_at="test"), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.select_option("#team-a", "Sharks|d1|Spring 2026")
            page.select_option("#team-b", "Falcons|d1|Spring 2026")
            cam = _ranking_rows(page, 2)
            assert [r[0] for r in cam[:2]] == ["1=", "1="]
            assert cam[0][5] == ("Direct record · Tied with Gia Green (APA record ID 9) — same evidence; "
                                 "the ranking can't separate them")
            assert cam[1][5] == ("Direct record · Tied with Ann Archer (APA record ID 1) — same evidence; "
                                 "the ranking can't separate them")
            assert cam[2][0] == "—"  # Bea: no evidence, unranked
            glance = page.locator("#team-matchups table").first.inner_text()
            assert ("Insufficient evidence to distinguish Ann Archer (APA record ID 1) / Gia Green (APA record ID 9) "
                    "against Cam Cole (APA record ID 3) — identical direct records (2-0, 2 meetings each).") in glance
        finally:
            browser.close()


def test_html_ranking_matches_the_shared_python_module_exactly(tmp_path: Path):
    """The HTML computes the ranking live in JavaScript; the Excel workbook
    uses analytics.ultimate_coach_matchup_evidence. Same rosters -> same
    order, rank labels, texts and comparison."""
    from analytics.ultimate_coach_excel_payload import build_player_vs_player_pairs, build_team_rosters
    from analytics.ultimate_coach_matchup_evidence import build_pair_index, matchup_evidence, members_by_scope

    payload = _tie_payload()
    path = tmp_path / "uc_cross.html"
    path.write_text(render(payload, built_at="test"), encoding="utf-8")
    members = members_by_scope(build_team_rosters(payload), payload["players"])
    expected = matchup_evidence(members["Sharks|d1|Spring 2026"], members["Falcons|d1|Spring 2026"],
                                build_pair_index(build_player_vs_player_pairs(payload)), "EIGHT")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(path.as_uri())
            page.select_option("#team-a", "Sharks|d1|Spring 2026")
            page.select_option("#team-b", "Falcons|d1|Spring 2026")
            for i, block in enumerate(expected["opponents"]):
                assert page.locator(f"#rank-block-{i} h3").inner_text().startswith("vs " + block["opponent_label"])
                assert page.locator(f"#rank-block-{i} p.muted").inner_text() == block["note"]
                got = [(r[0], r[1], r[3], r[4], r[5]) for r in _ranking_rows(page, i)]
                want = [(r["rank"], r["player"], r["direct_text"], r["shared_text"], r["basis"]) for r in block["rows"]]
                assert got == want
            comparison = page.locator("#team-comparison").inner_text()
            c = expected["comparison"]
            for value in (c["direct_meetings"], c["opponents_met"], c["pairings"]):
                assert value in comparison
            for key in ("rostered", "captured_sl", "sl_total", "games", "no_games"):
                assert f"\t{c['ours'][key]}\t{c['theirs'][key]}" in comparison
        finally:
            browser.close()

