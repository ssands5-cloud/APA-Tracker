"""The standalone page in the artifact's broadcast experience (ui="broadcast"), in a real browser.

It must behave like the artifact (seven tabs, scoreboard hero, facts strip, matchup rows) while the Ultimate Coach
engine stays intact: the same decisions give the same recommendations, every existing control still works, the file
runs offline, and the classic page is unchanged. Synthetic data only (the all-categories war-room fixture).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from tests.test_excel_war_room_formulas import _payload
from ui.ultimate_coach import render

OURS, THEIRS, OTHER = "sharks-a|d1|Fall 2026", "falcons-a|d1|Fall 2026", "owls-a|d1|Fall 2026"
TABS = ["home", "schedule", "matchnight", "recs", "threats", "team", "summary"]


@pytest.fixture(scope="module")
def html_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("bc") / "uc.html"
    path.write_text(render(_payload(), built_at="2026-11-11 12:00 UTC", viewer_member_external_id="1001", ui="broadcast"),
                    encoding="utf-8")
    return path


@pytest.fixture
def page(html_path):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.errors, page.requests = [], []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.on("console", lambda m: page.errors.append(m.text[:160]) if m.type == "error" else None)
        page.on("request", lambda r: page.requests.append(r.url))
        page.goto(html_path.as_uri())
        page.wait_for_selector("#bc-team-a")
        yield page
        browser.close()


def _tab(page, name):
    page.click(f"a.nav-tab[data-tab={name}]")
    page.wait_for_function("n => document.body.dataset.view === n", arg=name)


def _pick(page, ours=OURS, theirs=THEIRS):
    page.select_option("#bc-team-a", ours)
    page.select_option("#bc-team-b", theirs)
    page.wait_for_selector(".matchup-row[data-their]")


def _engine_plan(page):
    """The engine's own 'If they put up' lines, read from the classic Tonight card (hidden in tab mode)."""
    return page.evaluate("""() => [...document.querySelectorAll('#match-plan .mp-resp li')].map(li => {
        const t = li.textContent, level = li.querySelector('.mp-level').textContent;
        const [their, rest] = t.split(' → '); return [their.trim(), rest.slice(0, rest.indexOf(level)).trim(), level];})""")


def test_the_page_is_the_artifacts_shell_and_works_offline(page):
    assert [t.strip() for t in page.locator("nav.main-nav .nav-tab").all_text_contents()] == [
        "Home", "Schedule Planner", "Match Night", "Recommendations", "Threats", "Team Status", "Summary"]
    assert page.locator(".logo-mark").inner_text() == "UC"
    assert page.locator(".ticker-item").count() > 4 and page.locator("header.app-header").is_visible()
    assert page.locator(".match-hero .team-mono-home").is_visible() and page.locator(".match-stats .stat-cell").count() == 4
    assert page.locator("#bc-home .badge-prematch").text_content() == "No Matchup"      # nothing picked yet: honest empty state
    assert all(u.startswith("file:") or u.startswith("data:") for u in page.requests), page.requests
    assert page.errors == []


def test_home_rows_equal_the_engines_plan_and_follow_the_opponent(page):
    _pick(page)
    assert page.locator(".match-hero .team-mono-home").text_content() == "SH"
    assert page.locator(".match-hero .team-mono-away").text_content() == "FA"
    rows = page.locator("#bc-home .matchup-row[data-their]")
    shown = [[r.locator(".matchup-their .matchup-player").text_content().rsplit("SL", 1)[0].strip().title(),
              r.locator(".matchup-our .matchup-player").text_content().rsplit("SL", 1)[0].strip().title(),
              r.locator(".evidence-badge").text_content().title()] for r in rows.all()]
    engine = [[a, b, c] for a, b, c in _engine_plan(page)]
    norm = lambda lines: [[x.lower() for x in line] for line in lines]
    assert norm(shown) == norm(engine) and shown, (shown, engine)
    before = page.locator("#bc-home .matchup-list").inner_text()
    _pick(page, ours=OURS, theirs=OTHER)                                              # switch opponents
    assert page.locator(".match-hero .team-mono-away").text_content() == "OW"
    assert page.locator("#bc-home .matchup-list").inner_text() != before
    assert [[x.lower() for x in l] for l in _engine_plan(page)]                       # and the engine plan changed with it


