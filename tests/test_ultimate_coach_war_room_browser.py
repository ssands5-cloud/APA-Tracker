"""The HTML Captain's War Room in a real browser: it must reproduce
analytics/ultimate_coach_war_room.py exactly (same categories, cell texts,
explanations, sends, risks, scouting cards and meetings as the Excel
companion), follow Match Day, and keep the captain's planning marks out of
the evidence. Uses the all-categories fixture from the Excel formula tests."""

from __future__ import annotations

import difflib
from collections import defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright

from analytics.ultimate_coach_excel_payload import build_team_rosters
from analytics.ultimate_coach_matchup_evidence import build_pair_index, members_by_scope
from analytics.ultimate_coach_war_room import (SENDABLE, meetings_index, next_send, next_send_lines,
                                               sl_bucket_index, war_room_pair)
from tests.test_excel_war_room_formulas import _games, _payload
from ui.ultimate_coach import render

OURS, THEIRS = "sharks-a|d1|Fall 2026", "falcons-a|d1|Fall 2026"
ANN, BEA, DEE = "Ann Archer (player 1 of 2)", "Bea Baker", "Dee Diaz"
CAM, EVE = "Cam Cole", "Eve Ellis"

# GPT audit (349815e) explicit authorization: "No coach observations" is metadata
# about the opinion (whether a note exists), not evidence the opinion could
# corrupt, so the isolation guard below allows exactly this one sentinel line to
# appear or disappear. It is matched by its full literal text, not by tag or
# selector -- GPT fba0f15 showed a tag-shaped exemption lets an unrelated change
# of the same tag ride along unnoticed, which is exactly the hole this avoids.
_NOTE_BADGE_SENTINEL = "T|SPAN|❓ No coach observations"

# GPT audit (issue #84, NOTES-01): the matrix header and the Best-sends opportunities table
# flag a noted opponent with the bare glyph alone (the note text itself lives in a title
# attribute, not a text node, so it carries no identifying text to exempt it the way the
# preview-style occurrences elsewhere are already exempted by containing the note). This is the
# same class of authorized live metadata as the badge above -- whether a note exists, not
# evidence it could corrupt -- so up to one occurrence per of those two icon-style locations may
# appear or disappear, matched by the exact literal glyph text, same bar as the sentinel above,
# not a tag-shaped exemption.
_NOTE_FLAG_GLYPH_LINE = "T|A|📝"
_NOTE_FLAG_GLYPH_LOCATIONS = 2


def _leaked_excluding_note_badge(changed: list[str], note: str) -> list[str]:
    """changed lines that are neither the note itself, the one authorized note-presence badge
    toggling off or on, nor the bare note-flag glyph toggling in its (at most two) icon-style
    locations. Each is capped so a second, unrelated change that happened to collide with the
    exact text is still caught rather than silently absorbed by the exemption."""
    badge_toggle = [line for line in changed
                    if line in ("+" + _NOTE_BADGE_SENTINEL, "-" + _NOTE_BADGE_SENTINEL)]
    assert len(badge_toggle) <= 1, f"note-presence badge moved more than once: {badge_toggle!r}"
    rest = [line for line in changed if line not in badge_toggle]
    glyph_toggle = [line for line in rest
                    if line in ("+" + _NOTE_FLAG_GLYPH_LINE, "-" + _NOTE_FLAG_GLYPH_LINE)]
    assert len(glyph_toggle) <= _NOTE_FLAG_GLYPH_LOCATIONS, (
        f"note-flag glyph moved in more locations than expected: {glyph_toggle!r}")
    rest = [line for line in rest if line not in glyph_toggle]
    return [line for line in rest if note not in line]


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
            # Superseded wording: see the Threat Panel gap fix (live_threats) -- scoped to
            # players still in tonight's lineup rather than our whole roster's history.
            assert f"{EVE} · SL 3 · 2-0 vs our roster still in play (2 meetings, 1 of our remaining players)" in risks
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
            assert "Zed Zane" in detail and "1-0 (1 game)" in detail and "0-1 (1 game)" in detail
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
                assert "vs Cam Cole: Ann Archer — 2-0 (2) direct" in text
                # Superseded wording: see the Threat Panel gap fix (live_threats).
                assert "Eve Ellis — 2-0 (2 meetings, small sample)" in text  # Tonight is compact; full detail (SL, meeting count) is in the War Room panel
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
            # "If they put up:" until the captain taps the opponent they actually sent (BLIND-01 #4).
            assert "WHO SHOULD I SEND NEXT?" in text.upper() and "they put up:" in text.lower()
            assert "1. Ann Archer (player 1 of 2) — 2-0 direct record (2 meetings)" in text   # the medal line is the answer
            assert text.count("availability unknown") == 2                     # said at the action, still eligible
            page.select_option('#lineup-lab select[data-plan="avail"][data-pid="1"]', "Available")
            assert page.locator("#next-send .ns-medal").nth(0).inner_text().count("availability unknown") == 0
            assert page.locator("#next-send .ns-medal").nth(1).inner_text().count("availability unknown") == 1
            page.select_option('#lineup-lab select[data-plan="avail"][data-pid="1"]', "Unknown")
            text = card.inner_text()
            # Below the medals, the rest is one line that still names the players; tapping shows each reason.
            assert card.locator(".ns-more summary").inner_text() == "⚠ Avoid: Bea Baker (0-2 (2 meetings), small sample)"
            card.locator(".ns-more summary").click()
            assert "⚠ Avoid Bea Baker — 0-2 direct record (2 meetings) — concerning · small sample" in card.inner_text()
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
            assert py["cards"][1]["quick_read"].startswith("Threat: 2-0 vs our roster (2 meetings, small sample) · No direct answer")
            clipped = page.evaluate("""[...document.querySelectorAll('#scouting-cards .scout')]
                .filter(c => [...c.querySelectorAll('dd')].some(d => d.getBoundingClientRect().right > c.getBoundingClientRect().right + 0.5)).length""")
            assert clipped == 0
            # Next Send opponents are one swipeable row on a phone (a real roster has 8 long names).
            assert page.evaluate("getComputedStyle(document.querySelector('#next-send .ns-chips')).flexWrap") == "nowrap"
            tops = page.evaluate("[...document.querySelectorAll('#next-send .ns-chip')].map(c => Math.round(c.getBoundingClientRect().top))")
            assert len(set(tops)) == 1
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            sizes=page.locator("#next-send .ns-send, #next-send .ns-chip").evaluate_all(
                "els=>els.map(e=>{let r=e.getBoundingClientRect();return [r.width,r.height]})")
            assert sizes and all(w>=44 and h>=44 for w,h in sizes),sizes
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
            assert "first by recorded direct results (tied with 1 other, same evidence): Ann Archer" in page.inner_text("#lineup-lab")
        finally:
            browser.close()


