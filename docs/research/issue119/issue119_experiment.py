"""Issue #119: does APA skill level add evidence beyond M3's confidence levels?

One deterministic, read-only experiment over a local archive snapshot. No production code is changed or
called with side effects; M3 itself (analytics.match_night_engine, analytics.ultimate_coach_confidence) is
imported unchanged. Writes results_<policy>.json (aggregates only, no player identifiers) to --out.

Sections: data quality; record policy; pre-match skill-level check; chronological replay (strictly earlier
dates); skill-pair outcome tables; Unknown-vs-Caution; main split backtest of models A/B/C1/C2 with bootstrap
intervals; independent re-estimation of A and B; leakage probe; rolling-origin validation; night-level outcomes;
game-one planner comparison (model-dependent); decision changes; explainability metrics.

Usage: python -I issue119_experiment.py --db <archive_snapshot.sqlite> --out <dir> [--policy clean|dedup|raw]
"""
import hashlib, json, math, sqlite3, sys
from collections import defaultdict, deque, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_common as _rc  # noqa: E402
DB, OUT, POLICY, SNAP = _rc.setup(__doc__)
import numpy as np  # noqa: E402
from pandas import Series  # noqa: E402
from analytics.ultimate_coach_confidence import pair_confidence, sl_changed_since_last_meeting, LEVEL_POINTS, FORM_MIN_GAMES  # noqa: E402
from analytics.match_night_engine import _Night  # noqa: E402
from replay_confidence_levels import FORMATS, local_day  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
EVAL_END, START, FIT_END, VAL_END = "2022-12-31", "2023-01-01", "2025-02-28", "2025-08-31"
ROLL_BLOCKS = [("2024-03-01", "2024-08-31"), ("2024-09-01", "2025-02-28"), ("2025-03-01", "2025-08-31"),
               ("2025-09-01", "2026-02-28"), ("2026-03-01", "2026-12-31")]
LEVELS = ["Strong", "Solid", "Thin", "Unknown", "Conflicted", "Caution"]
B = 300
rng = np.random.default_rng(20261122)
R = {"policy": POLICY, "snapshot": SNAP}

con = sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True)
raw = con.execute("""SELECT h.player_id,h.opponent_id,h.result,h.own_skill_level,h.opponent_skill_level,h.format,m.match_date,h.match_id
  FROM player_head_to_head h JOIN matches m ON m.id=h.match_id ORDER BY h.rowid""").fetchall()
mt = {r[0]: r[1:] for r in con.execute("SELECT id,home_team_id,away_team_id,home_score,away_score,is_scored,is_bye FROM matches")}
pt = {(r[0], r[1]): r[2] for r in con.execute("SELECT player_id,match_id,team_id FROM player_matches")}


def wilson(w, n, z=1.96):
    if not n:
        return [None, None]
    p = w / n; d = 1 + z * z / n; c = p + z * z / (2 * n); a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - a) / d, 4), round((c + a) / d, 4)]


# ======================= 1. data quality and record policy =======================
by_key = defaultdict(list)
for r in raw:
    by_key[(r[7], r[0], r[1])].append(r)
identical = {k for k, v in by_key.items() if len(v) > 1 and len({(x[2], x[3], x[4]) for x in v}) == 1}
conflicting = {k for k, v in by_key.items() if len(v) > 1 and k not in identical}
first = {k: v[0] for k, v in by_key.items()}
mirror = Counter()
for (m, p, o), r in first.items():
    if r[2] not in ("W", "L"):
        mirror["no_result"] += 1; continue
    q = first.get((m, o, p))
    if q is None:
        mirror["no_mirror_row"] += 1
    elif q[2] == r[2]:
        mirror["mirror_same_result"] += 1
    elif (q[3], q[4]) != (r[4], r[3]):
        mirror["mirror_skill_mismatch"] += 1
rows_per_match = Counter(Counter(r[7] for r in raw if r[2] in ("W", "L") and r[5] in FORMATS).values())
R["quality"] = {"rows": len(raw), "duplicate_keys_identical": len(identical), "duplicate_keys_conflicting": len(conflicting),
                "mirror_checks": dict(mirror), "decided_rows_per_match": dict(rows_per_match),
                "rows_missing_skill_level": sum(1 for r in raw if r[2] in ("W", "L") and (not r[3] or not r[4])),
                "self_pairs": sum(1 for r in raw if r[0] == r[1])}
