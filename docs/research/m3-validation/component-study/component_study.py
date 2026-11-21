"""M3 component study. Read-only. See PREREGISTRATION.md."""
import sys, json, sqlite3, math, hashlib
from collections import defaultdict, deque
from pathlib import Path
import numpy as np
from pandas import Series
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_common as _rc
DB, OUT = _rc.setup(__doc__)
from analytics.ultimate_coach_confidence import pair_confidence, sl_changed_since_last_meeting
from replay_confidence_levels import FORMATS, local_day
sys.stdout.reconfigure(encoding="utf-8")
START, FIT_END, VAL_END = "2023-01-01", "2025-02-28", "2025-08-31"
B = 300
rng = np.random.default_rng(20261122)
LEVELS = ["Strong", "Solid", "Thin", "Unknown", "Conflicted", "Caution"]

con = sqlite3.connect(Path(DB).as_uri() + "?mode=ro", uri=True)
rows = con.execute("""SELECT h.player_id,h.opponent_id,h.result,h.own_skill_level,h.opponent_skill_level,h.format,m.match_date,h.match_id
  FROM player_head_to_head h JOIN matches m ON m.id=h.match_id WHERE h.result IN ('W','L')""").fetchall()
mt = {r[0]: r[1:3] for r in con.execute("SELECT id,home_team_id,away_team_id FROM matches")}
pt = {(r[0], r[1]): r[2] for r in con.execute("SELECT player_id,match_id,team_id FROM player_matches")}
games = defaultdict(list)
for p, o, res, slp, slo, fmt, day, mid in rows:
    if fmt in FORMATS and p != o:
        games[(FORMATS[fmt], local_day(day))].append((p, o, res == "W", slp, slo, mid))

for _k in games:
    games[_k].sort(key=lambda g: (str(g[5]), str(g[0]), str(g[1])))
pairs = defaultdict(dict); overall = defaultdict(lambda: [0, 0]); recent = defaultdict(lambda: deque(maxlen=10))
team = defaultdict(lambda: [0, 0])
FEATS = {"EIGHT": [], "NINE": []}


def sh(w, n, k=6): return (w + k / 2) / (n + k)


for (fmt, day), obs in sorted(games.items()):
    for p, o, won, slp, slo, mid in obs:
        if day < START or not slp or not slo:
            continue
        if (hashlib.md5(f"{mid}|{min(p,o)}|{max(p,o)}".encode()).digest()[0] & 1) != (1 if p < o else 0):
            continue  # one fixed orientation per game
        m = mt.get(mid)
        tp, to = pt.get((p, mid)), pt.get((o, mid))
        if not m or tp is None or to is None:
            continue
        mine, theirs = pairs[(fmt, p)], pairs[(fmt, o)]
        rec = mine.get(o)
        shared = None
        if rec is None:
            common = mine.keys() & theirs.keys() - {p, o}
            if common:
                shared = (sum(mine[x][0] for x in common), sum(mine[x][1] for x in common),
                          sum(theirs[x][0] for x in common), sum(theirs[x][1] for x in common), len(common))
        ch = sl_changed_since_last_meeting([{"sort": rec[2], "own_sl": rec[3], "opp_sl": rec[4]}] if rec else [], slp, slo)
        op, oo = overall[(fmt, p)], overall[(fmt, o)]
        lv = pair_confidence((rec[0], rec[1]) if rec else None, own_overall=tuple(op), opp_overall=tuple(oo), shared=shared, sl_changed=ch)["level"]
        dw, dg = (rec[0], rec[1]) if rec else (0, 0)
        rp, ro = recent[(fmt, p)], recent[(fmt, o)]
        tpp, too = team[(fmt, tp)], team[(fmt, to)]
        gap = max(-4, min(4, slp - slo))
        x = {
            "DIRECT": [sh(dw, dg, 2) - .5, math.log1p(dg), float(dg > 0)],
            "SKILL": [float(gap == k) for k in range(-4, 5)] + [float(slp)],
            "FORM_OVERALL": [sh(*op) - .5, sh(*oo) - .5, math.log1p(op[1]), math.log1p(oo[1])],
            "RECENT": [sh(sum(rp), len(rp)) - .5, sh(sum(ro), len(ro)) - .5],
            "SHARED": [(sh(shared[0], shared[1]) - sh(shared[2], shared[3])) if shared else 0.0, float(shared[4]) if shared else 0.0],
            "SLCHG": [float(bool(ch))],
            "HOME": [float(tp == m[0])],
            "TEAM": [sh(*tpp, 20) - .5, sh(*too, 20) - .5],
            "M3": [float(lv == L) for L in LEVELS],
        }
        FEATS[fmt].append((day, mid, int(won), x))
    for p, o, won, slp, slo, mid in obs:
        rec = pairs[(fmt, p)].setdefault(o, [0, 0, day, slp, slo]); rec[0] += int(won); rec[1] += 1; rec[2:] = [day, slp, slo]
        overall[(fmt, p)][0] += int(won); overall[(fmt, p)][1] += 1
        recent[(fmt, p)].append(int(won))
        tp = pt.get((p, mid))
        if tp is not None:
            team[(fmt, tp)][0] += int(won); team[(fmt, tp)][1] += 1

