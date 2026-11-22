"""HTML/Excel V2 parity in native Microsoft Excel: the workbook's live V2 engine and the HTML's V2 engine give the same
strategic advice for the same live state, compared by stable player IDs.

Synthetic data only. One payload builds both the HTML and the workbook. Two 8-Ball and two 9-Ball teams; a same-name
pair inside one roster (distinct skill levels), a same-name pair across teams, unknown skill levels, same-date
records. Each seeded state sets the workbook's own input cells (Lineup Lab availability and Played marks on both
sides, skill cap including off, Five-Game Plan first put-up, Command Center put-up) and gives the page the same
state (__ucPlanFor). Compared: rosters left, lead (player, their reply, equally good leads, wording), the answer to
every put-up (player, role, win chance, matchup text, strategic explanation), both five-game plans, night totals,
planned long shots, and the live answer for the selected put-up. Any difference fails.

Negative controls: a wrong win chance in the workbook's V2 data and a changed strategic threshold in the VBA engine
must each be detected. Needs Windows, Microsoft Excel and "Trust access to the VBA project object model".
"""
from __future__ import annotations

import json
import random
import shutil

import pytest

win32 = pytest.importorskip("win32com.client")
from playwright.sync_api import sync_playwright  # noqa: E402

from analytics.uc_v2_inputs import load_compact_from_html  # noqa: E402
from analytics.ultimate_coach_match_day import build_match_day_section  # noqa: E402
from tests.test_excel_war_room_formulas import _hist, _player  # noqa: E402
from ui.excel_v2_coach import install  # noqa: E402
from ui.export_excel_ultimate_coach import write_workbook  # noqa: E402
from ui.ultimate_coach import render  # noqa: E402

TEAMS = {  # team id -> (division, format, [(pid, ext, name, SL)])
    "lions-a": ("d5", "EIGHT", [(101, "3101", "Ann Archer", 7), (102, "3102", "Ann Archer", 4), (103, "3103", "Sam Stone", 6),
                                (104, "3104", "Bo Burke", 5), (105, "3105", "Cy Cole", 5), (106, "3106", "Di Dunn", 3),
                                (107, "3107", "Ed Ewing", None)]),
    "tigers-a": ("d5", "EIGHT", [(201, "3201", "Sam Stone", 6), (202, "3202", "Flo Ford", 5), (203, "3203", "Gil Gray", 5),
                                 (204, "3204", "Hal Hunt", 4), (205, "3205", "Ike Ives", 2), (206, "3206", "Jo Jett", None)]),
    "bears-n": ("d7", "NINE", [(301, "3301", "Kai Kent", 7), (302, "3302", "Lu Lane", 5), (303, "3303", "Mo Mays", 4),
                               (304, "3304", "Ned Nash", 3), (305, "3305", "Oz Orr", 2), (306, "3306", "Pia Pratt", 1)]),
    "wolves-n": ("d7", "NINE", [(401, "3401", "Quin Quay", 6), (402, "3402", "Rae Ross", 5), (403, "3403", "Sol Sato", 3),
                                (404, "3404", "Tess Toms", 2), (405, "3405", "Uma Upton", None)]),
}
OTHERS = {"EIGHT": [(901, "3901", "Vic Vance", 4), (902, "3902", "Wes Webb", 5)],
          "NINE": [(911, "3911", "Xan Xu", 4), (912, "3912", "Yul Yates", 3)]}
PAIRS = [("lions-a", "tigers-a", "EIGHT"), ("tigers-a", "lions-a", "EIGHT"), ("bears-n", "wolves-n", "NINE"),
         ("wolves-n", "bears-n", "NINE")]
STATES_PER_PAIR = 12


def _label(team):
    div, fmt, _ = TEAMS[team]
    return f"{team.split('-')[0].capitalize()} · Fall 2026 · {'8-Ball' if fmt == 'EIGHT' else '9-Ball'}"


def _key(team):
    return f"{team}|{TEAMS[team][0]}|Fall 2026"