kept, seen = [], set()
for r in raw:
    k = (r[7], r[0], r[1])
    if POLICY == "clean" and k in conflicting:
        continue
    if POLICY in ("dedup", "clean") and k in identical:
        if k in seen:
            continue
        seen.add(k)
    kept.append(r)
R["quality"]["rows_kept"] = len(kept)

# ======================= 2. pre-match skill-level check =======================
# If a match's recorded level were set AFTER that match, a win in that match would line up with a rise recorded
# on the same match. If it is the level played at, a win precedes a rise on the NEXT match.
seq = defaultdict(list)
for p, o, res, slp, slo, fmt, day, mid in kept:
    if res in ("W", "L") and fmt in FORMATS and slp:
        seq[(FORMATS[fmt], p)].append((local_day(day), str(mid), slp, res == "W"))
pm = {}
for fmt in ("EIGHT", "NINE"):
    c = {"same": [[0, 0], [0, 0]], "next": [[0, 0], [0, 0]]}   # [won][rise] counts
    for (f, p), s in seq.items():
        if f != fmt:
            continue
        s.sort()
        for i in range(1, len(s) - 1):
            won = int(s[i][3])
            c["same"][won][int(s[i][2] > s[i - 1][2])] += 1
            c["next"][won][int(s[i + 1][2] > s[i][2])] += 1
    def rates(t):
        return {"rise_rate_after_loss": round(t[0][1] / max(1, sum(t[0])), 5), "rise_rate_after_win": round(t[1][1] / max(1, sum(t[1])), 5),
                "n_losses": sum(t[0]), "n_wins": sum(t[1])}
    pm[fmt] = {"rise_recorded_on_the_same_match": rates(c["same"]), "rise_recorded_on_the_next_match": rates(c["next"])}
R["prematch_skill_check"] = pm

# ======================= 3. chronological replay =======================
games = defaultdict(list)
for p, o, res, slp, slo, fmt, day, mid in kept:
    if res in ("W", "L") and fmt in FORMATS and p != o:
        games[(FORMATS[fmt], local_day(day))].append((p, o, res == "W", slp, slo, mid))
for k in games:
    games[k].sort(key=lambda g: (str(g[5]), str(g[0]), str(g[1])))


def sh(w, n, k=6):
    return (w + k / 2) / (n + k)


pairs = defaultdict(dict); overall = defaultdict(lambda: [0, 0]); recent = defaultdict(lambda: deque(maxlen=10))


def features(fmt, p, o, slp, slo):
    mine, theirs = pairs[(fmt, p)], pairs[(fmt, o)]
    rec = mine.get(o); shared = None
    if rec is None:
        common = mine.keys() & theirs.keys() - {p, o}
        if common:
            shared = (sum(mine[x][0] for x in common), sum(mine[x][1] for x in common),
                      sum(theirs[x][0] for x in common), sum(theirs[x][1] for x in common), len(common))
    ch = sl_changed_since_last_meeting([{"sort": rec[2], "own_sl": rec[3], "opp_sl": rec[4]}] if rec else [], slp, slo)
    op, oo = tuple(overall[(fmt, p)]), tuple(overall[(fmt, o)])
    lv = pair_confidence((rec[0], rec[1]) if rec else None, own_overall=op, opp_overall=oo, shared=shared, sl_changed=ch)["level"]
    thresh = lv == "Unknown" and rec is None and (op[1] < FORM_MIN_GAMES or oo[1] < FORM_MIN_GAMES)
    dw, dg = (rec[0], rec[1]) if rec else (0, 0)
    rp, ro = recent[(fmt, p)], recent[(fmt, o)]
    x = {"M3": [float(lv == L) for L in LEVELS],
         "SLPAIR": [float(slp == a and slo == b) for a in range(1, 10) for b in range(1, 10)],
         "DIRECT": [sh(dw, dg, 2) - .5, math.log1p(dg), float(dg > 0)],
         "SHARED": [(sh(shared[0], shared[1]) - sh(shared[2], shared[3])) if shared else 0.0, float(shared[4]) if shared else 0.0],
         "RECENT": [sh(sum(rp), len(rp)) - .5, sh(sum(ro), len(ro)) - .5],
         "FORM": [sh(*op) - .5, sh(*oo) - .5, math.log1p(op[1]), math.log1p(oo[1])]}
    return x, {"lv": lv, "thresh": thresh, "op": op, "oo": oo, "dw": dw, "dg": dg, "rp": (sum(rp), len(rp))}


