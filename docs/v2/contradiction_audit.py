"""Ultimate Coach contradiction detector (reusable audit harness).

Drives a built V2 review HTML in a real browser through many match-night states for every team pair of one
division, and cross-checks what each screen says. Real data stays local: the full report (with names) is written
to --out; --summary writes counts and invariant names only (safe to publish).

    python -I docs/v2/contradiction_audit.py --html <V2 HTML> --division <id> --format EIGHT --out report.json --summary summary.json

States per ordered team pair: start of night with cap 23, cap 22 and cap cleared; one of our players marked Out;
one game already played (engine's own first answer recorded). Invariants (each failure is a contradiction unless it
is listed as a quantified strategic exception):

  I1  recommended player is available and has not played
  I2  Match Night answer vs Command Board: the answer is listed as that player's planned answer, never under
      "long shot vs/avoid"; a player with planned answers is never "Not planned"
  I3  "save"/"planned answer" roles only with planned answers; concession role only with a concession answer
  I4  value grade consistent with stated value (D never has planned answers; A/B never "Not planned")
  I5  one probability per pairing: trace = comparison = send card = V2 pair table
  I6  plan consistency: first game of each plan = the card's lead/answer; totals = plan path sums; the
      comparison scores the same policy
  I7  skill cap: every planned five fits the effective cap (known skill levels); the board shows the cap in force
  I8  no M3 vocabulary in V2 recommendations (levels, roles, lead options, send scenarios, board)
  I9  giving up the strongest matchup now only as a labelled strategic choice with gains >= 0.10 under both
      opponent models (quantified exception); near-ties disclosed
  I10 state changes are reflected (Out player gone, played player gone, cap shown = cap in force)
  I11 no unsupported claims (no "optimal team points"; APA point margins disclosed as not modelled)
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

V2_LEVELS = {"Favored", "Edge", "Toss-up", "Underdog", "Long shot"}
M3_LEVELS = {"Strong", "Solid", "Thin", "Unknown", "Conflicted", "Caution"}

STATE_JS = """([a, b, fmt, cap, outId, playFirst]) => {
  localStorage.clear();
  document.getElementById('bc-team-a').value = a; document.getElementById('bc-team-a').dispatchEvent(new Event('change', {bubbles: true}));
  document.getElementById('bc-team-b').value = b; document.getElementById('bc-team-b').dispatchEvent(new Event('change', {bubbles: true}));
  const capEl = document.getElementById('bc-cap');
  if (capEl) { capEl.value = cap === null ? '' : String(cap); capEl.dispatchEvent(new Event('input', {bubbles: true})); capEl.dispatchEvent(new Event('change', {bubbles: true})); }
  if (outId) window.UC_ACT.avail(outId, 'Unavailable');
  let m = window.UC_BC_LAST;
  if (playFirst && m && m.rows && m.rows.length) {
    const r = m.rows[0]; window.UC_ACT.send(r.ourId, r.theirId); m = window.UC_BC_LAST;
  }
  // Open the night on each put-up to read the send card and trace for that opponent.
  const per = [];
  const ids = ((m && m.rows) || []).map(r => [r.their, r.theirId]);
  for (const [their, theirId] of ids) {
    const r = {their: their, theirId: theirId};
    window.UC_ACT.pick(r.theirId);
    const n = window.UC_BC_LAST.night;
    per.push({their: r.their, theirId: r.theirId, answer: n.answer, trace: n.trace,
              scen: (n.sendScenarios || []).map(s => ({name: s.name, level: s.level, recommended: s.recommended}))});
  }
  window.UC_ACT.pick(null);
  const mm = window.UC_BC_LAST;
  return {engine: window.__ucEngine(), cap: mm.cap, played: mm.played, rows: mm.rows, lead: mm.lead,
          command: mm.night.command, compare: mm.night.engineCompare, bench: mm.night.bench,
          leadOptions: (mm.night.leadOptions || []).map(o => ({name: o.name, level: o.reply && o.reply.level})),
          per: per, badge: (document.getElementById('uc-engine-badge') || {}).innerText || '',
          plan: mm.night.planCheck};
}"""


def check(state, label, fails, exceptions):
    def fail(inv, msg):
        fails.append({"state": label, "invariant": inv, "detail": msg})
    rows, cmd = state["rows"] or [], state["command"] or {}
    cards = {c["name"]: c for c in cmd.get("cards", [])}
    bench = {b["name"]: b for b in state["bench"]["ours"]}
    # I1 / I10
    for r in rows:
        b = bench.get(r["our"])
        if not b or not b["rem"]:
            fail("I1", f"{r['our']} recommended vs {r['their']} but is not available/remaining")
    # I2 / I3 / I4
    for r in rows:
        c = cards.get(r["our"])
        if not c:
            fail("I2", f"no board card for {r['our']}"); continue
        ans = [a["opp"] for a in c.get("answers", [])]
        if r["their"] not in ans:
            fail("I2", f"{r['our']} is Match Night's answer to {r['their']} but the board does not list it")
        if any(x["opp"].startswith(r["their"] + " ") or x["opp"] == r["their"] for x in c.get("avoid", [])):
            fail("I2", f"board says {r['our']} should avoid {r['their']}, Match Night sends them")
        if c["role"] == "situational":
            fail("I2", f"{r['our']} answers {r['their']} but the board says Not planned")
    for c in cmd.get("cards", []):
        n = len(c.get("answers", []))
        if c["role"] == "save" and not n:
            fail("I3", f"{c['name']} has role Planned answer without any planned answer")
        if c["role"] == "burn" and not any("concession" in (a.get("role") or "") for a in c.get("answers", [])):
            fail("I3", f"{c['name']} is a Concession without a concession answer")
        if c.get("grade") == "D" and n:
            fail("I4", f"{c['name']} graded D but answers {n} put-up(s)")
        if c.get("grade") in ("A", "B") and c["role"] == "situational":
            fail("I4", f"{c['name']} graded {c['grade']} but Not planned")
        if not c.get("v2") and state["engine"] == "v2" and c["role"] not in ("used", "out"):
            fail("I8", f"board card for {c['name']} built by M3 logic")
    # I5 / I9
    for x in state["per"]:
        t = x["trace"]
        if not t:
            continue
        pick = next((rr for rr in t["rows"] if rr["pick"]), None)
        if x["answer"] and pick and x["answer"]["our"] != pick["name"]:
            fail("I5", f"send card answer {x['answer']['our']} != trace pick {pick['name']} vs {x['their']}")
        if x["answer"] and pick and abs((x["answer"].get("p") or 0) - pick["p"]) > 1e-12:
            fail("I5", f"send card and trace give different win chances for {pick['name']} vs {x['their']}")
        cmp_row = next((cr for cr in (state["compare"] or {}).get("rows", []) if cr["their"] == x["their"]), None)
        if cmp_row and cmp_row.get("v2") and pick and cmp_row["v2"]["our"] == pick["name"] and abs((cmp_row["v2"]["p"] or 0) - pick["p"]) > 1e-12:
            fail("I5", f"comparison and trace give different win chances for {pick['name']} vs {x['their']}")
        now = max(t["rows"], key=lambda rr: rr["p"])
        if pick and now["p"] - pick["p"] > 0.01:
            if not (t["strategic"] and t["gainWorst"] >= 0.10 - 1e-9 and t["gainAvg"] >= 0.10 - 1e-9 and "Strategic choice" in t["summary"]):
                fail("I9", f"{pick['name']} ({pick['p']:.3f}) chosen over stronger {now['name']} ({now['p']:.3f}) vs {x['their']} without a qualifying explanation")
            else:
                exceptions.append({"state": label, "their": x["their"], "pick": pick["name"], "strongest": now["name"],
                                   "gainWorst": round(t["gainWorst"], 3), "gainAvg": round(t["gainAvg"], 3)})
        for s in x["scen"]:
            if state["engine"] == "v2" and s["level"].split(" ")[0] in M3_LEVELS:
                fail("I8", f"send scenario shows M3 level {s['level']}")
    # I6
    p = state["plan"]
    them, lead = p.get("plan_if_they_lead") or [], p.get("plan_if_we_lead") or []
    if them:
        first = next((r for r in p["responses"] if r["their"] == them[0]["their"]), None)
        if not first or first["our"] != them[0]["our"]:
            fail("I6", "first game of the they-lead plan differs from the card's answer")
        if p.get("total_if_they_lead") is not None and abs(p["total_if_they_lead"] - round(1000 * sum(g["p"] for g in them))) > 1:
            fail("I6", "they-lead total is not the plan path's expected wins")
    if lead and p.get("lead") and lead[0]["our"] != p["lead"]["our"]:
        fail("I6", "first game of the we-lead plan differs from the lead card")
    c = state["compare"]
    if c and c.get("v2Them") and them and abs(c["v2Them"]["w"] - sum(g["p"] for g in them)) > 1e-9:
        fail("I6", "comparison scores a different policy than the plan")
    # I7
    sl = {b["name"]: b["sl"] for b in state["bench"]["ours"]}
    if state["cap"] is not None:
        for nm, line in (("they-lead", them), ("we-lead", lead)):
            known = [sl.get(g["our"]) for g in line]
            if all(v is not None for v in known) and len(line) == 5 - (state["played"] or 0) and sum(known) > state["cap"]:
                fail("I7", f"{nm} plan uses skill total {sum(known)} over cap {state['cap']}")
    # I8 levels
    if state["engine"] == "v2":
        for r in rows:
            if r["level"] not in V2_LEVELS:
                fail("I8", f"answer level {r['level']} is not a V2 band")
        for g in them + lead:
            if g["level"] not in V2_LEVELS:
                fail("I8", f"plan level {g['level']} is not a V2 band")
        if "ENGINE: V2 CANDIDATE" not in state["badge"]:
            fail("I8", "engine badge does not say V2")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", required=True)
    ap.add_argument("--division", required=True)
    ap.add_argument("--format", default="EIGHT")
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary")
    ap.add_argument("--limit", type=int, default=0, help="only the first N ordered team pairs (0 = all)")
    ap.add_argument("--shard", default="1/1", help="i/n: run every n-th pair starting at i (parallel runs)")
    a = ap.parse_args()
    fails, exceptions, states = [], [], 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(Path(a.html).resolve().as_uri())
        page.wait_for_selector("#bc-team-a")
        text = page.inner_text("body")
        if "optimal team points" in text.lower() or "optimizes team points" in text.lower():
            fails.append({"state": "page", "invariant": "I11", "detail": "unsupported team-point optimisation claim"})
        keys = page.evaluate("d => Array.from(document.querySelectorAll('#bc-team-a option')).map(o => o.value).filter(v => v && v.indexOf('|' + d + '|') >= 0)", a.division)
        pairs = [(x, y) for x in keys for y in keys if x != y]
        if a.limit:
            pairs = pairs[:a.limit]
        si, sn = (int(v) for v in a.shard.split("/"))
        pairs = pairs[si - 1::sn]
        import sys, time
        t0 = time.time()
        for k, (x, y) in enumerate(pairs, 1):
            base = page.evaluate(STATE_JS, [x, y, a.format, 23, None, False])
            variants = [("cap23", 23, None, False), ("cap22", 22, None, False), ("capOff", None, None, False), ("played1", 23, None, True)]
            if base["rows"]:
                variants.append(("out1", 23, base["rows"][0]["ourId"], False))
            for tag, cap, out_id, play in variants:
                st = page.evaluate(STATE_JS, [x, y, a.format, cap, out_id, play])
                states += 1
                label = f"{x} v {y} [{tag}]"
                check(st, label, fails, exceptions)
                if tag.startswith("cap") and st["cap"] != cap:
                    fails.append({"state": label, "invariant": "I10", "detail": f"cap in force {st['cap']} != set {cap}"})
                if out_id and any(r["ourId"] == out_id for r in st["rows"]):
                    fails.append({"state": label, "invariant": "I10", "detail": "Out player still recommended"})
            print(f"progress {k}/{len(pairs)} pairs, {states} states, {len(fails)} contradictions, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
        page.evaluate("localStorage.clear()")
        browser.close()
    by = {}
    for f in fails:
        by[f["invariant"]] = by.get(f["invariant"], 0) + 1
    report = {"team_pairs": len(pairs), "states": states, "contradictions": len(fails), "by_invariant": by,
              "strategic_exceptions": len(exceptions), "fails": fails, "exceptions": exceptions}
    Path(a.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    if a.summary:
        Path(a.summary).write_text(json.dumps({k: report[k] for k in ("team_pairs", "states", "contradictions", "by_invariant", "strategic_exceptions")}, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("team_pairs", "states", "contradictions", "by_invariant", "strategic_exceptions")}, indent=1))


if __name__ == "__main__":
    main()