def _payload():
    rng = random.Random(7)
    players, evidence = [], []
    for team, (div, fmt, roster) in TEAMS.items():
        for pid, ext, name, sl in roster:
            players.append(_player(pid, ext, name, [_hist(team, div, fmt, sl, 3, 6)]))
    for fmt, roster in OTHERS.items():
        for pid, ext, name, sl in roster:
            players.append(_player(pid, ext, name, [_hist("others-x", "d0" + fmt[0], fmt, sl, 1, 2)]))

    def game(a, b, fmt, result, day):
        date = f"2026-0{day // 28 + 8}-{day % 28 + 1:02d}T19:00:00-06:00"
        flip = "L" if result == "W" else "W"
        evidence.extend([
            {"player_id": a, "opponent_id": b, "format": fmt, "result": result, "match_date": date, "session_name": "Fall 2026",
             "own_skill_level": 5, "opponent_skill_level": 4, "points_earned": 2},
            {"player_id": b, "opponent_id": a, "format": fmt, "result": flip, "match_date": date, "session_name": "Fall 2026",
             "own_skill_level": 4, "opponent_skill_level": 5, "points_earned": 1}])

    for a, b, fmt in PAIRS[::2]:
        ours, theirs, others = TEAMS[a][2], TEAMS[b][2], OTHERS[fmt]
        for o in ours:
            for t in theirs:
                for _ in range(rng.choice([0, 0, 1, 2, 3])):
                    game(o[0], t[0], fmt, rng.choice("WWL" if (o[3] or 4) >= (t[3] or 4) else "WLL"), rng.randrange(40))
        for p in ours + theirs:
            for x in others:
                for _ in range(rng.choice([0, 1, 2, 6])):
                    game(p[0], x[0], fmt, rng.choice("WL"), rng.choice([3, 3, 10, 20, 30]))   # same dates too
    fixture = {"match_id": 1, "match_external_id": "1", "match_date": "2026-10-11T11:00:00-06:00", "format": "EIGHT",
               "format_raw": "8-Ball Open", "session_name": "Fall 2026", "week": 1, "status": "UNPLAYED", "location": None,
               "home_team_id": "lions-a", "home_team_name": "Lions", "away_team_id": "tigers-a", "away_team_name": "Tigers",
               "home_score": None, "away_score": None, "is_bye": False, "is_scored": False, "is_finalized": False}
    payload = {"schema": "test", "probability_publication": "FORBIDDEN", "matchup_probability": None,
               "predictive_confidence": None, "requires_live_apa_login": False, "database_mutated": False,
               "name_matching_used": False, "trust": {}, "counts": {"players": len(players), "head_to_head_rows": len(evidence)},
               "players": players, "evidence": evidence}
    payload["match_day"] = build_match_day_section([fixture], players)
    return payload


PAGE = """([a, b, fmt, rem, unplayedIds, playedN, playedSl, cap]) => {
  const full = window.__ucPlanFor(a, b, fmt, null, null, 0, 0, null, 'v2').v2.night;
  const unplayed = full.theirs.map(t => unplayedIds.indexOf(String(t.id)) >= 0);
  const mp = window.__ucPlanFor(a, b, fmt, rem, unplayed, playedN, playedSl, cap, 'v2');
  const n = mp.v2 && mp.v2.night;
  if (!n) return {none: true};
  const oid = {}, tid = {};
  n.ours.forEach(p => oid[p.name] = String(p.id)); n.theirs.forEach(p => tid[p.name] = String(p.id));
  const plan = l => (l || []).map(g => ({leader: g.leader, our: String(g.our_id), their: String(g.their_id), p: g.p}));
  return {ours: n.ours.map(p => String(p.id)), theirs: n.theirs.map(p => String(p.id)), games: n.gamesLeft,
    lead: mp.lead && mp.lead.our_id !== undefined && mp.responses ? {our: String(mp.lead.our_id), reply: tid[mp.lead.their_reply],
      equal: (mp.lead.equally_good || []).map(x => oid[x]), why: mp.lead.why, whyLead: mp.lead.why_lead} : null,
    responses: (mp.responses || []).map(r => ({their: tid[r.their], pick: oid[r.our], role: r.role, p: r.p, why: r.why, cost: r.cost_later})),
    planUs: plan(mp.plan_if_we_lead), planThem: plan(mp.plan_if_they_lead),
    totalUs: mp.total_if_we_lead, totalThem: mp.total_if_they_lead,
    sacrifices: (mp.sacrifices || []).map(s => ({our: oid[s.our], their: tid[s.their], why: s.why}))}; }"""


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("v2xl")
    payload = _payload()
    html = tmp / "uc.html"
    html.write_text(render(payload, built_at="2026-10-07 18:00 UTC", viewer_member_external_id="3101", ui="broadcast",
                           engine="v2"), encoding="utf-8")
    xlsx = write_workbook(payload, tmp / "uc.xlsx", built_at="2026-10-07 18:00 UTC", viewer_member_external_id="3101")
    xlsm = tmp / "uc.xlsm"
    info = install(xlsx, load_compact_from_html(html), xlsm, meta={"data_snapshot": "synthetic parity payload"})
    return html, xlsm, info


