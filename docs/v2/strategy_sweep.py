"""V2 candidate strategy sweep: how the executed V2 policy behaves on every team pair of one division.

Runs locally against a built V2 review HTML (real data stays on the machine). Writes aggregates only: no
player, team or division names, no ids. Reproduce:

    python -I docs/v2/strategy_sweep.py --html <V2 review HTML> --division <division id> --format EIGHT --out <json>

Selection: every ordered pair of distinct teams whose scope key contains |<division>| in the chosen format; start
of night, everyone available, no games played; once with the default cap (23) and once with the cap cleared.
For each pair and each of their legal put-ups: the V2 answer, the strongest matchup now, M3's answer, and whether
V2 gave up the strongest matchup. Policies scored with V2's win chances under identical opponent models (their
most damaging choice / even choices), for the whole night: V2 as executed, M3's choices, always the strongest
matchup now, and plain worst-case optimisation (V2 before the captain-control rule); plus the best possible
worst-case value (benchmark). The 0.10 threshold and the even-choice model are provisional policy choices.
"""
import argparse
import json
import statistics
from pathlib import Path

from playwright.sync_api import sync_playwright

JS = """([div, fmt, cap]) => {
  const keys = Array.from(document.querySelectorAll('#bc-team-a option')).map(o => o.value).filter(v => v && v.indexOf('|' + div + '|') >= 0);
  const out = {pairs: [], decisions: [], excluded: 0};
  for (const a of keys) for (const b of keys) {
    if (a === b) continue;
    const c = window.__ucEngineCompare(a, b, fmt, cap);
    const plan = window.__ucPlanFor(a, b, fmt, null, null, 0, 0, cap, 'v2');
    const m3 = window.__ucPlanFor(a, b, fmt, null, null, 0, 0, cap, 'm3');
    if (!c || !c.v2Them || !(plan.responses || []).length) { out.excluded++; continue; }
    out.pairs.push({v2: c.v2Them, m3: c.m3Them, now: c.strongestNowThem, mm: c.minimaxThem, bench: c.benchThem,
                    v2L: c.v2Lead, m3L: c.m3Lead, nowL: c.strongestNowLead, mmL: c.minimaxLead, benchL: c.benchLead});
    for (const r of plan.responses) {
      const t = window.__ucV2Trace(a, b, fmt, r.their, null, cap);
      if (!t) continue;
      const now = t.rows.reduce((x, y) => y.p > x.p ? y : x), pick = t.rows.find(x => x.pick);
      const m3r = (m3.responses || []).find(x => x.their === r.their), m3row = m3r ? t.rows.find(x => x.name === m3r.our) : null;
      const benchBest = Math.max(...t.rows.map(x => x.totalWorst));
      out.decisions.push({strategic: t.strategic, gainW: t.gainWorst, gainA: t.gainAvg, pNow: now.p, pPick: pick.p,
        pM3: m3row ? m3row.p : null, role: pick.role, worstPrefersOther: benchBest - now.totalWorst > 1e-9});
    }
  }
  return out;
}"""


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 4) if xs else None


def summarise(raw):
    d, p = raw["decisions"], raw["pairs"]
    strat = [x for x in d if x["strategic"]]
    pol = lambda key, f: mean([x[key][f] for x in p if x.get(key)])
    roles = {}
    for x in d:
        roles[x["role"]] = roles.get(x["role"], 0) + 1
    return {
        "team_pairs": len(p), "excluded_pairs": raw["excluded"], "put_up_decisions": len(d),
        "v2_gives_up_strongest_now": len(strat),
        "worst_case_policy_would_give_up_strongest_now": sum(x["worstPrefersOther"] for x in d),
        "when_v2_gives_it_up": {"mean_win_chance_given_up": mean([x["pNow"] - x["pPick"] for x in strat]),
                                "mean_gain_worst": mean([x["gainW"] for x in strat]), "mean_gain_even": mean([x["gainA"] for x in strat])},
        "mean_win_chance_now": {"v2_answer": mean([x["pPick"] for x in d]), "m3_answer": mean([x["pM3"] for x in d]),
                                "strongest_now": mean([x["pNow"] for x in d])},
        "roles": roles,
        "whole_night_expected_wins_they_put_up_first": {
            k: {"worst_case": pol(key, "w"), "even_choices": pol(key, "a")}
            for k, key in (("v2_executed", "v2"), ("m3_choices", "m3"), ("always_strongest_now", "now"), ("plain_worst_case", "mm"))},
        "whole_night_expected_wins_we_put_up_first": {
            k: {"worst_case": pol(key, "w"), "even_choices": pol(key, "a")}
            for k, key in (("v2_executed", "v2L"), ("m3_choices", "m3L"), ("always_strongest_now", "nowL"), ("plain_worst_case", "mmL"))},
        "benchmark_best_possible_worst_case": {"they_put_up_first": mean([x["bench"] for x in p]), "we_put_up_first": mean([x["benchL"] for x in p])},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", required=True)
    ap.add_argument("--division", required=True)
    ap.add_argument("--format", default="EIGHT")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    result = {"description": "V2 candidate strategy sweep (aggregates only)", "format": a.format,
              "threshold_expected_wins": 0.10, "opponent_models": ["most damaging choice", "even choices"], "runs": {}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(Path(a.html).resolve().as_uri())
        page.wait_for_timeout(2500)
        for label, cap in (("cap_23", 23), ("cap_cleared", None)):
            result["runs"][label] = summarise(page.evaluate(JS, [a.division, a.format, cap]))
        browser.close()
    Path(a.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
