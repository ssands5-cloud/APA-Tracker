"""Match Night Engine (M3): exact against an independent game-tree search, cap-safe, and captain-shaped."""
from __future__ import annotations

import random

import pytest

from analytics.match_night_engine import _Night, match_plan
from analytics.ultimate_coach_confidence import LEVEL_POINTS

LEVELS = list(LEVEL_POINTS)


def L(level):
    return {"level": level, "points": LEVEL_POINTS[level], "why": f"{level} evidence", "text": f"{level} — {level} evidence"}


def night(our_specs, their_specs, grid):
    ours = [{"id": f"o{i}", "name": n, "sl": s} for i, (n, s) in enumerate(our_specs)]
    theirs = [{"id": f"t{j}", "name": n, "sl": s} for j, (n, s) in enumerate(their_specs)]
    value = {(o["id"], t["id"]): L(grid[i][j]) for i, o in enumerate(ours) for j, t in enumerate(theirs)}
    return ours, theirs, value


def brute(ours, theirs, value, games, cap, used, we_lead):
    """Plain game-tree search with no memo and no shared code: the reference answer."""
    def legal(rem_o, i, games_after, spent):
        sl = ours[i]["sl"] if isinstance(ours[i]["sl"], int) else 0
        if cap is None:
            return True
        rest = sorted(ours[k]["sl"] for k in rem_o if k != i and isinstance(ours[k]["sl"], int))
        unknown = sum(1 for k in rem_o if k != i and not isinstance(ours[k]["sl"], int))
        need = min(max(0, games_after - unknown), len(rest))
        return used + spent + sl + sum(rest[:need]) <= cap

    def go(rem_o, rem_t, g, spent, lead):
        cand = [i for i in rem_o if legal(rem_o, i, g - 1, spent)] if g > 0 else []
        if not cand or not rem_t:
            return 0
        def after(i, j):
            sl = ours[i]["sl"] if isinstance(ours[i]["sl"], int) else 0
            return value[(ours[i]["id"], theirs[j]["id"])]["points"] + go(
                [k for k in rem_o if k != i], [k for k in rem_t if k != j], g - 1, spent + sl, not lead)
        if lead:
            return max(min(after(i, j) for j in rem_t) for i in cand)
        return min(max(after(i, j) for i in cand) for j in rem_t)

    games = max(0, min(games, len(ours), len(theirs)))
    return go(list(range(len(ours))), list(range(len(theirs))), games, 0, we_lead)


@pytest.mark.parametrize("seed", range(200))
def test_plan_values_match_an_independent_game_tree_search(seed):
    rng = random.Random(seed)
    no, nt = rng.randint(2, 5), rng.randint(2, 5)
    our_specs = [(f"O{i}", rng.choice([2, 3, 4, 5, 6, 7, None])) for i in range(no)]
    their_specs = [(f"T{j}", rng.choice([2, 3, 4, 5, 6])) for j in range(nt)]
    grid = [[rng.choice(LEVELS) for _ in range(nt)] for _ in range(no)]
    ours, theirs, value = night(our_specs, their_specs, grid)
    games = rng.randint(1, 4)
    cap = rng.choice([None, 12, 15, 23])
    used = rng.choice([0, 0, 3])
    plan = match_plan(ours, theirs, value, games_left=games, cap=cap, used=used)
    if plan.get("lead") is None:
        return
    assert plan["total_if_we_lead"] == brute(ours, theirs, value, games, cap, used, True)
    assert plan["total_if_they_lead"] == brute(ours, theirs, value, games, cap, used, False)
    # The game plan is a legal night: nobody used twice, cap respected on known skill levels.
    for line in (plan["plan_if_we_lead"], plan["plan_if_they_lead"]):
        assert len({p["our"] for p in line}) == len(line) and len({p["their"] for p in line}) == len(line)
        assert len(line) <= plan["games_left"]
        if cap is not None:
            known = sum(next(o["sl"] for o in ours if o["name"] == p["our"]) or 0 for p in line)
            assert used + known <= cap
        assert [p["leader"] for p in line] == [("us" if (n % 2 == 0) == (line[0]["leader"] == "us") else "them")
                                               for n in range(len(line))]
    for board in (plan["best_board"], plan["safest_board"]):
        assert len({p["our"] for p in board}) == len(board)
        if cap is not None:
            assert used + sum(next(o["sl"] for o in ours if o["name"] == p["our"]) or 0 for p in board) <= cap