class Book:
    def __init__(self, path):
        self.xl = win32.DispatchEx("Excel.Application")
        self.xl.Visible = False
        self.xl.DisplayAlerts = False
        self.wb = self.xl.Workbooks.Open(str(path))
        self.R = self.name("wr_OurPids").Rows.Count

    def name(self, n):
        return self.wb.Names(n).RefersToRange

    def col(self, n):
        return [("" if v[0] is None else str(int(v[0]) if isinstance(v[0], float) and v[0].is_integer() else v[0]))
                for v in self.name(n).Value]

    def set(self, sheet, cell, value):
        self.wb.Worksheets(sheet).Range(cell).Value = value

    def teams(self, ours, theirs):
        for sheet in ("War Room", "Lineup Lab"):
            self.set(sheet, "C5", _label(ours))
            self.set(sheet, "C6", _label(theirs))
        self.set("Lineup Lab", "C9", "")

    def state(self, unavailable, played_ours, played_theirs, cap, first, put_up_label):
        ll_our, ll_opp = 12, 15 + self.R
        our_pids, opp_pids = self.col("wr_OurPids"), self.col("wr_OppPids")
        for k, pid in enumerate(our_pids):
            self.set("Lineup Lab", f"C{ll_our + k}", "Unavailable" if pid in unavailable else "")
            self.set("Lineup Lab", f"D{ll_our + k}", "Played" if pid in played_ours else "")
        for k, pid in enumerate(opp_pids):
            self.set("Lineup Lab", f"C{ll_opp + k}", "Played" if pid in played_theirs else "")
        self.set("Lineup Lab", "C7", "" if cap is None else cap)
        self.set("Five-Game Plan", "B5", first)
        self.set("Command Center", "C6", put_up_label)
        self.xl.Calculate()
        return json.loads(self.name("v2_Stamp").Worksheet.Range("B3").Value)

    def close(self):
        self.wb.Close(SaveChanges=False)
        self.xl.Quit()


def _compare(x, h):
    """Excel trace x vs HTML state h; returns a list of differences (empty = same advice)."""
    d = []
    if x.get("status") != "ok":
        return [f"excel status {x.get('status')}"]
    for k in ("ours", "theirs"):
        if x[k] != h[k]:
            d.append(f"{k}: {x[k]} vs {h[k]}")
    if (x["lead"] is None) != (h["lead"] is None):
        return d + ["lead presence"]
    if x["lead"]:
        for k in ("our", "reply", "equal", "why", "whyLead"):
            if x["lead"][k] != h["lead"][k]:
                d.append(f"lead {k}: {x['lead'][k]!r} vs {h['lead'][k]!r}")
    xr = {r["their"]: r for r in x["responses"]}
    if sorted(xr) != sorted(r["their"] for r in h["responses"]):
        d.append("put-ups answered")
    for r in h["responses"]:
        e = xr.get(r["their"])
        if not e:
            continue
        for k in ("pick", "role", "why", "cost"):
            if e[k] != r[k]:
                d.append(f"answer to {r['their']} {k}: {e[k]!r} vs {r[k]!r}")
        if abs(e["p"] - r["p"]) > 1e-12:
            d.append(f"answer to {r['their']} p")
    for k in ("planUs", "planThem"):
        a, b = x[k], h[k]
        if [(g["leader"], g["our"], g["their"]) for g in a] != [(g["leader"], g["our"], g["their"]) for g in b] or \
                any(abs(g["p"] - q["p"]) > 1e-12 for g, q in zip(a, b)):
            d.append(f"{k}: {a} vs {b}")
    if x["lead"]:
        if round(1000 * x["totals"]["us"]["w"]) != h["totalUs"] or round(1000 * x["totals"]["them"]["w"]) != h["totalThem"]:
            d.append("night totals")
    if [(s["our"], s["their"], s["why"]) for s in x["sacrifices"]] != [(s["our"], s["their"], s["why"]) for s in h["sacrifices"]]:
        d.append(f"planned long shots {x['sacrifices']} vs {h['sacrifices']}")
    if x["selected"] is not None:
        e = xr[x["selected"]]
        if not x["answer"].startswith("They put up ") or f": send " not in x["answer"] or e["cost"] not in x["answer"]:
            d.append("live answer text")
    return d


