"""Cross-runtime policy parity, not native Excel acceptance."""
import pytest
from playwright.sync_api import sync_playwright

from analytics.uc_v2_pair_model import band, win_probability
from analytics.uc_v2_policy import V2Policy, classify
from tests.test_uc_v2_candidate import _render


def players(ids, levels):
    return [{"id": i, "name": i.upper(), "sl": sl} for i, sl in zip(ids, levels)]


def matrix(ours, theirs, fmt):
    return {(o["id"], t["id"]): win_probability(fmt, o["sl"], t["sl"])
            for o in ours for t in theirs}


def browser_values(p):
    return {f"{o}|{t}": {"p": v, "v2": True, "points": round(1000*(v-.5)),
                         "level": band(v), "why": "", "text": ""}
            for (o, t), v in p.items()}


def compare(a, b):
    """Recursive comparison; stable IDs and roles exact, numbers near machine precision."""
    if isinstance(a, dict):
        assert a.keys() == b.keys()
        for k in a:
            compare(a[k], b[k])
    elif isinstance(a, list):
        assert len(a) == len(b)
        for x, y in zip(a, b):
            compare(x, y)
    elif isinstance(a, float):
        assert a == pytest.approx(b, abs=1e-12, rel=0)
    else:
        assert a == b


# Driven by the actual browser's executed policy, not the M3 plan or a test copy.
PROJECT = """([o,t,v,g,c,u,tu]) => {
  const mp=window.__ucV2Apply(window.__ucMatchPlan(o,t,v,g,c,u,c,tu),o,t,v,g,c,u,tu);
  const n=mp.v2.night, pol=mp.v2.policy, om=n.fullOurs, tm=n.fullTheirs;
  const L=pol.st(om,tm,true), T=pol.st(om,tm,false);
  const line=(om,tm,lead)=>pol.line(om,tm,lead).map(x=>({
    leader:x.leader,our_id:String(o[x.our].id),their_id:String(t[x.their].id),p:x.p}));
  const out={lead:null,responses:{},totals:{us:{w:L.w,a:L.a},them:{w:T.w,a:T.a}},
             lines:{us:line(om,tm,true),them:line(om,tm,false)}};
  if(!L.lead)return out;
  const leadRow=r=>({our_id:String(o[r.i].id),their_id:String(t[r.reply].id),
    w:r.w,a:r.a,p:v[String(o[r.i].id)+'|'+String(t[r.reply].id)].p});
  out.lead=leadRow(L.lead);
  out.lead_options=L.rows.map(leadRow);
  out.lead_equal_ids=L.rows.filter(r=>r!==L.lead && Math.abs(r.w-L.lead.w)<.02 &&
    Math.abs(r.a-L.lead.a)<.02).map(r=>String(o[r.i].id));
  for(const j of n.legalTheirs(om,tm)){
    const r=pol.respond(om,tm,j);
    const rows=r.rows.map(x=>{
      const {i,...fields}=x;
      return {...fields,our_id:String(o[i].id),later:line(om&~(1<<i),tm&~(1<<j),true)};
    });
    out.responses[String(t[j].id)]={pick:String(o[r.pick.i].id),now:String(o[r.now.i].id),
      strat:String(o[r.strat.i].id),avgBest:String(o[r.avgBest.i].id),
      strategic:r.strategic,gainWorst:r.gainWorst,gainAvg:r.gainAvg,rows};
  }
  return out;
}"""


def test_strategic_concession_vs_immediate_strength():
    o, t = players("ab", [5, 5]), players("xy", [5, 5])
    p = {("a","x"):.60, ("b","x"):.55, ("a","y"):.70, ("b","y"):.40}
    r = V2Policy(o,t,p,2,None).trace()["responses"]["x"]
    assert r["pick"] == "b" and r["now"] == "a"
    assert r["strategic"]
    assert r["gainWorst"] == pytest.approx(.25)
    assert r["gainAvg"] == pytest.approx(.25)
    assert r["rows"][1]["later"][0]["our_id"] == "a"


def test_one_model_gain_alone_is_not_enough():
    rows = [dict(i=0,p=.6,totalWorst=.75,totalAvg=.875),
            dict(i=1,p=.55,totalWorst=1.,totalAvg=.95)]
    r = classify(rows)
    assert not r["strategic"] and r["pick"]["i"] == 0


def test_missing_probability_fails_closed_and_duplicate_names_keep_ids():
    o, t = players("ab", [5,5]), players("xy", [5,5])
    o[1]["name"] = o[0]["name"]
    t[1]["name"] = t[0]["name"]
    p = {(a["id"], b["id"]): .5 for a in o for b in t}
    r = V2Policy(o,t,p,2,None).trace()
    assert set(r["responses"]) == {"x","y"}
    assert r["responses"]["x"]["pick"] == "a"
    assert r["responses"]["x"]["rows"][1]["our_id"] == "b"
    p.pop(("b","y"))
    with pytest.raises(ValueError, match="Missing/invalid"):
        V2Policy(o,t,p,2,None)


def test_browser_policy_matches_python(tmp_path):
    # Equivalent pre-filtered states: original roster, both teams out/played,
    # cap override, prior spend, incomplete skill, no feasible five, end.
    o = players("abcdef", [6,5,4,3,4,2])
    t = players("uvwxyz", [7,3,4,5,2,3])
    cases = [(o,t,5,23,0,0), (o,t,5,22,0,0), (o,t,5,None,0,0),
             (o[1:],t[1:],4,23,6,7), (o[2:],t[2:],3,23,9,10),
             (o[3:],t[3:],2,23,11,12), (o[-2:],t[-2:],1,23,18,18),
             (o[:-1],t[:-1],5,23,0,0), (o,t,5,8,0,0),
             (players("ab",[None,4]),t[-2:],2,23,5,5),
             (o,t,0,23,20,20)]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(_render(tmp_path).as_uri())
            for fmt in ("EIGHT","NINE"):
                for ours,theirs,games,cap,used,opp_used in cases:
                    p = matrix(ours,theirs,fmt)
                    actual = page.evaluate(PROJECT,[ours,theirs,browser_values(p),games,cap,used,opp_used])
                    expected = V2Policy(ours,theirs,p,games,cap,used,opp_used).trace()
                    expected.pop("policy")
                    expected.pop("opponent_cap_relaxed")
                    expected.pop("cap_incomplete")
                    expected.pop("opponent_cap_incomplete")
                    compare(expected,actual)
        finally:
            browser.close()
