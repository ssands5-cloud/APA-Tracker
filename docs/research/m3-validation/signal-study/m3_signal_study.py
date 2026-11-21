"""M3 score signal study. Read-only. See PREREGISTRATION.md (rules fixed before running)."""
import sys, json, sqlite3, math
from collections import defaultdict
from pathlib import Path
import numpy as np
from pandas import Series
REPO = r"D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker\.worktrees\uc-broadcast-ui"
sys.path.insert(0, REPO)
from analytics.ultimate_coach_confidence import pair_confidence, sl_changed_since_last_meeting, LEVEL_POINTS
sys.path.insert(0, REPO + r"\scripts")
from replay_confidence_levels import FORMATS, local_day
DB = r"D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging.db"
sys.stdout.reconfigure(encoding="utf-8")
TRAIN_END = "2025-08-31"; START = "2023-01-01"; B = 1000
rng = np.random.default_rng(20261120)

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
    if fmt not in FORMATS or p == o:
        continue
    games[(FORMATS[fmt], local_day(day))].append((p, o, res == "W", slp, slo, mid))
pairs = defaultdict(dict)
overall = defaultdict(lambda: [0, 0])
lvl = {}
for (fmt, day), obs in sorted(games.items()):
    for p, o, won, slp, slo, mid in obs:
        mine, theirs = pairs[(fmt, p)], pairs[(fmt, o)]
        rec = mine.get(o)
        shared = None
        if rec is None:
            common = mine.keys() & theirs.keys() - {p, o}
            if common:
                shared = (sum(mine[x][0] for x in common), sum(mine[x][1] for x in common),
                          sum(theirs[x][0] for x in common), sum(theirs[x][1] for x in common), len(common))
        ch = sl_changed_since_last_meeting([{"sort": rec[2], "own_sl": rec[3], "opp_sl": rec[4]}] if rec else [], slp, slo)
        L = pair_confidence((rec[0], rec[1]) if rec else None, own_overall=tuple(overall[(fmt, p)]),
                            opp_overall=tuple(overall[(fmt, o)]), shared=shared, sl_changed=ch)["level"]
        lvl[(fmt, mid, p, o)] = (LEVEL_POINTS[L], L, int(won), slp, slo, day)
    for p, o, won, slp, slo, mid in obs:
        rec = pairs[(fmt, p)].setdefault(o, [0, 0, day, slp, slo])
        rec[0] += int(won); rec[1] += 1; rec[2:] = [day, slp, slo]
        overall[(fmt, p)][0] += int(won); overall[(fmt, p)][1] += 1

bymatch = defaultdict(list)
for (fmt, mid, p, o), v in lvl.items():
    bymatch[(fmt, mid)].append((p, o) + v)


def fit_logit_slope(g):
    b = 0.0
    for _ in range(50):
        gr = h = 0.0
        for gap, w in g:
            pp = 1 / (1 + math.exp(-b * gap))
            gr += (w - pp) * gap
            h -= pp * (1 - pp) * gap * gap
        if h == 0:
            break
        b -= gr / h
    return b


train_stats = {}
for fmt in ("EIGHT", "NINE"):
    cnt = defaultdict(lambda: [0, 0])
    gl = []
    for (f, mid, p, o), v in lvl.items():
        if f != fmt or v[5] < START or v[5] > TRAIN_END or not v[3] or not v[4]:
            continue
        cnt[(v[3], v[4])][0] += v[2]
        cnt[(v[3], v[4])][1] += 1
        gl.append((v[3] - v[4], v[2]))
    train_stats[fmt] = (cnt, fit_logit_slope(gl))


def exp_win(fmt, a, b_):
    cnt, slope = train_stats[fmt]
    prior = 1 / (1 + math.exp(-slope * (a - b_)))
    w, n = cnt.get((a, b_), (0, 0))
    return (w + 25 * prior) / (n + 25)


data = {"EIGHT": [], "NINE": []}
for (fmt, mid), items in bymatch.items():
    m = mt.get(mid)
    if not m:
        continue
    home, away, hs, as_, scored, bye = m
    if not scored or bye or hs is None or as_ is None:
        continue
    day = items[0][7]
    if day < START:
        continue
    if len(items) != 10 or pm_count[mid].get(home) != 5 or pm_count[mid].get(away) != 5:
        continue
    side = defaultdict(lambda: [0, 0.0, 0])
    ok = True
    for p, o, pts, L, won, slp, slo, d in items:
        t = pt.get((p, mid))
        if t not in (home, away) or not slp or not slo:
            ok = False
            break
        s = side[t]
        s[0] += pts
        s[1] += exp_win(fmt, slp, slo)
        s[2] += slp
    if not ok or home not in side or away not in side:
        continue
    H, A = side[home], side[away]
    data[fmt].append(dict(day=day, hm3=H[0], am3=A[0], hexp=H[1], aexp=A[1], hsl=H[2], asl=A[2], hp=hs, ap=as_))