def test_a_coach_note_is_remembered_cleared_and_never_changes_the_evidence(tmp_path: Path):
    """Issue #84 scenario 8: a note saves, survives a reload, does NOT come back
    after being cleared, and never moves the evidence.

    The cockpit keeps planning marks and notes under its own localStorage key,
    `ultimate-coach:plan-v2`. The Match Night phone app's `match-night:*` keys
    already have persistence tests; this key had none, so a regression in the
    cockpit's own storage would have gone unnoticed.

    The evidence assertion is the point of the whole feature: a note is the
    coach's opinion, and if writing one could reorder the ranked evidence then
    opinion would be quietly laundering itself into fact.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            page.wait_for_timeout(400)
            note = "ZZTESTNOTE-breaks-hard-off-the-rail"
            tables = lambda: page.eval_on_selector_all(
                "table", "els => els.slice(0, 3).map(t => t.innerText)")

            before = tables()
            box = page.locator("textarea.plan").first
            box.scroll_into_view_if_needed()
            box.fill(note)
            box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
            page.wait_for_timeout(400)

            # GPT audit (issue #84, NOTES-01): the Best-sends table's note-flag glyph is now live
            # (authorized metadata about the opinion, not evidence), so it is stripped before
            # comparing -- the comparison still catches any real evidence change underneath it.
            strip_flag = lambda rows: [t.replace("📝", "") for t in rows]
            assert strip_flag(tables()) == strip_flag(before), "a coach note must never reorder the evidence"

            stored = page.evaluate(
                "n => Object.keys(localStorage).filter(k => (localStorage.getItem(k) || '').includes(n))",
                note)
            assert stored == ["ultimate-coach:plan-v2"], stored

            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(400)
            assert page.locator("textarea.plan").first.input_value() == note, "note must survive a reload"

            box = page.locator("textarea.plan").first
            box.scroll_into_view_if_needed()
            box.fill("")
            box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
            page.wait_for_timeout(400)
            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(400)

            assert page.locator("textarea.plan").first.input_value() == ""
            assert note not in page.locator("body").inner_text(), "a cleared note must not reappear"
            assert errors == [], errors
        finally:
            browser.close()


def test_html_head_to_head_never_mixes_formats(tmp_path: Path):
    """The HTML side of the same guard as the Excel cross-format test.

    HTML and Excel compute this independently, so proving it in the workbook
    says nothing about the page. Ann and Cam meet 2-0 in 8-Ball and 0-3 in
    9-Ball; each format must report only its own meetings, and the opponent
    pool must be scoped too -- an opponent met only in 8-Ball should not be
    offered while 9-Ball is selected.
    """
    from tests.test_excel_war_room_formulas import _cross_format_payload

    path = tmp_path / "xfmt.html"
    path.write_text(render(_cross_format_payload(), built_at="2026-10-07 18:00 UTC",
                           viewer_member_external_id="1001"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for fmt, label, meetings in (("EIGHT", "8-Ball", 2), ("NINE", "9-Ball", 3)):
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.goto(path.as_uri())
                page.wait_for_load_state("load")
                page.select_option("#format", fmt)
                page.select_option("#player-a", "1")
                page.wait_for_timeout(300)

                pool = page.eval_on_selector_all(
                    "#player-b option", "els => els.filter(e => e.value).map(e => e.textContent)")
                cam = [t for t in pool if "Cam Cole" in t]
                assert len(cam) == 1, (fmt, pool)
                assert f"{meetings} meeting" in cam[0], (fmt, cam[0])
                # Zed was met in 8-Ball only, so 9-Ball must not offer him
                assert any("Zed Zane" in t for t in pool) == (fmt == "EIGHT"), (fmt, pool)

                page.select_option("#player-b", "10")
                page.wait_for_timeout(300)
                summary = page.locator("#summary").inner_text()
                assert f"{meetings} recorded direct meeting" in summary, (fmt, summary[:200])
                assert label in summary
                assert errors == [], errors
                page.close()
        finally:
            browser.close()


def test_coach_notes_stay_with_their_player_and_never_cross_browser_contexts(tmp_path: Path):
    """The lifecycle the first note test did NOT cover (GPT 53c6e48).

    That test used one context and one note, so three claims I had made were
    broader than the evidence: a genuinely separate browser context, editing an
    existing note rather than only setting and clearing it, and two notes not
    bleeding into each other. This covers those.

    Context isolation is the privacy-relevant one. Notes are the captain's
    private opinions about named people and they live only in the browser; a
    second context standing in for another device or profile must start empty.
    """
    path = tmp_path / "notes2.html"
    path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC",
                           viewer_member_external_id="1001"), encoding="utf-8")
    first, second, edited = "ZZNOTE-first-target", "ZZNOTE-second-target", "ZZNOTE-first-EDITED"

    def write(page, index, text):
        box = page.locator("textarea.plan").nth(index)
        box.scroll_into_view_if_needed()
        box.fill(text)
        box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
        page.wait_for_timeout(300)

    def values(page):
        return page.eval_on_selector_all("textarea.plan", "els => els.map(e => e.value)")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)
            assert len(values(page)) >= 2, "fixture must offer at least two note targets"

            # two different targets keep their own text
            write(page, 0, first)
            write(page, 1, second)
            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)
            assert values(page)[:2] == [first, second]

            # editing one must not disturb the other
            write(page, 0, edited)
            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)
            assert values(page)[:2] == [edited, second], "an edit must not bleed between targets"

            # clearing one leaves the other intact
            write(page, 0, "")
            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)
            assert values(page)[:2] == ["", second]
            ctx.close()

            # a genuinely separate context -- another device or profile -- starts empty
            fresh = browser.new_context(viewport={"width": 1280, "height": 900})
            page2 = fresh.new_page()
            page2.goto(path.as_uri())
            page2.wait_for_load_state("load")
            page2.wait_for_timeout(300)
            assert values(page2)[:2] == ["", ""], "notes must not leak across browser contexts"
            body = page2.locator("body").inner_text()
            for leaked in (first, second, edited):
                assert leaked not in body
            fresh.close()
        finally:
            browser.close()


def test_a_coach_note_follows_its_player_not_the_slot_when_the_fixture_changes(tmp_path: Path):
    """Switching Match Day must never move a note onto a different person.

    Notes are stored under `coach` keyed by player id, so this should hold --
    but the failure mode if it ever regressed to position keying is bad enough
    to pin: the captain's private written opinion about one named opponent
    would silently appear attached to a different named opponent on the next
    fixture. That is worse than losing the note.

    Oct 11 faces one opponent team, Oct 25 faces another, so the note targets
    are disjoint between the two dates.
    """
    path = tmp_path / "fixture_switch.html"
    path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC",
                           viewer_member_external_id="1001"), encoding="utf-8")
    note = "ZZNOTE-belongs-to-the-oct-11-opponent"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)

            stored = lambda: page.evaluate(
                "() => JSON.parse(localStorage.getItem('ultimate-coach:plan-v2') || '{}').coach || {}")
            values = lambda: page.eval_on_selector_all("textarea.plan", "els => els.map(e => e.value)")

            box = page.locator("textarea.plan").first
            box.scroll_into_view_if_needed()
            box.fill(note)
            box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
            page.wait_for_timeout(300)

            owner = [k for k, v in stored().items() if v.get("n") == note]
            assert len(owner) == 1, stored()

            # a different date means a different opponent team
            page.select_option("#md-date-list", "2026-10-25")
            page.wait_for_timeout(500)
            assert note not in page.locator("body").inner_text(), (
                "the note must not reappear against the new fixture's opponents")
            assert all(v == "" for v in values()), values()
            assert [k for k, v in stored().items() if v.get("n") == note] == owner, (
                "switching fixtures must not re-key or drop the stored note")

            # and it is still there when that opponent comes back
            page.select_option("#md-date-list", "2026-10-11")
            page.wait_for_timeout(500)
            assert page.locator("textarea.plan").first.input_value() == note
            assert errors == [], errors
        finally:
            browser.close()


def test_writing_a_coach_note_changes_nothing_on_the_page_except_the_note(tmp_path: Path):
    """All-surface version of the opinion/evidence boundary.

    Two rounds of correction got this to something that actually earns the
    word "all". First version compared the first three tables, which could not
    have seen a leak in the matrix, Next Send, Tonight, Inspect, a scouting
    card or the Player vs Player summary.

    Second version walked leaf ELEMENTS and skipped any element with children,
    so text held by a parent NEXT TO a child element was invisible -- GPT
    f6dcb35/5b8e525 reproduced the hole, and on the real page 42 elements carry
    their own text beside child elements. "Rank 1" becoming "Rank 2" alongside
    an untouched span would have passed.

    Third version added the selected interaction states GPT kept listing as
    open: a section's open/closed state, checkbox state, aria-pressed and
    button classes. The page really carries these -- 3 details elements, 2
    checkboxes, 8 aria-pressed nodes and 2 toggled buttons -- and none were
    covered by text nodes or .value. A collapsed section or a flipped toggle
    is state a reader acts on.

    So this walks real TEXT NODES with a TreeWalker, every form control's
    value, and those interaction states, then requires every changed entry to
    contain the note. Anything else that moves is evidence reacting to an
    opinion, which is the one thing this feature must never do.

    The note is deliberately short: a long one renders as a <details>, which
    would legitimately add an element and is a different case from a leak.
    """
    path = tmp_path / "all_surface.html"
    path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC",
                           viewer_member_external_id="1001"), encoding="utf-8")
    note = "ZZNOTE-all-surface-probe"

    read_all = """() => {
      const out = [];
      // Real text nodes: a parent's own text is captured even when it also has
      // element children, which an element-level walk silently drops.
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent) return NodeFilter.FILTER_REJECT;
          if (['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
          return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
      });
      // No positional index in the key: inserting one node would shift every
      // later index and the diff would report hundreds of phantom changes.
      let node;
      while ((node = walker.nextNode())) {
        out.push('T|' + node.parentElement.tagName + '|' + node.nodeValue.trim());
      }
      // and the interaction state the text walk cannot see. The one control
      // being edited is skipped BY ELEMENT IDENTITY, so nothing else needs an
      // exemption -- a tag-shaped key would exempt every control of that tag.
      document.querySelectorAll('input, select, textarea').forEach((el, j) => {
        if (el.dataset.zzEdited === '1') return;
        out.push('V|' + j + '|' + el.tagName + '|' + (el.value || ''));
      });
      // Selected interaction states, which neither the text walk nor .value sees:
      // a collapsed section, a ticked box or a pressed toggle are all state a
      // reader acts on, and none of them should move because an opinion was typed.
      document.querySelectorAll('details').forEach((el, j) => {
        out.push('S|details|' + j + '|' + (el.open ? 'open' : 'closed'));
      });
      document.querySelectorAll('input[type=checkbox], input[type=radio]').forEach((el, j) => {
        out.push('S|checked|' + j + '|' + (el.checked ? '1' : '0'));
      });
      document.querySelectorAll('[aria-pressed]').forEach((el, j) => {
        out.push('S|pressed|' + j + '|' + el.getAttribute('aria-pressed'));
      });
      document.querySelectorAll('button').forEach((el, j) => {
        out.push('S|btnclass|' + j + '|' + (el.className || ''));
      });
      return out;
    }"""

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            page.wait_for_timeout(400)

            # mark the control we are about to edit so its own value is never compared
            page.eval_on_selector("textarea.plan", "el => { el.dataset.zzEdited = '1'; }")
            before = page.evaluate(read_all)
            assert len(before) > 400, f"page looks unrendered ({len(before)} entries)"

            box = page.locator("textarea.plan").first
            box.scroll_into_view_if_needed()
            box.fill(note)
            box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
            page.wait_for_timeout(500)
            after = page.evaluate(read_all)

            changed = [line for line in difflib.unified_diff(before, after, lineterm="", n=0)
                       if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]

            # Only two things are excused: the edited control's own value (excluded
            # above by element identity) and the one note-presence badge sentinel
            # (excused by _leaked_excluding_note_badge, matched by exact text, not
            # by tag). Anything else that changed is a leak unless it literally
            # contains the note.
            leaked = _leaked_excluding_note_badge(changed, note)
            assert leaked == [], (
                "writing a coach note moved text that is not the note itself: " + repr(leaked[:5]))
            assert changed, "the note should at least render somewhere"
            assert errors == [], errors
        finally:
            browser.close()


def test_a_coach_note_changes_nothing_once_the_workflows_are_populated(tmp_path: Path):
    """The populated-workflow version of the isolation guard (GPT 619aa0b).

    The default-page guard proves the property on a page where nothing has been
    chosen. GPT's point is that the interesting state is a page the captain has
    actually driven: a Player vs Player comparison selected, the matrix toggled
    to Captain view, an availability mark set. A leak could plausibly appear
    only once those are populated, and the default-page test would never see it.

    Everything is set up BEFORE the baseline snapshot, so the selections
    themselves are not what is being measured -- only whether typing an opinion
    afterwards disturbs any of it.
    """
    path = tmp_path / "populated.html"
    path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC",
                           viewer_member_external_id="1001"), encoding="utf-8")
    note = "ZZNOTE-populated-workflow"

    read_all = """() => {
      const out = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent) return NodeFilter.FILTER_REJECT;
          if (['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
          return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
      });
      let node;
      while ((node = walker.nextNode())) {
        out.push('T|' + node.parentElement.tagName + '|' + node.nodeValue.trim());
      }
      document.querySelectorAll('input, select, textarea').forEach((el, j) => {
        if (el.dataset.zzEdited === '1') return;
        out.push('V|' + j + '|' + el.tagName + '|' + (el.value || ''));
      });
      document.querySelectorAll('details').forEach((el, j) => {
        out.push('S|details|' + j + '|' + (el.open ? 'open' : 'closed'));
      });
      document.querySelectorAll('[aria-pressed]').forEach((el, j) => {
        out.push('S|pressed|' + j + '|' + el.getAttribute('aria-pressed'));
      });
      return out;
    }"""

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)

            # drive the page the way a captain would, BEFORE any measurement
            page.select_option("#player-a", "1")
            page.wait_for_timeout(200)
            opponents = page.eval_on_selector_all(
                "#player-b option", "els => els.filter(e => e.value).map(e => e.value)")
            assert opponents, "fixture must offer a Player vs Player opponent"
            page.select_option("#player-b", opponents[0])
            page.click("button.mv[data-view='captain']")
            page.wait_for_timeout(400)

            populated = page.evaluate(read_all)
            assert any(line.startswith("S|pressed|") for line in populated)

            page.eval_on_selector("textarea.plan", "el => { el.dataset.zzEdited = '1'; }")
            before = page.evaluate(read_all)

            box = page.locator("textarea.plan").first
            box.scroll_into_view_if_needed()
            box.fill(note)
            box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
            page.wait_for_timeout(500)
            after = page.evaluate(read_all)

            changed = [line for line in difflib.unified_diff(before, after, lineterm="", n=0)
                       if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
            leaked = _leaked_excluding_note_badge(changed, note)
            assert leaked == [], (
                "a coach note disturbed a populated workflow: " + repr(leaked[:5]))
            # Non-vacuity (GPT b85f13c): without this a DROPPED note passes with
            # changed == [], and the test would be celebrating its own silence.
            assert changed, "the note must render somewhere, or this proves nothing"
            assert any(note in line for line in changed)
            assert page.locator("textarea.plan").first.input_value() == note
            assert errors == [], errors
        finally:
            browser.close()


def test_a_long_coach_note_survives_whole(tmp_path: Path):
    """A long observation must be stored and restored in full, never clipped.

    Scope, stated because I could not reach the rest: past 48 characters the
    note is PRESENTED as a collapsed <details> with a 36-character summary, so
    it cannot push Risks off a phone screen. That preview only renders for a
    listed threat or a chosen Next Send opponent, and this fixture produces
    neither -- writing notes into every available control rendered no preview
    at all. So the collapsed presentation is NOT exercised here.

    What is exercised is the half that loses data if it breaks: the stored note
    itself. A summary being short is a design choice; the note being short is
    data loss, and that is what this pins.
    """
    path = tmp_path / "long_note.html"
    path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC",
                           viewer_member_external_id="1001"), encoding="utf-8")
    long_note = ("ZZLONGNOTE plays safe off the rail all night and will not cut the ball "
                 "into the side pocket under pressure, so leave that shot open on purpose")
    assert len(long_note) > 48, "must exceed the collapse threshold"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)

            box = page.locator("textarea.plan").first
            box.scroll_into_view_if_needed()
            box.fill(long_note)
            box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
            page.wait_for_timeout(400)

            stored = page.evaluate(
                "() => JSON.parse(localStorage.getItem('ultimate-coach:plan-v2') || '{}').coach || {}")
            kept = [v.get("n") for v in stored.values() if v.get("n")]
            assert kept == [long_note], f"the stored note must be whole, got {kept}"

            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(400)
            restored = page.locator("textarea.plan").first.input_value()
            assert restored == long_note, "a reload must not clip the note"
            assert len(restored) == len(long_note)
            assert errors == [], errors
        finally:
            browser.close()


def test_a_long_note_collapses_on_the_first_screen_without_losing_a_word(tmp_path: Path):
    """The collapsed-preview case, now reachable.

    The default fixture has no opponent with a winning record against us, so
    the threats list is empty and the note preview never renders -- which is
    why an earlier attempt at this test found nothing. Giving one opponent a
    losing record for us makes them a threat and reaches the path.

    The design intent (GPT audit #84) is that a long observation must not push
    Risks off a phone screen. The hazard that creates is the opposite one:
    silently clipping the captain's words. So this pins both halves -- the
    summary is short, and the full note is still in the document.

    innerText deliberately is NOT used for that check: a collapsed <details>
    excludes its hidden content from innerText, which looks exactly like data
    loss and is not. textContent is the honest measure here.
    """
    payload = _payload()
    payload["evidence"] = payload["evidence"] + _games(3, 10, "LLL") + _games(2, 10, "LL")
    payload["counts"] = {"players": len(payload["players"]),
                         "head_to_head_rows": len(payload["evidence"])}
    path = tmp_path / "threat_note.html"
    path.write_text(render(payload, built_at="2026-10-07 18:00 UTC",
                           viewer_member_external_id="1001"), encoding="utf-8")
    long_note = ("ZZLONGNOTE plays safe off the rail all night and will not cut the ball "
                 "into the side pocket under pressure")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)

            assert "Cam Cole" in page.locator(".decide-threats").inner_text(), "fixture must produce a threat"

            for index in range(page.eval_on_selector_all("textarea.plan", "els => els.length")):
                box = page.locator("textarea.plan").nth(index)
                box.scroll_into_view_if_needed()
                box.fill(long_note)
                box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
            page.wait_for_timeout(400)

            # The first screen picks the note up on the next render, not in place.
            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(400)

            shown = page.evaluate("""(note) => {
              const d = document.querySelector('details.note-more');
              if (!d) return null;
              const summary = d.querySelector('summary');
              return {open: d.open,
                      wholeNoteInDom: d.textContent.includes(note),
                      summaryLength: (summary ? summary.textContent : '').length};
            }""", long_note)

            assert shown is not None, "a long note on a threat must render its preview"
            assert shown["open"] is False, "it must start collapsed so Risks stay on screen"
            assert shown["wholeNoteInDom"], "collapsing must not cost a single word"
            assert shown["summaryLength"] < len(long_note), "the summary is the short part"
            assert errors == [], errors
        finally:
            browser.close()


def test_a_note_does_not_disturb_a_populated_inspect_selection(tmp_path: Path):
    """The populated-Inspect case GPT kept listing as open.

    Inspect is filled by clicking a matrix cell, which pins one pair's evidence
    below the matrix. A captain mid-match has that open on the pair they are
    deciding about. Writing an opinion must neither move the evidence nor throw
    away the selection they are reading -- losing their place would be a small
    bug with a bad moment attached to it.
    """
    path = tmp_path / "inspect_note.html"
    path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC",
                           viewer_member_external_id="1001"), encoding="utf-8")
    note = "ZZNOTE-inspect-populated"

    read_all = """() => {
      const out = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent) return NodeFilter.FILTER_REJECT;
          if (['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
          return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
      });
      let node;
      while ((node = walker.nextNode())) {
        out.push('T|' + node.parentElement.tagName + '|' + node.nodeValue.trim());
      }
      document.querySelectorAll('input, select, textarea').forEach((el, j) => {
        if (el.dataset.zzEdited === '1') return;
        out.push('V|' + j + '|' + el.tagName + '|' + (el.value || ''));
      });
      return out;
    }"""

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)

            cell = page.locator("button.mcell").first
            assert cell.count() > 0, "fixture must render a matrix to inspect"
            cell.click()
            page.wait_for_timeout(400)

            pinned = page.locator("#wr-pair").inner_text()
            assert pinned.strip(), "clicking a cell must populate Inspect"

            page.eval_on_selector("textarea.plan", "el => { el.dataset.zzEdited = '1'; }")
            before = page.evaluate(read_all)

            box = page.locator("textarea.plan").first
            box.scroll_into_view_if_needed()
            box.fill(note)
            box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
            page.wait_for_timeout(400)
            after = page.evaluate(read_all)

            changed = [line for line in difflib.unified_diff(before, after, lineterm="", n=0)
                       if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
            leaked = _leaked_excluding_note_badge(changed, note)
            assert leaked == [], "a note disturbed a populated Inspect view: " + repr(leaked[:5])
            assert changed, "the note must render somewhere, or this proves nothing"

            assert page.locator("#wr-pair").inner_text() == pinned, (
                "writing a note must not discard the pair the captain was reading")
            assert errors == [], errors
        finally:
            browser.close()


def test_a_long_note_on_a_phone_expands_readably_and_leaves_risks_reachable(tmp_path: Path):
    """The presentation intent itself, on the viewport it was written for.

    GPT audit #84's stated reason for collapsing a long note is that it must
    not push Risks off a phone screen; GPT 630c862 noted the expanded and
    phone-geometry halves were still unverified. This checks the whole
    bargain on a 375px viewport: collapsed by default with Risks still there,
    expanding reveals the note as actually visible text, and Risks survives
    the expansion rather than being displaced out of the document.

    Uses innerText for the expanded check on purpose -- here the question IS
    visibility, which is exactly what innerText answers and textContent does
    not. The earlier test used textContent because its question was whether
    the words still existed. Same element, different question.
    """
    payload = _payload()
    payload["evidence"] = payload["evidence"] + _games(3, 10, "LLL") + _games(2, 10, "LL")
    payload["counts"] = {"players": len(payload["players"]),
                         "head_to_head_rows": len(payload["evidence"])}
    path = tmp_path / "phone_note.html"
    path.write_text(render(payload, built_at="2026-10-07 18:00 UTC",
                           viewer_member_external_id="1001"), encoding="utf-8")
    long_note = ("ZZLONGNOTE plays safe off the rail all night and will not cut the ball "
                 "into the side pocket under pressure")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 375, "height": 812})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)

            for index in range(page.eval_on_selector_all("textarea.plan", "els => els.length")):
                box = page.locator("textarea.plan").nth(index)
                box.scroll_into_view_if_needed()
                box.fill(long_note)
                box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(400)

            details = page.locator("details.note-more").first
            assert details.count() > 0, "the threat fixture must render the preview"
            assert details.evaluate("el => !el.open"), "collapsed by default on a phone"

            risks = page.locator(".decide-risks").first
            assert risks.count() > 0 and risks.inner_text().strip(), "Risks must be present while collapsed"

            # expanding must make the whole note genuinely visible, not merely present
            details.locator("summary").first.click()
            page.wait_for_timeout(300)
            assert details.evaluate("el => el.open")
            assert long_note in details.inner_text(), "expanding must reveal the full note as visible text"

            # ...and Risks must survive the expansion
            assert risks.inner_text().strip(), "Risks must still be reachable after expanding"
            overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            assert overflow <= 1, f"a long note must not cause sideways scrolling, got {overflow}px"
            assert errors == [], errors
        finally:
            browser.close()


def test_a_note_does_not_reset_an_alternate_next_send_opponent(tmp_path: Path):
    """The last of the populated-workflow cases GPT listed.

    Next Send defaults to the first unplayed opponent, but the captain picks
    whoever the other team actually put up. That choice is the whole point of
    the panel: the advice underneath it is only correct for the opponent
    standing at the table.

    So writing a note must not silently bounce the selection back to the
    default. A captain who typed an observation and then acted on advice for
    the wrong opponent would have been misled by the tool at the exact moment
    it is supposed to help.
    """
    path = tmp_path / "next_send_note.html"
    path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC",
                           viewer_member_external_id="1001"), encoding="utf-8")
    note = "ZZNOTE-alternate-next-send"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(path.as_uri())
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)

            chips = page.locator("button.ns-chip")
            assert chips.count() >= 2, "fixture must offer more than one opponent to choose"
            assert chips.nth(0).evaluate("el => el.getAttribute('aria-pressed')") == "true"

            alternate = chips.nth(1)
            chosen_label = alternate.inner_text()
            alternate.click()
            page.wait_for_timeout(400)

            assert page.locator("button.ns-chip").nth(1).evaluate(
                "el => el.getAttribute('aria-pressed')") == "true", "clicking a chip must select it"
            advice_before = page.locator("#next-send").inner_text()

            box = page.locator("textarea.plan").first
            box.scroll_into_view_if_needed()
            box.fill(note)
            box.evaluate("e => { e.dispatchEvent(new Event('input', {bubbles: true})); e.blur(); }")
            page.wait_for_timeout(400)

            still = page.locator("button.ns-chip").nth(1)
            assert still.evaluate("el => el.getAttribute('aria-pressed')") == "true", (
                "a note must not bounce the selection back to the default opponent")
            assert still.inner_text() == chosen_label

            advice_after = page.locator("#next-send").inner_text()

            # Bidirectional and ordered (GPT 4613fbe). Searching only for NEW lines
            # misses a deleted warning and misses a reorder of unchanged lines --
            # both of which change the advice a captain reads.
            moved = [line for line in difflib.unified_diff(
                        advice_before.splitlines(), advice_after.splitlines(), lineterm="", n=0)
                     if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
            leaked = [line for line in moved if note not in line]
            assert leaked == [], f"the advice changed for reasons other than the note: {leaked[:4]}"

            # Non-vacuity: the note must actually have been stored and rendered,
            # or an inert page would pass this test by changing nothing at all.
            assert page.locator("textarea.plan").first.input_value() == note
            stored = page.evaluate(
                "() => JSON.parse(localStorage.getItem('ultimate-coach:plan-v2') || '{}').coach || {}")
            assert any(entry.get("n") == note for entry in stored.values()), stored
            assert errors == [], errors
        finally:
            browser.close()


def test_blind_send_answers_before_the_captain_picks_an_opponent(tmp_path: Path):
    """Decision-first: when WE lead there is no chip to pick, so the answer must already be there.

    Every other recommendation on this page is conditioned on "they put up X". In APA the lead
    alternates, so a captain regularly chooses first and had no answer at all.
    Design: docs/superpowers/specs/2026-10-11-blind-send-design.md
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            card = page.locator("#tonight .blind-send")
            assert card.count() == 1, "the lead answer must be present without any interaction"
            text = card.inner_text()
            assert "if we put up first" in text.lower(), text   # the label is styled uppercase
            # It names one of our players and says why, in recorded terms -- never odds.
            names = [n.split(" (APA")[0] for n in (ANN, BEA, DEE)]
            assert any(n in text for n in names), text
            for banned in ("%", "odds", "probability", "chance"):
                assert banned not in text.lower(), (banned, text)

            # It appears ABOVE the "they put up" chips: the answer precedes the question.
            order = page.evaluate(
                "() => {const t=document.querySelector('#tonight');"
                " const b=t.querySelector('.blind-send'), n=t.querySelector('#next-send');"
                " return b.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING ? 'before' : 'after';}")
            assert order == "before", "the lead recommendation must precede the opponent chips"

            # Marking our lead candidate unavailable must change the answer, not keep a stale one.
            first = card.locator(".bs-name").inner_text()
            assert first in names, first
            pid = page.evaluate(
                "(nm) => {const r=[...document.querySelectorAll('#lineup-lab select[data-plan=\"avail\"]')];"
                " const row=r.find(s=>s.closest('tr')&&s.closest('tr').innerText.includes(nm));"
                " return row?row.getAttribute('data-pid'):null;}", first)
            if pid:
                page.select_option(f'#lineup-lab select[data-plan="avail"][data-pid="{pid}"]', "Unavailable")
                assert page.locator("#tonight .blind-send .bs-name").inner_text() != first
            assert errors == []
        finally:
            browser.close()


