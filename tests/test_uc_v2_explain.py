"""V2 wording parity: Python explanation text == the page's own answer text (why + cost_later), character for character.

Synthetic data only. Negative controls show the comparison detects a dropped tie clause, a wrong later-line length
and Python's half-even rounding in place of JavaScript's half-up.
"""
import pytest
from playwright.sync_api import sync_playwright

import analytics.uc_v2_explain as ex
from analytics.uc_v2_inputs import V2Inputs, load_compact_from_html
from analytics.uc_v2_pair_model import evidence_gaps
from analytics.uc_v2_policy import V2Policy
import random

from tests.test_uc_v2_candidate import _render
from tests.test_uc_v2_inputs import _built
from tests.test_uc_v2_policy_fuzz_parity import _state
from tests.test_uc_v2_policy_parity import browser_values
from tests.test_ultimate_coach_war_room_browser import OURS, THEIRS

PAGE = """([a, b, cap]) => { const mp = window.__ucPlanFor(a, b, 'EIGHT', null, null, 0, 0, cap, 'v2');
  const n = mp.v2.night;
  return (mp.responses || []).map(r => ({their_id: String(n.theirs.find(t => t.name === r.their).id), our: r.our, why: r.why, cost: r.cost_later})); }"""


FUZZ = """([o,t,v,g,c,u,tu]) => (window.__ucV2Apply(window.__ucMatchPlan(o,t,v,g,c,u,c,tu),o,t,v,g,c,u,tu).responses || [])
  .map(r => ({their: r.their, cost: r.cost_later}))"""


def _fuzz_diffs(page, n_states=120):
    """Random states with forced near-ties (tie clauses, strategic choices, alternatives) in both formats."""
    rng, diffs, kinds = random.Random(20261123), [], set()
    for fmt in ("EIGHT", "NINE"):
        for _ in range(n_states):
            ours, theirs, p, games, cap, used, opp_used = _state(rng, fmt)
            try:
                tr = V2Policy(ours, theirs, p, games, cap, used, opp_used).trace()
            except ValueError:
                continue
            on = {o["id"]: o["name"] for o in ours}
            tn = {t["id"]: t["name"] for t in theirs}
            by_name = {tn[k]: v for k, v in tr["responses"].items()}
            for r in page.evaluate(FUZZ, [ours, theirs, browser_values(p), games, cap, used, opp_used]):
                text = ex.options_text(by_name[r["their"]], on, tn)
                kinds |= {k for k in ("Practically tied", "Practically equal plan", "Strategic choice:", "Strategic alternative:",
                                      "also the best plan") if k in r["cost"]}
                if text != r["cost"]:
                    diffs.append((r["cost"], text))
    return diffs, kinds


def test_fuzz_explanations_equal_the_page(tmp_path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(_render(tmp_path).as_uri())
            diffs, kinds = _fuzz_diffs(page)
        finally:
            browser.close()
    assert diffs == []
    assert len(kinds) == 5, f"wording branches not all covered: {kinds}"


def _python_texts(inputs, cap):
    ours, theirs, p = inputs.matchup(OURS, THEIRS, "EIGHT")
    raw_o = {str(m["id"]): m for m in inputs.roster(OURS)}
    raw_t = {str(t["id"]): t for t in inputs.roster(THEIRS)}
    on = {o["id"]: o["name"] for o in ours}
    tn = {t["id"]: t["name"] for t in theirs}
    tr = V2Policy(ours, theirs, p, 5, cap).trace()
    out = {}
    for tid, resp in tr["responses"].items():
        oid = resp["pick"]
        kw = inputs.pair_inputs(raw_o[oid], raw_t[tid], "EIGHT")
        gaps = evidence_gaps(kw["direct"], kw["shared"], kw["form_p"], kw["form_o"], raw_o[oid]["skill_level"],
                             raw_t[tid]["skill_level"])
        out[tid] = dict(our=on[oid], why=ex.pair_text(p[(oid, tid)], gaps), cost=ex.options_text(resp, on, tn))
    return out


def _diffs(inputs, page_rows, cap):
    py = _python_texts(inputs, cap)
    diffs = []
    for r in page_rows:
        q = py.get(r["their_id"])
        if q is None:
            diffs.append(f"missing answer {r['their_id']}")
            continue
        for k in ("our", "why", "cost"):
            if q[k] != r[k]:
                diffs.append(f"{k} vs {r['their_id']}: page={r[k]!r} python={q[k]!r}")
    return diffs


@pytest.mark.parametrize("crowded", [False, True])
@pytest.mark.parametrize("consume", [False, True])
def test_explanations_equal_the_page(tmp_path, crowded, consume):
    path = _built(tmp_path, crowded, consume)
    inputs = V2Inputs(load_compact_from_html(path))
    seen = set()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            for cap in (23, 22, 21, None):
                rows = page.evaluate(PAGE, [OURS, THEIRS, cap])
                assert rows, "the page must answer something"
                assert _diffs(inputs, rows, cap) == []
                seen |= {r["cost"].split(" (")[0].split(":")[0] for r in rows}
        finally:
            browser.close()
    assert seen, "no explanation text compared"


def test_rounding_matches_javascript():
    assert ex.pct(0.625) == "63%" and ex.pct(0.385) == "39%"     # Math.round half-up (Python round(62.5) == 62)
    assert ex.wins(0.0125) == "+0.013" and ex.wins(-0.0) == "+0.000" and ex.wins(-0.1) == "-0.100"


@pytest.mark.parametrize("fault", ["no_tie_clause", "floor_percent", "min_gain_text"])
def test_negative_controls_detect_wrong_wording(tmp_path, monkeypatch, fault):
    path = _built(tmp_path, True, True)
    inputs = V2Inputs(load_compact_from_html(path))
    if fault == "no_tie_clause":
        orig = ex.options_text
        monkeypatch.setattr(ex, "options_text", lambda resp, o, t: orig(
            dict(resp, rows=[dict(r, tiedNow=False, equalPlan=False) for r in resp["rows"]]), o, t))
    elif fault == "floor_percent":
        monkeypatch.setattr(ex, "js_round", lambda x: int(x))
    else:
        monkeypatch.setattr(ex, "MIN_GAIN_TEXT", "0.1")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            found = []
            for cap in (23, 22, 21, None):
                found += _diffs(inputs, page.evaluate(PAGE, [OURS, THEIRS, cap]), cap)
            page.goto(_render(tmp_path).as_uri())
            found += _fuzz_diffs(page, 40)[0]
        finally:
            browser.close()
    assert found, f"the {fault} fault must be detected"