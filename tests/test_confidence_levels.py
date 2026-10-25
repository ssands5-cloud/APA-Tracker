"""Captain confidence levels: the stated rule, its scenarios, and phone/HTML parity with Python."""
from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from analytics.ultimate_coach_confidence import LEVEL_POINTS, overall_record, pair_confidence, sl_changed_since_last_meeting
from tests.test_excel_war_room_formulas import _games, _payload
from tests.test_ultimate_coach_war_room_browser import OURS, THEIRS, _python_war_room_for
from ui.ultimate_coach import render

NONE = (0, 0)


def level(direct, own=NONE, opp=NONE, shared=None, sl_changed=False):
    return pair_confidence(direct, own_overall=own, opp_overall=opp, shared=shared, sl_changed=sl_changed)["level"]


def test_challenge_scenarios_read_the_way_history_says():
    assert level((1, 1)) == "Thin"                                   # 1-0
    assert level((8, 10)) == "Strong"                                # 8-2
    assert level(None, own=(50, 65), opp=(30, 60)) == "Strong"       # 50-15, no direct history
    assert level((1, 1), own=(20, 40), opp=(40, 60)) == "Conflicted" # 1-0 with weaker form
    assert level((0, 1), own=(40, 60), opp=(20, 40)) == "Conflicted" # 0-1 with stronger form
    assert level((0, 1)) == "Caution"
    assert level((6, 6)) == "Strong" and level((3, 4)) == "Solid" and level((2, 2)) == "Thin"
    assert level((2, 4)) == "Thin"                                   # even record
    assert level((2, 3), own=(40, 60), opp=(30, 60)) == "Strong"     # 3 meetings plus better form
    assert level((1, 1), own=(40, 60), opp=(30, 60)) == "Solid"      # thin record backed by form
    assert level(None, own=(35, 60), opp=(30, 60)) == "Solid"
    assert level(None, own=(20, 60), opp=(40, 60)) == "Caution"
    assert level(None) == "Unknown"


def test_skill_level_change_drops_one_level_and_says_why():
    c = pair_confidence((8, 10), own_overall=NONE, opp_overall=NONE, sl_changed=True)
    assert c["level"] == "Solid" and "skill levels changed" in c["why"]
    assert level((3, 4), sl_changed=True) == "Thin"
    assert level((1, 1), sl_changed=True) == "Thin"       # already Thin: nothing lower to drop to
    assert level((0, 2), sl_changed=True) == "Caution"     # a loss is not softened


def test_shared_opponents_need_three_for_solid():
    assert level(None, shared=(6, 8, 2, 8, 4)) == "Solid"
    assert level(None, shared=(6, 8, 2, 8, 2)) == "Thin"
    assert level(None, shared=(2, 8, 6, 8, 4)) == "Caution"
    assert level(None, shared=(4, 8, 4, 8, 4)) == "Unknown"


def test_boundaries_are_exact_and_thin_overall_records_do_not_count():
    # Form (w+5)/(g+10): 25-15 -> 30/50 = .60 ; 20-20 -> 25/50 = .50. Gap exactly .10 >= .05.
    assert level(None, own=(25, 40), opp=(20, 40)) == "Solid"
    # Gap exactly .05: (22.5 not integral) use 45/100 vs 40/100 -> (45+5)/110 vs (40+5)/110 = .4545.. vs .409..
    # Exact-equality case: own 27/40 -> 32/50 = .64, opp 22/40 -> 27/50 = .54: gap .10; 24.5 impossible, so test .15 edge:
    assert level(None, own=(35, 40), opp=(20, 40)) == "Strong"   # .80 vs .50 = .30
    assert level(None, own=(27, 40), opp=(20, 40)) == "Solid"    # .64 vs .50 = .14 < .15
    assert level(None, own=(28, 40), opp=(20, 40)) == "Strong"   # .66 vs .50 = .16
    assert level(None, own=(50, 65), opp=(30, 19)) == "Unknown"  # opponent under 20 games: no form signal
    assert level((1, 1), own=(10, 60), opp=(5, 10)) == "Thin"    # weaker form ignored when opponent record is thin


def test_points_order_matches_levels():
    order = ["Strong", "Solid", "Thin", "Unknown", "Caution"]
    assert [LEVEL_POINTS[x] for x in order] == sorted((LEVEL_POINTS[x] for x in order), reverse=True)
    assert LEVEL_POINTS["Conflicted"] == LEVEL_POINTS["Unknown"]


def test_overall_record_uses_complete_scopes_only():
    p = {"career_stats": [{"format": "EIGHT", "matches_won": 10, "matches_played": 20},
                          {"format": "EIGHT", "matches_won": None, "matches_played": 5},
                          {"format": "EIGHT", "matches_won": True, "matches_played": 3},
                          {"format": "NINE", "matches_won": 9, "matches_played": 9},
                          {"format": "EIGHT", "matches_won": 7, "matches_played": 6}]}
    assert overall_record(p, "EIGHT") == (10, 20)
    assert overall_record(None, "EIGHT") == (0, 0)


def test_sl_change_needs_both_current_and_latest_captured():
    games = [{"sort": "2026-09-01", "own_sl": 5, "opp_sl": 4}, {"sort": "2026-01-01", "own_sl": 4, "opp_sl": 4}]
    assert sl_changed_since_last_meeting(games, 5, 4) is False
    assert sl_changed_since_last_meeting(games, 6, 4) is True
    assert sl_changed_since_last_meeting(games, None, 4) is False
    assert sl_changed_since_last_meeting([{"sort": "", "own_sl": 5, "opp_sl": 4}], 6, 4) is False


def _career(w, g, extra=()):
    return [{"format": "EIGHT", "matches_won": w, "matches_played": g}, *extra]


def parity_payload():
    p = _payload(crowded=True)
    records = {1: _career(50, 65), 2: _career(20, 40), 3: _career(8, 15), 4: _career(30, 60, [{"format": "EIGHT", "matches_won": None, "matches_played": 9}]),
               5: _career(40, 60), 6: _career(28, 40), 10: _career(30, 60), 11: _career(20, 40), 12: _career(45, 60), 13: _career(5, 30)}
    for player in p["players"]:
        player["career_stats"] = records.get(player["id"], [])
    p["evidence"] = (_games(1, 10, "W") + _games(2, 10, "WWWWWWWWLL") + _games(3, 10, "LL") + _games(4, 10, "WL")
                     + _games(5, 11, "WWW") + _games(6, 11, "L") + _games(1, 12, "WWLL") + _games(3, 12, "W")
                     + _games(5, 13, "W") + _games(6, 13, "WW") + _games(11, 12, "LW") + _games(10, 13, "WL"))
    return p


@pytest.mark.parametrize("width", [390])
def test_phone_confidence_matches_python_for_every_pairing(tmp_path, width):
    payload = parity_payload()
    py = _python_war_room_for(payload)
    expected = [[next(r for r in b["rows"] if r["member"]["id"] == m["id"])["confidence"]["text"] for m in py["ours"]]
                for b in py["blocks"]]
    levels = {t.split(" — ")[0] for row in expected for t in row}
    assert {"Strong", "Thin", "Caution", "Conflicted"} <= levels, levels   # the fixture exercises the rule
    path = tmp_path / "confidence.html"
    path.write_text(render(payload, built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001"), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(path.as_uri())
            js = page.evaluate(f"window.__ucConfidence({OURS!r}, {THEIRS!r}, 'EIGHT')")
            assert js == expected
            assert errors == []
        finally:
            browser.close()