FEATS = {"EIGHT": [], "NINE": []}
NIGHTS = {"EIGHT": [], "NINE": []}
gap_tab = defaultdict(lambda: [0, 0])
for (fmt, day), obs in sorted(games.items()):
    bym = defaultdict(list)
    for g in obs:
        bym[g[5]].append(g)
    if day > VAL_END:
        for mid, gl in bym.items():
            m = mt.get(mid)
            if not m or len(gl) != 10 or not m[4] or m[5]:
                continue
            home, away = m[0], m[1]
            sl = {g[0]: g[3] for g in gl}
            hp = sorted({g[0] for g in gl if pt.get((g[0], mid)) == home}); ap = sorted({g[0] for g in gl if pt.get((g[0], mid)) == away})
            if len(hp) != 5 or len(ap) != 5 or any(not sl.get(x) for x in hp + ap):
                continue
            NIGHTS[fmt].append({"hp": hp, "ap": ap, "sl": {x: sl[x] for x in hp + ap},
                                "cross": {(h, a): features(fmt, h, a, sl[h], sl[a]) for h in hp for a in ap},
                                "realized": [(g[0], g[1], int(g[2])) for g in gl if g[0] in hp], "hs": m[2], "as": m[3]})
    for p, o, won, slp, slo, mid in obs:
        if (hashlib.md5(f"{mid}|{min(p,o)}|{max(p,o)}".encode()).digest()[0] & 1) != (1 if p < o else 0):
            continue
        if not slp or not slo:
            continue
        x, meta = features(fmt, p, o, slp, slo)
        if slp != slo:
            lowp, lowo, lw = (slp, slo, won) if slp < slo else (slo, slp, not won)
            low_games = meta["op"][1] if slp < slo else meta["oo"][1]
            for scope in ("all", "lt20" if low_games < FORM_MIN_GAMES else "ge20", "2023+" if day >= START else "pre2023"):
                t = gap_tab[(fmt, scope, lowp, lowo)]; t[0] += int(lw); t[1] += 1
        if day >= "2012-01-01":
            FEATS[fmt].append(dict(day=day, mid=mid, p=p, o=o, won=int(won), x=x, slp=slp, slo=slo, **meta))
    for p, o, won, slp, slo, mid in obs:
        rec = pairs[(fmt, p)].setdefault(o, [0, 0, day, slp, slo]); rec[0] += int(won); rec[1] += 1; rec[2:] = [day, slp, slo]
        overall[(fmt, p)][0] += int(won); overall[(fmt, p)][1] += 1
        recent[(fmt, p)].append(int(won))
R["coverage"] = {f: {"games_modelled_since_2012": len(FEATS[f]), "test_nights_5v5": len(NIGHTS[f])} for f in FEATS}
R["sl_tables"] = {f: [{"scope": s, "lower_sl": lo, "higher_sl": hi, "lower_wins": w, "games": n, "rate": round(w / n, 4), "ci": wilson(w, n)}
                      for (ff, s, lo, hi), (w, n) in sorted(gap_tab.items()) if ff == f and n >= 20] for f in ("EIGHT", "NINE")}

