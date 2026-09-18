"""Render/browser tests for the offline Ultimate Coach Scout."""

from __future__ import annotations

import json

import pytest

from ui.ultimate_coach_scout import render_ultimate_coach_scout

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright


def _player(pid, name, *, default=True, direct=None):
    direct = direct or {}
    base_format = {
        "wins": 2,
        "losses": 1,
        "games": 3,
        "win_rate": 2 / 3,
        "unique_opponents": len(direct),
        "avg_own_skill_level": 4,
        "avg_opponent_skill_level": 5,
        "first_match_date": "2026-01-01T19:00:00-07:00",
        "last_match_date": "2026-02-01T19:00:00-07:00",
        "recent5_wins": 2,
        "recent5_losses": 1,
        "recent5_games": 3,
        "recent5_win_rate": 2 / 3,
        "display_skill_level": 4,
        "display_skill_level_status": "current_roster",
        "latest_observed_skill_level": 4,
        "latest_observed_skill_date": "2026-02-01T19:00:00-07:00",
        "opponents": direct,
    }
    return {
        "player_id": pid,
        "external_id": f"EXT-{pid}",
        "name": name,
        "identity_status": "canonical_team_history" if default else "scoresheet_only_or_unscoped",
        "selectable_by_default": default,
        "formats": {"EIGHT": dict(base_format), "NINE": dict(base_format, opponents={})},
        "career_stats": [],
        "team_history": [],
    }


def _payload():
    shared_for_a = {
        "3": {
            "opponent_id": 3,
            "opponent_external_id": "EXT-3",
            "opponent_name": "Shared",
            "wins": 2,
            "losses": 0,
            "games": 2,
            "win_rate": 1.0,
            "avg_own_skill_level": 4,
            "avg_opponent_skill_level": 4,
            "first_match_date": "2026-01-01T19:00:00-07:00",
            "last_match_date": "2026-01-02T19:00:00-07:00",
            "meetings": [],
        },
        "2": {
            "opponent_id": 2,
            "opponent_external_id": "EXT-2",
            "opponent_name": "Bravo",
            "wins": 1,
            "losses": 0,
            "games": 1,
            "win_rate": 1.0,
            "avg_own_skill_level": 4,
            "avg_opponent_skill_level": 5,
            "first_match_date": "2026-02-01T19:00:00-07:00",
            "last_match_date": "2026-02-01T19:00:00-07:00",
            "meetings": [
                {
                    "match_external_id": "M-1",
                    "match_date": "2026-02-01T19:00:00-07:00",
                    "session_name": "Spring 2026",
                    "result": "W",
                    "own_skill_level": 4,
                    "opponent_skill_level": 5,
                    "points_earned": 2,
                    "nine_ball_points": None,
                }
            ],
        },
    }
    shared_for_b = {
        "3": {
            "opponent_id": 3,
            "opponent_external_id": "EXT-3",
            "opponent_name": "Shared",
            "wins": 0,
            "losses": 1,
            "games": 1,
            "win_rate": 0.0,
            "avg_own_skill_level": 5,
            "avg_opponent_skill_level": 4,
            "first_match_date": "2026-01-03T19:00:00-07:00",
            "last_match_date": "2026-01-03T19:00:00-07:00",
            "meetings": [],
        }
    }
    a = _player(1, "Alpha", direct=shared_for_a)
    b = _player(2, "Bravo", direct=shared_for_b)
    shared = _player(3, "Shared")
    unresolved = _player(4, "Ghost", default=False)
    return {
        "schema": "ultimate-coach-scout-v1",
        "odds_status": "LOCKED_NOT_CALIBRATED",
        "players": [a, b, shared, unresolved],
        "counts": {
            "players": 4,
            "canonical_players": 3,
            "scoresheet_only_or_unscoped_players": 1,
            "head_to_head_rows_used": 6,
        },
        "quality": {
            "catalog_scope_conflicts": [],
            "unrecognized_head_to_head_formats": 0,
            "head_to_head_rows_with_unsafe_dates": 0,
        },
        "catalog": {
            "schema": "ultimate-coach-historical-catalog-v2",
            "counts": {"sessions": 8, "divisions": 36},
            "source_limitations": [],
        },
        "reports": {},
    }


def test_renderer_keeps_odds_locked_and_escapes_script_breakout():
    payload = _payload()
    payload["players"][0]["name"] = "</script><script>alert(1)</script>"
    html = render_ultimate_coach_scout(payload)

    assert "ODDS LOCKED" in html
    assert "LOCKED_NOT_CALIBRATED" in html
    assert "</script><script>alert(1)</script>" not in html
    assert "\\u003c/script\\u003e" in html


@pytest.fixture(scope="module")
def scout_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("ultimate-scout") / "scout.html"
    path.write_text(render_ultimate_coach_scout(_payload()), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


def test_browser_computes_direct_and_shared_evidence_without_probability(browser, scout_path):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(scout_path.as_uri())

    result = page.evaluate(
        "() => window.__ultimateCoachTestHooks.computeComparison('1','2','EIGHT')"
    )

    assert result["direct"]["games"] == 1
    assert result["direct"]["wins"] == 1
    assert len(result["shared"]) == 1
    assert result["shared"][0]["opponent_name"] == "Shared"
    assert page.locator("#odds-status").inner_text() == "ODDS LOCKED"
    assert "probability is intentionally locked" in page.locator(".odds-lock").inner_text().lower()
    assert errors == []
    page.close()


def test_scoresheet_only_player_hidden_until_opt_in(browser, scout_path):
    page = browser.new_page(viewport={"width": 1000, "height": 800})
    page.goto(scout_path.as_uri())

    assert page.locator("#player-a option", has_text="Ghost").count() == 0
    page.check("#include-unresolved")
    assert page.locator("#player-a option", has_text="Ghost").count() == 1
    page.close()


def test_mobile_layout_has_no_horizontal_overflow(browser, scout_path):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(scout_path.as_uri())
    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
    assert overflow is False
    page.close()