def captain_night():
    our = [("Paul", 6), ("Rashael", 5), ("Bob", 4), ("Tony", 3), ("Dana", 5), ("Eli", 2)]
    their = [("Xavier", 6), ("Yara", 5), ("Mike", 4), ("Steve", 3), ("Zed", 5)]
    grid = [
        ["Strong", "Thin", "Solid", "Unknown", "Thin"],       # Paul
        ["Unknown", "Strong", "Thin", "Unknown", "Caution"],  # Rashael
        ["Caution", "Thin", "Strong", "Thin", "Unknown"],     # Bob
        ["Caution", "Caution", "Unknown", "Caution", "Caution"],  # Tony
        ["Thin", "Unknown", "Unknown", "Solid", "Strong"],    # Dana
        ["Unknown", "Unknown", "Thin", "Thin", "Unknown"],    # Eli
    ]
    return night(our, their, grid)


def test_captain_night_answers_like_a_strong_captain():
    ours, theirs, value = captain_night()
    plan = match_plan(ours, theirs, value, games_left=5, cap=23)
    answers = {r["their"]: r["our"] for r in plan["responses"]}
    # Each of their players gets our only Strong answer, if they put that player up.
    assert answers["Xavier"] == "Paul" and answers["Yara"] == "Rashael"
    assert answers["Mike"] == "Bob" and answers["Zed"] == "Dana"
    # Against Steve, Dana is the better pairing tonight but our only Strong answer to Zed: keep her.
    steve = next(r for r in plan["responses"] if r["their"] == "Steve")
    assert steve["our"] != "Dana" and "keep Dana" in steve["cost_later"]
    # We never lead with a player who is our only Strong answer to someone.
    assert plan["lead"]["our"] not in {"Paul", "Rashael", "Bob", "Dana"}
    assert "keeps" in plan["lead"]["why_lead"]
    holds = {h["our"]: h["why"] for h in plan["holds"]}
    assert "Paul" in holds and "only Strong answer to Xavier" in holds["Paul"]
    assert all("only Strong answer" in w for w in holds.values())
    # The cheapest concession is the player with no good matchups.
    assert plan["sacrifices"][0]["our"] == "Tony"
    assert plan["best_board"] and all(p["level"] in ("Strong", "Thin") for p in plan["best_board"])
    assert plan["cap"]["slack"] >= 0 and plan["cap"]["incomplete"] is False
    assert plan["fragility"]["player"] in {"Paul", "Rashael", "Bob", "Dana"}


def test_plan_is_deterministic():
    ours, theirs, value = captain_night()
    assert match_plan(ours, theirs, value, games_left=5, cap=23) == match_plan(ours, theirs, value, games_left=5, cap=23)


def test_edges_never_invent_a_plan():
    ours, theirs, value = captain_night()
    done = match_plan(ours, theirs, value, games_left=0, cap=23)
    assert done["lead"] is None and done["responses"] == [] and done["best_board"] == []
    # A missing skill level makes the cap check incomplete; it is never treated as 0 in the cap summary.
    ours[3]["sl"] = None
    plan = match_plan(ours, theirs, value, games_left=5, cap=23)
    assert plan["cap_incomplete"] is True and plan["cap"]["incomplete"] is True
    # Fewer of our players than games: the night is as long as the shorter side.
    short = match_plan(ours[:2], theirs, value, games_left=5, cap=None)
    assert short["games_left"] == 2 and len(short["plan_if_we_lead"]) == 2
    # No evidence at all: a legal plan, everything Unknown, nothing fragile, no sacrifice claimed as cheap.
    blank = {k: L("Unknown") for k in value}
    plain = match_plan(ours, theirs, blank, games_left=5, cap=None)
    assert set(plain["confidence"]) == {"Unknown"} and plain["fragility"]["rating"] == "Low"
    assert plain["holds"] == []


def test_cap_that_cannot_be_met_yields_no_plan_rather_than_an_illegal_one():
    ours, theirs, value = captain_night()
    plan = match_plan(ours, theirs, value, games_left=5, cap=10)
    assert plan["lead"] is None
    night_obj = _Night(ours, theirs, value, 5, 10, 0)
    assert night_obj.legal_ours(night_obj.full_ours) == []


