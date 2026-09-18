"""Real-browser interaction test for the offline Ultimate Coach cockpit."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from ui.ultimate_coach import render


def _payload():
    return {
        "schema": "ultimate-coach-cockpit-v1",
        "probability_status": "NOT_CALIBRATED",
        "players": [
            {"id": 1, "external_id": "1", "name": "Alpha Adams", "current_skill_level": 4, "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": []},
            {"id": 2, "external_id": "2", "name": "Bravo Brown", "current_skill_level": 5, "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": []},
            {"id": 3, "external_id": "3", "name": "Charlie Clark", "current_skill_level": 4, "current_matches_won": None, "current_matches_played": None, "team_history": [], "career_stats": []},
        ],
        "evidence": [
            {"player_id": 1, "opponent_id": 2, "match_id": 10, "match_external_id": "10", "match_date": "2026-01-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "W", "own_skill_level": 4, "opponent_skill_level": 5, "points_earned": 3, "nine_ball_points": None},
            {"player_id": 1, "opponent_id": 3, "match_id": 11, "match_external_id": "11", "match_date": "2026-02-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "W", "own_skill_level": 4, "opponent_skill_level": 4, "points_earned": 3, "nine_ball_points": None},
            {"player_id": 2, "opponent_id": 3, "match_id": 12, "match_external_id": "12", "match_date": "2026-03-01T19:00:00-07:00", "session_name": "Spring 2026", "format": "EIGHT", "result": "L", "own_skill_level": 5, "opponent_skill_level": 4, "points_earned": 0, "nine_ball_points": None},
        ],
        "counts": {"players": 3, "head_to_head_rows": 3},
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
            page.select_option("#player-b", "2")
            assert "1-0" in page.locator("#direct").inner_text()
            assert "Charlie Clark" in page.locator("#shared").inner_text()
            assert "NOT CALIBRATED" in page.locator("#status").inner_text()

            page.fill("#search-b", "Charlie")
            assert page.locator("#player-b option").count() == 1
            assert page.locator("#player-b option").first.inner_text() == "Charlie Clark"

            page.select_option("#format", "NINE")
            assert "0-0" in page.locator("#direct").inner_text()
            assert "No recorded shared opponents" in page.locator("#shared").inner_text()
        finally:
            browser.close()
