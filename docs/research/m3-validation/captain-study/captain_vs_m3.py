"""Captain vs M3 (counterfactual matchings of the realized ten players). Read-only. See PREREGISTRATION.md."""
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
                         dex=eh - ea, hp=m["hp"], ap=m["ap"]))
    tr = [r for r in recs if r["day"] <= TRAIN_END]; te = [r for r in recs if r["day"] > TRAIN_END]
    R = {"n_train": len(tr), "n_test": len(te)}

    # ---- categories on test team-boards
    def cats(L):
        vals, nulls, ops = [], [], []
        for r in L:
            for k, nk, ok in (("rh", "nullh", "opth"), ("ra", "nulla", "opta")):
                if r[k] is not None:
                    vals.append(r[k]); nulls.append(r[nk]); ops.append(r[ok])
        return np.array(vals), np.array(nulls), np.array(ops)
    v, nul, op = cats(te)
    def shares(v):
        return [float((v == 0).mean()), float(((v > 0) & (v <= .05)).mean()), float(((v > .05) & (v <= .40)).mean()), float((v > .40).mean())]
    R["team_boards_with_alternatives"] = int(len(v)); R["share_no_alternative"] = 1 - len(v) / (2 * len(te))
    R["category_shares_optimal_near_sub_strong"] = shares(v)
    R["null_share_optimal_random_matching"] = float(nul.mean())
    R["mean_regret"] = float(v.mean())
    bs, bd = [], []
    for _ in range(B):
        s = rng.integers(0, len(v), len(v))
        bs.append(shares(v[s])); bd.append(float(op[s].mean() - nul[s].mean()))
    bs = np.array(bs)
    R["category_share_cis"] = [ci(bs[:, i]) for i in range(4)]
    R["optimal_minus_null"] = float(op.mean() - nul.mean()); R["optimal_minus_null_ci"] = ci(bd)
    # random-matching benchmark for mean regret
    # ---- dose response
    def A(L, k): return np.array([r[k] for r in L], float)
    def feats(L):
        rh = np.array([np.nan if r["rh"] is None else r["rh"] for r in L]); ra = np.array([np.nan if r["ra"] is None else r["ra"] for r in L])
        rd = np.where(np.isnan(rh), 0, rh) * -1 + np.where(np.isnan(ra), 0, ra)  # regret_away - regret_home (>0 favours home)
        return np.c_[A(L, "dsl"), A(L, "dex")], rd
    Xs_tr, rd_tr = feats(tr); Xs_te, rd_te = feats(te)
    sd = rd_tr.std()
    y_tr = A(tr, "hp") - A(tr, "ap"); y_te = A(te, "hp") - A(te, "ap")
    Xf_tr = np.c_[Xs_tr, rd_tr / sd]; Xf_te = np.c_[Xs_te, rd_te / sd]
    bsm, bfm = ols(Xs_tr, y_tr), ols(Xf_tr, y_tr)
    wk_tr, wk_te = y_tr != 0, y_te != 0
    yw_tr, yw_te = (y_tr > 0)[wk_tr].astype(float), (y_te > 0)[wk_te].astype(float)
    ls, lf = logit(Xs_tr[wk_tr], yw_tr), logit(Xf_tr[wk_tr], yw_tr)
    d_auc = auc(yw_te, logit_p(lf, Xf_te[wk_te])) - auc(yw_te, logit_p(ls, Xs_te[wk_te]))
    d_r2 = r2(y_te, ols_pred(bfm, Xf_te)) - r2(y_te, ols_pred(bsm, Xs_te))
    bda, bdr, bcw, bcp = [], [], [], []
    n = len(te)
    for _ in range(B):
        s = rng.integers(0, n, n); y = y_te[s]; w = wk_te[s]; yw = (y > 0)[w].astype(float)
        bda.append(auc(yw, logit_p(lf, Xf_te[s][w])) - auc(yw, logit_p(ls, Xs_te[s][w])))
        bdr.append(r2(y, ols_pred(bfm, Xf_te[s])) - r2(y, ols_pred(bsm, Xs_te[s])))
        Xb = np.c_[Xs_te[s], rd_te[s] / sd]; bcp.append(ols(Xb, y)[3]); bcw.append(logit(Xb[w], yw, 15)[3])
    Xt = np.c_[Xs_te, rd_te / sd]
    fw = logit(Xt[wk_te], yw_te); fp = ols(Xt, y_te)
    R["dose_response"] = {"rdiff_sd_train": float(sd), "share_rdiff_zero_test": float((rd_te == 0).mean()),
        "coef_logit_win_per_sd": float(fw[3]), "coef_logit_win_ci": ci(bcw), "train_coef_logit": float(lf[3]),
        "coef_points_per_sd": float(fp[3]), "coef_points_ci": ci(bcp), "train_coef_points": float(bfm[3]),
        "dAUC": float(d_auc), "dAUC_ci": ci(bda), "dR2": float(d_r2), "dR2_ci": ci(bdr)}
    # team-night win rate by own regret tercile (test), no controls
    vv, ww = [], []
    for r in te:
        if r["hp"] == r["ap"]: continue
        for k, win in (("rh", r["hp"] > r["ap"]), ("ra", r["ap"] > r["hp"])):
            if r[k] is not None: vv.append(r[k]); ww.append(float(win))
    vv, ww = np.array(vv), np.array(ww); qs = np.quantile(vv, [1 / 3, 2 / 3]); tc = np.digitize(vv, qs)
    R["win_rate_by_own_regret_tercile_low_mid_high"] = [float(ww[tc == t].mean()) for t in range(3)]
    R["tercile_cuts"] = [float(x) for x in qs]
    lo, hi = vv <= 0, vv > .40
    R["win_rate_optimal_boards"] = float(ww[lo].mean()) if lo.any() else None; R["n_optimal_boards"] = int(lo.sum())
    R["win_rate_strongly_suboptimal"] = float(ww[hi].mean()) if hi.any() else None; R["n_strongly_sub"] = int(hi.sum())
    # sensitivity (assumption-bound): moving own regret to zero, per-team win prob change via logit coef per SD of rdiff
    meanr = float(vv.mean()); R["sensitivity_if_causal"] = {"mean_regret": meanr, "logit_shift_per_team": float(fw[3] * meanr / sd),
        "approx_win_prob_gain_near_even": float(0.25 * fw[3] * meanr / sd)}
    out[fmt] = R
cnt = con.execute("""SELECT AVG(c) FROM (SELECT COUNT(*) c FROM (SELECT home_team_id t,substr(match_date,1,4) y FROM matches WHERE is_scored=1 AND is_bye=0
  UNION ALL SELECT away_team_id,substr(match_date,1,4) FROM matches WHERE is_scored=1 AND is_bye=0) GROUP BY t,y HAVING COUNT(*)>=6)""").fetchone()
out["avg_matches_per_team_year"] = cnt[0]
(OUT / "results.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=1))