def _random_night(seed):
    rng = random.Random(seed)
    no, nt = rng.randint(2, 6), rng.randint(2, 6)
    our_specs = [(f"O{i}", rng.choice([2, 3, 4, 5, 6, 7, None])) for i in range(no)]
    their_specs = [(f"T{j}", rng.choice([2, 3, 4, 5, 6])) for j in range(nt)]
    grid = [[rng.choice(LEVELS) for _ in range(nt)] for _ in range(no)]
    ours, theirs, value = night(our_specs, their_specs, grid)
    return ours, theirs, value, rng.randint(0, 5), rng.choice([None, 12, 15, 23]), rng.choice([0, 0, 4])


def test_phone_engine_produces_the_identical_plan(tmp_path):
    from playwright.sync_api import sync_playwright
    from tests.test_excel_war_room_formulas import _payload
    from ui.ultimate_coach import render
    path = tmp_path / "engine.html"
    path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001"), encoding="utf-8")
    cases = [_random_night(seed) for seed in range(60)] + [captain_night() + (5, 23, 0)]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(path.as_uri())
            for ours, theirs, value, games, cap, used in cases:
                js_value = {f"{o}|{t}": v for (o, t), v in value.items()}
                js = page.evaluate("a => window.__ucMatchPlan(a[0], a[1], a[2], a[3], a[4], a[5])",
                                   [ours, theirs, js_value, games, cap, used])
                assert js == match_plan(ours, theirs, value, games_left=games, cap=cap, used=used), (games, cap, used)
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_match_night_plan_card_matches_python_and_replans_after_a_send(tmp_path, width):
    from playwright.sync_api import sync_playwright
    from analytics.match_night_engine import plan_for_war_room
    from tests.test_confidence_levels import parity_payload
    from tests.test_ultimate_coach_war_room_browser import OURS, THEIRS, _python_war_room_for
    from ui.ultimate_coach import render
    payload = parity_payload()
    py = _python_war_room_for(payload)
    path = tmp_path / "plan.html"
    path.write_text(render(payload, built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001"), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(path.as_uri())
            ids = [m["id"] for m in py["ours"]]
            for remaining, unplayed, played_n, played_sl, cap in ((None, None, 0, 0, None), (None, None, 0, 0, 23),
                                                                 (ids[1:], [False, True], 1, 5, 23), (ids[:3], None, 2, 9, None)):
                js = page.evaluate("a => window.__ucPlanFor(a[0], a[1], 'EIGHT', a[2], a[3], a[4], a[5], a[6])",
                                   [OURS, THEIRS, remaining, unplayed, played_n, played_sl, cap])
                assert js == plan_for_war_room(py, remaining=None if remaining is None else set(remaining),
                                               unplayed=unplayed, played_count=played_n, played_sl=played_sl, cap=cap)
            card = page.locator("#match-plan")
            text = card.inner_text()
            first = plan_for_war_room(py)
            assert "if we put up first" in text.lower() and first["lead"]["our"] in text and "if they put up" in text.lower()
            for r in first["responses"]:
                assert f"{r['their']} → {r['our']}" in text
            assert "not odds" in text and "%" not in text
            before = first["games_left"]
            page.locator("#next-send [data-send-our]").first.click()
            after = page.locator("#match-plan .mp-sub").inner_text()
            assert after.startswith(f"{before - 1} game") or "No games left" in page.locator("#match-plan").inner_text()
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("seed", range(120))
def test_boards_are_optimal_against_brute_force(seed):
    from itertools import combinations, permutations
    ours, theirs, value, games, cap, used = _random_night(1000 + seed)
    k = max(0, min(games, len(ours), len(theirs)))
    plan = match_plan(ours, theirs, value, games_left=games, cap=cap, used=used)
    if plan.get("lead") is None or k == 0:
        return
    pts = {(o["name"], t["name"]): value[(o["id"], t["id"])]["points"] for o in ours for t in theirs}
    sl = {o["name"]: o["sl"] for o in ours}
    best_total = best_safe = None
    for ts in combinations(theirs, k):
        for os_ in permutations(ours, k):
            if cap is not None and used + sum(sl[o["name"]] or 0 for o in os_) > cap:
                continue
            vals = [pts[(o["name"], t["name"])] for o, t in zip(os_, ts)]
            tot, worst = (sum(vals), min(vals)), (min(vals), sum(vals))
            best_total = tot if best_total is None or tot > best_total else best_total
            best_safe = worst if best_safe is None or worst > best_safe else best_safe

    def key(board, safest):
        vals = [pts[(p["our"], p["their"])] for p in board]
        return (min(vals), sum(vals)) if safest else (sum(vals), min(vals))
    assert key(plan["best_board"], False) == best_total
    assert key(plan["safest_board"], True) == best_safe
