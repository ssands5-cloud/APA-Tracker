"""Who-plays vs how-paired decomposition of the M3 board total (derived from captain_vs_m3.py)

Captain vs M3 (counterfactual matchings of the realized ten players). Read-only. See PREREGISTRATION.md."""
import sys, json, sqlite3, math, itertools
from collections import defaultdict
from pathlib import Path
import numpy as np
from pandas import Series
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_common as _rc
DB, OUT = _rc.setup(__doc__)
from analytics.ultimate_coach_confidence import pair_confidence, sl_changed_since_last_meeting, LEVEL_POINTS
from replay_confidence_levels import FORMATS, local_day
sys.stdout.reconfigure(encoding="utf-8")
TRAIN_END = "2025-08-31"; START = "2023-01-01"; B = 1000
rng = np.random.default_rng(20261121)
PERMS = np.array(list(itertools.permutations(range(5))))

con = sqlite3.connect(Path(DB).as_uri() + "?mode=ro", uri=True)
rows = con.execute("""SELECT h.player_id,h.opponent_id,h.result,h.own_skill_level,h.opponent_skill_level,h.format,m.match_date,h.match_id
  FROM player_head_to_head h JOIN matches m ON m.id=h.match_id WHERE h.result IN ('W','L')""").fetchall()
mt = {r[0]: r[1:] for r in con.execute("SELECT id,home_team_id,away_team_id,home_score,away_score,is_scored,is_bye FROM matches")}
pt = {(r[0], r[1]): r[2] for r in con.execute("SELECT player_id,match_id,team_id FROM player_matches")}
pm_count = defaultdict(lambda: defaultdict(int))
for (p, m), t in pt.items():
    pm_count[m][t] += 1
games = defaultdict(list)
for p, o, res, slp, slo, fmt, day, mid in rows:
    if fmt in FORMATS and p != o:
        games[(FORMATS[fmt], local_day(day))].append((p, o, res == "W", slp, slo, mid))
for _k in games:
    games[_k].sort(key=lambda g: (str(g[5]), str(g[0]), str(g[1])))
pairs = defaultdict(dict); overall = defaultdict(lambda: [0, 0])


def level_pts(fmt, p, o, slp, slo):
    mine, theirs = pairs[(fmt, p)], pairs[(fmt, o)]
    rec = mine.get(o); shared = None
    if rec is None:
        common = mine.keys() & theirs.keys() - {p, o}
        if common:
            shared = (sum(mine[x][0] for x in common), sum(mine[x][1] for x in common),
                      sum(theirs[x][0] for x in common), sum(theirs[x][1] for x in common), len(common))
    ch = sl_changed_since_last_meeting([{"sort": rec[2], "own_sl": rec[3], "opp_sl": rec[4]}] if rec else [], slp, slo)
    return LEVEL_POINTS[pair_confidence((rec[0], rec[1]) if rec else None, own_overall=tuple(overall[(fmt, p)]),
                                        opp_overall=tuple(overall[(fmt, o)]), shared=shared, sl_changed=ch)["level"]]


matches = {"EIGHT": [], "NINE": []}
histrows = []  # (fmt, p, o, won, slp, slo, day) for SL-pair training
for (fmt, day), obs in sorted(games.items()):
    bym = defaultdict(list)
    for g in obs:
        bym[g[5]].append(g)
    if day >= START:
        for mid, gl in bym.items():
            m = mt.get(mid)
            if not m or len(gl) != 10:
                continue
            home, away, hs, as_, scored, bye = m
            if not scored or bye or hs is None or as_ is None or pm_count[mid].get(home) != 5 or pm_count[mid].get(away) != 5:
                continue
            hp, ap, sl = [], [], {}
            real = {}
            ok = True
            for p, o, won, slp, slo, _ in gl:
                t = pt.get((p, mid))
                if t not in (home, away) or not slp or not slo:
                    ok = False; break
                sl[p] = slp
                (hp if t == home else ap).append(p)
                if t == home:
                    real[p] = o
            hp, ap = sorted(set(hp)), sorted(set(ap))
            if not ok or len(hp) != 5 or len(ap) != 5 or set(real.values()) != set(ap):
                continue
            LH = np.array([[level_pts(fmt, h, a, sl[h], sl[a]) for a in ap] for h in hp], float)
            LA = np.array([[level_pts(fmt, a, h, sl[a], sl[h]) for a in ap] for h in hp], float)  # away's view of the pair
            rp = [ap.index(real[h]) for h in hp]
            matches[fmt].append(dict(day=day, LH=LH, LA=LA, rp=rp, slh=[sl[h] for h in hp], sla=[sl[a] for a in ap], hp=hs, ap=as_))
    for p, o, won, slp, slo, mid in obs:
        rec = pairs[(fmt, p)].setdefault(o, [0, 0, day, slp, slo])
        rec[0] += int(won); rec[1] += 1; rec[2:] = [day, slp, slo]
        overall[(fmt, p)][0] += int(won); overall[(fmt, p)][1] += 1
        histrows.append((fmt, slp, slo, int(won), day))


