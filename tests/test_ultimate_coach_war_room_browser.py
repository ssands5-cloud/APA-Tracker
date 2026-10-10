"""The HTML Captain's War Room in a real browser: it must reproduce
analytics/ultimate_coach_war_room.py exactly (same categories, cell texts,
explanations, sends, risks, scouting cards and meetings as the Excel
companion), follow Match Day, and keep the captain's planning marks out of
the evidence. Uses the all-categories fixture from the Excel formula tests."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright

from analytics.ultimate_coach_excel_payload import build_team_rosters
from analytics.ultimate_coach_matchup_evidence import build_pair_index, members_by_scope
from analytics.ultimate_coach_war_room import (SENDABLE, meetings_index, next_send, next_send_lines,
                                               sl_bucket_index, war_room_pair)
from tests.test_excel_war_room_formulas import _payload
from ui.ultimate_coach import render

OURS, THEIRS = "sharks-a|d1|Fall 2026", "falcons-a|d1|Fall 2026"
ANN, BEA, DEE = "Ann Archer (APA record ID 1001)", "Bea Baker (APA record ID 1002)", "Dee Diaz (APA record ID 1003)"
CAM, EVE = "Cam Cole (APA record ID 2001)", "Eve Ellis (APA record ID 2002)"


def _page(tmp_path: Path, browser):
    path = tmp_path / "wr.html"
    path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001"),
                    encoding="utf-8")
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(path.as_uri())
    page.wait_for_load_state("load")
    return page, errors


def _python_war_room():
    return _python_war_room_for(_payload())


def _python_war_room_for(payload):
    players = payload["players"]
    agg = defaultdict(lambda: [0, 0])
    for r in payload["evidence"]:
        a = agg[(r["player_id"], r["opponent_id"], r["format"])]
        a[1] += 1
        a[0] += r["result"] == "W"
    index = build_pair_index([{"player_id": p, "opponent_id": o, "format": f, "wins": w, "games": g}
                              for (p, o, f), (w, g) in agg.items()])
    members = members_by_scope(build_team_rosters(payload), players)
    ids = {p["id"] for p in players}
    return war_room_pair(members[OURS], members[THEIRS], index, "EIGHT",
                         sl_index=sl_bucket_index(payload["evidence"], ids),
                         meetings=meetings_index(payload["evidence"], ids, "America/Denver"),
                         players_by_id={p["id"]: p for p in players}, session_name="Fall 2026")


def test_html_war_room_matches_the_shared_python_module_exactly(tmp_path: Path):
    py = _python_war_room()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            js = page.evaluate(f"window.__ucWarRoomPair({OURS!r}, {THEIRS!r}, 'EIGHT')")
            assert js["matrix"] == [[[c["category"], c["cell"], c["explanation"], c["reason"], c["captain"]] for c in row["cells"]]
                                    for row in py["matrix"]]
            assert [[c for row in js["matrix"] for c in [x[0] for x in row]]] == [["G", "I", "R", "X", "E", "R"]]
            assert js["best"] == [[r["player"] for r in b["rows"] if r["category"] in SENDABLE] for b in py["blocks"]]
            assert js["concerning"] == [c["text"] for c in py["concerning"]]
            assert js["threats"] == [c["threat_text"] for c in py["threats"]]
            keys = ("quick_read", "sl", "team_record", "lifetime", "sample", "vs_ours", "met_list", "shared_summary", "by_sl",
                    "winning_sl", "losing_sl", "missing")
            assert js["cards"] == [[c[k] for k in keys] for c in py["cards"]]
            assert js["meetings"] == [[g["date"], g["our"]["id"], g["opp"]["id"], g["result"], g["session"]] for g in py["meetings"]]
            assert errors == []
        finally:
            browser.close()


def test_war_room_follows_match_day_and_marks_never_change_evidence(tmp_path: Path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            # Suggested date (earliest on/after the build date) and its single fixture are used automatically.
            assert page.input_value("#md-date") == "2026-10-11"
            assert "Suggested: the earliest scheduled date on or after the build date." in page.inner_text("#md-status")
            assert page.input_value("#team-a") == OURS and page.input_value("#team-b") == THEIRS
            sends = page.inner_text("#wr-opportunities")
            assert f"1. {ANN} — 2-0 (2)" in sends and f"2. {DEE} — 1-1 (2)" in sends
            assert f"≈ {ANN} — ≈ 1-0 vs 0-1 (1 shared)" in sends and f"1. {ANN} — ≈" not in sends
            risks = page.inner_text("#wr-risks")
            assert f"{EVE} · SL 3 · 2-0 vs our roster (2 meetings, 1 of our players)" in risks
            assert f"{BEA} vs {CAM}: 0-2 direct (2 meetings)" in risks
            cells = page.locator("#wr-matrix .mcell")
            assert [cells.nth(i).inner_text() for i in range(6)] == [
                "2-0 (2)", "≈ 1-0 vs 0-1 (1 shared)", "0-2 (2)", "No verified evidence", "1-1 (2)", "0-2 (2)"]
            assert "cat-G" in cells.nth(0).get_attribute("class") and "cat-X" in cells.nth(3).get_attribute("class")
            before = page.evaluate(f"JSON.stringify(window.__ucWarRoomPair({OURS!r}, {THEIRS!r}, 'EIGHT'))")

            # Ann unavailable: she leaves the candidates, Dee becomes the send vs Cam, Eve becomes an open risk.
            page.select_option('#lineup-lab select[data-plan="avail"][data-pid="1"]', "Unavailable")
            sends = page.inner_text("#wr-opportunities")
            assert f"1. {DEE} — 1-1 (2)" in sends and ANN not in sends
            assert "No favorable, even or indirect evidence among our remaining players." in sends
            assert f"{EVE} — no evidence-backed option left" in page.inner_text("#wr-risks")
            lab = page.inner_text("#lineup-lab")
            assert "2 of 3 (2 with unknown availability — still counted as remaining)" in lab
            assert "4 known subtotal · 1 remaining player(s) without a captured SL — not a complete total" in lab
            # Evidence is untouched by marks.
            assert page.evaluate(f"JSON.stringify(window.__ucWarRoomPair({OURS!r}, {THEIRS!r}, 'EIGHT'))") == before
            assert page.locator("#wr-matrix .mcell").nth(0).inner_text() == "2-0 (2)"

            # Reference cap only when entered; selected lineup totals disclose missing SLs.
            page.select_option('#lineup-lab select[data-plan="lineup"][data-pid="2"]', "Planned")
            page.select_option('#lineup-lab select[data-plan="lineup"][data-pid="3"]', "Played")
            assert "your reference cap" not in page.inner_text("#lineup-lab")
            page.fill("#ll-cap", "23")
            page.press("#ll-cap", "Enter")
            page.locator("#ll-cap").blur()
            assert ("Known subtotal 4 · 1 selected player(s) without a captured SL · your reference cap: 23 "
                    "(user-entered, not verified) — not a lineup-legality check.") in page.inner_text("#lineup-lab")

            # Opponent played retires that opponent; notes reach the scouting card and survive reloads.
            page.check('#lineup-lab input[data-plan="played"][data-pid="10"]')
            assert "Already played." in page.inner_text("#wr-opportunities")
            page.fill('#scouting-cards textarea[data-pid="11"]', "Breaks hard")
            page.reload()
            page.wait_for_load_state("load")
            assert page.input_value('#scouting-cards textarea[data-pid="11"]') == "Breaks hard"
            assert page.input_value('#lineup-lab select[data-plan="avail"][data-pid="1"]') == "Unavailable"

            # Marks belong to the team they were made for: another opponent starts clean.
            page.fill("#search-team-b", "Owls")
            page.wait_for_timeout(400)
            page.select_option("#team-b", "owls-a|d1|Fall 2026")
            assert "Already played." not in page.inner_text("#wr-opportunities")

            assert errors == []
        finally:
            browser.close()


def test_matrix_cell_opens_the_evidence_behind_it(tmp_path: Path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            page.locator("#wr-matrix .mcell").nth(1).click()   # Ann vs Eve: shared opponents only
            detail = page.inner_text("#wr-pair")
            assert f"{ANN} vs {EVE}" in detail and "Indirect evidence only" in detail
            assert "Zed Zane (APA record ID 2003)" in detail and "1-0 (1 game)" in detail and "0-1 (1 game)" in detail
            page.locator("#wr-matrix .mcell").nth(0).click()   # Ann vs Cam: direct 2-0
            detail = page.inner_text("#wr-pair")
            assert "Favorable direct record" in detail and "Sun Sep 20, 2026" in detail
            assert errors == []
        finally:
            browser.close()


def test_html_career_text_matches_python_for_incomplete_and_zero_records(tmp_path: Path):
    """Same four cases as the Python regression: the HTML scouting card must never show 0-10 for unknown wins."""
    from analytics.ultimate_coach_war_room import _career_text
    cases = [[(None, 10)], [(4, None)], [(6, 8), (None, 10), (3, None)], [(0, 10)], [(0, 0)], []]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            for rows in cases:
                stats = [{"format": "EIGHT", "matches_won": w, "matches_played": g} for w, g in rows]
                js = page.evaluate("s => window.__ucCareerText({career_stats: s}, 'EIGHT')", stats)
                assert js == _career_text({"career_stats": stats}, "EIGHT"), rows
            assert errors == []
        finally:
            browser.close()


def test_planning_marks_belong_to_one_fixture_and_notes_follow_the_player(tmp_path: Path):
    """GPT audit #84 repro: Played on Oct 11 must not leak into the Oct 25 Falcons fixture."""
    ann_l = '#lineup-lab select[data-plan="lineup"][data-pid="1"]'
    ann_a = '#lineup-lab select[data-plan="avail"][data-pid="1"]'
    cam_p = '#lineup-lab input[data-plan="played"][data-pid="10"]'
    cam_note = '#scouting-cards textarea[data-pid="10"]'

    def oct25_falcons(page):
        page.fill("#md-date", "2026-10-25")
        assert "2 scheduled matches" in page.inner_text("#md-status")      # never auto-picked
        cards = page.locator("#md-fixtures .fixture")
        idx = [i for i in range(cards.count()) if "Falcons" in cards.nth(i).inner_text()][0]
        page.click(f"#md-compare-{idx}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            assert "Oct 11, 2026" in page.inner_text("#ll-context")
            page.select_option(ann_l, "Played")
            page.check(cam_p)
            page.fill(cam_note, "Slow safeties")

            oct25_falcons(page)                                   # same teams, different fixture
            assert "Oct 25, 2026" in page.inner_text("#ll-context")
            assert page.input_value(ann_l) == "" and not page.is_checked(cam_p)
            assert page.input_value(cam_note) == "Slow safeties"  # notes describe the player
            page.select_option(ann_a, "Unavailable")

            page.fill("#md-date", "2026-10-11")                   # back: Oct 11 marks return, Oct 25's don't
            assert page.input_value(ann_l) == "Played" and page.is_checked(cam_p)
            assert page.input_value(ann_a) == "Unknown"

            page.reload(); page.wait_for_load_state("load")       # survives reload, still per fixture
            assert page.input_value(ann_l) == "Played" and page.is_checked(cam_p)
            oct25_falcons(page)
            assert page.input_value(ann_a) == "Unavailable" and page.input_value(ann_l) == ""

            # Same date, other fixture (vs Owls): a different opponent and fixture -> clean.
            page.fill("#md-date", "2026-10-25")
            page.click("#md-compare-0")
            assert "Owls" in page.inner_text("#team-rosters") and page.input_value(ann_a) == "Unknown"

            # Teams picked by hand (no fixture): its own context, no fixture's marks.
            page.fill("#search-team-b", "Falcons"); page.wait_for_timeout(400)
            page.select_option("#team-b", THEIRS)
            assert "picked by hand" in page.inner_text("#ll-context")
            assert page.input_value(ann_l) == "" and page.input_value(ann_a) == "Unknown" and not page.is_checked(cam_p)
            assert errors == []
        finally:
            browser.close()


def test_first_screen_shows_tonight_before_setup(tmp_path: Path):
    """GPT visual audit: the first viewport must show the fixture and decision overview, not only setup."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for vp in ({"width": 1280, "height": 900}, {"width": 390, "height": 844}):
                page, errors = _page(tmp_path, browser)
                page.set_viewport_size(vp)
                box = page.locator("#tonight").bounding_box()
                assert box and box["y"] < vp["height"] * 0.6, (vp, box)
                text = page.inner_text("#tonight")
                assert "Sun Oct 11, 2026 · 11:00 AM MDT" in text and "Sharks" in text and "Falcons" in text
                assert "vs Cam Cole: Ann Archer — 2-0 (2) direct" in text and "Eve Ellis — 2-0 vs our roster (2 meetings)" in text
                assert "vs Eve Ellis: Ann Archer — ≈ shared-opponent only (the only shared-opponent candidate)" in text
                assert page.evaluate("document.documentElement.scrollWidth") <= vp["width"]
                assert errors == []
                page.close()
        finally:
            browser.close()


# ---- GPT audit #84 (Paul's real HTML UAT): a Match Day change with no applicable fixture must not leave the
# previous fixture's Tonight panel, opponent, sends or print context on screen.

def _stale_page(tmp_path: Path, browser):
    from analytics.ultimate_coach_match_day import build_match_day_section
    from tests.test_excel_war_room_formulas import _fixture
    payload = _payload()
    raw = [_fixture(1, "2026-10-11T11:00:00-06:00", "sharks-a", "falcons-a"),
           _fixture(2, "2026-11-01T11:00:00-07:00", "sharks-a", "bye", bye=True),
           _fixture(3, "2026-10-25T11:00:00-06:00", "sharks-a", "owls-a"),
           _fixture(4, "2026-10-25T19:00:00-06:00", "sharks-a", "falcons-a"),
           _fixture(7, "2026-11-08T11:00:00-07:00", "sharks-a", "owls-a")]
    raw[-1]["away_team_id"], raw[-1]["away_team_name"] = "ghosts-a", "Ghosts"   # no captured roster
    payload["match_day"] = build_match_day_section(raw, payload["players"])
    path = tmp_path / "stale.html"
    path.write_text(render(payload, built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001"), encoding="utf-8")
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(path.as_uri())
    page.wait_for_load_state("load")
    return page, errors


def _assert_no_followed_fixture(page, *, expect):
    tonight = page.inner_text("#tonight")
    assert "Oct 11" not in tonight and "Falcons" not in tonight and "Cam Cole" not in tonight, tonight
    assert expect in tonight, (expect, tonight)
    assert page.input_value("#team-a") == "" and page.input_value("#team-b") == ""
    for sel in ("#wr-opportunities", "#wr-risks", "#wr-matrix", "#lineup-lab", "#scouting-cards", "#wr-meetings"):
        assert page.inner_text(sel).strip() == "", sel
    assert page.locator("#print-matchup").count() == 0          # nothing to print for an old fixture


def _assert_oct11(page):
    tonight = page.inner_text("#tonight")
    assert "Sun Oct 11, 2026 · 11:00 AM MDT" in tonight and "Falcons" in tonight
    assert page.input_value("#team-a") == OURS and page.input_value("#team-b") == THEIRS
    assert f"1. {ANN} — 2-0 (2)" in page.inner_text("#wr-opportunities")


def test_match_day_change_without_an_applicable_fixture_clears_the_followed_matchup(tmp_path: Path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _stale_page(tmp_path, browser)
            _assert_oct11(page)
            page.fill("#md-date", "2026-11-26")                                   # valid date, no match
            _assert_no_followed_fixture(page, expect="No scheduled match")
            assert "Thu Nov 26, 2026" in page.inner_text("#tonight")
            page.fill("#md-date", "2026-10-11"); _assert_oct11(page)               # return restores
            page.fill("#md-date", "2026-11-01")                                   # bye
            _assert_no_followed_fixture(page, expect="Bye")
            assert "Sun Nov 1, 2026" in page.inner_text("#tonight") and "MST" in page.inner_text("#tonight")
            page.fill("#md-date", "2026-11-08")                                   # opponent without a roster
            _assert_no_followed_fixture(page, expect="Ghosts")
            assert "roster" in page.inner_text("#tonight")
            page.fill("#md-date", "2026-10-25")                                   # two fixtures: none chosen
            _assert_no_followed_fixture(page, expect="2 fixtures")
            page.click("#md-compare-1")                                           # explicit choice applies
            assert "Oct 25, 2026" in page.inner_text("#tonight") and page.input_value("#team-b") == THEIRS
            page.fill("#md-date", "2026-10-11"); _assert_oct11(page)
            page.select_option("#md-viewer", "4")                                 # a player with no current team
            _assert_no_followed_fixture(page, expect="No current team")
            assert errors == []
        finally:
            browser.close()


def test_manual_exploration_is_labelled_and_a_match_day_change_returns_to_following(tmp_path: Path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _stale_page(tmp_path, browser)
            page.fill("#search-team-b", "Owls"); page.wait_for_timeout(400)
            page.select_option("#team-b", "owls-a|d1|Fall 2026")
            tonight = page.inner_text("#tonight")
            assert "Teams picked by hand" in tonight and "Owls" in tonight and "Oct 11" not in tonight
            page.fill("#md-date", "2026-11-26")                                   # Match Day change: follow again
            _assert_no_followed_fixture(page, expect="No scheduled match")
            page.fill("#md-date", "2026-10-11"); _assert_oct11(page)
            assert errors == []
        finally:
            browser.close()


# ---- HTML parity with the Excel START HERE / Command Center / Coach Notes (plan:
# docs/superpowers/plans/2026-10-07-html-onboarding-command-center-coach-notes.md) ----

def test_start_here_card_explains_the_cockpit_and_remembers_being_closed(tmp_path: Path):
    from analytics.ultimate_coach_war_room import ONBOARDING_LIMITS
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            card = page.locator("#start-here")
            assert card.get_attribute("open") is not None                     # open on a first visit
            text = card.inner_text()
            for needle in ("What Ultimate Coach does", "Quick start", "Match Day", "Lineup Lab", "Print",
                           "Build date: Wed Oct 7, 2026", "latest recorded result Sun Sep 27, 2026", "Version: ",
                           f"1 · Player: {ANN}", "4 · Scheduled date: Sun Oct 11, 2026",
                           "5 · Fixture: Home vs Falcons · Fall 2026 · 8-Ball (the only fixture that day"):
                assert needle in text, needle
            for line in ONBOARDING_LIMITS:                                      # same limitations as Excel
                assert line.lstrip("• ") in text, line
            for href in ("#match-day-card", "#team-section", "#lineup-lab", "#scouting-cards"):
                assert card.locator(f'a[href="{href}"]').count() >= 1, href
            page.click("#start-here summary")
            page.wait_for_function("localStorage.getItem('ultimate-coach:start-here-closed') === '1'")
            page.reload(); page.wait_for_load_state("load")
            assert page.locator("#start-here").get_attribute("open") is None    # remembered closed
            assert errors == []
        finally:
            browser.close()


def test_tonight_is_a_command_center_with_excels_counts(tmp_path: Path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            t = page.inner_text("#tonight")
            for needle in ("Available: 0", "Unavailable: 0", "Unknown: 3 (not the same as unavailable)",
                           "Already used: 0 · planned: 0",
                           "Favorable direct record (any sample size): 1", "Concerning (more direct losses than wins): 2",
                           "Limited evidence: 1 even direct · 1 shared-opponent only", "Insufficient verified evidence in this snapshot: 1",
                           "Missing information: 0 player(s) without a captured SL · 2 not yet played"):
                assert needle in t, needle
            lines = t.splitlines()                                         # each count on its own line
            for needle in ("Available: 0", "Unavailable: 0", "Concerning (more direct losses than wins): 2"):
                assert needle in lines, needle
            page.select_option('#lineup-lab select[data-plan="avail"][data-pid="1"]', "Unavailable")
            page.select_option('#lineup-lab select[data-plan="lineup"][data-pid="2"]', "Played")
            t = page.inner_text("#tonight")
            assert "Unavailable: 1" in t and "Unknown: 2 (not the same as unavailable)" in t and "Already used: 1 · planned: 0" in t
            assert errors == []
        finally:
            browser.close()


def test_coach_notes_are_tagged_per_player_durable_and_never_evidence(tmp_path: Path):
    from analytics.ultimate_coach_war_room import COACH_TAGS
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            before = page.evaluate(f"JSON.stringify(window.__ucWarRoomPair({OURS!r}, {THEIRS!r}, 'EIGHT'))")
            card = page.locator("#scouting-cards .scout").first
            assert "Your opinion, not APA facts." in card.inner_text()
            options = card.locator('select[data-plan="tag1"] option').all_text_contents()
            assert options[1:] == COACH_TAGS
            card.locator('select[data-plan="tag1"]').select_option("Slow shooter")
            card.locator('select[data-plan="tag2"]').select_option("Strong safety player")
            card.locator('textarea[data-plan="note"]').fill("Plays the long game")
            summary = "Coach: Slow shooter · Strong safety player: Plays the long game"
            assert card.locator(".coach-summary").inner_text() == summary
            assert page.evaluate(f"JSON.stringify(window.__ucWarRoomPair({OURS!r}, {THEIRS!r}, 'EIGHT'))") == before
            page.fill("#md-date", "2026-10-25"); page.click("#md-compare-1")        # another fixture, same player
            assert page.locator("#scouting-cards .scout").first.locator(".coach-summary").inner_text() == summary
            page.reload(); page.wait_for_load_state("load")
            assert page.locator("#scouting-cards .scout").first.locator(".coach-summary").inner_text() == summary
            # Notes written by the earlier (per-team) version are kept, now on the player.
            page.evaluate("""() => { const k='ultimate-coach:plan-v2'; const o=JSON.parse(localStorage.getItem(k));
                o.coach={}; o.notes={'falcons-a|d1|Fall 2026': {'11': {n: 'Old note'}}}; localStorage.setItem(k, JSON.stringify(o)); }""")
            page.reload(); page.wait_for_load_state("load")
            assert page.locator("#scouting-cards .scout").nth(1).locator(".coach-summary").inner_text() == "Coach: Old note"
            assert errors == []
        finally:
            browser.close()



def test_cleared_migrated_coach_note_stays_cleared(tmp_path: Path):
    """GPT audit #84 repro: legacy note imported, cleared by the captain, then reload must not bring it back."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            page.evaluate("""() => { const k='ultimate-coach:plan-v2'; const o=JSON.parse(localStorage.getItem(k)||'{}');
                o.coach={}; o.notes={'falcons-a|d1|Fall 2026': {'10': {n: 'SYNTHETIC legacy note'}}}; localStorage.setItem(k, JSON.stringify(o)); }""")
            page.reload(); page.wait_for_load_state("load")
            card = page.locator("#scouting-cards .scout").first
            assert card.locator(".coach-summary").inner_text() == "Coach: SYNTHETIC legacy note"
            card.locator('textarea[data-plan="note"]').fill("")
            page.reload(); page.wait_for_load_state("load")
            assert page.locator("#scouting-cards .scout").first.locator(".coach-summary").inner_text() == ""
            card = page.locator("#scouting-cards .scout").first
            card.locator('textarea[data-plan="note"]').fill("Replacement")
            page.reload(); page.wait_for_load_state("load")
            assert page.locator("#scouting-cards .scout").first.locator(".coach-summary").inner_text() == "Coach: Replacement"
            assert errors == []
        finally:
            browser.close()


def test_player_vs_player_reads_like_coaching_software(tmp_path: Path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            assert page.title() == "Ultimate Coach — Captain's War Room"
            page.select_option("#player-a", "1"); page.wait_for_timeout(200)
            page.select_option("#player-b", "10"); page.wait_for_timeout(200)
            section = page.inner_text("#player-section")
            assert "in EIGHT" not in section and "in 8-Ball" in section
            meetings = page.inner_text("#meetings")
            assert "Sun Sep 20, 2026" in meetings and "T19:00" not in meetings
            # The page shows historical percentages, so the banner separates them from predictions (GPT #84).
            assert "Lifetime win rate" in section          # a historical percentage slot (— without career data)
            status = page.inner_text("#status")
            assert status.startswith("Win probability: NOT CALIBRATED — no predicted odds are shown.")
            assert "historical win rates" in status and "not a prediction" in status
            assert "Scout & Compare" not in status and "before a percentage appears" not in status
            th = page.locator("#wr-matrix thead th").nth(1)
            assert th.locator(".id-line").evaluate("e => getComputedStyle(e).display") == "block"
            assert errors == []
        finally:
            browser.close()


def test_next_send_card_matches_python_and_mark_sent_moves_the_night_forward(tmp_path: Path):
    py = _python_war_room()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            for j in range(len(py["blocks"])):
                for remaining, unplayed in ((None, None), ([3], None), (None, [True, False])):
                    js = page.evaluate(f"window.__ucNextSend({OURS!r}, {THEIRS!r}, 'EIGHT', {j}, "
                                       f"{'null' if remaining is None else remaining}, "
                                       f"{'null' if unplayed is None else str(unplayed).lower()})")
                    ids = None if remaining is None else set(remaining)
                    assert js == next_send_lines(next_send(py, j, remaining=ids, unplayed=unplayed)), (j, remaining)
            card = page.locator("#tonight #next-send")
            text = card.inner_text()
            assert "WHO SHOULD I SEND NEXT?" in text.upper() and "They put up:" in text
            assert "🥇 Ann Archer — 2-0 direct record (2 meetings)" in text   # the medal line is the answer
            assert text.count("availability unknown") == 2                     # said at the action, still eligible
            page.select_option('#lineup-lab select[data-plan="avail"][data-pid="1"]', "Available")
            assert page.locator("#next-send .ns-medal").nth(0).inner_text().count("availability unknown") == 0
            assert page.locator("#next-send .ns-medal").nth(1).inner_text().count("availability unknown") == 1
            page.select_option('#lineup-lab select[data-plan="avail"][data-pid="1"]', "Unknown")
            text = card.inner_text()
            # Below the medals, the rest is one line that still names the players; tapping shows each reason.
            assert card.locator(".ns-more summary").inner_text() == "⚠ Avoid: Bea Baker (0-2)"
            card.locator(".ns-more summary").click()
            assert "⚠ Avoid Bea Baker — 0-2 direct record (2 meetings) — concerning" in card.inner_text()
            # Chips: tap Eve -> shared-only, never medalled.
            page.click("#next-send .ns-chip:has-text('Eve Ellis')")
            text = page.locator("#next-send").inner_text()
            assert "shared-opponent candidates only (≈, not ordered)" in text and "🥇" not in text
            # A coach note on Eve is shown as opinion.
            page.fill('#scouting-cards textarea[data-pid="11"]', "Slow, careful safeties")
            page.click("#next-send .ns-chip:has-text('Cam Cole')")
            page.click("#next-send .ns-chip:has-text('Eve Ellis')")
            assert "📝 Coach: Slow, careful safeties (your opinion, not APA facts)" in page.locator("#next-send").inner_text()
            assert "📝 Coach: Slow, careful safeties (opinion)" in page.inner_text("#tonight .decide-threats")
            assert "📝 Coach: Slow, careful safeties (your opinion, not APA facts)" in page.inner_text("#wr-risks")
            # ✓ Sent vs Cam: Ann Played, Cam played; Eve is the only chip left and Ann no longer appears.
            page.click("#next-send .ns-chip:has-text('Cam Cole')")
            page.click("#next-send .ns-send[data-send-our='1']")
            chips = page.locator("#next-send .ns-chip")
            assert chips.count() == 1 and "Eve Ellis" in chips.nth(0).inner_text()
            assert "Ann Archer" not in page.locator("#next-send").inner_text()
            assert page.input_value('#lineup-lab select[data-plan="lineup"][data-pid="1"]') == "Played"
            assert page.is_checked('#lineup-lab input[data-plan="played"][data-pid="10"]')
            assert errors == []
        finally:
            browser.close()


def test_scouting_cards_open_with_a_quick_read_and_never_clip_on_a_phone(tmp_path: Path):
    py = _python_war_room()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            path = tmp_path / "wr.html"
            path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001"),
                            encoding="utf-8")
            page = browser.new_context(**pw.devices["Pixel 7"]).new_page()
            page.goto(path.as_uri())
            page.wait_for_selector("#scouting-cards .scout")
            reads = page.locator("#scouting-cards .quick-read")
            assert [reads.nth(i).inner_text().replace("QUICK READ", "Quick read").split(" ", 2)[2]
                    for i in range(reads.count())] == [c["quick_read"] for c in py["cards"]]
            assert py["cards"][1]["quick_read"].startswith("Threat: 2-0 vs our roster (2 meetings) · No direct answer")
            clipped = page.evaluate("""[...document.querySelectorAll('#scouting-cards .scout')]
                .filter(c => [...c.querySelectorAll('dd')].some(d => d.getBoundingClientRect().right > c.getBoundingClientRect().right + 0.5)).length""")
            assert clipped == 0
            # Next Send opponents are one swipeable row on a phone (a real roster has 8 long names).
            assert page.evaluate("getComputedStyle(document.querySelector('#next-send .ns-chips')).flexWrap") == "nowrap"
            tops = page.evaluate("[...document.querySelectorAll('#next-send .ns-chip')].map(c => Math.round(c.getBoundingClientRect().top))")
            assert len(set(tops)) == 1
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        finally:
            browser.close()


def test_matrix_captain_view_is_a_remembered_toggle_over_the_same_evidence(tmp_path: Path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            cells = page.locator("#wr-matrix .mcell")
            evidence = [cells.nth(i).inner_text() for i in range(6)]
            assert evidence[0] == "2-0 (2)"                                   # Evidence view by default (= Excel)
            before = page.evaluate(f"JSON.stringify(window.__ucWarRoomPair({OURS!r}, {THEIRS!r}, 'EIGHT'))")
            page.click("#wr-matrix .mv[data-view='captain']")
            assert [cells.nth(i).inner_text() for i in range(6)] == ["🟢 2-0", "🟡 ≈", "🔴 0-2", "⚪", "🟡 1-1", "🔴 0-2"]
            assert "unknown, not weak" in page.inner_text("#wr-matrix")
            assert "cat-G" in cells.nth(0).get_attribute("class")              # colors and categories unchanged
            page.reload()
            page.wait_for_selector("#wr-matrix .mcell")
            assert page.locator("#wr-matrix .mcell").nth(0).inner_text() == "🟢 2-0"   # remembered on this device
            page.locator("#wr-matrix .mcell").nth(0).click()                   # cells still open the evidence
            assert "Favorable direct record" in page.inner_text("#wr-pair")
            page.click("#wr-matrix .mv[data-view='evidence']")
            assert [page.locator("#wr-matrix .mcell").nth(i).inner_text() for i in range(6)] == evidence
            assert page.evaluate(f"JSON.stringify(window.__ucWarRoomPair({OURS!r}, {THEIRS!r}, 'EIGHT'))") == before
            assert errors == []
        finally:
            browser.close()


def test_legacy_notes_from_every_scope_are_preserved_and_clearing_never_resurrects(tmp_path: Path):
    """GPT audit #84 P2 (preservation variant): two different legacy observations for one player under two team
    scopes, and a legacy note that differs from an existing coach note, must all survive migration."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            page.evaluate("""() => { const k='ultimate-coach:plan-v2'; const o=JSON.parse(localStorage.getItem(k)||'{}');
                o.coach={'11': {n: 'SYNTHETIC current note'}};
                o.notes={'falcons-a|d1|Fall 2026': {'10': {n: 'SYNTHETIC scope A note'}, '11': {n: 'SYNTHETIC older Eve note'}},
                         'owls-a|d1|Fall 2026': {'10': {n: 'SYNTHETIC scope B note'}}};
                localStorage.setItem(k, JSON.stringify(o)); }""")
            page.reload(); page.wait_for_load_state("load")
            cam, eve = page.locator("#scouting-cards .scout").nth(0), page.locator("#scouting-cards .scout").nth(1)
            assert cam.locator(".coach-summary").inner_text() == "Coach: SYNTHETIC scope A note"
            assert "SYNTHETIC scope B note" in cam.locator(".coach-archive").inner_text()          # not lost
            assert eve.locator(".coach-summary").inner_text() == "Coach: SYNTHETIC current note"   # current wins
            assert "SYNTHETIC older Eve note" in eve.locator(".coach-archive").inner_text()        # legacy kept
            stored = page.evaluate("JSON.parse(localStorage.getItem('ultimate-coach:plan-v2'))")
            assert stored["notes"] == {} and len(stored["archive"]["10"]) == 1                      # migrated once
            cam.locator('textarea[data-plan="note"]').fill("")                                     # clear: stays clear
            page.reload(); page.wait_for_load_state("load")
            cam = page.locator("#scouting-cards .scout").nth(0)
            assert cam.locator(".coach-summary").inner_text() == ""
            assert cam.locator('textarea[data-plan="note"]').input_value() == ""
            assert "SYNTHETIC scope B note" in cam.locator(".coach-archive").inner_text()
            assert errors == []
        finally:
            browser.close()


def test_send_lists_and_best_send_text_match_python_including_ties(tmp_path: Path):
    from analytics.ultimate_coach_war_room import best_send_text, send_list_text
    from tests.test_excel_war_room_formulas import _tied_payload
    payload = _tied_payload()
    py = _python_war_room_for(payload)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            path = tmp_path / "tied.html"
            path.write_text(render(payload, built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001"), encoding="utf-8")
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            for remaining in (None, [3, 5], [1, 2, 3]):
                js = page.evaluate(f"window.__ucSendTexts({OURS!r}, {THEIRS!r}, 'EIGHT', {'null' if remaining is None else remaining})")
                ids = None if remaining is None else set(remaining)
                expected = []
                for b in py["blocks"]:
                    rows = [r for r in b["rows"] if r["category"] in SENDABLE and (ids is None or r["member"]["id"] in ids)]
                    expected.append([send_list_text(rows), best_send_text(rows)])
                assert js == expected, remaining
            assert js[0][0].startswith("1. ") and "1= " in page.evaluate(f"window.__ucSendTexts({OURS!r}, {THEIRS!r}, 'EIGHT', null)")[0][0]
            assert "1= Ann Archer" in page.inner_text("#wr-opportunities") and "1= Fay Fox" in page.inner_text("#wr-opportunities")
            assert "best-supported send (tied with 1 other, same evidence): Ann Archer" in page.inner_text("#lineup-lab")
        finally:
            browser.close()