def test_bars_show_recorded_results_with_sample_sizes_never_odds(page):
    _pick(page)
    text = page.locator("#bc-home .matchup-bars").first.text_content()
    assert "direct" in text and "meeting" in text and "small sample" in text
    assert "Evidence strength within the conditional plan; not a predicted win or loss" in page.locator("#bc-home").inner_text()


def test_reference_cap_is_the_existing_skill_cap_input(page):
    _pick(page)
    page.fill("#bc-cap", "23")
    assert page.input_value("#ll-cap") == "23"
    assert "Cap 23" in page.locator("#match-plan .mp-sub").inner_text()
    assert page.locator("#bc-night .night-pill").nth(2).text_content().lower().startswith("cap 23")


def test_match_night_runs_the_loop_pick_send_result_undo(page):
    _pick(page)
    _tab(page, "matchnight")
    assert page.locator("#bc-night").is_visible() and not page.locator("#tonight").is_visible()
    chips = page.locator("#bc-night .night-chip")
    assert chips.count() == 2
    chips.nth(1).click()                                                              # they put up the second opponent
    assert page.locator("#bc-night .night-chip[aria-pressed=true]").text_content().lower()[:4] == chips.nth(1).text_content().lower()[:4]
    hero_name = page.locator("#bc-night .send-name").text_content().lower()
    engine_answer = page.locator("#next-send .ns-plan-answer b").first.text_content().lower()
    assert hero_name == engine_answer, (hero_name, engine_answer)                      # same decision as the engine
    page.click("#bc-night .send-hero [data-send]")                                    # confirm the pairing
    assert page.locator("#bc-night .night-pill").nth(0).text_content().lower() == "game 2 of 5"
    assert page.locator("#bc-night .bench-item.used").count() >= 1
    assert page.locator("#bc-night .game-row").count() == 1
    page.click("#bc-night [data-result][data-r=W]")                                   # record the result
    assert "1-0" in page.locator("#bc-night .night-pill").nth(1).text_content()
    page.reload()                                                                     # kept for tonight, in this browser
    page.wait_for_selector("#bc-night")
    _tab(page, "home")
    _pick(page)                                                                       # same fixture again: its marks come back
    _tab(page, "matchnight")
    page.wait_for_selector("#bc-night .game-row")
    assert page.locator("#bc-night .game-row .res.W").count() == 1
    page.click("#bc-night [data-undo]")                                               # undo the send
    assert page.locator("#bc-night .game-row").count() == 0 and page.locator("#bc-night .bench-item.used").count() == 0
    assert page.errors == []


def test_bench_availability_changes_the_recommendation_inputs(page):
    _pick(page)
    _tab(page, "matchnight")
    first = page.locator("#bc-night [data-avail]").first
    assert first.text_content() == "Unknown"
    first.click()
    assert page.locator("#bc-night [data-avail]").first.text_content() == "Available"
    page.locator("#bc-night [data-avail]").first.click()
    assert page.locator("#bc-night [data-avail]").first.text_content() == "Unavailable"
    assert page.locator("#bc-night .alt-row .matchup-player, #bc-night .send-name").all_text_contents()  # engine still answers


def test_match_night_surfaces_failed_result_saves_and_recovers(page):
    _pick(page)
    _tab(page, "matchnight")
    page.locator("#bc-night .night-chip").first.click()
    page.locator("#bc-night .send-hero [data-send]").click()
    page.evaluate("""() => {
        window.originalSetItem = Storage.prototype.setItem;
        Storage.prototype.setItem = function(key, value) {
            if (key === "ultimate-coach:plan-v2") throw new DOMException("Synthetic quota", "QuotaExceededError");
            return window.originalSetItem.call(this, key, value);
        };
    }""")
    page.locator("#bc-night [data-result][data-r=W]").click()
    warning = page.locator("#bc-night [role=status]")
    assert warning.is_visible()
    assert "Planning changes are not saved" in warning.inner_text()
    assert "Results are available while this page is open" in page.locator("#bc-night").inner_text()
    page.evaluate("() => { Storage.prototype.setItem = window.originalSetItem; }")
    page.locator("#bc-night [data-result][data-r='']").click()
    page.locator("#bc-night [data-result][data-r=W]").click()
    assert warning.text_content() == ""
    page.reload()
    _tab(page, "home")
    _pick(page)
    _tab(page, "matchnight")
    assert page.locator("#bc-night .game-row .res.W").count() == 1
    assert page.errors == []