def _states(rng, ours, theirs, fmt):
    out = []
    for n in range(STATES_PER_PAIR):
        our_ids = [str(p[0]) for p in TEAMS[ours][2]]
        their_ids = [str(p[0]) for p in TEAMS[theirs][2]]
        played_n = rng.choice([0, 0, 1, 2, 3])
        played_ours = rng.sample(our_ids, played_n)
        played_theirs = rng.sample(their_ids, min(len(their_ids) - 1, played_n + rng.choice([0, 0, 1, -1]) if played_n else 0))
        rest = [p for p in our_ids if p not in played_ours]
        unavailable = rng.sample(rest, rng.choice([0, 0, 1, 2]))
        cap = rng.choice([23, 23, 22, 19, 25, None]) if n else 23
        first = rng.choice(["We put up first", "They put up first"])
        out.append((unavailable, played_ours, played_theirs, cap, first))
    return out


def _run(book, page, pairs, states_per_pair=None, rng_seed=20261122):
    rng = random.Random(rng_seed)
    diffs, compared, kinds = [], 0, set()
    for ours, theirs, fmt in pairs:
        book.teams(ours, theirs)
        sl = {str(p[0]): p[3] for p in TEAMS[ours][2]}
        for unavailable, played_ours, played_theirs, cap, first in _states(rng, ours, theirs, fmt)[:states_per_pair]:
            unplayed = [str(p[0]) for p in TEAMS[theirs][2] if str(p[0]) not in played_theirs]
            labels = book.col("wr_OppLabels")
            pick = rng.choice(unplayed)
            put_up = labels[book.col("wr_OppPids").index(pick)]
            x = book.state(set(unavailable), set(played_ours), set(played_theirs), cap, first, put_up)
            rem = [p for p in sl if p not in unavailable and p not in played_ours]
            played_sl = sum(sl[p] for p in played_ours if sl[p])
            h = page.evaluate(PAGE, [_key(ours), _key(theirs), fmt, rem, unplayed, len(played_ours), played_sl, cap])
            if h.get("none"):
                continue
            compared += 1
            kinds |= {r["role"] for r in h["responses"]} | {"tie" for r in h["responses"] if "Practically" in r["cost"]}
            d = _compare(x, h)
            if d:
                diffs.append((ours, theirs, unavailable, played_ours, played_theirs, cap, d[:4]))
    return diffs, compared, kinds


def test_excel_v2_gives_the_same_advice_as_the_html(built):
    html, xlsm, _ = built
    book = Book(xlsm)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(); page.goto(html.as_uri())
                diffs, compared, kinds = _run(book, page, PAIRS)
            finally:
                browser.close()
    finally:
        book.close()
    assert diffs == [], diffs[:3]
    assert compared >= 0.8 * STATES_PER_PAIR * len(PAIRS), f"only {compared} states compared"
    assert "Recommended competitive matchup" in kinds and len(kinds) >= 3, f"too few answer kinds covered: {kinds}"


@pytest.mark.parametrize("fault", ["win_chance", "strategic_threshold"])
def test_negative_controls_detect_a_wrong_workbook(built, tmp_path, fault):
    html, xlsm, _ = built
    copy = tmp_path / "fault.xlsm"
    shutil.copy(xlsm, copy)
    book = Book(copy)
    try:
        if fault == "win_chance":
            pairs = book.name("v2_Pairs")
            for r in range(1, pairs.Rows.Count + 1):
                pairs.Cells(r, 2).Value = 1 - pairs.Cells(r, 2).Value if r % 3 == 0 else pairs.Cells(r, 2).Value
            book.name("v2_Stamp").Value = "tampered"
        else:
            code = book.wb.VBProject.VBComponents("UcV2Engine").CodeModule
            for i in range(1, code.CountOfLines + 1):
                if code.Lines(i, 1).startswith("Private Const STRATEGIC_GAIN"):
                    code.ReplaceLine(i, "Private Const STRATEGIC_GAIN As Double = 0.01")
        book.name("v2_Stamp").Worksheet.Range("B2").Value = "tampered-" + fault
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(); page.goto(html.as_uri())
                diffs, compared, _ = _run(book, page, PAIRS, states_per_pair=6)
            finally:
                browser.close()
    finally:
        book.close()
    assert compared and diffs, f"the {fault} fault must be detected"