def auc(y, s):
    r = Series(s).rank().to_numpy()
    n1 = y.sum()
    n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def ols(X, y):
    X1 = np.c_[np.ones(len(X)), X]
    return np.linalg.lstsq(X1, y, rcond=None)[0]


def ols_pred(b, X):
    return np.c_[np.ones(len(X)), X] @ b


def logit(X, y, it=30):
    X1 = np.c_[np.ones(len(X)), X]
    b = np.zeros(X1.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X1 @ b))
        W = p * (1 - p) + 1e-9
        b = b + np.linalg.solve(X1.T @ (X1 * W[:, None]) + 1e-8 * np.eye(len(b)), X1.T @ (y - p))
    return b


def logit_p(b, X):
    return 1 / (1 + np.exp(-(np.c_[np.ones(len(X)), X] @ b)))


def ci(a):
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]


def pearson(x, y):
    if x.std() == 0 or y.std() == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x, y):
    return pearson(Series(x).rank().to_numpy(), Series(y).rank().to_numpy())


def r2(y, p):
    return 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def ll(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


out = {}
for fmt in ("EIGHT", "NINE"):
    D = data[fmt]
    tr = [d for d in D if d["day"] <= TRAIN_END]
    te = [d for d in D if d["day"] > TRAIN_END]

    def arr(L, k):
        return np.array([d[k] for d in L], float)

    def feats(L):
        return (arr(L, "hsl") - arr(L, "asl"), arr(L, "hexp") - arr(L, "aexp"), arr(L, "hm3") - arr(L, "am3"))

    R = {"n_train": len(tr), "n_test": len(te)}

    def teamlevel(L):
        m3 = np.r_[arr(L, "hm3"), arr(L, "am3")]
        pts = np.r_[arr(L, "hp"), arr(L, "ap")]
        win = np.r_[(arr(L, "hp") > arr(L, "ap")), (arr(L, "ap") > arr(L, "hp"))].astype(float)
        tie = np.r_[(arr(L, "hp") == arr(L, "ap")), (arr(L, "hp") == arr(L, "ap"))]
        return m3, pts, win, tie

    for label, L in (("test", te), ("train", tr)):
        m3, pts, win, tie = teamlevel(L)
        keep = ~tie
        q = {"m3_mean": float(m3.mean()), "m3_sd": float(m3.std()),
             "r_points": pearson(m3, pts), "rho_points": spearman(m3, pts),
             "r_win": pearson(m3[keep], win[keep]), "rho_win": spearman(m3[keep], win[keep])}
        rp, rw = [], []
        n = len(L)
        for _ in range(B if label == "test" else 200):
            s = rng.integers(0, n, n)
            ii = np.r_[s, s + n]
            x, y, w, t = m3[ii], pts[ii], win[ii], tie[ii]
            rp.append(pearson(x, y))
            k = ~t
            rw.append(pearson(x[k], w[k]))
        q["r_points_ci"] = ci(rp)
        q["r_win_ci"] = ci(rw)
        if label == "test":
            qs = np.quantile(m3, [1 / 3, 2 / 3])
            ter = np.digitize(m3, qs)
            q["tercile_cuts"] = [float(x) for x in qs]
            q["win_rate_by_m3_tercile"] = [float(win[keep & (ter == t)].mean()) for t in range(3)]
            q["mean_points_by_m3_tercile"] = [float(pts[ter == t].mean()) for t in range(3)]
        R["team_" + label] = q

    sl, ex, m3d = feats(tr)
    tsl, tex, tm3 = feats(te)
    ypd_tr = arr(tr, "hp") - arr(tr, "ap")
    ypd_te = arr(te, "hp") - arr(te, "ap")
    sd_m3 = m3d.std()
    Xs_tr = np.c_[sl, ex]
    Xs_te = np.c_[tsl, tex]
    Xf_tr = np.c_[sl, ex, m3d / sd_m3]
    Xf_te = np.c_[tsl, tex, tm3 / sd_m3]
    bs = ols(Xs_tr, ypd_tr)
    bf = ols(Xf_tr, ypd_tr)
    dr2 = r2(ypd_te, ols_pred(bf, Xf_te)) - r2(ypd_te, ols_pred(bs, Xs_te))
    wk_tr = ypd_tr != 0
    wk_te = ypd_te != 0
    ywin_tr = (ypd_tr > 0)[wk_tr].astype(float)
    ywin_te = (ypd_te > 0)[wk_te].astype(float)
    ls = logit(Xs_tr[wk_tr], ywin_tr)
    lf = logit(Xf_tr[wk_tr], ywin_tr)
    ps, pf = logit_p(ls, Xs_te[wk_te]), logit_p(lf, Xf_te[wk_te])
    d_auc = auc(ywin_te, pf) - auc(ywin_te, ps)
    d_ll = ll(ywin_te, ps) - ll(ywin_te, pf)
    bd_r2, bd_auc, bd_ll, bc_pts, bc_win = [], [], [], [], []
    n = len(te)
    for _ in range(B):
        s = rng.integers(0, n, n)
        y = ypd_te[s]
        bd_r2.append(r2(y, ols_pred(bf, Xf_te[s])) - r2(y, ols_pred(bs, Xs_te[s])))
        w = wk_te[s]
        yw = (y > 0)[w].astype(float)
        bd_auc.append(auc(yw, logit_p(lf, Xf_te[s][w])) - auc(yw, logit_p(ls, Xs_te[s][w])))
        bd_ll.append(ll(yw, logit_p(ls, Xs_te[s][w])) - ll(yw, logit_p(lf, Xf_te[s][w])))
        Xb = np.c_[tsl[s], tex[s], tm3[s] / sd_m3]
        bc_pts.append(ols(Xb, y)[3])
        bc_win.append(logit(Xb[w], yw, 15)[3])
    Xt = np.c_[tsl, tex, tm3 / sd_m3]
    full_pts = ols(Xt, ypd_te)
    full_win = logit(Xt[wk_te], ywin_te)
    R["adjusted"] = {
        "sd_dm3_train": float(sd_m3), "test_dm3_sd": float(tm3.std()),
        "share_dm3_zero": float((tm3 == 0).mean()),
        "coef_points_per_sd_m3": float(full_pts[3]), "coef_points_ci": ci(bc_pts),
        "coef_logit_win_per_sd_m3": float(full_win[3]), "coef_logit_win_ci": ci(bc_win),
        "train_coef_points_per_sd": float(bf[3]), "train_coef_logit_per_sd": float(lf[3]),
        "dR2": float(dr2), "dR2_ci": ci(bd_r2), "dAUC": float(d_auc), "dAUC_ci": ci(bd_auc),
        "dLogLoss_gain": float(d_ll), "dLogLoss_ci": ci(bd_ll),
        "auc_skill_only": float(auc(ywin_te, ps)), "auc_with_m3": float(auc(ywin_te, pf)),
        "r2_skill_only": float(r2(ypd_te, ols_pred(bs, Xs_te))), "r2_with_m3": float(r2(ypd_te, ols_pred(bf, Xf_te))),
        "r_dm3_vs_pointsdiff": pearson(tm3, ypd_te), "r_dslsum_vs_pointsdiff": pearson(tsl, ypd_te),
        "r_dexp_vs_pointsdiff": pearson(tex, ypd_te),
        "r_dm3_vs_dslsum": pearson(tm3, tsl), "r_dm3_vs_dexp": pearson(tm3, tex),
    }
    sub = np.abs(tm3) >= 3
    if sub.sum() > 50:
        ys = ypd_te[sub]
        ms = tm3[sub]
        pos = ys[(ms > 0) & (ys != 0)]
        neg = ys[(ms < 0) & (ys != 0)]
        R["subset_absdm3_ge3"] = {"n": int(sub.sum()), "r_dm3_pointsdiff": pearson(ms, ys),
                                  "home_win_rate_dm3_pos": float((pos > 0).mean()), "n_pos": int(len(pos)),
                                  "home_win_rate_dm3_neg": float((neg > 0).mean()), "n_neg": int(len(neg))}
    yh = np.where(ypd_te > 0, 1.0, np.where(ypd_te == 0, 0.5, 0.0))
    R["tie_share_test"] = float((ypd_te == 0).mean())
    R["r_dm3_halfwin"] = pearson(tm3, yh)
    lv = defaultdict(int)
    for (f, mid, p, o), v in lvl.items():
        if f == fmt and v[5] > TRAIN_END:
            lv[v[1]] += 1
    tot = sum(lv.values())
    R["level_mix_test"] = {k: round(c / tot, 3) for k, c in lv.items()}
    R["by_dm3_bin"] = []
    for lo, hi in [(-99, -6), (-5, -1), (0, 0), (1, 5), (6, 99)]:
        k = (tm3 >= lo) & (tm3 <= hi)
        if k.sum() >= 20:
            kk = k & wk_te
            R["by_dm3_bin"].append({"bin": f"{lo}..{hi}", "n": int(k.sum()), "mean_home_pts_diff": float(ypd_te[k].mean()),
                                    "home_win_rate": float((ypd_te[kk] > 0).mean())})
    out[fmt] = R
Path("results.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=1))
