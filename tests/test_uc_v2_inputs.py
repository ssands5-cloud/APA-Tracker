"""V2 input adapter parity: Python inputs on the embedded payload == the page's own V2 inputs and recommendations.

Synthetic data only. Both evidence build modes (plain, and production 'consume' which reverses same-date rows).
Negative controls show the comparison detects a wrong roster order, a wrong recent-form window and wrong direct counts.
"""
import pytest
from playwright.sync_api import sync_playwright

import analytics.uc_v2_inputs as ui_inputs
from analytics.uc_v2_inputs import V2Inputs, load_compact_from_html
from analytics.uc_v2_policy import V2Policy
from tests.test_excel_war_room_formulas import _payload
from tests.test_ultimate_coach_war_room_browser import OURS, THEIRS
from ui.ultimate_coach import render

PAGE = """([a, b, cap]) => { const mp = window.__ucPlanFor(a, b, 'EIGHT', null, null, 0, 0, cap, 'v2');
  const n = mp.v2.night, val = {};
  for (const o of n.ours) for (const t of n.theirs) { const v = n.value[String(o.id) + '|' + String(t.id)]; val[String(o.id) + '|' + String(t.id)] = v ? v.p : null; }
  return {ours: n.ours.map(p => String(p.id)), theirs: n.theirs.map(p => String(p.id)), p: val,
          lead: mp.lead ? String(mp.lead.our_id) : null, responses: (mp.responses || []).map(r => ({their: r.their, our: r.our, role: r.role}))}; }"""


def _built(tmp_path, crowded, consume):
    path = tmp_path / f"uc-{crowded}-{consume}.html"
    path.write_text(render(_payload(crowded=crowded), built_at="2026-10-07 18:00 UTC", viewer_member_external_id="1001",
                           ui="broadcast", engine="v2", consume_evidence=consume), encoding="utf-8")
    return path


def _differences(inputs, page_state, cap):
    ours, theirs, p = inputs.matchup(OURS, THEIRS, "EIGHT")
    diffs = []
    if [o["id"] for o in ours] != page_state["ours"]:
        diffs.append("our roster order")
    if [t["id"] for t in theirs] != page_state["theirs"]:
        diffs.append("their roster order")
    for k, v in page_state["p"].items():
        o, t = k.split("|")
        if abs(p[(o, t)] - v) > 1e-12:
            diffs.append(f"p {k}")
    tr = V2Policy(ours, theirs, p, 5, cap).trace()
    name = {o["id"]: o["name"] for o in ours}
    tname = {t["id"]: t["name"] for t in theirs}
    for r in page_state["responses"]:
        tid = next(k for k, v in tname.items() if v == r["their"])
        py = tr["responses"][tid]
        role = next(row["role"] for row in py["rows"] if row["our_id"] == py["pick"])
        if not r["our"].startswith(name[py["pick"]]) or role != r["role"]:
            diffs.append(f"answer vs {r['their']}")
    if tr["lead"] and tr["lead"]["our_id"] != page_state["lead"]:
        diffs.append("lead")
    return diffs


@pytest.mark.parametrize("crowded", [False, True])
@pytest.mark.parametrize("consume", [False, True])
def test_adapter_inputs_and_recommendations_equal_the_page(tmp_path, crowded, consume):
    path = _built(tmp_path, crowded, consume)
    inputs = V2Inputs(load_compact_from_html(path))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            for cap in (23, 22, None):
                state = page.evaluate(PAGE, [OURS, THEIRS, cap])
                assert state["responses"], "the page must answer something (no empty comparison)"
                assert _differences(inputs, state, cap) == []
        finally:
            browser.close()


@pytest.mark.parametrize("fault", ["roster_order", "recent_window", "direct_counts"])
def test_negative_controls_detect_a_wrong_adapter(tmp_path, monkeypatch, fault):
    path = _built(tmp_path, True, True)
    if fault == "roster_order":
        monkeypatch.setattr(ui_inputs, "_member_key", lambda m: (str(m.get("name")).lower(),))
    elif fault == "recent_window":
        orig = V2Inputs._record
        def last5(self, pid, fmt):
            (w, n), _ = orig(self, pid, fmt)
            rows = [r for r in self.rows_for(pid, fmt) if self._val(r, "result") in ("W", "L")]
            rows.sort(key=lambda r: str(self._val(r, "match_date")))
            last = rows[-5:]
            return (w, n), (sum(1 for r in last if self._val(r, "result") == "W"), len(last))
        monkeypatch.setattr(V2Inputs, "_record", last5)
    else:
        orig_opp = V2Inputs._opp_map
        def wins_only(self, pid, fmt):
            return {k: [w, w] for k, (w, g) in orig_opp(self, pid, fmt).items()}
        monkeypatch.setattr(V2Inputs, "_opp_map", wins_only)
    inputs = V2Inputs(load_compact_from_html(path))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(); page.goto(path.as_uri())
            state = page.evaluate(PAGE, [OURS, THEIRS, 23])
            assert _differences(inputs, state, 23), f"the {fault} fault must be detected"
        finally:
            browser.close()