def test_skill_cap_warns_before_a_send_locks_the_captain_out_of_a_legal_lineup(tmp_path: Path):
    """APA caps the total skill level you put up; spend the low numbers early and you are stuck.

    The cap constant existed in the page and was never used, and the Excel cap said outright it
    was not a legality check. Nothing is assumed: with no cap entered this renders nothing.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            assert page.locator("#tonight .lineup-budget").count() == 0, "no cap entered, no claim"

            page.fill("#ll-cap", "23")
            page.dispatch_event("#ll-cap", "change")
            budget = page.locator("#tonight .lineup-budget")
            assert budget.count() == 1, "a cap the captain entered must be used, not just stored"
            assert "23" in budget.inner_text(), budget.inner_text()

            # The fixture has an unknown SL: a low captured subtotal comparison is not a proof of illegality.
            page.fill("#ll-cap", "2")
            page.dispatch_event("#ll-cap", "change")
            txt = page.locator("#tonight .lineup-budget").inner_text()
            assert "incomplete" in txt.lower() and "no lineup cleared" in txt.lower(), txt
            assert "cannot field a legal lineup" not in txt.lower()
            assert errors == []
        finally:
            browser.close()


def test_response_panel_does_not_pretend_they_have_put_someone_up(tmp_path: Path):
    """BLIND-01 #4: the panel preselects an opponent, which read as though they had sent him.

    It still has to show something useful, but before the captain taps a chip it must say the
    response is a possibility, not a fact.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            note = page.locator("#next-send .ns-hypothetical")
            assert note.count() == 1 and note.first.is_visible(), (
                "an unchosen opponent must be labelled as hypothetical, and visibly so")
            assert "nobody put up yet" in note.inner_text().lower(), note.inner_text()
            assert "if they put up" in page.locator("#next-send .ns-ask").inner_text().lower()

            # Once the captain taps the opponent they really sent, it becomes a statement of fact.
            page.locator("#next-send .ns-chip").first.click()
            assert page.locator("#next-send .ns-hypothetical").count() == 0
            assert page.locator("#next-send .ns-ask").inner_text().lower().startswith("they put up")
            assert errors == []
        finally:
            browser.close()