def test_command_board_updates_send_costs_and_the_five_game_path(page):
    _pick(page)
    _tab(page, "matchnight")
    slots = page.locator("#bc-night .path-slots .slot")
    assert slots.count() == 5
    assert "No pairing planned" in slots.last.inner_text()
    assert page.locator("#bc-night .pcard .grade").count() > 0
    page.locator("#bc-night .night-chip").first.click()
    costs = page.locator("#bc-send-costs [data-cost-player]")
    available = page.evaluate("UC_BC_LAST.night.bench.ours.filter(p => p.rem).map(p => p.id)")
    assert sorted(costs.evaluate_all("rows => rows.map(r => r.dataset.costPlayer)")) == sorted(available)
    send = page.locator("#bc-night .send-hero [data-send]")
    sent_id = send.get_attribute("data-send")
    assert costs.first.get_attribute("data-cost-player") == sent_id
    assert "Engine answer" in costs.first.inner_text()
    assert "vs " in costs.first.text_content()
    assert page.locator("#bc-night .path-tabs strong").is_visible()
    assert "we put up" in slots.nth(1).inner_text().lower()
    send.click()
    assert "pairing confirmed" in slots.first.inner_text().lower()
    assert slots.nth(1).inner_text().lower().startswith("game 2")
    assert page.locator("#bc-send-costs").count() == 0
    page.locator("#bc-night .night-chip").first.click()
    assert page.locator(f'#bc-send-costs [data-cost-player="{sent_id}"]').count() == 0
    assert page.errors == []


def test_command_board_shows_open_slots_when_cap_blocks_a_plan(page):
    _pick(page)
    page.fill("#bc-cap", "1")
    _tab(page, "matchnight")
    assert page.locator("#bc-night .path-slots .slot .st").all_text_contents() == ["No pairing planned"] * 5
    assert page.errors == []


def test_captain_can_confirm_a_different_player_from_the_send_comparison(page):
    _pick(page)
    _tab(page, "matchnight")
    page.locator("#bc-night .night-chip").first.click()
    recommended = page.locator("#bc-night .send-hero [data-send]").get_attribute("data-send")
    option = page.locator(f'#bc-send-costs [data-cost-player]:not([data-cost-player="{recommended}"])').first
    player = option.get_attribute("data-cost-player")
    name = option.locator("strong").text_content()
    option.get_by_role("button", name="Confirm", exact=False).click()
    assert name.lower() in page.locator("#bc-night .path-slots .slot").first.inner_text().lower()
    assert page.evaluate("id => UC_BC_LAST.night.bench.ours.find(p => p.id === id).lineup", player) == "Played"
    assert page.evaluate("id => UC_BC_LAST.night.bench.ours.find(p => p.id === id).rem", recommended)
    assert page.errors == []


def test_every_existing_capability_is_reachable_in_a_tab(page):
    _pick(page)
    expect = {"schedule": ["#match-day-card"], "matchnight": ["#bc-night"],
              "recs": ["#wr-matrix", "#wr-opportunities", "#team-comparison", "#team-matchups", "#wr-meetings", "#player-section"],
              "threats": ["#wr-risks", "#scouting-cards", "#matchup-notes"],
              "team": ["#lineup-lab", "#team-rosters"], "summary": ["#start-here", "#trust-section"]}
    for tab, ids in expect.items():
        _tab(page, tab)
        for sel in ids:
            assert page.locator(sel).first.is_visible(), (tab, sel)
        # and nothing from the other tabs bleeds in
        for other, oids in expect.items():
            if other != tab and other != "matchnight":
                for sel in oids:
                    assert not page.locator(sel).first.is_visible(), (tab, sel)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), tab
    assert page.errors == []


@pytest.mark.parametrize("width", [390, 1280])
def test_no_horizontal_scroll_on_any_tab(html_path, width):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.goto(html_path.as_uri())
        page.wait_for_selector("#bc-team-a")
        page.select_option("#bc-team-a", OURS)
        page.select_option("#bc-team-b", THEIRS)
        for tab in TABS:
            page.click(f"a.nav-tab[data-tab={tab}]")
            page.wait_for_function("n => document.body.dataset.view === n", arg=tab)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, tab)
        browser.close()


def test_the_classic_page_is_unchanged():
    classic = render(_payload(), built_at="2026-11-11 12:00 UTC", viewer_member_external_id="1001")
    assert "data-bc=" not in classic and 'class="app-header"' not in classic
    assert 'id="bc-home"' not in classic and 'id="bc-night"' not in classic and "<body class=\"\"" in classic
    with pytest.raises(ValueError):
        render(_payload(), ui="other")


