"""Ultimate Coach V2 candidate: pairing model, planner wiring, engine switch and M3-vs-V2 comparison.

All data here is synthetic. M3 stays the baseline and the default build is unchanged (checked below).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from analytics.ultimate_coach_confidence import pair_confidence
from analytics.uc_v2_pair_model import (V2_LEVEL_ORDER, band, feature_vector, load_model, pair_value,
                                        team_points, win_probability)
from tests.test_ultimate_coach_war_room_browser import OURS, THEIRS, _payload
from ui.ultimate_coach import render


def _render(tmp_path: Path, *, ui="classic", engine="v2") -> Path:
    path = tmp_path / f"uc-{ui}-{engine}.html"
    path.write_text(render(_payload(), built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001",
                           ui=ui, engine=engine), encoding="utf-8")
    return path


# ---------------------------------------------------------------- model (Python reference)

def test_model_file_holds_aggregates_only_and_both_formats():
    model = load_model()
    assert set(model["formats"]) == {"EIGHT", "NINE"}
    for fmt in ("EIGHT", "NINE"):
        m = model["formats"][fmt]
        assert len(m["coef"]) == len(m["mu"]) == len(m["sd"]) == 92
        assert m["holdout"]["test_logloss"] < m["holdout"]["test_logloss_constant"], "must beat a coin flip out of sample"
        assert 0.8 <= m["holdout"]["test_calibration_intercept_slope"][1] <= 1.2
    text = json.dumps(model)
    for forbidden in ("player", "team_id", "name", "match_id"):
        assert forbidden not in text.replace("team_points", "").replace("team_nights", "")


def test_probability_is_symmetric_and_bounded():
    kw = dict(direct=(3, 5), recent_p=(6, 10), recent_o=(4, 10), form_p=(120, 200), form_o=(90, 200))
    p = win_probability("EIGHT", 5, 4, **kw)
    q = win_probability("EIGHT", 4, 5, direct=(2, 5), recent_p=(4, 10), recent_o=(6, 10), form_p=(90, 200), form_o=(120, 200))
    assert 0 < p < 1 and abs(p + q - 1) < 1e-12


def test_missing_evidence_is_never_scored_as_even_and_skill_gaps_count_by_format():
    # No meetings, no shared opponents, no form: M3 says Unknown (0 points, the same as even).
    assert pair_confidence(None, own_overall=(0, 0), opp_overall=(0, 0), shared=None, sl_changed=False)["level"] == "Unknown"
    eight = win_probability("EIGHT", 3, 7)
    nine = win_probability("NINE", 3, 7)
    assert eight < 0.35, eight                      # a large underdog in 8-Ball (archive: about 22-30%)
    assert abs(nine - 0.5) < abs(eight - 0.5)       # 9-Ball handicap races keep it much closer
    assert win_probability("EIGHT", 5, 5) == pytest.approx(0.5, abs=1e-9)
    v = pair_value("EIGHT", 3, 7)
    assert v["level"] in ("Long shot", "Underdog") and v["points"] < 0
    assert "no direct meetings" in v["why"] and "fewer than 10 recorded games" in v["why"]   # gaps are disclosed


def test_direct_history_shared_opponents_recent_form_and_career_all_move_the_estimate():
    base = win_probability("EIGHT", 5, 5, form_p=(100, 200), form_o=(100, 200), recent_p=(5, 10), recent_o=(5, 10))
    assert win_probability("EIGHT", 5, 5, direct=(6, 7), form_p=(100, 200), form_o=(100, 200), recent_p=(5, 10), recent_o=(5, 10)) > base
    assert win_probability("EIGHT", 5, 5, shared=(9, 10, 2, 10, 3), form_p=(100, 200), form_o=(100, 200), recent_p=(5, 10), recent_o=(5, 10)) > base
    assert win_probability("EIGHT", 5, 5, form_p=(100, 200), form_o=(100, 200), recent_p=(9, 10), recent_o=(2, 10)) > base
    assert win_probability("EIGHT", 5, 5, form_p=(150, 200), form_o=(60, 200), recent_p=(5, 10), recent_o=(5, 10)) > base


def test_fit_script_and_module_share_one_feature_definition():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fit", Path(__file__).resolve().parents[1] / "scripts" / "fit_uc_v2_pair_model.py")
    fit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fit)
    for args in [(3, 7, None, None, (0, 0), (0, 0), (0, 0), (0, 0)),
                 (5, 4, (3, 5), (1, 2, 3, 4, 2), (6, 10), (4, 10), (120, 200), (90, 210)),
                 (6, 6, None, (5, 8, 2, 9, 3), (2, 3), (9, 10), (7, 9), (400, 700))]:
        assert fit.feature_vector(*args) == feature_vector(*args)


def test_bands_and_team_points():
    assert [band(p) for p in (0.7, 0.55, 0.5, 0.42, 0.2)] == V2_LEVEL_ORDER
    tp = load_model()["formats"]["EIGHT"]["team_points"]
    assert tp["per_individual_win"] > tp["per_individual_loss"] >= 0
    assert team_points("EIGHT", 1.0) == pytest.approx(tp["per_individual_win"])
    assert team_points("MASTERS", 0.5) is None


# ---------------------------------------------------------------- browser: parity, planner, switch

def test_js_probabilities_match_python_exactly(tmp_path):
    path = _render(tmp_path)
    cases = [("EIGHT", 3, 7, {}), ("NINE", 3, 7, {}), ("EIGHT", 5, 4, {"direct": [3, 5], "recent_p": [6, 10], "recent_o": [4, 10],
             "form_p": [120, 200], "form_o": [90, 200]}), ("NINE", 6, 6, {"shared": [5, 8, 2, 9, 3], "form_p": [7, 9], "form_o": [400, 700]}),
             ("EIGHT", None, 4, {"form_p": [10, 20]})]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            for fmt, a, b, kw in cases:
                js = page.evaluate("([f,a,b,o]) => window.__ucV2Probability(f,a,b,o)", [fmt, a, b, kw])
                py = win_probability(fmt, a, b, **{k: tuple(v) for k, v in kw.items()})
                assert js == pytest.approx(py, abs=1e-12), (fmt, a, b, kw)
        finally:
            browser.close()


def _scenario():
    """Owner acceptance shape (synthetic, universal): their strong SL7 and our newcomer SL3 with no meetings.

    Every experienced player of ours has a weaker career record than their SL7, so M3 rates them Caution (-3) while
    the newcomer (under 20 games) is Unknown (0, the same as even) -- M3 sends the SL3. V2 must price the skill gap."""
    ours = [{"id": "a", "name": "A6", "sl": 6, "form": (300, 620)}, {"id": "b", "name": "B5", "sl": 5, "form": (260, 540)},
            {"id": "c", "name": "C4", "sl": 4, "form": (250, 450)}, {"id": "d", "name": "D3 newcomer", "sl": 3, "form": (5, 7)},
            {"id": "e", "name": "E4", "sl": 4, "form": (240, 420)}]
    theirs = [{"id": "x", "name": "X7", "sl": 7, "form": (691, 1084)}, {"id": "y", "name": "Y3", "sl": 3, "form": (100, 230)},
              {"id": "z", "name": "Z4", "sl": 4, "form": (200, 400)}, {"id": "w", "name": "W5", "sl": 5, "form": (250, 500)},
              {"id": "v", "name": "V2", "sl": 2, "form": (50, 130)}]
    m3, v2 = {}, {}
    for o in ours:
        for t in theirs:
            m3[f'{o["id"]}|{t["id"]}'] = pair_confidence(None, own_overall=o["form"], opp_overall=t["form"], shared=None, sl_changed=False)
            v = pair_value("EIGHT", o["sl"], t["sl"], form_p=o["form"], form_o=t["form"],
                           recent_p=(min(10, o["form"][1]) * o["form"][0] // max(1, o["form"][1]), min(10, o["form"][1])),
                           recent_o=(min(10, t["form"][1]) * t["form"][0] // max(1, t["form"][1]), min(10, t["form"][1])))
            v.pop("gaps")
            v2[f'{o["id"]}|{t["id"]}'] = v
    strip = lambda xs: [{"id": x["id"], "name": x["name"], "sl": x["sl"]} for x in xs]
    return strip(ours), strip(theirs), m3, v2


def test_owner_scenario_v2_does_not_answer_a_strong_sl7_with_an_sl3_newcomer_because_evidence_is_missing(tmp_path):
    ours, theirs, m3, v2 = _scenario()
    assert m3["d|x"]["level"] == "Unknown" and all(m3[f"{k}|x"]["level"] == "Caution" for k in "abce")
    path = _render(tmp_path)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            plan = lambda value: page.evaluate("([o,t,v]) => window.__ucMatchPlan(o,t,v,5,null,0,null,0)", [ours, theirs, value])
            p3, p2 = plan(m3), plan(v2)
            answer = lambda p: next(r for r in p["responses"] if r["their"] == "X7")
            assert answer(p3)["our"] == "D3 newcomer"                       # the M3 behaviour the owner rejected
            a2 = answer(p2)
            assert a2["our"] != "D3 newcomer", a2
            assert "% estimated win chance" in a2["why"]
            # The SL3 is the weakest option against X7 under V2, by a clear margin.
            assert v2["d|x"]["p"] == min(v2[f"{k}|x"]["p"] for k in "abcde")
            # Concessions are named as such, with their estimate.
            assert all(s["level"] in V2_LEVEL_ORDER for s in p2["sacrifices"])
        finally:
            browser.close()


def test_v2_explains_why_a_stronger_option_is_saved_in_expected_games(tmp_path):
    path = _render(tmp_path)
    ours = [{"id": "a", "name": "Ace", "sl": 5}, {"id": "b", "name": "Bo", "sl": 5}]
    theirs = [{"id": "x", "name": "Xan", "sl": 5}, {"id": "y", "name": "Yul", "sl": 5}]
    mk = lambda p: {"level": band(p), "points": int(round(1000 * (p - 0.5))),
                    "p": p, "why": f"{round(100 * p)}% estimated win chance", "text": "", "v2": True}
    value = {"a|x": mk(0.60), "b|x": mk(0.55), "a|y": mk(0.70), "b|y": mk(0.40)}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            p = page.evaluate("([o,t,v]) => window.__ucV2Apply(window.__ucMatchPlan(o,t,v,2,null,0,null,0),o,t,v,2,null,0,0)", [ours, theirs, value])
            r = next(r for r in p["responses"] if r["their"] == "Xan")
            # Saving Ace for Yul is worth 0.25 expected wins in the worst case and on average: a strategic choice,
            # labelled as one, with the strongest matchup named and the captain's option stated.
            assert r["our"] == "Bo" and r["role"] == "Strategic choice"
            assert "Strategic choice: Bo (55%) instead of the strongest matchup Ace (60%)" in r["cost_later"]
            assert "keeps Ace for later (Ace vs Yul)" in r["cost_later"] and "+0.250 expected wins" in r["cost_later"]
            assert "The captain may prefer the stronger matchup now." in r["cost_later"]
        finally:
            browser.close()


@pytest.mark.parametrize("ui", ["classic", "broadcast"])
def test_v2_build_opens_on_v2_shows_the_comparison_and_switches_to_m3(tmp_path, ui):
    path = _render(tmp_path, ui=ui)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 900}); errors = []
            page.on("pageerror", lambda e: errors.append(str(e))); page.goto(path.as_uri())
            assert page.evaluate("window.__ucEngine()") == "v2"
            compare = page.locator("#uc-engine-compare").first
            assert compare.count() == 1
            text = compare.inner_text()
            assert "M3 vs V2 candidate" in text and "M3 answer" in text.replace("M3 ANSWER", "M3 answer")
            assert "log loss" in text and "calibration slope" in text
            v2_plan = page.evaluate(f"window.__ucPlanFor({OURS!r},{THEIRS!r},'EIGHT',null,null,0,0,23,'v2')")
            m3_plan = page.evaluate(f"window.__ucPlanFor({OURS!r},{THEIRS!r},'EIGHT',null,null,0,0,23,'m3')")
            assert all(r["level"] in V2_LEVEL_ORDER for r in v2_plan["responses"])
            assert all(r["level"] not in V2_LEVEL_ORDER for r in m3_plan["responses"])
            assert page.evaluate("window.__ucEngine('m3')") == "m3"
            assert "ENGINE: M3 BASELINE" in page.inner_text("#uc-engine-badge")
            page.reload()
            assert page.evaluate("window.__ucEngine()") == "v2", "a V2 build always reopens on V2"
            assert "ENGINE: V2 CANDIDATE" in page.inner_text("#uc-engine-badge")
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            assert errors == []
        finally:
            browser.close()


def test_default_build_is_unchanged_m3_only(tmp_path):
    html = render(_payload(), built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001")
    assert "var UC_V2_MODEL=" not in html and 'UC_ENGINE_DEFAULT="v2"' not in html
    assert "No matchup probability is displayed" in html
    path = tmp_path / "m3.html"; path.write_text(html, encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            assert page.evaluate("window.__ucEngine()") == "m3"
            assert page.evaluate("window.__ucEngine('v2')") == "m3", "no V2 model in a standard build"
            assert page.locator("#uc-engine-compare, .uc-engine-switch").count() == 0
        finally:
            browser.close()


def test_unknown_engine_is_rejected():
    with pytest.raises(ValueError):
        render(_payload(), built_at="2026-10-07 18:00 UTC", engine="v3")


def test_v2_keeps_the_strongest_matchup_when_saving_a_player_gains_too_little(tmp_path):
    """Worst-case solving alone gave up the strongest matchup for tiny gains (63% of real decisions); V2 does not."""
    path = _render(tmp_path)
    ours = [{"id": "a", "name": "Ace", "sl": 5}, {"id": "b", "name": "Bo", "sl": 5}]
    theirs = [{"id": "x", "name": "Xan", "sl": 5}, {"id": "y", "name": "Yul", "sl": 5}]
    mk = lambda p: {"level": band(p), "points": int(round(1000 * (p - 0.5))), "p": p,
                    "why": f"{round(100 * p)}% estimated win chance", "text": "", "v2": True}
    value = {"a|x": mk(0.60), "b|x": mk(0.55), "a|y": mk(0.58), "b|y": mk(0.50)}   # saving Ace gains only 0.03
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            m3_style = page.evaluate("([o,t,v]) => window.__ucMatchPlan(o,t,v,2,null,0,null,0)", [ours, theirs, value])
            assert next(r for r in m3_style["responses"] if r["their"] == "Xan")["our"] == "Bo"   # the worst-case search alone
        finally:
            browser.close()
    # Through the V2 plan path the captain-control rule applies: strongest matchup, alternative shown with its numbers.
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            out = page.evaluate("""([o,t,v]) => { const mp = window.__ucMatchPlan(o,t,v,2,null,0,null,0);
                return window.__ucV2Apply(mp,o,t,v,2,null,0,0).responses; }""", [ours, theirs, value])
            r = next(r for r in out if r["their"] == "Xan")
            assert r["our"] == "Ace" and r["role"] == "Recommended competitive matchup"
            assert "Strongest matchup available (60%)" in r["cost_later"]
            assert "Strategic alternative: Bo (55%) keeps Ace for later" in r["cost_later"]
            assert "+0.030 expected wins only if they always make their most damaging choice" in r["cost_later"]
            assert "Not enough to give up the stronger matchup" in r["cost_later"]
        finally:
            browser.close()


def test_decision_trace_lists_every_available_player_with_the_numbers(tmp_path):
    path = _render(tmp_path, ui="broadcast")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            t = page.evaluate(f"window.__ucV2Trace({OURS!r},{THEIRS!r},'EIGHT','Cam Cole',null,23)")
            assert t["opponent"] == "Cam Cole" and t["games"] >= 1 and t["minGain"] == 0.10
            assert len(t["rows"]) == 3 and sum(r["pick"] for r in t["rows"]) == 1
            for r in t["rows"]:
                for k in ("sl", "direct", "shared", "recent", "career", "apaCareer", "p", "matchPoints", "restWorst", "restAvg",
                          "totalWorst", "totalAvg", "nightPointsWorst", "nightPointsAvg", "later", "cap", "role"):
                    assert k in r, k
                assert abs(r["totalWorst"] - (r["p"] + r["restWorst"])) < 1e-12
                assert r["totalAvg"] >= r["totalWorst"] - 1e-12      # even choices are never worse than the worst case
            pick = next(r for r in t["rows"] if r["pick"])
            assert pick["role"] and t["summary"]
        finally:
            browser.close()


def _two_by_two(page, a_x, b_x, a_y, b_y):
    ours = [{"id": "a", "name": "Ace", "sl": 5}, {"id": "b", "name": "Bo", "sl": 5}]
    theirs = [{"id": "x", "name": "Xan", "sl": 5}, {"id": "y", "name": "Yul", "sl": 5}]
    mk = lambda p: {"level": band(p), "points": int(round(1000 * (p - 0.5))), "p": p,
                    "why": f"{round(100 * p)}% estimated win chance", "text": f"{band(p)} — {round(100 * p)}%", "v2": True}
    value = {"a|x": mk(a_x), "b|x": mk(b_x), "a|y": mk(a_y), "b|y": mk(b_y)}
    return page.evaluate("([o,t,v]) => window.__ucV2Apply(window.__ucMatchPlan(o,t,v,2,null,0,null,0),o,t,v,2,null,0,0)",
                         [ours, theirs, value])


def test_gpt_counterexample_every_reported_number_is_the_policy_v2_actually_plays(tmp_path):
    """GPT review of f628b13: Ace/Xan .60, Bo/Xan .55, Ace/Yul .58, Bo/Yul .50. V2 answers Xan with Ace, so the night
    it plays is .60 + .50 = 1.10 if they put up Xan; the old pure-minimax 1.13 must appear only as a benchmark."""
    path = _render(tmp_path)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            mp = _two_by_two(page, 0.60, 0.55, 0.58, 0.50)
            r = {x["their"]: x for x in mp["responses"]}
            assert r["Xan"]["our"] == "Ace" and r["Yul"]["our"] == "Ace"
            line = mp["plan_if_they_lead"]
            assert [(g["their"], g["our"]) for g in line] == [("Xan", "Ace"), ("Yul", "Bo")]
            assert mp["total_if_they_lead"] == 1100                 # .60 + .50, the policy's own worst case
            assert abs(sum(g["p"] for g in line) - 1.10) < 1e-9
        finally:
            browser.close()


def test_whole_night_rollout_is_consistent_on_every_surface(tmp_path):
    """Lead, answers, both game plans, totals and the comparison all come from one executed policy."""
    path = _render(tmp_path, ui="broadcast")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            mp = page.evaluate(f"window.__ucPlanFor({OURS!r},{THEIRS!r},'EIGHT',null,null,0,0,23,'v2')")
            them, lead = mp["plan_if_they_lead"], mp["plan_if_we_lead"]
            assert them and lead
            # First game of each plan is exactly what the cards recommend.
            assert lead[0]["our"] == mp["lead"]["our"] and lead[0]["leader"] == "us"
            first = next(r for r in mp["responses"] if r["their"] == them[0]["their"])
            assert them[0]["our"] == first["our"] and them[0]["leader"] == "them"
            # Totals are the plans' own expected wins (worst-case path), in thousandths.
            assert mp["total_if_they_lead"] == round(1000 * sum(g["p"] for g in them))
            assert mp["total_if_we_lead"] == round(1000 * sum(g["p"] for g in lead))
            # The comparison scores the same policy the same way, and never above the best possible worst case.
            c = page.evaluate(f"window.__ucEngineCompare({OURS!r},{THEIRS!r},'EIGHT',23)")
            assert abs(c["v2Them"]["w"] - sum(g["p"] for g in them)) < 1e-9
            assert c["v2Them"]["w"] <= c["benchThem"] + 1e-9 and c["v2Lead"]["w"] <= c["benchLead"] + 1e-9
            assert c["m3Them"]["w"] <= c["benchThem"] + 1e-9            # M3's choices scored on the same terms
            assert c["v2Them"]["a"] >= c["v2Them"]["w"] - 1e-9
            # Every answer in the comparison carries the plan's own role (no separate under-40% rule).
            roles = {r["their"]: r["role"] for r in mp["responses"]}
            for row in c["rows"]:
                if row["v2"]:
                    assert row["v2"]["role"] == roles[row["their"]]
                    assert row["v2"]["concession"] == ("deliberate concession" in roles[row["their"]])
        finally:
            browser.close()


def test_best_available_long_shot_is_not_called_a_deliberate_concession(tmp_path):
    """GPT finding 5: a sub-40% answer that IS the strongest matchup now is the best available, not a concession."""
    path = _render(tmp_path)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            mp = _two_by_two(page, 0.35, 0.30, 0.45, 0.40)
            r = next(x for x in mp["responses"] if x["their"] == "Xan")
            assert r["our"] == "Ace" and r["p"] < 0.40
            assert r["role"] == "Best available (every option is a long shot)"
            assert "deliberate concession" not in r["role"]
        finally:
            browser.close()


@pytest.mark.parametrize("ui", ["classic", "broadcast"])
def test_rebuilt_v2_file_opens_on_v2_even_after_m3_was_chosen_before(tmp_path, ui, monkeypatch):
    """Owner review failure: an earlier 'M3' choice stored in the browser made a rebuilt V2 file open on M3."""
    monkeypatch.setenv("UC_BUILD_LABEL", "test-build-1")
    old = _render(tmp_path, ui=ui)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 900})
            page = context.new_page(); errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(old.as_uri())
            page.locator("#uc-engine-badge [data-engine='m3']").click()
            assert page.evaluate("window.__ucEngine()") == "m3"
            # Simulate the earlier candidate's stored preference too.
            page.evaluate("localStorage.setItem('ultimate-coach:engine','m3')")
            # Rebuild (new label) at the same path and reopen in the same browser profile.
            monkeypatch.setenv("UC_BUILD_LABEL", "test-build-2")
            _render(tmp_path, ui=ui)
            page.goto(old.as_uri())
            assert page.evaluate("window.__ucEngine()") == "v2"
            assert page.evaluate("localStorage.getItem('ultimate-coach:engine')") is None
            badge = page.locator("#uc-engine-badge")
            assert badge.is_visible() and "engine-v2" in badge.get_attribute("class")
            text = badge.inner_text()
            assert "ENGINE: V2 CANDIDATE" in text and "build test-build-2" in text and "2026-10-07 18:00 UTC" in text
            # The badge stays on screen while scrolling (sticky at the top).
            page.mouse.wheel(0, 3000); page.wait_for_timeout(100)
            assert badge.bounding_box()["y"] <= 1
            plan = page.evaluate(f"window.__ucPlanFor({OURS!r},{THEIRS!r},'EIGHT',null,null,0,0,23,window.__ucEngine())")
            assert all(r["level"] in V2_LEVEL_ORDER for r in plan["responses"]), "default plan is V2"
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            assert errors == []
        finally:
            browser.close()


def test_v2_send_card_has_no_legacy_save_or_spend_notes_and_never_lists_its_answer_as_avoid(tmp_path):
    path = _render(tmp_path, ui="broadcast")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            page.select_option("#bc-team-a", OURS); page.select_option("#bc-team-b", THEIRS)
            page.wait_for_selector(".matchup-row[data-their]")
            for their in page.evaluate("() => window.UC_BC_LAST.rows.map(r => r.theirId)"):
                page.evaluate("id => window.UC_ACT.pick(id)", their)
                n = page.evaluate("""() => { const n = window.UC_BC_LAST.night;
                    return {engine: n.engine, answer: n.answer && n.answer.our, avoid: n.avoid.map(c => c.name),
                            notes: n.ranked.map(c => (c.save || '') + (c.cost || '')).join(' '), p: n.ranked.map(c => c.v2p)}; }""")
                assert n["engine"] == "v2"
                assert n["answer"] not in n["avoid"]
                assert "consider saving" not in n["notes"] and "Sending now spends" not in n["notes"]
                ps = [x for x in n["p"] if x is not None]
                assert ps == sorted(ps, reverse=True), "alternatives ordered by V2's estimate"
        finally:
            browser.close()


def test_later_long_shot_is_classified_at_its_own_step_of_the_night(tmp_path):
    """GPT-004: a planned long shot in a later game gets the role the rule gives at THAT state, not at the start."""
    path = _render(tmp_path)
    ours = [{"id": "a", "name": "Ace", "sl": 5}, {"id": "b", "name": "Bo", "sl": 5}, {"id": "c", "name": "Cy", "sl": 5}]
    theirs = [{"id": "x", "name": "Xan", "sl": 5}, {"id": "y", "name": "Yul", "sl": 5}, {"id": "z", "name": "Zed", "sl": 5}]
    mk = lambda p: {"level": band(p), "points": int(round(1000 * (p - 0.5))), "p": p, "why": "", "text": f"{band(p)} — {round(100 * p)}%", "v2": True}
    ps = {"a": 0.70, "b": 0.60, "c": 0.30}
    value = {f"{o}|{t}": mk(ps[o]) for o in "abc" for t in "xyz"}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            mp = page.evaluate("([o,t,v]) => window.__ucV2Apply(window.__ucMatchPlan(o,t,v,3,null,0,null,0),o,t,v,3,null,0,0)", [ours, theirs, value])
            line = mp["plan_if_they_lead"]
            assert [g["leader"] for g in line] == ["them", "us", "them"] and line[2]["our"] == "Cy"
            sac = [x for x in mp["sacrifices"] if x["our"] == "Cy"]
            assert sac, "the forced 30% game must be reported"
            # At game 3 only Cy is left: best available. At the start state the same put-up would get Ace's
            # "Recommended competitive matchup" label, which was the bug.
            assert sac[0]["why"].startswith("Best available (every option is a long shot)"), sac[0]["why"]
        finally:
            browser.close()


def test_absent_v2_answer_never_becomes_a_recorded_ranking_send(tmp_path):
    """GPT-008: with no engine answer, a V2 page shows no Send pick (M3 mode keeps its baseline behaviour)."""
    path = _render(tmp_path, ui="broadcast")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            page.select_option("#bc-team-a", OURS); page.select_option("#bc-team-b", THEIRS)
            page.wait_for_selector(".matchup-row[data-their]")
            page.evaluate("id => window.UC_ACT.pick(id)", page.evaluate("() => window.UC_BC_LAST.rows[0].theirId"))
            out = page.evaluate("""() => { const m = JSON.parse(JSON.stringify(window.UC_BC_LAST));
                m.night.answer = null; window.UC_BC.render(m);
                const hero = document.querySelector('#bc-night .send-hero');
                return {engine: m.night.engine, ranked: m.night.ranked.length, send: document.querySelectorAll('#bc-night .send-hero [data-send]').length,
                        text: hero ? hero.innerText : ''}; }""")
            assert out["engine"] == "v2" and out["ranked"] > 0
            assert out["send"] == 0, "no Send button without an engine answer"
            assert "No engine answer" in out["text"]
        finally:
            browser.close()


def test_v2_risk_line_is_v2s_own_list_not_the_recorded_record_list(tmp_path):
    path = _render(tmp_path, ui="broadcast")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            page.select_option("#bc-team-a", OURS); page.select_option("#bc-team-b", THEIRS)
            page.wait_for_selector(".matchup-row[data-their]")
            page.evaluate("id => window.UC_ACT.pick(id)", page.evaluate("() => window.UC_BC_LAST.rows[0].theirId"))
            n = page.evaluate("""() => { const n = window.UC_BC_LAST.night;
                return {flag: n.openRisksV2, risks: n.openRisks, plan: n.planCheck.responses.filter(r => r.p < 0.40).map(r => r.their)}; }""")
            assert n["flag"] is True
            assert sorted(n["risks"]) == sorted(n["plan"])
        finally:
            browser.close()