def test_blind_card_never_calls_an_unknown_lead_an_even_record(tmp_path: Path):
    """BLIND-01 boundary on the phone: unknown must not be rendered as evidence of safety.

    Marking the candidates who hold records Unavailable leaves a player with none at the top of
    the ranking. He only outranks the rest because they have LOSING records, so the card must
    say unranked/unknown rather than inventing "even vs 0 of 2".
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            for pid in ("1", "3"):                 # leave the player with no direct evidence on top
                sel = f'#lineup-lab select[data-plan="avail"][data-pid="{pid}"]'
                if page.locator(sel).count():
                    page.select_option(sel, "Unavailable")
            card = page.locator("#tonight .blind-send")
            if card.count():
                text = card.inner_text().lower()
                assert "even vs 0" not in text, text
                if "unranked" in text or "not safer" in text:
                    assert "no evidence-backed pick" in text or "unknown" in text, text
            assert errors == []
        finally:
            browser.close()


def test_a_recommended_send_says_when_it_costs_coverage_elsewhere(tmp_path: Path):
    """Next Send answers one pairing at a time; the captain could not see what it costs later.

    This test previously looped over .ns-cost elements that the stock fixture never produces, so
    it passed without ever exercising a warning (GPT caught it). It now BUILDS the positive case:
    Ann is the only favorable option against both Cam and Eve, so sending her at Cam spends the
    one we hold against Eve, and the card has to say so.
    """
    payload = _payload()
    payload["evidence"] = payload["evidence"] + _games(1, 11, "WW")      # Ann beats Eve twice
    path = tmp_path / "wr-cost.html"
    path.write_text(render(payload, built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001"),
                    encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(path.as_uri())
            page.wait_for_load_state("load")

            costs = page.locator("#next-send .ns-cost")
            assert costs.count() >= 1, "the positive case must actually render a warning"
            text = costs.first.inner_text().lower()
            assert "favorable direct option" in text, text
            assert "leaves" in text, text
            # The save flag beside it names the opponent; the cost line must not repeat it.
            assert "eve" not in text, ("the opponent is named once, by the save flag", text)
            for banned in ("%", "odds", "probability", "chance"):
                assert banned not in text, (banned, text)
            # And the save flag is the thing that names who is given up.
            assert "eve" in page.locator("#next-send .ns-save").first.inner_text().lower()
            assert "2-0 in 2 meetings, small sample" in page.locator("#next-send .ns-save").first.inner_text()
            assert errors == []
        finally:
            browser.close()


def test_dangerous_opponents_reflects_who_is_actually_left_tonight(tmp_path: Path):
    """Threat Panel gap: the old flag summed a record across our WHOLE roster's history,

    including players who are Unavailable or have already Played. In the stock fixture, Eve
    Ellis's entire "dangerous" record (2-0) is built on Dee alone (the only one of our players
    who has ever met her). Marking Dee Unavailable must turn that from a live warning into an
    explicit UNKNOWN -- not a declaration that Eve is safe. GPT audit correction: the first
    version of this said "no longer a live risk" here, which reads as a clearance the data does
    not support -- missing evidence is uncertainty, not safety.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            before = page.locator("#tonight .decide-threats").inner_text()
            assert "Eve" in before and "remaining roster" in before.lower(), before

            page.select_option('#lineup-lab select[data-plan="avail"][data-pid="3"]', "Unavailable")
            after = page.locator("#tonight .decide-threats").inner_text()
            assert "no longer a live risk" not in after.lower(), after
            assert "unknown" in after.lower(), after
            assert "still in play" not in after.lower(), after
            assert "Eve" in after, after      # named, not silently dropped

            risks_panel = page.locator("#wr-risks").inner_text()
            assert "unknown vs who is left, not cleared" in risks_panel.lower(), risks_panel
            assert "historically 2-0" in risks_panel.lower(), risks_panel
            assert errors == []
        finally:
            browser.close()


