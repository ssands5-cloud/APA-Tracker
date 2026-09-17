"""Release-blocker browser coverage for APA's verified 4-player/19 fallback.

These tests are intentionally deterministic.  They inject synthetic Match Night
scopes into the real generated Coach Dashboard so the browser behavior does not
depend on fixture luck.
"""

from __future__ import annotations

import shutil

import pytest

from scripts import build_coach_advantage_bundle as builder
from scripts.build_coherent_demo import build as build_coherent
from scripts.build_full_production_demo import FIXTURE_SCOPE

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright


@pytest.fixture(scope="module")
def coherent_db(tmp_path_factory):
    return build_coherent(
        str(tmp_path_factory.mktemp("match_night_fallback") / "demo_coherent.db")
    )


@pytest.fixture(scope="module")
def run_root():
    root = builder.PROJECT_ROOT / "coach-advantage-runs" / "pytest-match-night-fallback"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def dashboard_path(coherent_db, run_root):
    target = run_root / "browser-test"
    builder.run_build(coherent_db, FIXTURE_SCOPE["our_team_id"], target, run_root)
    path = target / "html" / "dashboard.html"
    assert path.is_file()
    return path


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture
def page(browser, dashboard_path):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(dashboard_path.as_uri())
    page.console_errors = errors  # type: ignore[attr-defined]
    try:
        yield page
    finally:
        page.close()


def _trend():
    return {
        "trend": "stable",
        "volatility": 0,
        "last_change": None,
        "readings": [],
        "reading_dates": [],
    }


def _roster_entry(player_id: int, name: str, skill_level: int | None):
    return {
        "id": player_id,
        "external_id": f"EXT-{player_id}",
        "name": name,
        "skill_level": skill_level,
        "trend": _trend(),
    }


def _scope(scope_id: int, skills: list[int | None]):
    our_team_id = f"SYN-OUR-{scope_id}"
    opp_team_id = f"SYN-OPP-{scope_id}"
    fmt = "8-Ball Open"
    session = f"Synthetic Session {scope_id}"
    our_roster = [
        _roster_entry(scope_id * 100 + i + 1, f"Our Player {i + 1}", skill)
        for i, skill in enumerate(skills)
    ]
    opponent = _roster_entry(scope_id * 1000 + 1, "Opponent One", 5)
    data = {
        "our_team": {"id": our_team_id, "name": f"Synthetic Our Team {scope_id}"},
        "opponent_team": {"id": opp_team_id, "name": f"Synthetic Opponent {scope_id}"},
        "format": fmt,
        "session_name": session,
        "our_roster": our_roster,
        "opponent_roster": [opponent],
        "evidence_counts": {
            "DIRECT": 0,
            "INDIRECT": 0,
            "UNKNOWN": 0,
            "total_feasible_pairings": 0,
        },
        "ranked_opponents": [],
        "lineup": None,
        "lineup_error": "Synthetic scope for deterministic fallback testing.",
        "summary": "Synthetic scope for deterministic fallback testing.",
        "real_matches": [],
    }
    key = f"{opp_team_id}|{fmt}|{session}"
    return key, data, our_roster, opponent


def _inject(page, scope_id: int, skills: list[int | None]):
    key, data, our_roster, opponent = _scope(scope_id, skills)
    page.evaluate(
        "(args) => window.__matchNightTestHooks.injectSyntheticScope("
        "args.scopeKey, args.scope, [])",
        {"scopeKey": key, "scope": data},
    )
    assert page.locator("#mn-scope").input_value() == key
    assert page.console_errors == []
    return our_roster, opponent


def _mark_played(page, player_ids):
    for player_id in player_ids:
        page.select_option(
            f"#mn-roster .mn-status-select[data-player-id='{player_id}']",
            "played",
        )


