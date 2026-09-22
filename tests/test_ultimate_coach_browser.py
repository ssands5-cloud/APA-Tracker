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
            assert page.locator("#player-b option").count() == 4
            assert "2 recorded opponents for Alpha Adams in 8-Ball" in page.locator("#search-status-b").inner_text()
            assert "Delta Dunn" not in page.locator("#player-b").inner_text()

            page.select_option("#player-b", "2")
            assert "1-0" in page.locator("#direct").inner_text()
            assert "Charlie Clark" in page.locator("#shared").inner_text()
            assert "1 recorded direct meeting" in page.locator("#summary").inner_text()
            assert "1 recorded opponent" in page.locator("#summary").inner_text()
            assert "NOT CALIBRATED" in page.locator("#status").inner_text()

            page.fill("#search-b", "Charlie")
            page.wait_for_timeout(250)
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
            assert page.locator("#player-b option").count() == 3
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