def test_printing_the_packet_from_any_tab_includes_the_whole_matchup(page):
    """Tabs are a screen convenience. Print (the Captain Packet) must carry every matchup section, as the classic page does."""
    _pick(page)
    _tab(page, "matchnight")
    assert not page.locator("#wr-matrix").first.is_visible()                           # hidden on screen in this tab
    page.emulate_media(media="print")
    for sel in ("#wr-matrix", "#wr-opportunities", "#wr-risks", "#lineup-lab", "#scouting-cards", "#wr-meetings"):
        assert page.locator(sel).first.is_visible(), sel
    assert not page.locator("header.app-header").is_visible() and not page.locator("#bc-night .send-hero").is_visible()


def test_summary_shows_the_league_table_and_results_from_recorded_matches(page):
    _pick(page)
    _tab(page, "summary")
    table = page.locator("#bc-league .league-table tbody tr")
    cells = [[c.strip() for c in r.locator("td").all_text_contents()] for r in table.all()]
    by_name = {c[1].lower(): c for c in cells}
    assert by_name["owls"][2:] == ["1", "1", "0", "0", "3"] and by_name["sharks"][2:] == ["1", "0", "1", "0", "2"]
    assert page.locator("#bc-league tr.mine .tn").text_content().lower() == "sharks"
    assert "owls vs sharks" in page.locator("#bc-league .res-row").first.text_content().lower()
    assert "not apa" not in page.locator("#bc-league").text_content().lower() and "official table" in page.locator("#bc-league .sub").first.text_content()


def test_command_board_covers_the_whole_roster_with_engine_derived_roles(page):
    _pick(page)
    _tab(page, "matchnight")
    cards = page.locator("#bc-night .pcard")
    assert cards.count() == 3                                                          # every one of our three players
    texts = {c.locator(".pcard-name").text_content().split("SL")[0].strip().lower(): c for c in cards.all()}
    ann = texts["ann archer (player 1 of 2)"]
    assert "save for cam cole" in ann.locator(".precommend").text_content().lower()    # her only favorable answer
    assert ann.locator(".role").text_content().lower() == "protect"
    assert "best targets" in ann.text_content().lower() and "cam cole" in ann.text_content().lower()
    assert "avoid" in texts["bea baker"].text_content().lower()                        # her recorded losing record
    assert all(c.locator(".pwhatif").count() == 1 for c in cards.all())                # what the plan loses without each player
    page.click("#bc-night [data-path=theyLead]")
    assert page.locator("#bc-night .path-slots .slot").count() == 5 and "they put up" in page.locator("#bc-night .path-slots").text_content().lower()
    # sending a player moves them to Used and the board re-plans
    page.locator("#bc-night .send-hero [data-send]").click()
    assert page.locator("#bc-night .pcard.used").count() == 1


def test_command_board_shows_the_plan_after_each_send(page):
    _pick(page)
    _tab(page, "matchnight")
    assert "after this send" in page.locator("#bc-night .send-hero").text_content().lower()
    ann = [c for c in page.locator("#bc-night .pcard").all() if "ann archer" in c.text_content().lower()][0]
    assert "if used now vs cam cole" in ann.text_content().lower() and "plan after" in ann.text_content().lower()
    # the engine itself, re-solved with Ann and Cam Cole used, gives the same plan text
    after = page.evaluate("window.UC_BC_LAST.night.command.cards.filter(c=>c.name.indexOf('Ann Archer')===0)[0].targets[0].after")
    assert after["left"] == 1 and after["conf"]
    page.click("#bc-night .send-hero [data-send]")
    page.locator("#bc-night .night-chip").first.click()
    after_text = page.locator("#bc-night .send-after").text_content()
    assert "no remaining path" in after_text and "3 open slots" in after_text
    assert page.errors == []


def test_plain_print_carries_the_path_and_roster_and_the_captain_packet_is_unchanged(page):
    _pick(page)
    _tab(page, "matchnight")
    page.emulate_media(media="print")
    assert page.locator("#bc-night .cmd-main table.glance").is_visible()
    assert page.locator("#bc-night .cmd-main .path-slots").is_visible()
    assert not page.locator("#bc-night .send-hero").is_visible() and not page.locator("header.app-header").is_visible()
    page.evaluate("document.body.classList.add('print-matchup')")                      # the focused Captain Packet
    assert not page.locator("#bc-night").is_visible() and page.locator("#matchup-print").is_visible()