def test_quick_read_badges_are_glanceable_and_sit_above_the_dense_sentence(tmp_path: Path):
    """Quick Read Scouting Cards gap: the existing quick-read line is a dense sentence a captain
    has to actually read; Paul's own spec is an icon and a few words.

    GPT audit correction (d3203ee/349815e): the first version of this test asserted the old,
    confidence-implying wording ("Limited direct evidence") and treated CAM's record as
    shared-opponent evidence. Both were wrong. CAM's six meetings are all CONCERNING (category
    R, real losses) -- direct evidence, not an absence of it -- so the badge states the plain
    count instead of an adjective: "Direct meetings vs roster: 6 meetings". EVE's two meetings are direct
    too (small sample), which the pre-fix category-filtered logic missed entirely and fell
    through to the shared-opponent branch; that was exactly the bug.

    Only the "No coach observations" badge is live (GPT's explicit, narrow authorization): it is
    metadata about whether an opinion exists, not evidence the opinion could corrupt, so it
    updates on input without a reload while every numeric badge stays exactly as last rendered.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            cards = page.locator("#scouting-cards .scout")
            assert cards.count() == 2, cards.count()

            cam, eve = cards.nth(0), cards.nth(1)
            cam_badges = cam.locator(".quick-read-badges").inner_text()
            assert "Direct meetings vs roster: 6 meetings" in cam_badges, cam_badges
            assert "No coach observations" in cam_badges, cam_badges

            eve_badges = eve.locator(".quick-read-badges").inner_text()
            assert "Direct meetings vs roster: 2 meetings (small sample)" in eve_badges, eve_badges
            assert "Recorded losses vs SL4" in eve_badges, eve_badges
            assert "No coach observations" in eve_badges, eve_badges

            # Badges precede the dense sentence in document order (decision before detail).
            order = page.evaluate(
                "() => {const c=document.querySelectorAll('#scouting-cards .scout')[0];"
                " const b=c.querySelector('.quick-read-badges'), q=c.querySelector('.quick-read');"
                " return b.compareDocumentPosition(q) & Node.DOCUMENT_POSITION_FOLLOWING ? 'before' : 'after';}")
            assert order == "before"

            # Writing an observation clears the missing-observations badge immediately, with no
            # reload -- and only that opponent's, and only that one badge. Evidence and weak-SL
            # stay exactly as last rendered, same as before.
            page.fill('#scouting-cards textarea[data-pid="10"]', "Breaks hard, go even")
            page.locator('#scouting-cards textarea[data-pid="10"]').dispatch_event("input")
            page.wait_for_timeout(200)
            cards = page.locator("#scouting-cards .scout")
            cam_badges_after = cards.nth(0).locator(".quick-read-badges").inner_text()
            assert "No coach observations" not in cam_badges_after, cam_badges_after
            assert "Direct meetings vs roster: 6 meetings" in cam_badges_after, cam_badges_after
            eve_badges_after = cards.nth(1).locator(".quick-read-badges").inner_text()
            assert "No coach observations" in eve_badges_after, eve_badges_after
            assert "Direct meetings vs roster: 2 meetings (small sample)" in eve_badges_after, eve_badges_after
            assert "Recorded losses vs SL4" in eve_badges_after, eve_badges_after

            # Clearing the note back out restores the missing-observations badge, live.
            page.fill('#scouting-cards textarea[data-pid="10"]', "")
            page.locator('#scouting-cards textarea[data-pid="10"]').dispatch_event("input")
            page.wait_for_timeout(200)
            assert "No coach observations" in cards.nth(0).locator(".quick-read-badges").inner_text()
            assert errors == []
        finally:
            browser.close()


def test_matrix_column_header_flags_opponents_with_a_coach_note(tmp_path: Path):
    """Coach Notes Integration gap: a captain scanning the matrix to decide who to send has no
    way to tell, without leaving the matrix for the scouting cards below, which opponents they
    have already personally scouted. The matrix is otherwise evidence-only (GPT's opinion/
    evidence isolation guard), so the flag lives in the column header text next to the opponent's
    name -- never inside the evidence cell itself -- and carries the same "(your opinion, not
    APA facts)" qualifier used everywhere else a coach note surfaces.

    Live, not just on reload (GPT audit issue #84, NOTES-01): the first version of this flag only
    updated on the next full render, so typing and blurring an observation left the flag absent
    until something else (a reload, a lineup mark) forced a re-render -- a captain who only wrote
    a note would never see it appear. Fixed by patching the flag's own stable slot on input.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            heads = page.locator(".matrix thead th")
            assert heads.count() == 3, heads.count()  # corner + CAM + EVE

            assert page.locator(".matrix thead th .note-flag").count() == 0, (
                "no note yet written, so no column should be flagged")

            page.fill('#scouting-cards textarea[data-pid="10"]', "Breaks hard, go even")
            page.locator('#scouting-cards textarea[data-pid="10"]').blur()
            page.wait_for_timeout(200)

            flags = page.locator(".matrix thead th .note-flag")
            assert flags.count() == 1, "the flag must appear live, with no reload"
            cam_head = page.locator(".matrix thead th").nth(1)
            assert "Cam Cole" in cam_head.inner_text()
            assert "📝" in cam_head.inner_text()
            assert flags.first.get_attribute("title") == (
                "Coach: Breaks hard, go even (your opinion, not APA facts)")
            eve_head = page.locator(".matrix thead th").nth(2)
            assert "📝" not in eve_head.inner_text(), eve_head.inner_text()

            # And it survives a reload, same as the note itself.
            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)
            assert page.locator(".matrix thead th .note-flag").count() == 1
            assert errors == [], errors
        finally:
            browser.close()