GROUPS = ["DIRECT", "SKILL", "FORM_OVERALL", "RECENT", "SHARED", "SLCHG", "HOME", "TEAM", "M3"]


def fit(X, y, lam, it=25):
    X1 = np.c_[np.ones(len(X)), X]; b = np.zeros(X1.shape[1]); pen = np.eye(len(b)) * lam; pen[0, 0] = 0
    for _ in range(it):
        p = 1 / (1 + np.exp(-X1 @ b)); W = p * (1 - p) + 1e-9
        b = b + np.linalg.solve(X1.T @ (X1 * W[:, None]) + pen, X1.T @ (y - p) - pen @ b)
    return b


def pred(b, X): return 1 / (1 + np.exp(-(np.c_[np.ones(len(X)), X] @ b)))
def ll_vec(y, p): p = np.clip(p, 1e-9, 1 - 1e-9); return -(y * np.log(p) + (1 - y) * np.log(1 - p))
def auc(y, s):
    r = Series(s).rank().to_numpy(); n1 = y.sum(); return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(y) - n1))


out = {}
for fmt in ("EIGHT", "NINE"):
    D = FEATS[fmt]
    days = np.array([d[0] for d in D]); mids = np.array([d[1] for d in D]); y = np.array([d[2] for d in D], float)
    cols, slices = [], {}
    pos = 0
    for g in GROUPS:
        arr = np.array([d[3][g] for d in D], float)
        slices[g] = (pos, pos + arr.shape[1]); pos += arr.shape[1]; cols.append(arr)
    X = np.hstack(cols)
    fi, va, te = days <= FIT_END, (days > FIT_END) & (days <= VAL_END), days > VAL_END
    tr = fi | va
    R = {"n_fit": int(fi.sum()), "n_val": int(va.sum()), "n_test": int(te.sum()), "test_base_rate": float(y[te].mean())}

    def cols_of(gs): return np.concatenate([np.arange(*slices[g]) for g in gs])

    def run(gs, train_mask, eval_mask, lam=None):
        c = cols_of(gs); mu = X[train_mask][:, c].mean(0); sd = X[train_mask][:, c].std(0) + 1e-9
        Z = (X[:, c] - mu) / sd
        if lam is None:
            best = None
            for l in (1, 30, 300, 3000):
                b = fit(Z[fi], y[fi], l); v = ll_vec(y[va], pred(b, Z[va])).mean()
                if best is None or v < best[0]: best = (v, l)
            lam = best[1]
        b = fit(Z[train_mask], y[train_mask], lam)
        return b, Z, lam, c, mu, sd

    base = ll_vec(y[te], np.full(te.sum(), y[tr].mean()))
    R["base_rate_logloss_test"] = float(base.mean())
    full_b, Zf, lam_f, cf, muf, sdf = run(GROUPS, tr, te)
    pf = pred(full_b, Zf[te]); lf = ll_vec(y[te], pf)
    R["full"] = {"logloss": float(lf.mean()), "auc": float(auc(y[te], pf)), "acc": float(((pf > .5) == y[te]).mean()), "lambda": lam_f}
    mid_te = mids[te]; uniq, inv = np.unique(mid_te, return_inverse=True)
    def clus(v):  # per-match sums for cluster bootstrap
        return np.bincount(inv, weights=v, minlength=len(uniq)), np.bincount(inv, minlength=len(uniq)).astype(float)
    def boot(v):
        s, n = clus(v); out_ = []
        for _ in range(B):
            k = rng.integers(0, len(uniq), len(uniq)); out_.append(s[k].sum() / n[k].sum())
        return [float(np.percentile(out_, 2.5)), float(np.percentile(out_, 97.5))]
    R["full"]["gain_vs_base"] = float(base.mean() - lf.mean()); R["full"]["gain_vs_base_ci"] = boot(base - lf)
    # single group, drop-one, permutation, mean |SHAP|
    R["groups"] = {}
    for g in GROUPS:
        b1, Z1, _, _, _, _ = run([g], tr, te); p1 = pred(b1, Z1[te]); l1 = ll_vec(y[te], p1)
        rest = [x for x in GROUPS if x != g]
        b2, Z2, _, _, _, _ = run(rest, tr, te); l2 = ll_vec(y[te], pred(b2, Z2[te]))
        # permutation
        c = np.arange(*slices[g]); pidx = []
        perm_inc = []
        for _ in range(5):
            Zp = Zf[te].copy(); sel = np.concatenate([np.arange(*slices[g])])
            idx = rng.permutation(te.sum()); Zp[:, sel] = Zp[idx][:, sel]
            perm_inc.append(ll_vec(y[te], pred(full_b, Zp)).mean() - lf.mean())
        shap = np.abs(Zf[te][:, sel] * full_b[1:][sel][None, :])  # contribution; centred below
        shap = np.abs((Zf[te][:, sel] - Zf[te][:, sel].mean(0)) * full_b[1:][sel][None, :]).sum(1).mean()
        R["groups"][g] = {"single_gain_vs_base": float(base.mean() - l1.mean()), "single_gain_ci": boot(base - l1),
                          "single_auc": float(auc(y[te], p1)),
                          "drop_one_loss_increase": float(l2.mean() - lf.mean()), "drop_one_ci": boot(l2 - lf),
                          "perm_importance": float(np.mean(perm_inc)), "mean_abs_shap_sum": float(shap)}
    # M3 alone vs skill alone vs full
    for name, gs in (("M3_only", ["M3"]), ("SKILL_only", ["SKILL"]), ("SKILL+M3", ["SKILL", "M3"]), ("full_without_M3", [g for g in GROUPS if g != "M3"])):
        b_, Z_, _, _, _, _ = run(gs, tr, te); p_ = pred(b_, Z_[te]); l_ = ll_vec(y[te], p_)
        R[name] = {"logloss": float(l_.mean()), "auc": float(auc(y[te], p_)), "loss_minus_full": float(l_.mean() - lf.mean()), "ci_loss_minus_full": boot(l_ - lf)}
    # greedy forward selection on validation (fit on fi only), evaluate once on test
    chosen, cur = [], float(ll_vec(y[va], np.full(va.sum(), y[fi].mean())).mean())
    while True:
        best = None
        for g in GROUPS:
            if g in chosen: continue
            c = cols_of(chosen + [g]); mu = X[fi][:, c].mean(0); sd = X[fi][:, c].std(0) + 1e-9; Z = (X[:, c] - mu) / sd
            b = fit(Z[fi], y[fi], lam_f); v = ll_vec(y[va], pred(b, Z[va])).mean()
            if best is None or v < best[0]: best = (v, g)
        if best is None or cur - best[0] < 0.0002: break
        chosen.append(best[1]); cur = best[0]
    b_, Z_, _, _, _, _ = run(chosen, tr, te, lam_f); p_ = pred(b_, Z_[te]); l_ = ll_vec(y[te], p_)
    R["selected_groups_in_order"] = chosen
    R["selected"] = {"logloss": float(l_.mean()), "auc": float(auc(y[te], p_)), "loss_minus_full": float(l_.mean() - lf.mean()), "ci": boot(l_ - lf)}
    # non-M3 coefficients of key terms (standardised), full model
    names = []
    for g in GROUPS: names += [f"{g}[{i}]" for i in range(slices[g][1] - slices[g][0])]
    R["full_standardised_coefs"] = {n: float(c) for n, c in zip(names, full_b[1:])}
    out[fmt] = R
(OUT / "results.json").write_text(json.dumps(out, indent=2))
for fmt in out:
    R = out[fmt]; print(fmt, R["n_test"], "base", round(R["base_rate_logloss_test"], 5), "full", R["full"])
    for g, v in R["groups"].items(): print("  ", g, {k: (round(x, 5) if isinstance(x, float) else x) for k, x in v.items()})
    for k in ("M3_only", "SKILL_only", "SKILL+M3", "full_without_M3", "selected_groups_in_order", "selected"): print("  ", k, R[k])