class TestMatchNightFourPlayerFallback:
    def test_standard_five_player_path_is_preferred(self, page):
        _inject(page, 21, [4, 4, 4, 4, 4])
        assessment = page.evaluate(
            "window.__matchNightTestHooks.assessCompletionOptions([], [4,4,4,4,4])"
        )
        assert assessment["standardFivePossible"] is True
        assert assessment["fourPlayerFallbackPossible"] is True
        assert assessment["preferredLineupSize"] == 5
        assert assessment["skillLimit"] == 23
        assert assessment["requiresForfeit"] is False
        assert "forfeit" not in page.locator("#mn-warning").inner_text().lower()
        assert page.console_errors == []

    def test_four_player_nineteen_fallback_is_surfaced_when_five_is_impossible(self, page):
        _inject(page, 22, [5, 5, 5, 4])
        assessment = page.evaluate(
            "window.__matchNightTestHooks.assessCompletionOptions([], [5,5,5,4])"
        )
        assert assessment["standardFivePossible"] is False
        assert assessment["fourPlayerFallbackPossible"] is True
        assert assessment["preferredLineupSize"] == 4
        assert assessment["skillLimit"] == 19
        assert assessment["requiresForfeit"] is True
        warning = page.locator("#mn-warning").inner_text().lower()
        assert "4-player" in warning
        assert "19" in warning
        assert "forfeit" in warning
        assert page.console_errors == []

    def test_four_player_total_of_twenty_is_rejected(self, page):
        _inject(page, 23, [5, 5, 5, 5])
        assessment = page.evaluate(
            "window.__matchNightTestHooks.assessCompletionOptions([], [5,5,5,5])"
        )
        assert assessment["standardFivePossible"] is False
        assert assessment["fourPlayerFallbackPossible"] is False
        assert assessment["preferredLineupSize"] is None
        warning = page.locator("#mn-warning").inner_text().lower()
        assert "no legal 5-player" in warning
        assert "no legal 4-player" in warning
        assert page.console_errors == []

    def test_unknown_fifth_skill_never_recommends_a_forfeit(self, page):
        _inject(page, 24, [4, 4, 4, 4, None])
        assessment = page.evaluate(
            "window.__matchNightTestHooks.assessCompletionOptions([], [4,4,4,4,null])"
        )
        assert assessment["standardFivePossible"] is None
        assert assessment["fourPlayerFallbackPossible"] is True
        assert assessment["preferredLineupSize"] is None
        assert assessment["requiresForfeit"] is False
        warning = page.locator("#mn-warning").inner_text().lower()
        assert "cannot verify" in warning
        assert "not recommend" in warning
        assert "must be forfeited" not in warning
        assert page.console_errors == []

    def test_candidate_card_identifies_fallback_and_required_forfeit(self, page):
        _inject(page, 25, [5, 5, 5, 4])
        card = page.locator("#mn-comparison .mn-card").first
        assert card.count() == 1
        assert "mn-fallback" in (card.get_attribute("class") or "")
        text = card.inner_text().lower()
        assert "4-player" in text
        assert "19" in text
        assert "forfeit" in text
        assert page.console_errors == []

    def test_completed_fallback_blocks_a_fifth_send(self, page):
        roster, _ = _inject(page, 26, [5, 5, 5, 4, 9])
        _mark_played(page, [p["id"] for p in roster[:4]])
        warning = page.locator("#mn-warning").inner_text().lower()
        comparison = page.locator("#mn-comparison").inner_text().lower()
        assert "4-player" in warning
        assert "match 5" in warning
        assert "forfeit" in warning
        assert "match 5" in comparison
        assert "forfeit" in comparison
        assert page.locator("#mn-comparison .mn-send-btn").count() == 0
        assert page.console_errors == []

    def test_standard_path_still_allows_the_fifth_send(self, page):
        roster, _ = _inject(page, 27, [4, 4, 4, 4, 4])
        _mark_played(page, [p["id"] for p in roster[:4]])
        assert "forfeit" not in page.locator("#mn-warning").inner_text().lower()
        buttons = page.locator("#mn-comparison .mn-send-btn")
        assert buttons.count() == 1
        assert buttons.first.get_attribute("data-player-id") == str(roster[4]["id"])
        assert page.console_errors == []

    def test_fallback_state_is_consistent_in_lineup_sticky_and_print_summary(self, page):
        roster, _ = _inject(page, 28, [5, 5, 5, 4])
        _mark_played(page, [p["id"] for p in roster])
        lineup = page.locator("#mn-lineup").inner_text().lower()
        sticky = page.locator("#mn-sticky").inner_text().lower()
        printed = page.locator("#mn-print-summary").text_content().lower()
        for text in (lineup, sticky, printed):
            assert "4-player" in text
            assert "19" in text
            assert "forfeit" in text
        assert page.console_errors == []

    def test_unknown_candidate_stays_unknown_not_fallback_recommended(self, page):
        roster, _ = _inject(page, 29, [None, 2, 2, 2, 2, 2])
        card = page.locator(
            f"#mn-comparison .mn-send-btn[data-player-id='{roster[0]['id']}']"
        ).locator("xpath=ancestor::div[contains(@class, 'mn-card')]")
        assert card.count() == 1
        classes = card.get_attribute("class") or ""
        text = card.inner_text().lower()
        assert "mn-unknown" in classes
        assert "mn-fallback" not in classes
        assert "fallback is not recommended" in text
        assert "must be forfeited" not in text
        assert page.console_errors == []

    def test_played_player_is_not_reused_as_available_completion_candidate(self, page):
        roster, _ = _inject(page, 30, [1, 7, 7, 7, 9])
        # If the already-played SL1 were accidentally left in the available
        # pool, the search could reuse that same person with three SL7s:
        # committed 1 + duplicated 1 + 7 + 7 + 7 == 23, a false legal five.
        _mark_played(page, [roster[0]["id"]])
        warning = page.locator("#mn-warning").inner_text().lower()
        assert "no legal 5-player" in warning
        assert "no legal 4-player" in warning
        assert page.console_errors == []

    def test_fallback_remains_readable_on_phone_width(self, browser, dashboard_path):
        phone = browser.new_page(viewport={"width": 390, "height": 844})
        errors: list[str] = []
        phone.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        phone.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            phone.goto(dashboard_path.as_uri())
            _inject(phone, 31, [5, 5, 5, 4])
            warning = phone.locator("#mn-warning").inner_text().lower()
            assert "4-player" in warning
            assert "forfeit" in warning
            dimensions = phone.evaluate(
                "() => ({inner: window.innerWidth, scroll: document.documentElement.scrollWidth})"
            )
            assert dimensions["scroll"] <= dimensions["inner"] + 1
            assert errors == []
        finally:
            phone.close()