# ======================= 4. Unknown vs Caution =======================
R["unknown_vs_caution"] = {}
for fmt in ("EIGHT", "NINE"):
    tab = defaultdict(lambda: [0, 0]); unk = unk_t = 0
    for d in FEATS[fmt]:
        if d["day"] < START:
            continue
        if d["lv"] == "Unknown":
            unk += 1; unk_t += int(d["thresh"])
        g = d["slp"] - d["slo"]
        if g >= 0:
            continue
        gb = "-1" if g == -1 else "-2" if g == -2 else "<=-3"
        if d["lv"] == "Unknown" and d["thresh"] and d["op"][1] < FORM_MIN_GAMES:
            key = "Unknown_own_lt20"
        elif d["lv"] == "Caution" and d["op"][1] >= 20 and d["oo"][1] >= 20 and d["dg"] == 0:
            key = "Caution_no_direct_both_ge20"
        else:
            continue
        t = tab[(gb, key)]; t[0] += d["won"]; t[1] += 1
    R["unknown_vs_caution"][fmt] = {"unknown_pairings": unk, "share_unknown_from_20_game_rule": round(unk_t / max(1, unk), 4),
                                    "rows": [{"gap": k[0], "group": k[1], "wins": w, "games": n, "rate": round(w / n, 4), "ci": wilson(w, n)}
                                             for k, (w, n) in sorted(tab.items())]}


# ======================= 5. models =======================
def fit(X, y, lam, it=25):
    X1 = np.c_[np.ones(len(X)), X]; b = np.zeros(X1.shape[1]); pen = np.eye(len(b)) * lam; pen[0, 0] = 0
    for _ in range(it):
        p = 1 / (1 + np.exp(-X1 @ b)); W = p * (1 - p) + 1e-9
        b = b + np.linalg.solve(X1.T @ (X1 * W[:, None]) + pen, X1.T @ (y - p) - pen @ b)
    return b


def llv(y, p):
    p = np.clip(p, 1e-9, 1 - 1e-9); return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def auc(y, s):
    y = np.asarray(y, float)
    if y.sum() in (0, len(y)):
        return None
    r = Series(s).rank().to_numpy(); n1 = y.sum(); return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(y) - n1)))


def calib(y, p):
    z = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1)); b = fit(z[:, None], y, 0.0, 30)
    bins = np.minimum((p * 10).astype(int), 9)
    ece = sum((bins == k).mean() * abs(y[bins == k].mean() - p[bins == k].mean()) for k in range(10) if (bins == k).any())
    return float(b[0]), float(b[1]), float(ece)


MODELS = {"A_M3": ["M3"], "B_SKILL": ["SLPAIR"], "C1_M3+SKILL": ["M3", "SLPAIR"], "C2_SKILL+EVIDENCE": ["SLPAIR", "DIRECT", "SHARED", "RECENT", "FORM"]}


class Fitted:
    def __init__(self, gs, D, fit_mask, val_mask, train_mask, y):
        self.gs = gs
        X = np.hstack([np.array([d["x"][g] for d in D], float) for g in gs])
        self.keep = X[train_mask].std(0) > 0
        X = X[:, self.keep]; self.mu, self.sd = X[train_mask].mean(0), X[train_mask].std(0)
        Z = (X - self.mu) / self.sd
        best = None
        for lam in (0.1, 1, 10, 100, 1000):
            v = llv(y[val_mask], self._p(fit(Z[fit_mask], y[fit_mask], lam), Z[val_mask])).mean()
            if best is None or v < best[0]:
                best = (v, lam)
        self.lam = best[1]; self.b = fit(Z[train_mask], y[train_mask], self.lam)

    @staticmethod
    def _p(b, Z):
        return 1 / (1 + np.exp(-(np.c_[np.ones(len(Z)), Z] @ b)))

    def predict_x(self, xs):
        X = np.hstack([np.array([x[g] for x in xs], float) for g in self.gs])[:, self.keep]
        return self._p(self.b, (X - self.mu) / self.sd)


def cluster_boot(v, mids, nb=B):
    uniq, inv = np.unique(mids, return_inverse=True)
    s = np.bincount(inv, weights=v, minlength=len(uniq)); n = np.bincount(inv, minlength=len(uniq)).astype(float)
    o = [s[k].sum() / n[k].sum() for k in (rng.integers(0, len(uniq), len(uniq)) for _ in range(nb))]
    return [float(np.percentile(o, 2.5)), float(np.percentile(o, 97.5))]


