"""Ultimate Coach contradiction detector, version 2 (GA-01 / GA-02).

Drives a built V2 review HTML in a real browser through many match-night states for every team pair of one
division and cross-checks what each screen says. Every invariant reports checked / skipped / failed counts, a
missing mandatory output is a failure (never a silent pass), and zero coverage fails the run. Real data stays
local: --out holds the detailed report (names); --summary holds counts, invariant names and the HTML hash only.

    python -I docs/v2/contradiction_audit.py --html <V2 HTML> --division <id> --format EIGHT --out report.json --summary summary.json [--shard i/n]

States per ordered team pair (format given by --format): cap 23 / 22 / cleared; toss us / them; 1-4 games already
played (the engine's own answers recorded); one of ours Out; one of theirs Out; no feasible five (all but three
of ours Out). Invariants:

  I0  the page shows the requested teams and format, in V2 (engine badge says V2)
  I1  recommended players are available on both sides and have not played; no duplicates in any planned line
  I2  Match Night answer vs Command Board (planned answer listed, never "long shot vs/avoid", never "Not planned")
  I3  roles need their evidence (planned answer / concession)
  I4  value grade consistent with stated value
  I5  one probability per pairing (trace = send card = comparison); the trace exists whenever there is an answer
  I6  plan consistency (first games = cards; totals = paths; comparison = same policy); comparison exists in V2
  I7  skill cap: prior spend + planned line <= cap when every skill level is known; unknown skill levels are
      reported as incomplete (skipped), never counted as zero
  I8  no M3 vocabulary in V2 recommendations; rendered send card names the model's answer; no legacy notes
  I9  giving up the strongest matchup only as a labelled strategic choice with >= 0.10 under both models
  I10 state changes reflected (Out players gone on both sides, played players gone, cap shown = cap in force)
  I11 no unsupported claims (no "optimal team points")
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

V2_LEVELS = {"Favored", "Edge", "Toss-up", "Underdog", "Long shot"}
M3_LEVELS = {"Strong", "Solid", "Thin", "Unknown", "Conflicted", "Caution"}
INVARIANTS = ["I0", "I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9", "I10", "I11"]

STATE_JS = """([a, b, fmt, cap, outIds, oppOutIds, played, toss]) => {
  const fire = (id, v, ev) => { const el = document.getElementById(id); if (!el) return; el.value = v; for (const e of ev) el.dispatchEvent(new Event(e, {bubbles: true})); };
  fire('team-format', fmt, ['change']);           // the team pickers list one format's teams
  fire('bc-team-a', a, ['change']); fire('bc-team-b', b, ['change']);
  let guard = 10;
  while (guard-- > 0 && window.UC_BC_LAST && window.UC_BC_LAST.night && (window.UC_BC_LAST.night.games || []).length) window.UC_ACT.undo();
  window.UC_ACT.toss('');
  const nb = () => (window.UC_BC_LAST && window.UC_BC_LAST.night && window.UC_BC_LAST.night.bench) || {ours: [], theirs: []};
  for (const p of nb().ours) if (p.avail === 'Unavailable') window.UC_ACT.avail(p.id, 'Available');
  for (const p of nb().theirs) if (p.out) window.UC_ACT.oppOut(p.id, false);
  fire('bc-cap', cap === null ? '' : String(cap), ['input', 'change']);
  if (toss) window.UC_ACT.toss(toss);
  for (const id of outIds) window.UC_ACT.avail(id, 'Unavailable');
  for (const id of oppOutIds) window.UC_ACT.oppOut(id, true);
  for (let k = 0; k < played; k++) {           // record the engine's own answers, one game at a time
    const m = window.UC_BC_LAST; if (!m || !m.rows || !m.rows.length) break;
    const r = m.rows[0]; window.UC_ACT.send(r.ourId, r.theirId);
  }
  const m = window.UC_BC_LAST;
  const per = [];
  for (const [their, theirId] of ((m && m.rows) || []).map(r => [r.their, r.theirId])) {
    window.UC_ACT.pick(theirId);
    const n = window.UC_BC_LAST.night, hero = document.querySelector('#bc-night .send-hero .send-name');
    per.push({their: their, theirId: theirId, answer: n.answer, trace: n.trace, avoid: (n.avoid || []).map(c => c.name),
              notes: (n.ranked || []).concat(n.unordered || []).map(c => (c.save || '') + (c.cost || '')).join(' '),
              rendered: hero ? hero.textContent.trim() : null, nextLeader: n.nextLeader || null,
              sendButtons: document.querySelectorAll('#bc-night .send-hero [data-send]').length,
              scen: (n.sendScenarios || []).map(s => ({name: s.name, level: s.level, recommended: s.recommended}))});
  }
  window.UC_ACT.pick('');
  const mm = window.UC_BC_LAST;
  return {engine: window.__ucEngine(), ourKey: mm.ourKey, theirKey: mm.theirKey, format: mm.format, cap: mm.cap, played: mm.played,
          rows: mm.rows, command: mm.night.command, compare: mm.night.engineCompare, bench: mm.night.bench, games: mm.night.games,
          per: per, badge: (document.getElementById('uc-engine-badge') || {}).innerText || '', plan: mm.night.planCheck};
}"""


class Counter:
    def __init__(self):
        self.c = {k: {"checked": 0, "skipped": 0, "failed": 0} for k in INVARIANTS}


def check(state, label, fails, exceptions, counts=None, expect=None):
    """Cross-check one rendered state. expect = (ourKey, theirKey, format label or None). Returns the counts."""
    counts = counts or Counter()

    def ok(inv):
        counts.c[inv]["checked"] += 1

    def skip(inv):
        counts.c[inv]["skipped"] += 1

    def fail(inv, msg):
        counts.c[inv]["checked"] += 1
        counts.c[inv]["failed"] += 1
        fails.append({"state": label, "invariant": inv, "detail": msg})

    rows, cmd, plan = state.get("rows") or [], state.get("command") or {}, state.get("plan")
    v2 = state.get("engine") == "v2"
    # I0 requested teams/format, V2
    if expect:
        if state.get("ourKey") != expect[0] or state.get("theirKey") != expect[1]:
            fail("I0", f"page shows {state.get('ourKey')} v {state.get('theirKey')}, requested {expect[0]} v {expect[1]}")
        elif expect[2] and expect[2] not in str(state.get("format")):
            fail("I0", f"page format {state.get('format')} != requested {expect[2]}")
        else:
            ok("I0")
    if not v2 or "ENGINE: V2 CANDIDATE" not in (state.get("badge") or ""):
        fail("I0", "not in V2 (engine or badge)")
    else:
        ok("I0")
    bench_ours = {str(b["id"]): b for b in (state.get("bench") or {}).get("ours", [])}
    bench_theirs = {str(b["id"]): b for b in (state.get("bench") or {}).get("theirs", [])}
    # I1 availability on both sides; no duplicates (stable ids)
    for r in rows:
        b, t = bench_ours.get(str(r.get("ourId"))), bench_theirs.get(str(r.get("theirId")))
        if not b or not b["rem"]:
            fail("I1", f"{r['our']} recommended vs {r['their']} but is not available/remaining")
        elif not t or not t["unplayed"] or t.get("out"):
            fail("I1", f"answer offered vs {r['their']} who has played or is out")
        else:
            ok("I1")
    if plan is None:
        fail("I6", "plan missing")
        plan = {}
    for nm in ("plan_if_they_lead", "plan_if_we_lead"):
        line = plan.get(nm) or []
        ids = [str(g.get("our_id") or g["our"]) for g in line]
        tids = [str(g.get("their_id") or g["their"]) for g in line]
        if len(set(ids)) != len(ids) or len(set(tids)) != len(tids):
            fail("I1", f"{nm} uses a player twice")
        elif any(i in bench_ours and not bench_ours[i]["rem"] for i in ids):
            fail("I1", f"{nm} uses a player of ours who is out or has played")
        elif any(t in bench_theirs and (not bench_theirs[t]["unplayed"] or bench_theirs[t].get("out")) for t in tids):
            fail("I1", f"{nm} plans against an opponent who has played or is out")
        elif line:
            ok("I1")
    # I2 / I3 / I4
    cards = {c["name"]: c for c in cmd.get("cards", [])}
    if rows and not cards:
        fail("I2", "answers exist but the Command Board is empty")
    for r in rows:
        c = cards.get(r["our"])
        if not c:
            fail("I2", f"no board card for {r['our']}")
            continue
        ans = [a["opp"] for a in c.get("answers", [])]
        if r["their"] not in ans:
            fail("I2", f"{r['our']} is Match Night's answer to {r['their']} but the board does not list it")
        elif any(x["opp"] == r["their"] or x["opp"].startswith(r["their"] + " ") for x in c.get("avoid", [])):
            fail("I2", f"board says {r['our']} should avoid {r['their']}, Match Night sends them")
        elif c["role"] == "situational":
            fail("I2", f"{r['our']} answers {r['their']} but the board says Not planned")
        else:
            ok("I2")
    for c in cmd.get("cards", []):
        n = len(c.get("answers", []))
        if c["role"] == "save" and not n:
            fail("I3", f"{c['name']} has role Planned answer without any planned answer")
        elif c["role"] == "burn" and not any("concession" in (a.get("role") or "") for a in c.get("answers", [])):
            fail("I3", f"{c['name']} is a Concession without a concession answer")
        else:
            ok("I3")
        if c.get("grade") == "D" and n:
            fail("I4", f"{c['name']} graded D but answers {n} put-up(s)")
        elif c.get("grade") in ("A", "B", "C") and c["role"] == "situational":
            fail("I4", f"{c['name']} graded {c['grade']} but Not planned")
        else:
            ok("I4")
        if v2 and not c.get("v2") and c["role"] not in ("used", "out"):
            fail("I8", f"board card for {c['name']} built by M3 logic")
    # I5 / I8 / I9 per put-up
    for x in state.get("per", []):
        t = x.get("trace")
        if x.get("answer") and not t:
            fail("I5", f"answer vs {x['their']} has no decision trace")
            continue
        if not t:
            skip("I5")
            continue
        pick = next((rr for rr in t["rows"] if rr["pick"]), None)
        if not pick:
            fail("I5", f"trace vs {x['their']} has no pick")
            continue
        if x.get("answer") and x["answer"]["our"] != pick["name"]:
            fail("I5", f"send card answer {x['answer']['our']} != trace pick {pick['name']} vs {x['their']}")
        elif x.get("answer") and abs((x["answer"].get("p") if x["answer"].get("p") is not None else -1) - pick["p"]) > 1e-12:
            fail("I5", f"send card and trace give different win chances for {pick['name']} vs {x['their']}")
        else:
            ok("I5")
        cmp_row = next((cr for cr in (state.get("compare") or {}).get("rows", []) if cr["their"] == x["their"]), None)
        if cmp_row and cmp_row.get("v2") and cmp_row["v2"]["our"] == pick["name"]:
            if abs((cmp_row["v2"]["p"] if cmp_row["v2"]["p"] is not None else -1) - pick["p"]) > 1e-12:
                fail("I5", f"comparison and trace give different win chances for {pick['name']} vs {x['their']}")
            else:
                ok("I5")
        if v2 and not x.get("answer") and x.get("nextLeader") != "us" and x.get("sendButtons"):
            fail("I8", f"Send button shown vs {x['their']} without a V2 engine answer")
        if v2 and x.get("answer"):
            if x.get("rendered") is None:
                fail("I8", f"no rendered send card vs {x['their']}")
            elif x.get("nextLeader") == "us":
                # Our put-up turn: the card is our put-up, which must be V2's lead (not an answer to their put-up).
                lead_pick = (plan or {}).get("lead") or {}
                if lead_pick.get("our") and x["rendered"] != lead_pick["our"]:
                    fail("I8", f"our put-up card names {x['rendered']} but V2's lead is {lead_pick.get('our')}")
                else:
                    ok("I8")
            elif x["rendered"] != x["answer"]["our"]:
                fail("I8", f"rendered send card names {x['rendered']} but the plan answer is {x['answer']['our']}")
            elif x["answer"]["our"] in x.get("avoid", []):
                fail("I2", f"send card recommends {x['answer']['our']} and lists them under avoid vs {x['their']}")
            elif "consider saving" in x.get("notes", "") or "Sending now spends" in x.get("notes", ""):
                fail("I8", f"legacy save/spend note on a V2 send card vs {x['their']}")
            elif any(s["level"].split(" ")[0] in M3_LEVELS for s in x.get("scen", [])):
                fail("I8", "send scenario shows an M3 level")
            else:
                ok("I8")
        now = max(t["rows"], key=lambda rr: rr["p"])
        if now["p"] - pick["p"] > 0.01:
            if t["strategic"] and t["gainWorst"] >= 0.10 - 1e-9 and t["gainAvg"] >= 0.10 - 1e-9 and "Strategic choice" in t["summary"]:
                ok("I9")
                exceptions.append({"state": label, "their": x["their"], "pick": pick["name"], "strongest": now["name"],
                                   "gainWorst": round(t["gainWorst"], 3), "gainAvg": round(t["gainAvg"], 3)})
            else:
                fail("I9", f"{pick['name']} ({pick['p']:.3f}) chosen over stronger {now['name']} ({now['p']:.3f}) vs {x['their']} without a qualifying explanation")
        else:
            ok("I9")
    # I6 plan consistency
    them, lead = plan.get("plan_if_they_lead") or [], plan.get("plan_if_we_lead") or []
    if rows and not them:
        fail("I6", "answers exist but the they-lead plan is empty")
    if them:
        first = next((r for r in plan.get("responses", []) if r["their"] == them[0]["their"]), None)
        if not first or first["our"] != them[0]["our"]:
            fail("I6", "first game of the they-lead plan differs from the card's answer")
        elif plan.get("total_if_they_lead") is not None and abs(plan["total_if_they_lead"] - round(1000 * sum(g["p"] for g in them))) > 1:
            fail("I6", "they-lead total is not the plan path's expected wins")
        else:
            ok("I6")
    if lead and plan.get("lead"):
        if lead[0]["our"] != plan["lead"]["our"]:
            fail("I6", "first game of the we-lead plan differs from the lead card")
        else:
            ok("I6")
    c = state.get("compare")
    if v2 and rows and not c:
        fail("I6", "V2 comparison missing")
    elif c and c.get("v2Them") and them:
        if abs(c["v2Them"]["w"] - sum(g["p"] for g in them)) > 1e-9:
            fail("I6", "comparison scores a different policy than the plan")
        else:
            ok("I6")
    # I7 skill cap including prior spend; unknown skill levels are incomplete, never zero
    sl = {str(b["id"]): b.get("sl") for b in (state.get("bench") or {}).get("ours", [])}
    if state.get("cap") is None:
        skip("I7")
    else:
        prior = [sl.get(str(g.get("ourId"))) for g in state.get("games") or []]
        for nm, line in (("they-lead", them), ("we-lead", lead)):
            if not line:
                skip("I7")
                continue
            plan_sl = [sl.get(str(g.get("our_id"))) for g in line]
            if any(v is None for v in plan_sl + prior):
                skip("I7")
                continue
            total = sum(prior) + sum(plan_sl)
            if total > state["cap"]:          # the cap limits any total, not only a full five
                fail("I7", f"{nm}: prior {sum(prior)} + plan {sum(plan_sl)} = {total} over cap {state['cap']}")
            else:
                ok("I7")
    # I8 vocabulary
    if v2:
        bad = [r["level"] for r in rows if r["level"] not in V2_LEVELS] + [g["level"] for g in them + lead if g["level"] not in V2_LEVELS]
        if bad:
            fail("I8", f"non-V2 levels in recommendations: {sorted(set(bad))}")
        elif rows:
            ok("I8")
    return counts


def main():
    from playwright.sync_api import sync_playwright
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", required=True)
    ap.add_argument("--division", required=True)
    ap.add_argument("--format", default="EIGHT")
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shard", default="1/1")
    a = ap.parse_args()
    fmt_label = {"EIGHT": "8-Ball", "NINE": "9-Ball"}.get(a.format)
    html_hash = hashlib.sha256(Path(a.html).read_bytes()).hexdigest()
    fails, exceptions, counts, states, no_answer = [], [], Counter(), 0, 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(Path(a.html).resolve().as_uri())
        page.wait_for_selector("#bc-team-a")
        text = page.inner_text("body").lower()
        counts.c["I11"]["checked"] += 1
        if "optimal team points" in text or "optimizes team points" in text:
            fails.append({"state": "page", "invariant": "I11", "detail": "unsupported team-point optimisation claim"})
            counts.c["I11"]["failed"] += 1
        page.evaluate("f => { const el = document.getElementById('team-format'); el.value = f; el.dispatchEvent(new Event('change', {bubbles: true})); }", a.format)
        keys = page.evaluate("d => Array.from(new Set(Array.from(document.querySelectorAll('#bc-team-a option')).map(o => o.value).filter(v => v && v.indexOf('|' + d + '|') >= 0)))", a.division)
        pairs = [(x, y) for x in keys for y in keys if x != y]
        if a.limit:
            pairs = pairs[:a.limit]
        si, sn = (int(v) for v in a.shard.split("/"))
        pairs = pairs[si - 1::sn]
        t0 = time.time()

        def i10(label, cond, msg):
            counts.c["I10"]["checked"] += 1
            if cond:
                counts.c["I10"]["failed"] += 1
                fails.append({"state": label, "invariant": "I10", "detail": msg})

        for k, (x, y) in enumerate(pairs, 1):
            base = page.evaluate(STATE_JS, [x, y, a.format, 23, [], [], 0, ""])
            ours = [p["id"] for p in base["bench"]["ours"]]
            theirs = [p["id"] for p in base["bench"]["theirs"]]
            variants = [("cap23", 23, [], [], 0, ""), ("cap22", 22, [], [], 0, ""), ("capOff", None, [], [], 0, ""),
                        ("tossUs", 23, [], [], 0, "us"), ("tossThem", 23, [], [], 0, "them")]
            variants += [(f"played{n}{t}", 23, [], [], n, t) for n in range(1, 5) for t in ("them", "us")]
            if base["rows"]:
                variants.append(("ourOut", 23, [base["rows"][0]["ourId"]], [], 0, ""))
            if theirs:
                variants.append(("theirOut", 23, [], [theirs[0]], 0, ""))
            if len(ours) > 3:
                variants.append(("noFive", 23, ours[3:], [], 0, ""))
            for tag, cap, out_ids, opp_out, played, toss in variants:
                st = page.evaluate(STATE_JS, [x, y, a.format, cap, out_ids, opp_out, played, toss])
                states += 1
                label = f"{x} v {y} [{tag}]"
                if not st["rows"]:
                    no_answer += 1
                check(st, label, fails, exceptions, counts, (x, y, fmt_label))
                if tag.startswith("cap"):
                    i10(label, st["cap"] != cap, f"cap in force {st['cap']} != set {cap}")
                for oid in out_ids:
                    i10(label, any(str(r["ourId"]) == str(oid) for r in st["rows"]), "Out player still recommended")
                for tid in opp_out:
                    i10(label, any(str(r["theirId"]) == str(tid) for r in st["rows"]), "their Out player still offered as a put-up")
                if played:
                    i10(label, (st["played"] or 0) != min(played, 5), f"{played} sends recorded but {st['played']} shown played")
            print(f"progress {k}/{len(pairs)} pairs, {states} states, {len(fails)} contradictions, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
        page.evaluate("localStorage.clear()")
        browser.close()
    mandatory = ("I0", "I1", "I2", "I5", "I6", "I8", "I9")
    coverage_ok = len(pairs) > 0 and states > 0 and all(counts.c[i]["checked"] > 0 for i in mandatory)
    by = {}
    for f in fails:
        by[f["invariant"]] = by.get(f["invariant"], 0) + 1
    report = {"html_sha256": html_hash, "format": a.format, "shard": a.shard, "team_pairs": len(pairs), "states": states,
              "no_answer_states": no_answer, "coverage_ok": coverage_ok, "counts": counts.c, "contradictions": len(fails),
              "by_invariant": by, "strategic_exceptions": len(exceptions), "fails": fails, "exceptions": exceptions}
    Path(a.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    summary = {k: report[k] for k in ("html_sha256", "format", "shard", "team_pairs", "states", "no_answer_states", "coverage_ok",
                                      "counts", "contradictions", "by_invariant", "strategic_exceptions")}
    if a.summary:
        Path(a.summary).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    if not coverage_ok:
        sys.exit("coverage check failed: zero pairs/states or a mandatory invariant was never checked")


if __name__ == "__main__":
    main()
