"""Real-browser interaction test for the offline Ultimate Coach cockpit."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

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


def test_browser_payload_compacts_and_preindexes_evidence():
    payload = _payload()
    compact = _browser_payload(payload)

    assert "evidence" not in compact
    assert compact["browser_payload_schema"] == "ultimate-coach-browser-compact-v1"
    assert compact["counts"] == payload["counts"]

    fields = compact["evidence_row_fields"]
    opponent_i = fields.index("opponent_id")
    result_i = fields.index("result")

    player_one = compact["evidence_index"]["1|EIGHT"]
    assert len(player_one) == 2
    assert player_one[0][opponent_i] == 2
    assert player_one[0][result_i] == "W"



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
            assert page.locator("#player-a option").nth(1).inner_text() == "Player 0599"
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
            assert "Ann Archer — strongest evidence-backed option: 2-0 direct (2 meetings)" in matchups
            # Drew: no direct history for anyone, but Bea shares Evan with Drew.
            assert "Bea Baker — no direct history vs Drew Diaz; best-supported by 1 shared-opponent result (1-0 vs those shared opponents)" in matchups
            # Finn: nobody on our roster has any direct or shared evidence at all.
            assert "No direct or shared-opponent evidence for any of our roster against Finn Frost" in matchups

            assert "FORBIDDEN" in matchups

            # Opponent roster labels must show the real skill level from
            # their team_history row (the roster-member object's own
            # "skill_level" field), never "undefined" -- a real bug found
            # against real staging data where the opponent-row template
            # read a "current_skill_level" field roster-member objects
            # never carry (only "skill_level" does).
            assert "Cam Cole (SL 3)" in matchups
            assert "Drew Diaz (SL 6)" in matchups
            assert "undefined" not in matchups
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
            assert "5*" in roster_a

            page.select_option("#team-a", "sharks-div-b|db|Spring 2026")
            roster_b = page.locator("#team-rosters").inner_text()
            assert roster_b.count("Gale Grant") == 1
            assert "1 rostered" in roster_b
        finally:
            browser.close()