def test_best_sends_now_flags_the_opponent_with_a_coach_note(tmp_path: Path):
    """Coach Notes Integration gap: "Best sends now" on the Tonight screen -- the first thing a
    captain sees on a phone before Dangerous opponents or the matrix -- named the opponent on
    every line but never said whether that opponent was one the captain had personally scouted.
    Dangerous opponents, two columns over on the same screen, already surfaces the exact same
    note via wrNotePreview; Best sends now was the one decide-grid column left out.

    Live, not just on reload (GPT audit issue #84, NOTES-01): the first version only updated on
    the next full render, so typing and blurring an observation left this line stale until
    something else forced a re-render. Fixed by patching the flag's own stable slot on input.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            sends = page.locator("#tonight .decide-sends")
            assert "Cam Cole" in sends.inner_text() and "Eve Ellis" in sends.inner_text()
            assert "📝" not in sends.inner_text(), "no note yet written, so no line should carry one"

            page.fill('#scouting-cards textarea[data-pid="10"]', "Breaks hard, go even")
            page.locator('#scouting-cards textarea[data-pid="10"]').blur()
            page.wait_for_timeout(200)

            text = page.locator("#tonight .decide-sends").inner_text()
            assert "📝 Coach: Breaks hard, go even (opinion)" in text, (
                "the note must appear live, with no reload: " + text)
            # The note sits on Cam's line, not Eve's -- confirmed by splitting on the opponent names.
            cam_part, _, eve_part = text.partition("Eve Ellis")
            assert "Breaks hard, go even" in cam_part
            assert "Breaks hard, go even" not in eve_part

            # And it survives a reload, same as the note itself.
            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)
            assert "📝 Coach: Breaks hard, go even (opinion)" in page.locator("#tonight .decide-sends").inner_text()
            assert errors == [], errors
        finally:
            browser.close()


def test_lineup_lab_best_remaining_sends_flags_the_opponent_with_a_coach_note(tmp_path: Path):
    """Coach Notes Integration gap: Lineup Lab's own "Best remaining sends" list -- what a
    captain checks while actually marking availability and lineup -- has the identical gap Best
    sends now had on the Tonight screen: it names the opponent on every line with no way to tell
    whether a personal scouting note exists without leaving the panel. Fixed the same way, reusing
    wrCoachSummary/wrNotePreview, replacing the plain wrList() call with an equivalent <ul
    class="wr-list"> built by hand so the note HTML is not escaped away.

    Live, not just on reload (GPT audit issue #84, NOTES-01): fixed the same way as the matrix
    header and Best sends now, via the flag's own stable slot patched on input.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            best = page.locator("#lineup-lab").locator("text=Best remaining sends").locator("xpath=following-sibling::ul[1]")
            assert "Cam Cole" in best.inner_text() and "Eve Ellis" in best.inner_text()
            assert "📝" not in best.inner_text(), "no note yet written, so no line should carry one"

            page.fill('#scouting-cards textarea[data-pid="11"]', "Shaky on the break")
            page.locator('#scouting-cards textarea[data-pid="11"]').blur()
            page.wait_for_timeout(200)

            text = best.inner_text()
            assert "📝 Coach: Shaky on the break (your opinion, not APA facts)" in text, (
                "the note must appear live, with no reload: " + text)
            # The note sits on Eve's line, not Cam's.
            cam_part, _, eve_part = text.partition("Eve Ellis")
            assert "Shaky on the break" not in cam_part
            assert "Shaky on the break" in eve_part

            # And it survives a reload, same as the note itself.
            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)
            best = page.locator("#lineup-lab").locator("text=Best remaining sends").locator("xpath=following-sibling::ul[1]")
            assert "📝 Coach: Shaky on the break (your opinion, not APA facts)" in best.inner_text()
            assert errors == [], errors
        finally:
            browser.close()


