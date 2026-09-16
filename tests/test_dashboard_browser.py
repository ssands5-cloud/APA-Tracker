"""Browser-driven regression test of a real, live-built Coach Dashboard.

Every other Coach Advantage Tools test either exercises the Python builder
directly or parses the generated HTML as a string -- neither one proves a
coach can actually click through the page the way they would in a real
browser. This test drives a real Chromium instance (Playwright, already a
project dependency -- see requirements-dev.txt) against the real
dashboard.html file scripts/build_coach_advantage_bundle.py produces from
the same coherent fixture database every other builder test uses, and
checks the same real interactions a coach would perform: pick a player,
narrow to an opponent, filter the opponent list, switch to a real team
scope, and read the Captain's Edge card and lineup table.

A REPORTER's own test: nothing here asserts a specific number (those are
covered by the Python-side tests), only that the real page renders and
responds to real clicks without a JavaScript error.
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
    """A private copy of the coherent rehearsal database -- not the shared
    data/demo_coherent.db every other test module's fixture also rebuilds
    (see tests/test_build_coach_advantage_bundle.py's own fixture docstring
    for the real Windows file-locking bug that pattern caused)."""
    return build_coherent(str(tmp_path_factory.mktemp("dashboard_browser") / "demo_coherent.db"))


@pytest.fixture(scope="module")
def run_root():
    # The builder's own preflight refuses a run_root outside the repository
    # boundary (scripts/build_full_production_demo.py's resolve_contained),
    # so this must live under PROJECT_ROOT -- matching
    # tests/test_build_coach_advantage_bundle.py's own fixture.
    root = builder.PROJECT_ROOT / "coach-advantage-runs" / "pytest-browser"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def run_dir(coherent_db, run_root):
    target = run_root / "browser-test"
    builder.run_build(coherent_db, FIXTURE_SCOPE["our_team_id"], target, run_root)
    return target


@pytest.fixture(scope="module")
def dashboard_path(run_dir):
    path = run_dir / "html" / "dashboard.html"
    assert path.is_file(), "the real builder must have produced dashboard.html"
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
    page = browser.new_page()
    console_errors: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    page.goto(dashboard_path.as_uri())
    page.console_errors = console_errors  # type: ignore[attr-defined]
    try:
        yield page
    finally:
        page.close()


class TestPlayerVsPlayerSelectors:
    def test_choosing_a_player_populates_a_real_opponent_and_report(self, page):
        player_select = page.locator("#pme-player")
        assert player_select.locator("option").count() > 0

        opponent_select = page.locator("#pme-opponent")
        assert opponent_select.locator("option").count() > 0

        result_text = page.locator("#pme-result").inner_text()
        assert "Evidence" in result_text
        assert "No data" not in result_text or "Observed win rate" in result_text

    def test_switching_players_narrows_to_that_players_real_opponents(self, page):
        player_select = page.locator("#pme-player")
        option_values = player_select.locator("option").evaluate_all(
            "options => options.map(o => o.value)"
        )
        assert len(option_values) >= 1

        for value in option_values[:2]:
            player_select.select_option(value)
            opponent_select = page.locator("#pme-opponent")
            assert opponent_select.locator("option").count() > 0

    def test_an_impossible_skill_level_filter_reports_no_opponents_not_a_crash(self, page):
        page.fill("#pme-filter-sl-min", "99")
        page.dispatch_event("#pme-filter-sl-min", "input")
        opponent_text = page.locator("#pme-opponent").inner_text()
        assert "No opponents match these filters" in opponent_text
        assert page.console_errors == []

    def test_clearing_the_filter_restores_the_real_opponent_list(self, page):
        page.fill("#pme-filter-sl-min", "99")
        page.dispatch_event("#pme-filter-sl-min", "input")
        page.fill("#pme-filter-sl-min", "")
        page.dispatch_event("#pme-filter-sl-min", "input")
        assert page.locator("#pme-opponent").locator("option").count() > 0

    def test_unchecking_every_trend_checkbox_reports_no_opponents_not_a_crash(self, page):
        for checkbox in page.locator(".pme-filter-trend").all():
            checkbox.uncheck()
        opponent_text = page.locator("#pme-opponent").inner_text()
        assert "No opponents match these filters" in opponent_text
        assert page.console_errors == []


class TestTeamVsTeamAndCaptainsEdge:
    def test_selecting_a_real_scope_renders_the_captains_edge_card(self, page):
        scope_select = page.locator("#tme-scope")
        assert scope_select.locator("option").count() > 0

        result_text = page.locator("#tme-result").inner_text()
        assert "Captain's Edge" in result_text
        assert "Evidence coverage" in result_text

    def test_the_lineup_table_shows_score_and_model_basis_context(self, page):
        result_text = page.locator("#tme-result").inner_text()
        assert "Approved lineup" in result_text
        assert "Score" in result_text
        assert "Model basis" in result_text

    def test_no_javascript_errors_across_every_real_scope(self, page):
        scope_select = page.locator("#tme-scope")
        option_values = scope_select.locator("option").evaluate_all(
            "options => options.map(o => o.value)"
        )
        for value in option_values:
            scope_select.select_option(value)
        assert page.console_errors == []


class TestNoConsoleErrorsOnLoad:
    def test_the_page_loads_with_no_javascript_error(self, page):
        assert page.console_errors == []
