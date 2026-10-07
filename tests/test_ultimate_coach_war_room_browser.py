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
from analytics.ultimate_coach_war_room import SENDABLE, meetings_index, sl_bucket_index, war_room_pair
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
    payload = _payload()
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
            assert js["matrix"] == [[[c["category"], c["cell"], c["explanation"]] for c in row["cells"]] for row in py["matrix"]]
            assert [[c for row in js["matrix"] for c in [x[0] for x in row]]] == [["G", "I", "R", "X", "E", "R"]]
            assert js["best"] == [[r["player"] for r in b["rows"] if r["category"] in SENDABLE] for b in py["blocks"]]
            assert js["concerning"] == [c["text"] for c in py["concerning"]]
            assert js["threats"] == [c["threat_text"] for c in py["threats"]]
            keys = ("sl", "team_record", "lifetime", "sample", "vs_ours", "met_list", "shared_summary", "by_sl",
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
            assert f"1. {ANN} — ≈ 1-0 vs 0-1 (1 shared)" in sends
            risks = page.inner_text("#wr-risks")
            assert f"{EVE} · SL 3 · 2-0 vs our roster (2 meetings, 1 of our players)" in risks
            assert f"{BEA} vs {CAM}: 0-2 direct (2 meetings)" in risks
            cells = page.locator("#wr-matrix .mcell")
            assert [cells.nth(i).inner_text() for i in range(6)] == [
                "2-0 (2)", "≈ 1-0 vs 0-1 (1 shared)", "0-2 (2)", "No evidence", "1-1 (2)", "0-2 (2)"]
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
                assert "Ann Archer vs Cam Cole (2-0 (2))" in text and "Eve Ellis (2-0 vs us)" in text
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