def test_opportunities_table_flags_the_opponent_with_a_coach_note(tmp_path: Path):
    """Coach Notes Integration gap: the desktop "Best sends -- top opportunities per opponent"
    table lists every opponent by name in its first column, same as the matrix header and the two
    phone-first send lists already fixed, but carried no note indicator. Fixed with the same
    compact note-flag span used in the matrix header (a dense data table, not prose, so the icon
    + title pattern fits better here than wrNotePreview's inline text).

    Live, not just on reload (GPT audit issue #84, NOTES-01): fixed the same way as the matrix
    header, via the flag's own stable slot patched on input.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            rows = page.locator("#wr-opportunities .send-table tbody tr")
            assert rows.count() == 2, rows.count()
            assert page.locator("#wr-opportunities .note-flag").count() == 0, (
                "no note yet written, so no row should be flagged")

            page.fill('#scouting-cards textarea[data-pid="10"]', "Breaks hard, go even")
            page.locator('#scouting-cards textarea[data-pid="10"]').blur()
            page.wait_for_timeout(200)

            flags = page.locator("#wr-opportunities .note-flag")
            assert flags.count() == 1, "the flag must appear live, with no reload"
            cam_row = page.locator("#wr-opportunities .send-table tbody tr").nth(0)
            assert "Cam Cole" in cam_row.inner_text()
            assert flags.first.get_attribute("title") == (
                "Coach: Breaks hard, go even (your opinion, not APA facts)")
            eve_row = page.locator("#wr-opportunities .send-table tbody tr").nth(1)
            assert "📝" not in eve_row.inner_text(), eve_row.inner_text()

            # And it survives a reload, same as the note itself.
            page.reload()
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)
            assert page.locator("#wr-opportunities .note-flag").count() == 1
            assert errors == [], errors
        finally:
            browser.close()


def test_dangerous_opponents_note_flag_updates_live(tmp_path: Path):
    """GPT audit (issue #84, NOTES-01 follow-up): the same staleness bug the matrix header and
    Best sends now had, found in a third and fourth place that predate this session -- Dangerous
    opponents in both Tonight's decide-threats and the #wr-risks panel. Eve Ellis is the stock
    fixture's default dangerous opponent (her 2-0 record against Dee is still live). Fixed the
    same way: wrNoteFlagSlot/wrPatchNoteFlags, reusing the existing bare-span rendering --
    #wr-risks previously went through wrList() (escapes every item, same defect Lineup Lab had),
    now a hand-built <ul class="wr-list">.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            before_tonight = page.locator("#tonight .decide-threats").inner_text()
            before_risks = page.locator("#wr-risks").inner_text()
            assert "Eve" in before_tonight and "📝" not in before_tonight
            assert "Eve" in before_risks and "📝" not in before_risks

            page.fill('#scouting-cards textarea[data-pid="11"]', "Slow, careful safeties")
            page.locator('#scouting-cards textarea[data-pid="11"]').blur()
            page.wait_for_timeout(200)

            tonight_text = page.locator("#tonight .decide-threats").inner_text()
            risks_text = page.locator("#wr-risks").inner_text()
            assert "📝 Coach: Slow, careful safeties (opinion)" in tonight_text, (
                "Tonight's Dangerous opponents must update live, with no reload: " + tonight_text)
            assert "📝 Coach: Slow, careful safeties (your opinion, not APA facts)" in risks_text, (
                "#wr-risks Dangerous opponents must update live, with no reload: " + risks_text)

            # Clearing it removes the flag live too, in both places.
            page.fill('#scouting-cards textarea[data-pid="11"]', "")
            page.locator('#scouting-cards textarea[data-pid="11"]').blur()
            page.wait_for_timeout(200)
            assert "📝" not in page.locator("#tonight .decide-threats").inner_text()
            assert "📝" not in page.locator("#wr-risks").inner_text()
            assert errors == [], errors
        finally:
            browser.close()


def test_next_send_note_box_updates_live(tmp_path: Path):
    """GPT audit (issue #84, NOTES-01 follow-up): the Next Send card's own note box
    (`.ns-coach`) has a background-styled wrapper that is only shown when a note exists, so it
    cannot just be an empty slot -- GPT: "empty wrappers are implementation work, not an owner-
    review gate." Fixed by always rendering the wrapper and toggling its CSS display, so an
    absent note never shows an empty colored box.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            page.click("#next-send .ns-chip:has-text('Cam Cole')")
            # The slot is rendered (so it can be patched live) but hidden until a note exists --
            # never an empty colored box.
            assert not page.locator("#next-send .ns-coach").is_visible()

            page.fill('#scouting-cards textarea[data-pid="10"]', "Breaks hard, go even")
            page.locator('#scouting-cards textarea[data-pid="10"]').blur()
            page.wait_for_timeout(200)

            box = page.locator("#next-send .ns-coach")
            assert box.count() == 1
            assert box.is_visible(), "the note box must appear live, with no reload"
            assert "📝 Coach: Breaks hard, go even (your opinion, not APA facts)" in box.inner_text()

            # Clearing the note hides the box again, live -- not an empty colored box left behind.
            page.fill('#scouting-cards textarea[data-pid="10"]', "")
            page.locator('#scouting-cards textarea[data-pid="10"]').blur()
            page.wait_for_timeout(200)
            assert not page.locator("#next-send .ns-coach").is_visible()
            assert errors == [], errors
        finally:
            browser.close()


def test_scouting_card_own_note_paragraph_updates_live(tmp_path: Path):
    """GPT audit (issue #84, NOTES-01 follow-up): the scouting card's own <p class="ns-coach">
    (distinct from the .coach-summary div at the bottom of the same card, which was already live)
    sits right under Quick read, and was still stale pre-fix. Same box-wrapper treatment as Next
    Send's note box: always rendered, display toggled, never an empty colored box.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            cam_card = page.locator("#scouting-cards .scout").nth(0)
            # The slot is rendered (so it can be patched live) but hidden until a note exists.
            assert not cam_card.locator("p.ns-coach").is_visible()

            page.fill('#scouting-cards textarea[data-pid="10"]', "Breaks hard, go even")
            page.locator('#scouting-cards textarea[data-pid="10"]').blur()
            page.wait_for_timeout(200)

            cam_card = page.locator("#scouting-cards .scout").nth(0)
            note_p = cam_card.locator("p.ns-coach")
            assert note_p.is_visible(), "the card's own note paragraph must appear live, with no reload"
            assert "📝 Coach: Breaks hard, go even (your opinion, not APA facts)" in note_p.inner_text()
            # The .coach-summary div (bottom of card) was already live; both now agree.
            assert "Coach: Breaks hard, go even" in cam_card.locator(".coach-summary").inner_text()

            page.fill('#scouting-cards textarea[data-pid="10"]', "")
            page.locator('#scouting-cards textarea[data-pid="10"]').blur()
            page.wait_for_timeout(200)
            assert not page.locator("#scouting-cards .scout").nth(0).locator("p.ns-coach").is_visible()
            assert errors == [], errors
        finally:
            browser.close()


def test_captain_matrix_row_and_column_show_favorable_option_counts(tmp_path: Path):
    """Captain Matrix gap (first increment): scanning the matrix by eye to count colored cells
    does not scale past a handful of players. The stock fixture's categories (row-major: Ann-Cam
    G, Ann-Eve I, Bea-Cam R, Bea-Eve X, Dee-Cam E, Dee-Eve R) give a row count of 1 favorable
    option for Ann and 0 for Bea/Dee, and a column count of 1 favorable remaining player for Cam
    and 0 for Eve. Marking Ann unavailable removes her from the column count (same category rule
    every cell already uses -- plan.rem -- just counted) without touching the evidence itself.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            rows = page.locator(".matrix tbody tr")
            assert rows.count() == 3, rows.count()
            row_counts = [rows.nth(i).locator("th .green-count").inner_text() for i in range(3)]
            assert row_counts == ["🟢×1", "🟢×0", "🟢×0"], row_counts  # Ann, Bea, Dee

            heads = page.locator(".matrix thead th")
            col_counts = [heads.nth(i).locator(".green-count").inner_text() for i in (1, 2)]
            assert col_counts == ["🟢×1", "🟢×0"], col_counts  # Cam, Eve
            assert heads.nth(1).locator(".green-count").get_attribute("title") == (
                "Favorable direct options among our remaining players")
            assert rows.nth(0).locator("th .green-count").get_attribute("title") == (
                "Favorable direct options among unplayed opponents")

            before_evidence = page.evaluate(
                f"JSON.stringify(window.__ucWarRoomPair({OURS!r}, {THEIRS!r}, 'EIGHT'))")
            page.select_option('#lineup-lab select[data-plan="avail"][data-pid="1"]', "Unavailable")

            heads = page.locator(".matrix thead th")
            col_counts_after = [heads.nth(i).locator(".green-count").inner_text() for i in (1, 2)]
            assert col_counts_after == ["🟢×0", "🟢×0"], (
                "Cam's column count must drop to 0 once Ann (its only green row) is unavailable",
                col_counts_after)
            # Evidence itself never moves -- only who counts as remaining.
            assert page.evaluate(
                f"JSON.stringify(window.__ucWarRoomPair({OURS!r}, {THEIRS!r}, 'EIGHT'))") == before_evidence
            assert errors == [], errors
        finally:
            browser.close()


def test_captain_matrix_counts_have_a_visible_phone_explanation(tmp_path: Path):
    """GPT audit (issue #84, MATRIX-01): a hover title explains nothing on a phone, which has no
    hover -- the actual synthetic phone case showed only a bare green dot x N with no visible
    meaning. Needed a compact visible key, worded so 0 is never read as "hardest" or "safe": it
    can just as easily mean even, shared-opponent-only or no verified evidence at all.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page, errors = _page(tmp_path, browser)
            legend = page.locator("#wr-matrix .matrix-count-legend")
            assert legend.count() == 1
            text = legend.inner_text()
            assert "favorable direct options left among unplayed opponents" in text
            assert "favorable direct record against them" in text
            # The caution against overreading a 0 must be visible, not just implied.
            assert "does not mean hardest or safe" in text
            assert errors == [], errors
        finally:
            browser.close()


def test_next_send_warns_before_spending_breaks_the_entered_budget(tmp_path: Path):
    payload = _payload()
    payload["players"][2]["team_history"][0]["skill_level"] = 3
    payload["evidence"] = [r for r in payload["evidence"]
                           if {r["player_id"], r["opponent_id"]} not in ({3, 10}, {3, 11})]
    payload["evidence"] += _games(3, 10, "WWWL") + _games(3, 11, "WW")
    path = tmp_path / "candidate_budget.html"
    path.write_text(render(payload, built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001"),
                    encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(path.as_uri())
            assert page.locator("#next-send .ns-budget").count() == 0  # no cap is assumed
            page.fill("#ll-cap", "7")
            page.locator("#ll-cap").dispatch_event("change")
            first = page.locator("#next-send .ns-medal").first
            assert first.locator("[data-send-our]").get_attribute("data-send-our") == "1"
            assert "exceeds your entered skill budget" in first.locator(".ns-budget").inner_text()
            assert page.locator("#next-send [data-send-our='3']").locator("..").locator(".ns-budget").count() == 0
            # Raising the budget changes the warning, not the evidence order.
            page.fill("#ll-cap", "8")
            page.locator("#ll-cap").dispatch_event("change")
            assert page.locator("#next-send .ns-budget").count() == 0
            assert page.locator("#next-send .ns-medal").first.locator("[data-send-our]").get_attribute("data-send-our") == "1"
            assert errors == []
        finally:
            browser.close()


def test_next_send_duplicate_names_keep_distinguishing_captured_skill(tmp_path: Path):
    from tests.test_excel_war_room_formulas import _payload as crowded_payload
    payload=crowded_payload(crowded=True)
    path=tmp_path/'duplicate.html'
    path.write_text(render(payload,built_at="2026-10-07 18:00 UTC",viewer_member_external_id="1001"),encoding="utf-8")
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page=browser.new_page();page.goto(path.as_uri())
            a=page.locator('#next-send [data-send-our="1"]').locator('..')
            b=page.locator('#next-send [data-send-our="4"]').locator('..')
            assert "Ann Archer (SL 5)" in a.inner_text()
            assert "Ann Archer (SL 4)" in b.inner_text()
            assert "APA record ID" not in a.inner_text()+b.inner_text()
        finally:browser.close()


def test_incomplete_budget_is_disclosed_once_for_shared_missing_skill(tmp_path: Path):
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page,errors=_page(tmp_path,browser)
            page.set_viewport_size({'width':390,'height':844})
            assert page.locator('#next-send .ns-budget-scope').count()==0
            before=page.locator('#next-send [data-send-our]').evaluate_all('(els)=>els.map(e=>e.dataset.sendOur)')
            page.fill('#ll-cap','20');page.locator('#ll-cap').dispatch_event('change')
            assert page.locator('#next-send .ns-budget-scope').count()==1
            assert page.locator('#next-send .ns-budget').count()==0
            assert page.locator('#next-send [data-send-our]').evaluate_all('(els)=>els.map(e=>e.dataset.sendOur)')==before
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            assert errors==[]
        finally:browser.close()


def test_sample_caution_is_visible_in_quick_read_and_folded_avoid(tmp_path: Path):
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page,errors=_page(tmp_path,browser)
            text=page.locator('#scouting-cards .quick-read').first.inner_text()
            assert 'Historical top record: Ann Archer (2-0, small sample)' in text
            assert 'Avoid: Bea Baker (0-2, small sample)' in text
            summary=page.locator('#next-send .ns-more summary')
            assert 'small sample' in summary.inner_text()
            assert not page.locator('#next-send .ns-more').evaluate('(el)=>el.open')
            page.set_viewport_size({'width':390,'height':844})
            assert 'small sample' in summary.inner_text()
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            assert errors==[]
        finally:browser.close()


def test_one_meeting_threat_stays_flagged_with_visible_sample_and_unknown_scope(tmp_path: Path):
    payload=_payload()
    payload['evidence']=[r for r in payload['evidence'] if {r['player_id'],r['opponent_id']}!={3,11}]+_games(3,11,'L')
    path=tmp_path/'thin-threat.html';path.write_text(render(payload,built_at='2026-10-07 18:00 UTC',viewer_member_external_id='1001'),encoding='utf-8')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={'width':390,'height':844});page.goto(path.as_uri())
            panel=page.locator('#tonight .decide-threats')
            assert 'remaining roster' in panel.inner_text().lower()
            assert 'Eve Ellis — 1-0 (1 meeting, small sample)' in panel.inner_text()
            assert 'small sample' in page.locator('#scouting-cards .quick-read').nth(1).inner_text()
            assert 'small sample' in page.locator('#wr-risks').inner_text()
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.select_option('#lineup-lab select[data-plan="avail"][data-pid="3"]','Unavailable')
            assert 'unknown vs our remaining roster' in panel.inner_text()
            assert 'small sample' in panel.inner_text()
            assert 'not cleared' in page.locator('#wr-risks').inner_text()
        finally:browser.close()


def test_next_send_distinguishes_meeting_sl_from_captured_roster_sl(tmp_path: Path):
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page,errors=_page(tmp_path,browser)
            first=page.locator('#next-send .ns-medal').first
            assert 'Meeting opponent SL 4; roster capture SL 6' in first.inner_text()
            assert 'Captured SL 6' in page.locator('#next-send .ns-chip').first.inner_text()
            assert 'Meeting opponent SL 4; roster capture SL 6' in page.locator('#scouting-cards .quick-read').first.inner_text()
            assert first.locator('[data-send-our]').get_attribute('data-send-our')=='1'
            page.set_viewport_size({'width':390,'height':844})
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            assert errors==[]
        finally:browser.close()


def test_entered_budget_counts_unknown_availability_and_does_not_clear_unknown_sl(tmp_path: Path):
    from tests.test_excel_war_room_formulas import _payload as crowded_payload
    path=tmp_path/"budget-trust.html"
    path.write_text(render(crowded_payload(crowded=True),built_at="2026-10-07 18:00 UTC",viewer_member_external_id="1001"),encoding="utf-8")
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={"width":390,"height":844});page.goto(path.as_uri())
            before=page.locator("#next-send [data-send-our]").evaluate_all("els=>els.map(e=>e.dataset.sendOur)")
            page.fill("#ll-cap","7");page.locator("#ll-cap").dispatch_event("change")
            # Current implementation already counts Unknown as remaining: challenge stale audit.
            assert page.locator("#tonight .lineup-budget").count()==1
            assert page.locator("#next-send .ns-budget-scope").count()==1
            # An uncaptured SL could be cheaper: captured subtotal is not a proof of illegality.
            assert "Cannot field a legal lineup" not in page.locator("#tonight .lineup-budget").inner_text()
            assert "No choice is cleared" in page.locator("#next-send .ns-budget-scope").inner_text()
            assert page.locator("#next-send [data-send-our]").evaluate_all("els=>els.map(e=>e.dataset.sendOur)")==before
            assert not page.evaluate("document.documentElement.scrollWidth>innerWidth")
        finally:browser.close()


def test_blind_pick_shares_next_send_label_and_carries_candidate_budget_warning(tmp_path: Path):
    from tests.test_excel_war_room_formulas import _payload as crowded_payload
    payload=crowded_payload(crowded=True)
    payload["players"][2]["team_history"][0]["skill_level"]=3
    path=tmp_path/"blind-budget.html"
    path.write_text(render(payload,built_at="2026-10-07 18:00 UTC",viewer_member_external_id="1001"),encoding="utf-8")
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={"width":390,"height":844});page.goto(path.as_uri())
            page.fill("#ll-cap","5");page.locator("#ll-cap").dispatch_event("change")
            lead=page.locator("#tonight .blind-send")
            assert lead.locator(".bs-name").inner_text()=="Ann Archer (SL 5)"
            assert "exceeds your entered skill budget" in lead.locator(".ns-budget").inner_text()
            assert "Cannot field a legal lineup" in page.locator("#tonight .lineup-budget").inner_text()
            assert page.locator("#next-send .ns-medal").first.locator("b").first.inner_text()==lead.locator(".bs-name").inner_text()
        finally:browser.close()


def test_missing_sl_does_not_turn_known_subtotal_into_proven_lineup_failure(tmp_path: Path):
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page,errors=_page(tmp_path,browser)
            page.fill("#ll-cap","7");page.locator("#ll-cap").dispatch_event("change")
            text=page.locator("#tonight .lineup-budget").inner_text()
            assert "Cannot field a legal lineup" not in text
            assert "unable to field a legal lineup" not in text
            assert "incomplete" in text
            assert errors==[]
        finally:browser.close()


def test_phone_matrix_note_flag_opens_the_actual_coach_observation(tmp_path: Path):
    path=tmp_path/"phone-note.html"
    path.write_text(render(_payload(),built_at="2026-10-07 18:00 UTC",viewer_member_external_id="1001"),encoding="utf-8")
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={"width":390,"height":844},has_touch=True,is_mobile=True)
            errors=[];page.on("pageerror",lambda e:errors.append(str(e)));page.goto(path.as_uri())
            before=page.locator("#next-send [data-send-our]").evaluate_all("els=>els.map(e=>e.dataset.sendOur)")
            note=page.locator('textarea[data-plan="note"][data-pid="10"]')
            note.fill("Patient safeties; coach opinion.");note.dispatch_event("change")
            flag=page.locator(".matrix thead th .note-flag")
            assert flag.get_attribute("href")=="#coach-note-10"
            box=flag.bounding_box();assert box["width"]>=44 and box["height"]>=44
            flag.tap()
            assert note.evaluate("e=>e===document.activeElement")
            assert note.input_value()=="Patient safeties; coach opinion."
            assert page.locator("#next-send [data-send-our]").evaluate_all("els=>els.map(e=>e.dataset.sendOur)")==before
            assert errors==[]
        finally:browser.close()
