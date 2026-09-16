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


class TestMatchNight:
    """Directive: "Match Night" -- "who should I send" plus a live lineup
    planner. Drives the real interactive flow against the real, live
    bundle: mark a player absent, get a real opponent announced, compare
    real candidates side by side, send one, and check the running lineup
    and legality warning update from real embedded data, not a fixture."""

    def test_marking_a_player_absent_removes_them_from_the_comparison(self, page):
        first_row = page.locator("#mn-roster .mn-roster-row").first
        player_name = first_row.locator(".mn-roster-name").inner_text()
        first_row.locator("select").select_option("absent")

        opponent_options = page.locator("#mn-opponent option").evaluate_all(
            "options => options.map(o => o.value)"
        )
        if opponent_options and opponent_options[0]:
            page.select_option("#mn-opponent", opponent_options[0])
        comparison_text = page.locator("#mn-comparison").inner_text()
        assert player_name not in comparison_text
        assert page.console_errors == []

    def test_sending_a_player_adds_a_board_and_marks_them_already_played(self, page):
        opponent_options = page.locator("#mn-opponent option").evaluate_all(
            "options => options.map(o => o.value)"
        )
        if not opponent_options or not opponent_options[0]:
            pytest.skip("no identified opponent to select in this fixture scope")
        page.select_option("#mn-opponent", opponent_options[0])

        send_button = page.locator("#mn-comparison .mn-send-btn").first
        if send_button.count() == 0:
            pytest.skip("no available candidate rendered for this fixture scope")
        sent_name = send_button.get_attribute("data-player-id")
        sent_label = send_button.inner_text()  # "Send <Name>"

        page.once("dialog", lambda dialog: dialog.accept())
        send_button.click()

        rows = page.locator("#mn-lineup table tbody tr")
        assert rows.count() == 1, "exactly one board should be recorded after one send"
        first_row_cells = rows.first.locator("td").all_inner_texts()
        assert first_row_cells[0] == "1"  # Board column
        assert sent_label.endswith(first_row_cells[1].split(" (SL")[0])  # Our player column

        status_select = page.locator(f"#mn-roster .mn-status-select[data-player-id='{sent_name}']")
        assert status_select.input_value() == "played"
        assert page.console_errors == []

    def test_the_exact_reported_repro_produces_one_assignment_not_two(self, page):
        """GPT audit follow-up (2026-09-16), P1: reproduces the exact
        reported sequence for commit f39ad08 -- send a player, flip their
        status back to Available, send them again -- which previously left
        TWO assignment rows for the same player (mnCommittedSkillLevels
        counted unique roster statuses, not assignments; mnSendPlayer
        enforced neither uniqueness nor the board cap). The roster
        status-select now retracts the stale assignment the instant status
        moves off "played", so this exact sequence must leave exactly one."""
        opponent_options = page.locator("#mn-opponent option").evaluate_all(
            "options => options.map(o => o.value)"
        )
        if not opponent_options or not opponent_options[0]:
            pytest.skip("no identified opponent to select in this fixture scope")
        page.select_option("#mn-opponent", opponent_options[0])
        send_button = page.locator("#mn-comparison .mn-send-btn").first
        if send_button.count() == 0:
            pytest.skip("no available candidate rendered for this fixture scope")
        player_id = send_button.get_attribute("data-player-id")
        page.once("dialog", lambda dialog: dialog.accept())
        send_button.click()
        assert page.locator("#mn-lineup table tbody tr").count() == 1

        page.select_option(f"#mn-roster .mn-status-select[data-player-id='{player_id}']", "available")
        assert page.locator("#mn-lineup table tbody tr").count() == 0, (
            "changing status away from Already played must retract the stale assignment"
        )

        opponent_options_2 = page.locator("#mn-opponent option").evaluate_all(
            "options => options.map(o => o.value)"
        )
        if not opponent_options_2 or not opponent_options_2[0]:
            pytest.skip("no opponent available to resend against after retraction")
        page.select_option("#mn-opponent", opponent_options_2[0])
        resend_button = page.locator(f"#mn-comparison .mn-send-btn[data-player-id='{player_id}']")
        if resend_button.count() == 0:
            pytest.skip("the same player has no matchup data against any remaining opponent")
        page.once("dialog", lambda dialog: dialog.accept())
        resend_button.click()

        rows = page.locator("#mn-lineup table tbody tr")
        assert rows.count() == 1, "resending after a clean retraction must leave exactly one board"
        status_select = page.locator(f"#mn-roster .mn-status-select[data-player-id='{player_id}']")
        assert status_select.input_value() == "played"
        assert page.console_errors == []

    def test_undo_removes_the_assignment_and_restores_availability(self, page):
        opponent_options = page.locator("#mn-opponent option").evaluate_all(
            "options => options.map(o => o.value)"
        )
        if not opponent_options or not opponent_options[0]:
            pytest.skip("no identified opponent to select in this fixture scope")
        page.select_option("#mn-opponent", opponent_options[0])
        send_button = page.locator("#mn-comparison .mn-send-btn").first
        if send_button.count() == 0:
            pytest.skip("no available candidate rendered for this fixture scope")
        player_id = send_button.get_attribute("data-player-id")
        page.once("dialog", lambda dialog: dialog.accept())
        send_button.click()
        assert page.locator("#mn-lineup table tbody tr").count() == 1

        page.click("#mn-lineup .mn-undo-btn")

        assert "No boards sent yet" in page.locator("#mn-lineup").inner_text()
        status_select = page.locator(f"#mn-roster .mn-status-select[data-player-id='{player_id}']")
        assert status_select.input_value() == "available"
        assert page.console_errors == []

    def test_five_sends_fill_the_match_and_a_sixth_is_refused(self, page):
        """GPT audit follow-up (2026-09-16), P1: mnSendPlayer previously had
        no board cap at all -- reproduced by sending six real players in a
        row. Sends up to five real (player, opponent) pairs from the live
        bundle and checks the panel then reports all boards sent with no
        further Send buttons offered, rather than allowing a sixth."""
        sent = 0
        for _ in range(5):
            opponent_options = page.locator("#mn-opponent option").evaluate_all(
                "options => options.map(o => o.value)"
            )
            if not opponent_options or not opponent_options[0]:
                break
            page.select_option("#mn-opponent", opponent_options[0])
            send_button = page.locator("#mn-comparison .mn-send-btn").first
            if send_button.count() == 0:
                break
            page.once("dialog", lambda dialog: dialog.accept())
            send_button.click()
            sent += 1
        if sent < 5:
            pytest.skip(
                f"this fixture scope only supports {sent} real sends, not enough to "
                "reach the 5-board cap"
            )
        assert page.locator("#mn-lineup table tbody tr").count() == 5
        comparison_text = page.locator("#mn-comparison").inner_text()
        assert "All 5 boards have been sent" in comparison_text
        assert page.locator("#mn-comparison .mn-send-btn").count() == 0
        assert page.console_errors == []

    def test_an_unknown_skill_candidate_never_shows_as_legality_preserving(self, page):
        """GPT audit follow-up (2026-09-16), P1: candidateCommitted used to
        silently drop a candidate's own unknown skill level instead of
        counting their slot as unverifiable, which could show "still legal"
        for a send that genuinely couldn't be checked. Finds a real
        roster player with no known skill level across every real scope in
        the bundle (skips honestly if none exists) and checks their card is
        always rendered Unknown, never marked legality-preserving."""
        all_team_data = page.evaluate(
            "JSON.parse(document.getElementById('cd-team-data').textContent)"
        )
        scope_key = unknown_player = None
        for key, report in all_team_data.items():
            for p in report["our_roster"]:
                if p["skill_level"] is None:
                    scope_key, unknown_player = key, p
                    break
            if unknown_player:
                break
        if unknown_player is None:
            pytest.skip("no real roster player in this bundle has an unknown skill level")

        page.select_option("#mn-scope", scope_key)
        opponent_options = page.locator("#mn-opponent option").evaluate_all(
            "options => options.map(o => o.value)"
        )
        if not opponent_options or not opponent_options[0]:
            pytest.skip("no identified opponent to select in this scope")
        page.select_option("#mn-opponent", opponent_options[0])

        card = page.locator(
            f"#mn-comparison .mn-send-btn[data-player-id='{unknown_player['id']}']"
        ).locator("xpath=ancestor::div[contains(@class, 'mn-card')]")
        if card.count() == 0:
            pytest.skip("this unknown-skill player has no matchup data for this opponent")
        classes = card.get_attribute("class") or ""
        assert "mn-unknown" in classes
        assert "mn-ok" not in classes
        assert "mn-warn" not in classes
        assert page.console_errors == []

    def test_the_probability_label_shows_the_real_model_source_not_a_fixed_claim(self, page):
        """GPT audit follow-up (2026-09-16), P2: modeled_win_probability is
        not always the skill-only model -- a DIRECT pairing's real
        model_source can be "...direct-history-and-skill". The comparison
        card previously labeled every row "Skill-only estimate
        (experimental)" regardless, repeating the exact model-basis
        conflation already fixed once this session in the lineup table.
        Checks a real DIRECT and/or real INDIRECT candidate's card shows
        its own real model_source, and the old fixed mislabel never
        appears, across every real scope (skips only if truly none of
        either kind has matchup data reachable through the UI)."""
        all_player_data = page.evaluate(
            "JSON.parse(document.getElementById('cd-player-data').textContent)"
        )
        candidates = [
            r for r in all_player_data.values()
            if r["evidence_label"] in ("DIRECT", "INDIRECT") and r["model_source"]
        ]
        checked_labels = set()
        for entry in candidates:
            scope_key = f"{entry['opponent_team_id']}|{entry['format']}|{entry['session_name']}"
            if scope_key not in page.evaluate(
                "Array.from(document.getElementById('mn-scope').options).map(o => o.value)"
            ):
                continue
            page.select_option("#mn-scope", scope_key)
            opponent_ids = page.locator("#mn-opponent option").evaluate_all(
                "options => options.map(o => o.value)"
            )
            if str(entry["opponent"]["id"]) not in opponent_ids:
                continue
            page.select_option("#mn-opponent", str(entry["opponent"]["id"]))
            card = page.locator(
                f"#mn-comparison .mn-send-btn[data-player-id='{entry['player']['id']}']"
            ).locator("xpath=ancestor::div[contains(@class, 'mn-card')]")
            if card.count() == 0:
                continue
            card_text = card.inner_text()
            assert entry["model_source"] in card_text
            # The old fixed *table-row label* is what must be gone -- the
            # plain-language summary honestly saying "Skill-only estimate"
            # for a real INDIRECT pairing (from player_matchup_engine's own
            # already-correct _summary_for()) is expected text, not a bug.
            assert "Skill-only estimate (experimental)" not in card_text
            checked_labels.add(entry["evidence_label"])
        if not checked_labels:
            pytest.skip("no DIRECT/INDIRECT candidate with matchup data was reachable through the UI")
        assert page.console_errors == []

    def test_the_completion_search_guard_returns_unknown_rather_than_hanging(self, page):
        """GPT audit follow-up (2026-09-16), P2: the JS port of
        legal_completion_exists had no MAX_COMPLETION_ATTEMPTS-equivalent
        guard, unlike the Python function it claims to mirror -- an
        unbounded recursive search in an interactive page can only ever
        freeze the tab, not fail loudly the way a script raising and
        exiting can. Calls the real function directly through the
        page's own test-only hook (see ui/dashboard.py's
        window.__matchNightTestHooks comment) with a synthetic 60-player
        pool needing all 5 slots -- C(60,5) is far past the real 200000
        bound -- and checks it returns the honest "cannot verify" signal
        quickly rather than hanging or throwing."""
        result = page.evaluate(
            "window.__matchNightTestHooks.legalCompletionExists([], Array(60).fill(2))"
        )
        assert result is None
        assert page.console_errors == []

    def test_match_night_state_survives_a_reload_via_local_storage(self, page):
        first_row = page.locator("#mn-roster .mn-roster-row").first
        first_row.locator("select").select_option("held")
        page.reload()

        reloaded_status = page.locator("#mn-roster .mn-roster-row").first.locator("select").input_value()
        assert reloaded_status == "held"
        assert page.console_errors == []

    def test_resetting_clears_the_saved_state(self, page):
        first_row = page.locator("#mn-roster .mn-roster-row").first
        first_row.locator("select").select_option("absent")

        page.once("dialog", lambda dialog: dialog.accept())
        page.click("#mn-reset")

        status = page.locator("#mn-roster .mn-roster-row").first.locator("select").input_value()
        assert status == "available"
        assert page.console_errors == []

    def test_a_completion_breaking_choice_prompts_a_confirm_dialog(self, page):
        """Find a real candidate (not a fixture) from the live embedded
        team data for whom sending them leaves the rest of the *whole* real
        roster unable to complete a legal lineup even in the
        best case -- i.e. candidate.skill_level + (the four smallest other
        known skill levels on the real roster) already exceeds the real
        23-Rule cap, using analytics.lineup_legality.legal_completion_exists
        (the same function this UI's JS is a direct port of) as the oracle.
        No availability needs to be held back for this: if the theoretical
        best case already fails, every real subset does too. Skips honestly
        if this real roster's skill levels can never produce that case."""
        from analytics.lineup_legality import TEAM_SKILL_LEVEL_LIMIT_5, legal_completion_exists

        all_team_data = page.evaluate(
            "JSON.parse(document.getElementById('cd-team-data').textContent)"
        )
        scope_key = candidate = None
        for key, report in all_team_data.items():
            known = [p for p in report["our_roster"] if p["skill_level"] is not None]
            if len(known) < 5:
                continue
            for c in sorted(known, key=lambda p: p["skill_level"], reverse=True):
                others = sorted(p["skill_level"] for p in known if p["id"] != c["id"])
                if c["skill_level"] + sum(others[:4]) > TEAM_SKILL_LEVEL_LIMIT_5:
                    scope_key, candidate = key, c
                    break
            if candidate is not None:
                break
        if candidate is None:
            pytest.skip(
                "no real roster in this bundle's skill levels can ever fail to "
                "complete a legal lineup no matter who is sent first -- no "
                "infeasible scenario to construct honestly this cycle"
            )
        page.select_option("#mn-scope", scope_key)
        # Sanity-check the constructed scenario against the real oracle before
        # trusting the browser to agree with it.
        others = [p["skill_level"] for p in known if p["id"] != candidate["id"]]
        assert legal_completion_exists([candidate["skill_level"]], others) is False

        opponent_options = page.locator("#mn-opponent option").evaluate_all(
            "options => options.map(o => o.value)"
        )
        if not opponent_options or not opponent_options[0]:
            pytest.skip("no identified opponent to select in this fixture scope")
        page.select_option("#mn-opponent", opponent_options[0])

        send_button = page.locator(f"#mn-comparison .mn-send-btn[data-player-id='{candidate['id']}']")
        if send_button.count() == 0:
            pytest.skip("the constructed candidate has no matchup data for this opponent")
        card = send_button.locator("xpath=ancestor::div[contains(@class, 'mn-card')]")
        assert "mn-warn" in (card.get_attribute("class") or "")

        dialog_messages = []
        page.once("dialog", lambda dialog: (dialog_messages.append(dialog.message), dialog.dismiss()))
        send_button.click()
        page.wait_for_timeout(100)

        assert dialog_messages, "expected a confirm() dialog before an infeasible send"
        assert "no legal" in dialog_messages[0].lower()
        # Dismissed, not accepted -- the send must not have been applied.
        status_select = page.locator(f"#mn-roster .mn-status-select[data-player-id='{candidate['id']}']")
        assert status_select.input_value() == "available"
        assert page.console_errors == []


class TestNoConsoleErrorsOnLoad:
    def test_the_page_loads_with_no_javascript_error(self, page):
        assert page.console_errors == []