def evaluate(D, fi, va, tr, te, y, mids, nb=B):
    fitted = {n: Fitted(gs, D, fi, va, tr, y) for n, gs in MODELS.items()}
    xs = [D[i]["x"] for i in np.where(te)[0]]
    preds = {n: f.predict_x(xs) for n, f in fitted.items()}
    yt = y[te]; lA = llv(yt, preds["A_M3"]); out = {"n_train": int(tr.sum()), "n_test": int(te.sum())}
    for n, p in preds.items():
        l = llv(yt, p); ci, cs, ece = calib(yt, p)
        out[n] = {"logloss": float(l.mean()), "brier": float(((p - yt) ** 2).mean()), "auc": auc(yt, p),
                  "calib_intercept": ci, "calib_slope": cs, "ece": ece,
                  "gain_vs_A": float((lA - l).mean()), "gain_vs_A_ci": cluster_boot(lA - l, mids[te], nb)}
    return fitted, preds, out


R["main"] = {}; R["independent"] = {}; R["leakage_probe"] = {}; R["rolling"] = {}; R["subgroups"] = {}
R["nights"] = {}; R["planner"] = {}; R["decisions"] = {}; R["explain"] = {}
for fmt in ("EIGHT", "NINE"):
    D = FEATS[fmt]
    days = np.array([d["day"] for d in D]); y = np.array([d["won"] for d in D], float); mids = np.array([d["mid"] for d in D])
    fi = (days >= START) & (days <= FIT_END); va = (days > FIT_END) & (days <= VAL_END); tr = (days >= START) & (days <= VAL_END); te = days > VAL_END
    fitted, preds, out = evaluate(D, fi, va, tr, te, y, mids)
    R["main"][fmt] = out
    yt = y[te]; T = [D[i] for i in np.where(te)[0]]
    # subgroups
    gap = np.array([d["slp"] - d["slo"] for d in T]); og = np.array([d["op"][1] for d in T]); tg = np.array([d["oo"][1] for d in T])
    lvl = np.array([d["lv"] for d in T]); slo = np.array([d["slo"] for d in T]); slp = np.array([d["slp"] for d in T])
    subs = {"gap<=-3": gap <= -3, "gap=-2": gap == -2, "gap=-1": gap == -1, "gap=0": gap == 0, "gap=+1": gap == 1, "gap=+2": gap == 2,
            "gap>=+3": gap >= 3, "either_lt20_games": (og < 20) | (tg < 20), "level_Unknown": lvl == "Unknown", "lower_vs_SL7": (slo == 7) & (slp < 7)}
    R["subgroups"][fmt] = {k: {"n": int(s.sum()), "actual": float(yt[s].mean()),
                               **{n: {"mean_pred": float(preds[n][s].mean()), "logloss": float(llv(yt[s], preds[n][s]).mean())} for n in MODELS}}
                           for k, s in subs.items() if s.sum() >= 30}
    # independent re-estimation (plain empirical rates)
    def empirical(keyf, alpha=10):
        c = defaultdict(lambda: [0, 0]); base = y[tr].mean()
        for i in np.where(tr)[0]:
            k = keyf(D[i]); c[k][0] += y[i]; c[k][1] += 1
        return np.array([(c[keyf(d)][0] + alpha * base) / (c[keyf(d)][1] + alpha) for d in T])
    R["independent"][fmt] = {"A_empirical_logloss": float(llv(yt, empirical(lambda d: d["lv"])).mean()),
                             "B_empirical_logloss": float(llv(yt, empirical(lambda d: (d["slp"], d["slo"]))).mean()),
                             "A_logistic_logloss": out["A_M3"]["logloss"], "B_logistic_logloss": out["B_SKILL"]["logloss"]}
    # leakage probe: recompute features for sampled test games directly from kept rows dated before the game
    hist = defaultdict(list)
    for (f2, day), obs in sorted(games.items()):
        if f2 == fmt:
            for p, o, won, a_, b_, mid in obs:
                hist[p].append((day, o, int(won)))
    mism = Counter()
    for i in rng.choice(len(T), size=min(400, len(T)), replace=False):
        d = T[i]
        bp = [h for h in hist[d["p"]] if h[0] < d["day"]]; bo = [h for h in hist[d["o"]] if h[0] < d["day"]]
        mism["own_overall"] += (sum(h[2] for h in bp), len(bp)) != tuple(d["op"])
        mism["opp_overall"] += (sum(h[2] for h in bo), len(bo)) != tuple(d["oo"])
        dr = [h for h in bp if h[1] == d["o"]]
        mism["direct"] += (sum(h[2] for h in dr), len(dr)) != (d["dw"], d["dg"])
        mism["recent10"] += (sum(h[2] for h in bp[-10:]), len(bp[-10:])) != tuple(d["rp"])
    R["leakage_probe"][fmt] = {"sampled": min(400, len(T)), "mismatches": {k: int(v) for k, v in mism.items()},
                               "matches_in_train_and_test": len({d["mid"] for d in D if START <= d["day"] <= VAL_END} & {d["mid"] for d in T}),
                               "latest_train_day": max(d["day"] for d in D if d["day"] <= VAL_END), "earliest_test_day": min(d["day"] for d in T)}
    # rolling-origin validation: 3-year training window ending at each block, last 6 months for the penalty choice
    roll = []
    for b0, b1 in ROLL_BLOCKS:
        y0 = str(int(b0[:4]) - 3) + b0[4:]
        trm = (days >= y0) & (days < b0); vstart = str(int(b0[:4]) - (1 if b0[5:7] <= "06" else 0)) + ("-09-01" if b0[5:7] <= "06" else "-03-01")
        fim = trm & (days < vstart); vam = trm & (days >= vstart); tem = (days >= b0) & (days <= b1)
        if tem.sum() < 500:
            continue
        _, _, o = evaluate(D, fim, vam, trm, tem, y, mids, nb=200)
        roll.append({"test_from": b0, "test_to": b1, "train_from": y0, **{k: (v if not isinstance(v, dict) else
                     {kk: v[kk] for kk in ("logloss", "auc", "brier", "gain_vs_A", "gain_vs_A_ci")}) for k, v in o.items()}})
    R["rolling"][fmt] = roll

    # night-level outcomes (realized boards)
    rows = []
    for nt in NIGHTS[fmt]:
        if nt["hs"] is None or nt["as"] is None:
            continue
        xs = [nt["cross"][(h, a)][0] for h, a, _ in nt["realized"]]
        rows.append((sum(w for _, _, w in nt["realized"]), {n: float(f.predict_x(xs).sum()) for n, f in fitted.items()},
                     1.0 if nt["hs"] > nt["as"] else 0.0 if nt["hs"] < nt["as"] else 0.5))
    act = np.array([r[0] for r in rows], float); wn = np.array([r[2] for r in rows]); dec = wn != 0.5
    R["nights"][fmt] = {"nights": len(rows), **{n: {"r_expected_vs_actual_games": float(np.corrcoef([r[1][n] for r in rows], act)[0, 1]),
                                                     "night_win_auc": auc(wn[dec], np.array([r[1][n] for r in rows])[dec])} for n in MODELS}}

    # planner comparison (model-dependent) and decision changes, game-one answer to their top player
    ev = (days >= "2013-01-01") & (days <= EVAL_END)
    evaluators = {"pre2023_C2": Fitted(MODELS["C2_SKILL+EVIDENCE"], D, ev & (days <= "2021-12-31"), ev & (days > "2021-12-31"), ev, y),
                  "pre2023_skill": Fitted(MODELS["B_SKILL"], D, ev & (days <= "2021-12-31"), ev & (days > "2021-12-31"), ev, y)}
    gains = {k: [] for k in evaluators}; n_ok = differ = m3_direct = m3_thr = c2_direct = 0; m3m, c2m = [], []
    chg = Counter()
    for nt in NIGHTS[fmt]:
        hp, ap, sl = nt["hp"], nt["ap"], nt["sl"]
        ours = [{"id": h, "name": str(h), "sl": sl[h]} for h in hp]; theirs = [{"id": a, "name": str(a), "sl": sl[a]} for a in ap]
        top = max(range(5), key=lambda j: (theirs[j]["sl"], -j))
        keys = [(h, a) for h in hp for a in ap]; xs = [nt["cross"][k][0] for k in keys]

        def ranked(values):
            n = _Night(ours, theirs, values, 5, 23, 0, 23, 0)
            leg = n.legal_ours(n.full_ours)
            return sorted(((n.pair(i, top) + n.solve(n.full_ours & ~(1 << i), n.full_theirs & ~(1 << top), True)), -i, i) for i in leg)[::-1]

        def pts(mode):
            v = {}
            for k in keys:
                meta = nt["cross"][k][1]; p_ = LEVEL_POINTS[meta["lv"]]
                if mode == "thresh_as_caution" and meta["thresh"]:
                    p_ = -3
                if mode == "unknown_minus1" and meta["lv"] == "Unknown":
                    p_ = -1
                v[k] = {"points": p_}
            return v
        r_m3 = ranked(pts("prod"))
        if not r_m3:
            continue
        r_c2 = ranked({k: {"points": float(p)} for k, p in zip(keys, fitted["C2_SKILL+EVIDENCE"].predict_x(xs))})
        a_m3, a_c2 = r_m3[0][2], r_c2[0][2]
        n_ok += 1; differ += a_m3 != a_c2
        for name, f in evaluators.items():
            ev_vals = {k: {"points": float(p)} for k, p in zip(keys, f.predict_x(xs))}
            n = _Night(ours, theirs, ev_vals, 5, 23, 0, 23, 0)
            val = lambda i: n.pair(i, top) + n.solve(n.full_ours & ~(1 << i), n.full_theirs & ~(1 << top), True)  # noqa: E731
            gains[name].append(val(a_c2) - val(a_m3))
        if len(r_m3) > 1:
            m3m.append(r_m3[0][0] - r_m3[1][0])
        if len(r_c2) > 1:
            c2m.append(r_c2[0][0] - r_c2[1][0])
        meta = nt["cross"][(hp[a_m3], ap[top])][1]; m3_direct += meta["dg"] > 0; m3_thr += meta["thresh"]
        c2_direct += nt["cross"][(hp[a_c2], ap[top])][1]["dg"] > 0
        for mode in ("thresh_as_caution", "unknown_minus1"):
            alt = ranked(pts(mode))
            chg[mode] += bool(alt) and alt[0][2] != a_m3

    def mci(v):
        v = np.array(v, float); bs = [rng.choice(v, len(v)).mean() for _ in range(B)]
        return {"mean": float(v.mean()), "ci": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
    R["planner"][fmt] = {"nights": n_ok, "answers_differ_C2_vs_M3": differ,
                         **{f"expected_games_gain_C2planner_minus_M3_eval_{k}": mci(v) for k, v in gains.items()}}
    R["decisions"][fmt] = {"nights": n_ok, "m3_answer_is_20_game_unknown": m3_thr,
                           "answer_changes_if_20_game_unknown_scored_caution": chg["thresh_as_caution"],
                           "answer_changes_if_every_unknown_scored_minus1": chg["unknown_minus1"]}
    m3m, c2m = np.array(m3m), np.array(c2m)
    R["explain"][fmt] = {"m3_answer_has_direct_record": round(m3_direct / n_ok, 4), "m3_answer_is_20_game_unknown": round(m3_thr / n_ok, 4),
                         "c2_answer_has_direct_record": round(c2_direct / n_ok, 4), "m3_tie_with_runner_up": round(float((m3m == 0).mean()), 4),
                         "m3_margin_le_1_point": round(float((m3m <= 1).mean()), 4),
                         "c2_margin_lt_0.05_expected_games": round(float((c2m < 0.05).mean()), 4), "c2_margin_median_expected_games": round(float(np.median(c2m)), 4)}

path = OUT / f"results_{POLICY}.json"
path.write_text(json.dumps(R, indent=1, default=str))
print("wrote", path)
for fmt in ("EIGHT", "NINE"):
    m = R["main"][fmt]
    print(fmt, "train", m["n_train"], "test", m["n_test"])
    for n in MODELS:
        x = m[n]
        print(f"  {n:20s} LL {x['logloss']:.4f} Brier {x['brier']:.4f} AUC {x['auc']:.4f} gain vs A {x['gain_vs_A']:+.4f} {[round(v, 4) for v in x['gain_vs_A_ci']]}")