def exp_tables(fmt):
    cnt = defaultdict(lambda: [0, 0]); gl = []
    for f, a, b, w, d in histrows:
        if f == fmt and START <= d <= TRAIN_END and a and b:
            cnt[(a, b)][0] += w; cnt[(a, b)][1] += 1; gl.append((a - b, w))
    bb = 0.0
    for _ in range(50):
        g = h = 0.0
        for gap, w in gl:
            pp = 1 / (1 + math.exp(-bb * gap)); g += (w - pp) * gap; h -= pp * (1 - pp) * gap * gap
        if h == 0: break
        bb -= g / h
    return cnt, bb


def auc(y, s):
    r = Series(s).rank().to_numpy(); n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
def ols(X, y): return np.linalg.lstsq(np.c_[np.ones(len(X)), X], y, rcond=None)[0]
def ols_pred(b, X): return np.c_[np.ones(len(X)), X] @ b
def logit(X, y, it=30):
    X1 = np.c_[np.ones(len(X)), X]; b = np.zeros(X1.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X1 @ b)); W = p * (1 - p) + 1e-9
        b = b + np.linalg.solve(X1.T @ (X1 * W[:, None]) + 1e-8 * np.eye(len(b)), X1.T @ (y - p))
    return b
def logit_p(b, X): return 1 / (1 + np.exp(-(np.c_[np.ones(len(X)), X] @ b)))
def ci(a): return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]
def r2(y, p): return 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def board_totals(L):  # L 5x5 -> totals for all 120 matchings
    return L[np.arange(5)[None, :], PERMS].sum(axis=1)


out = {}
RES = {}
for fmt in ("EIGHT", "NINE"):
    cnt, slope = exp_tables(fmt)
    def ew(a, b):
        prior = 1 / (1 + math.exp(-slope * (a - b))); w, n = cnt.get((a, b), (0, 0)); return (w + 25 * prior) / (n + 25)
    recs = []
    for m in matches[fmt]:
        th, ta = board_totals(m["LH"]), board_totals(m["LA"].T if False else m["LA"][np.arange(5)[:, None], np.arange(5)[None, :]])
        # LA[h][a] is the away player's points for facing h; away total for matching perm = sum_i LA[i, perm[i]]
        ta = m["LA"][np.arange(5)[None, :], PERMS].sum(axis=1)
        idx = int(np.where((PERMS == np.array(m["rp"])).all(axis=1))[0][0])
        def reg(t):
            rng_ = t.max() - t.min()
            return (None if rng_ == 0 else float((t.max() - t[idx]) / rng_)), float((t == t.max()).mean()), int(t[idx] == t.max())
        rh, nh, oh = reg(th); ra, na, oa = reg(ta)
        eh = sum(ew(m["slh"][i], m["sla"][m["rp"][i]]) for i in range(5)); ea = sum(ew(m["sla"][m["rp"][i]], m["slh"][i]) for i in range(5))
        recs.append(dict(day=m["day"], rh=rh, ra=ra, nullh=nh, nulla=na, opth=oh, opta=oa, dsl=sum(m["slh"]) - sum(m["sla"]),
                         dex=eh - ea, invh=float(th.mean()), inva=float(ta.mean()), resh=float(th[idx]-th.mean()), resa=float(ta[idx]-ta.mean()), hp=m["hp"], ap=m["ap"]))

    tr = [r for r in recs if r["day"] <= TRAIN_END]; te = [r for r in recs if r["day"] > TRAIN_END]
    def A(L, k): return np.array([r[k] for r in L], float)
    def X(L): return np.c_[A(L, "dsl"), A(L, "dex"), A(L, "invh") - A(L, "inva"), A(L, "resh") - A(L, "resa")]
    Xtr, Xte = X(tr), X(te); sd = Xtr.std(0); Xtr /= sd; Xte /= sd
    ytr = A(tr, "hp") - A(tr, "ap"); yte = A(te, "hp") - A(te, "ap")
    wtr, wte = ytr != 0, yte != 0
    yw = (yte > 0)[wte].astype(float); ywt = (ytr > 0)[wtr].astype(float)
    f = logit(Xte[wte], yw)
    cs = []
    for _ in range(B):
        k = rng.integers(0, len(te), len(te)); w = wte[k]; cs.append(logit(Xte[k][w], ((yte[k] > 0)[w]).astype(float), 15))
    cs = np.array(cs)
    base = logit(Xtr[wtr][:, :2], ywt); inv = logit(Xtr[wtr][:, :3], ywt); full = logit(Xtr[wtr], ywt)
    a0 = auc(yw, logit_p(base, Xte[wte][:, :2])); a1 = auc(yw, logit_p(inv, Xte[wte][:, :3])); a2 = auc(yw, logit_p(full, Xte[wte]))
    RES[fmt] = dict(n=len(te), coef_names=["dSL", "dExpSL", "M3 invariant part (who plays)", "M3 matching-specific part (how paired)"],
                    coef=[float(v) for v in f[1:]], ci=[ci(cs[:, i + 1]) for i in range(4)],
                    auc_skill=float(a0), auc_plus_invariant=float(a1), auc_plus_both=float(a2),
                    sd_inv=float(sd[2]), sd_res=float(sd[3]), corr_inv_vs_res=float(np.corrcoef(Xte[:, 2], Xte[:, 3])[0, 1]))
(OUT / "decomp_results.json").write_text(json.dumps(RES, indent=2)); print(json.dumps(RES, indent=1))
