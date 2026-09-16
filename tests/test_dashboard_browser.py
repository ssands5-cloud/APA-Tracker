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

    def test_a_skill_level_filter_only_keeps_opponents_at_or_above_the_real_minimum(self, page):
        """GPT audit follow-up (2026-09-16, 14:00 UTC): the prior version of
        this test only checked that surviving options were individually
        valid -- a loop over zero options trivially passes, so it could not
        catch real, valid options being wrongly dropped. This version
        computes the exact expected option set from the same real data and
        index the page itself uses (cd-player-data / cd-player-opponent-index)
        and asserts the rendered <option> set equals it exactly, not just
        that whatever remains is individually plausible."""
        player_data, opponent_index = page.evaluate(
            "() => [JSON.parse(document.getElementById('cd-player-data').textContent),"
            " JSON.parse(document.getElementById('cd-player-opponent-index').textContent)]"
        )
        real_skill_levels = sorted({
            r["opponent"]["skill_level"] for r in player_data.values()
            if r["opponent"]["skill_level"] is not None
        })
        if len(real_skill_levels) < 2:
            pytest.skip("the coherent fixture has fewer than two distinct opponent skill levels")
        threshold = real_skill_levels[len(real_skill_levels) // 2]

        player_id = page.locator("#pme-player").input_value()
        candidates = opponent_index.get(player_id, [])
        expected_keys = {
            c["key"] for c in candidates
            if player_data.get(c["key"], {}).get("opponent", {}).get("skill_level") is not None
            and player_data[c["key"]]["opponent"]["skill_level"] >= threshold
        }
        # expected_keys may legitimately be empty for this player -- the
        # equality check below still passes/fails correctly either way.

        page.fill("#pme-filter-sl-min", str(threshold))
        page.dispatch_event("#pme-filter-sl-min", "input")

        option_keys = {
            key for key in page.locator("#pme-opponent").locator("option").evaluate_all(
                "options => options.map(o => o.value)"
            )
            if key
        }
        assert option_keys == expected_keys
        assert page.console_errors == []

    def test_a_players_sparkline_shows_a_real_reading_count_and_date_caption(self, page):
        """GPT audit follow-up (2026-09-16, 14:00 UTC): the previous version
        of this test passed via `expected_count in result_text or real_dates`
        -- true whenever any date existed, regardless of whether the count
        text ever appeared -- and never inspected the actual SVG <title> or
        plotted points, despite the test's stated purpose. This version
        finds the selected player's own trend row by its real name, reads
        the SVG <title> and <polyline points> directly out of that specific
        element (not "somewhere in the result panel"), and checks both
        against the exact caption text and exact coordinates
        ui/dashboard.py's sparkline()/sparklineCaption() compute."""
        player_data = page.evaluate(
            "JSON.parse(document.getElementById('cd-player-data').textContent)"
        )
        candidate = None
        for report in player_data.values():
            trend = report["player"]["trend"]
            if len(trend["readings"]) >= 2:
                candidate = (report["player"]["id"], report["player"]["name"], trend)
                break
        if candidate is None:
            pytest.skip("the coherent fixture has no player with 2+ skill-level readings")
        player_id, player_name, trend = candidate
        readings = trend["readings"]
        real_dates = [d for d in trend["reading_dates"] if d]

        page.select_option("#pme-player", str(player_id))

        date_range = f"{real_dates[0]} → {real_dates[-1]}" if real_dates else "no dates recorded"
        scale = (
            f", skill level {min(readings)}–{max(readings)}"
            " (points spaced by reading order, not real elapsed time)"
        )
        expected_caption = f"{len(readings)} reading(s), {date_range}{scale}"

        w, h, pad = 90, 22, 2
        lo, hi = min(readings), max(readings)
        span = (hi - lo) or 1
        step = (w - pad * 2) / (len(readings) - 1)
        expected_points = [
            (round(pad + i * step, 1), round(h - pad - ((v - lo) / span) * (h - pad * 2), 1))
            for i, v in enumerate(readings)
        ]

        svg_data = page.evaluate(
            """(name) => {
                var rows = document.querySelectorAll('#pme-result tr');
                for (var i = 0; i < rows.length; i++) {
                    var th = rows[i].querySelector('th');
                    if (!th || th.textContent !== name) continue;
                    var svg = rows[i].querySelector('svg.cd-spark');
                    if (!svg) return null;
                    var title = svg.querySelector('title');
                    var polyline = svg.querySelector('polyline');
                    return {
                        title: title ? title.textContent : null,
                        points: polyline ? polyline.getAttribute('points') : null,
                    };
                }
                return null;
            }""",
            player_name,
        )
        assert svg_data is not None, f"no sparkline <svg> found in {player_name!r}'s own row"
        assert svg_data["title"] == expected_caption

        actual_points = [
            tuple(float(coord) for coord in pair.split(","))
            for pair in svg_data["points"].split()
        ]
        # abs=0.1: JS's toFixed(1) and Python's round() can disagree by up to
        # one tenth exactly at a .x5 boundary (different rounding modes) --
        # this still catches a wrong point count, wrong axis, or a
        # materially wrong coordinate, not just a rounding-mode quirk.
        assert len(actual_points) == len(expected_points)
        for (ax, ay), (ex, ey) in zip(actual_points, expected_points):
            assert ax == pytest.approx(ex, abs=0.1)
            assert ay == pytest.approx(ey, abs=0.1)
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

    def test_the_lineup_table_shows_score_and_score_basis_context(self, page):
        result_text = page.locator("#tme-result").inner_text()
        assert "Approved lineup" in result_text
        assert "Score" in result_text
        assert "Score basis" in result_text
        assert "Direct evidence" in result_text

    def test_a_direct_slots_score_basis_is_not_conflated_with_its_model_source(self, page):
        """GPT audit follow-up (2026-09-16, 14:00 UTC): the prior version of
        this test only checked that both source strings occurred somewhere
        in the whole team panel -- true both before and after the original
        column-swap bug it was written to catch, since both strings are
        always present in the panel's embedded JSON regardless of which
        visible column they land in. This version reads the actual rendered
        table, finds this specific slot's row by player name, and asserts
        the Score basis cell equals lineup_score_source exactly and the
        Direct evidence cell contains model_source -- not the other way
        around."""
        team_data = page.evaluate(
            "JSON.parse(document.getElementById('cd-team-data').textContent)"
        )
        direct_slot = None
        scope_key = None
        for key, report in team_data.items():
            lineup = report.get("lineup")
            if not lineup:
                continue
            for slot in lineup["assignments"]:
                if slot["evidence_label"] == "DIRECT":
                    direct_slot = slot
                    scope_key = key
                    break
            if direct_slot:
                break
        if direct_slot is None:
            pytest.skip("the coherent fixture has no DIRECT lineup slot to check this cycle")

        page.select_option("#tme-scope", scope_key)

        lineup_table = page.locator("#tme-result table", has_text="Score basis")
        row = lineup_table.locator("tbody tr", has_text=direct_slot["player_name"]).first
        cells = row.locator("td").all_inner_texts()
        # <td> order per ui/dashboard.py: Board, Our player, Opponent,
        # Evidence, Score, Score basis, Direct evidence.
        score_basis_cell, direct_evidence_cell = cells[5], cells[6]

        assert score_basis_cell == direct_slot["lineup_score_source"]
        assert direct_slot["model_source"] in direct_evidence_cell
        # The two sources genuinely differ for this fixture -- prove the
        # Score basis cell didn't just happen to also contain model_source
        # as a substring of a longer string.
        assert direct_slot["model_source"] != direct_slot["lineup_score_source"]
        assert direct_slot["lineup_score_source"] not in direct_evidence_cell
        assert page.console_errors == []

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
