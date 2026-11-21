"""Issue #119 controls requested by independent review (evidence only; no fixes, tuning or new models).

1. Global 20-game threshold removal: every pairing re-scored by the production rule with FORM_MIN_GAMES = 0,
   whatever its original level; full transition matrix by format; regression control on the reproduced case.
2. Decision-type isolation: every individual M3 decision is logged as LEAD or RESPONSE, and tie frequency,
   tie-break sensitivity, evaluator-value differences and preservation are measured per type, at the decision
   itself (no trajectory confounding).
3. Paired night-level comparisons on identical populations; deterministic seeds from SHA-256 (stable across
   processes); 1,000 bootstrap resamples; mean, median, percentiles, worst and best; exclusions disclosed.

Unplayed games are scored by the same pre-2023 evaluators as night_replay.py / focused_impact.py (skill+evidence
and skill-only). Simulated expected individual game wins are NOT APA team points.
Set FOCUS_FORMAT=EIGHT or NINE to run one format.
Usage: python -I focused_controls.py --db <archive_snapshot.sqlite> --out <dir> [--policy clean]
"""
import hashlib, json, math, os, random, sqlite3, sys
from collections import defaultdict, deque, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_common as _rc  # noqa: E402
DB, OUT, POLICY, SNAP = _rc.setup(__doc__)
import numpy as np  # noqa: E402
import analytics.ultimate_coach_confidence as conf_mod  # noqa: E402
from analytics.ultimate_coach_confidence import pair_confidence, sl_changed_since_last_meeting, LEVEL_POINTS, FORM_MIN_GAMES  # noqa: E402
from analytics.match_night_engine import _Night  # noqa: E402
from replay_confidence_levels import FORMATS, local_day  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
FMTS = [os.environ["FOCUS_FORMAT"]] if os.environ.get("FOCUS_FORMAT") else ["EIGHT", "NINE"]
START, VAL_END, EVAL_END = "2023-01-01", "2025-08-31", "2022-12-31"
LEVELS = ["Strong", "Solid", "Thin", "Unknown", "Conflicted", "Caution"]
NBOOT = 1000


def seed(*parts):
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


def level_nogate(direct, op, oo, shared, ch):
    saved = conf_mod.FORM_MIN_GAMES
    conf_mod.FORM_MIN_GAMES = 0
    try:
        return pair_confidence(direct, own_overall=op, opp_overall=oo, shared=shared, sl_changed=ch)["level"]
    finally:
        conf_mod.FORM_MIN_GAMES = saved


R = {"policy": POLICY, "snapshot": SNAP, "formats": FMTS, "bootstrap_resamples": NBOOT,
     "regression_control_reproduced_case": {
         "inputs": "no direct record; own record 5-2 (7 games); opponent record 691-393 (1,084 games)",
         "smoothed_difference_points": round(100 * ((691 + 5) / (1084 + 10) - (5 + 5) / (7 + 10)), 3),
         "production_level": pair_confidence(None, own_overall=(5, 7), opp_overall=(691, 1084))["level"],
         "global_gate_removed_level": level_nogate(None, (5, 7), (691, 1084), None, False)}}
con = sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True)
raw = con.execute("""SELECT h.player_id,h.opponent_id,h.result,h.own_skill_level,h.opponent_skill_level,h.format,m.match_date,h.match_id
  FROM player_head_to_head h JOIN matches m ON m.id=h.match_id ORDER BY h.rowid""").fetchall()
mt = {r[0]: r[1:] for r in con.execute("SELECT id,home_team_id,away_team_id,home_score,away_score,is_scored,is_bye FROM matches")}
pt = {(r[0], r[1]): r[2] for r in con.execute("SELECT player_id,match_id,team_id FROM player_matches")}
by_key = defaultdict(list)
for r in raw:
    by_key[(r[7], r[0], r[1])].append(r)
ident = {k for k, v in by_key.items() if len(v) > 1 and len({(x[2], x[3], x[4]) for x in v}) == 1}
confl = {k for k, v in by_key.items() if len(v) > 1 and k not in ident}
kept, seen = [], set()
for r in raw:
    k = (r[7], r[0], r[1])
    if POLICY == "clean" and k in confl:
        continue
    if POLICY in ("dedup", "clean") and k in ident:
        if k in seen:
            continue
        seen.add(k)
    kept.append(r)
games = defaultdict(list)
for p, o, res, slp, slo, fmt, day, mid in kept:
    if res in ("W", "L") and fmt in FORMATS and p != o and FORMATS[fmt] in FMTS:
        games[(FORMATS[fmt], local_day(day))].append((p, o, res == "W", slp, slo, mid))
for k in games:
    games[k].sort(key=lambda g: (str(g[5]), str(g[0]), str(g[1])))


def sh(w, n, k=6):
    return (w + k / 2) / (n + k)


pairs = defaultdict(dict); overall = defaultdict(lambda: [0, 0]); recent = defaultdict(lambda: deque(maxlen=10))
GROUPS = ["SLPAIR", "DIRECT", "SHARED", "RECENT", "FORM"]


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
    direct = (rec[0], rec[1]) if rec else None
    lv = pair_confidence(direct, own_overall=op, opp_overall=oo, shared=shared, sl_changed=ch)["level"]
    lvg = level_nogate(direct, op, oo, shared, ch)                       # global: every pairing, any level
    dw, dg = (rec[0], rec[1]) if rec else (0, 0)
    rp, ro = recent[(fmt, p)], recent[(fmt, o)]
    x = {"SLPAIR": [float(slp == a and slo == b) for a in range(1, 10) for b in range(1, 10)],
         "DIRECT": [sh(dw, dg, 2) - .5, math.log1p(dg), float(dg > 0)],
         "SHARED": [(sh(shared[0], shared[1]) - sh(shared[2], shared[3])) if shared else 0.0, float(shared[4]) if shared else 0.0],
         "RECENT": [sh(sum(rp), len(rp)) - .5, sh(sum(ro), len(ro)) - .5],
         "FORM": [sh(*op) - .5, sh(*oo) - .5, math.log1p(op[1]), math.log1p(oo[1])]}
    return x, {"lv": lv, "lv_global": lvg, "lv_unknown_only": lvg if lv == "Unknown" else lv}


ROWS = {f: [] for f in FMTS}; NIGHTS = {f: [] for f in FMTS}; TRANS = {f: Counter() for f in FMTS}
EXCL = {f: Counter() for f in FMTS}
for (fmt, day), obs in sorted(games.items()):
    bym = defaultdict(list)
    for g in obs:
        bym[g[5]].append(g)
    if day > VAL_END:
        for mid, gl in bym.items():
            m = mt.get(mid)
            if not m or not m[4] or m[5]:
                EXCL[fmt]["unscored_or_bye"] += 1; continue
            if len(gl) != 10:
                EXCL[fmt]["not_ten_decided_rows"] += 1; continue
            sl = {g[0]: g[3] for g in gl}
            hp = list({g[0] for g in gl if pt.get((g[0], mid)) == m[0]}); ap = list({g[0] for g in gl if pt.get((g[0], mid)) == m[1]})
            if len(hp) != 5 or len(ap) != 5:
                EXCL[fmt]["not_five_per_side"] += 1; continue
            if any(not sl.get(x) for x in hp + ap):
                EXCL[fmt]["missing_skill_level"] += 1; continue
            hp.sort(key=lambda x: (-sl[x], x)); ap.sort(key=lambda x: (-sl[x], x))
            NIGHTS[fmt].append({"mid": mid, "hp": hp, "ap": ap, "sl": {x: sl[x] for x in hp + ap},
                                "cross": {(h, a): features(fmt, h, a, sl[h], sl[a]) for h in hp for a in ap}})
    for p, o, won, slp, slo, mid in obs:
        if (hashlib.md5(f"{mid}|{min(p,o)}|{max(p,o)}".encode()).digest()[0] & 1) != (1 if p < o else 0) or not slp or not slo:
            continue
        if "2013-01-01" <= day <= EVAL_END or day >= START:
            x, meta = features(fmt, p, o, slp, slo)
            if day <= EVAL_END:
                ROWS[fmt].append((day, x, int(won)))
            else:
                TRANS[fmt][(meta["lv"], meta["lv_global"])] += 1
    for p, o, won, slp, slo, mid in obs:
        rec = pairs[(fmt, p)].setdefault(o, [0, 0, day, slp, slo]); rec[0] += int(won); rec[1] += 1; rec[2:] = [day, slp, slo]
        overall[(fmt, p)][0] += int(won); overall[(fmt, p)][1] += 1
        recent[(fmt, p)].append(int(won))


def fit(X, y, lam, it=25):
    X1 = np.c_[np.ones(len(X)), X]; b = np.zeros(X1.shape[1]); pen = np.eye(len(b)) * lam; pen[0, 0] = 0
    for _ in range(it):
        p = 1 / (1 + np.exp(-X1 @ b)); W = p * (1 - p) + 1e-9
        b = b + np.linalg.solve(X1.T @ (X1 * W[:, None]) + pen, X1.T @ (y - p) - pen @ b)
    return b


def llv(y, p):
    p = np.clip(p, 1e-9, 1 - 1e-9); return -(y * np.log(p) + (1 - y) * np.log(1 - p))


class Model:
    def __init__(self, gs, rows, lo, fit_end, val_end):
        self.gs = gs
        sel = [r for r in rows if lo <= r[0] <= val_end]
        X = np.array([np.concatenate([r[1][g] for g in gs]) for r in sel]); y = np.array([r[2] for r in sel], float)
        d = np.array([r[0] for r in sel]); fi, va = d <= fit_end, d > fit_end
        self.keep = X.std(0) > 0; X = X[:, self.keep]; self.mu, self.sd = X.mean(0), X.std(0); Z = (X - self.mu) / self.sd
        self.lam = min(((llv(y[va], 1 / (1 + np.exp(-(np.c_[np.ones(va.sum()), Z[va]] @ fit(Z[fi], y[fi], lam))))).mean(), lam)
                        for lam in (0.1, 1, 10, 100, 1000)))[1]
        self.b = fit(Z, y, self.lam)

    def p(self, xs):
        X = np.array([np.concatenate([x[g] for g in self.gs]) for x in xs])[:, self.keep]
        return 1 / (1 + np.exp(-(np.c_[np.ones(len(X)), (X - self.mu) / self.sd] @ self.b)))


def at_least(ps, k):
    dist = [1.0]
    for p in ps:
        dist = [a * (1 - p) + (dist[i - 1] * p if i else 0) for i, a in enumerate(dist + [0.0])]
    return sum(dist[k:])


def play(nt, ours_ids, level_key, ev_vals, opp, we_first, tie_rng=None, log_decisions=None):
    sl, ap = nt["sl"], nt["ap"]
    ours = [{"id": h, "name": str(h), "sl": sl[h]} for h in ours_ids]; theirs = [{"id": a, "name": str(a), "sl": sl[a]} for a in ap]
    vals = {k: {"points": LEVEL_POINTS[nt["cross"][k][1][level_key]]} for k in nt["cross"]}
    npol = _Night(ours, theirs, vals, 5, 23, 0, 23, 0); nev = _Night(ours, theirs, ev_vals, 5, 23, 0, 23, 0)
    om, tm = npol.full_ours, npol.full_theirs
    top = max(range(5), key=lambda i: (sl[ours_ids[i]], -nt["hp"].index(ours_ids[i])))
    log = []
    for k in range(5):
        we_lead = (k % 2 == 0) == we_first
        lo, lt = npol.legal_ours(om), npol.legal_theirs(om, tm)
        if not lo or not lt:
            return None
        if we_lead:
            sc = {i: min(npol.pair(i, j) + npol.solve(om & ~(1 << i), tm & ~(1 << j), False) for j in lt) for i in lo}
            evv = lambda t: min(nev.pair(t, jj) + nev.solve(om & ~(1 << t), tm & ~(1 << jj), False) for jj in lt)  # noqa: E731
        else:
            if opp == "adversarial":
                j = min(lt, key=lambda jj: (max(nev.pair(ii, jj) + nev.solve(om & ~(1 << ii), tm & ~(1 << jj), True) for ii in lo), jj))
            else:
                j = lt[0]
            sc = {i: npol.pair(i, j) + npol.solve(om & ~(1 << i), tm & ~(1 << j), True) for i in lo}
            evv = lambda t: nev.pair(t, j) + nev.solve(om & ~(1 << t), tm & ~(1 << j), True)  # noqa: E731
        best = max(sc.values()); tied = [i for i in lo if sc[i] == best]
        i = tied[0] if tie_rng is None else tie_rng.choice(tied)
        if log_decisions is not None:
            entry = {"type": "LEAD" if we_lead else "RESPONSE", "game": k + 1, "tied": len(tied), "top_chosen": i == top,
                     "top_available": bool(om >> top & 1)}
            if len(tied) > 1:
                vals_t = [evv(t) for t in tied]
                entry["eval_spread"] = max(vals_t) - min(vals_t)
                entry["prod_minus_random_expected"] = evv(tied[0]) - float(np.mean(vals_t))
                entry["prod_minus_best_tied"] = evv(tied[0]) - max(vals_t)
            log_decisions.append(entry)
        if we_lead:
            if opp == "adversarial":
                j = min(lt, key=lambda jj: (nev.pair(i, jj) + nev.solve(om & ~(1 << i), tm & ~(1 << jj), False), jj))
            else:
                j = min(lt, key=lambda jj: (nev.pair(i, jj), jj))
        log.append((we_lead, ours_ids[i], ap[j], i, j))
        om, tm = om & ~(1 << i), tm & ~(1 << j)
    ps = [nev.pair(i, j) for *_, i, j in log]
    return {"eg": float(sum(ps)), "p3": at_least(ps, 3), "cap_ok": sum(sl[h] for _, h, _, _, _ in log) <= 23,
            "seq": tuple((wl, h, a) for wl, h, a, _, _ in log),
            "top_game": next(n for n, (_, h, _, _, _) in enumerate(log) if h == ours_ids[top]) + 1}


def dist(v):
    v = np.asarray(v, float)
    rs = np.random.default_rng(seed("boot", len(v), float(v.sum())))
    idx = rs.integers(0, len(v), (NBOOT, len(v)))
    means = v[idx].mean(1)
    return {"n": int(len(v)), "mean": float(v.mean()), "ci95": [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))],
            "median": float(np.median(v)), "p05": float(np.percentile(v, 5)), "p25": float(np.percentile(v, 25)),
            "p75": float(np.percentile(v, 75)), "p95": float(np.percentile(v, 95)), "worst": float(v.min()), "best": float(v.max()),
            "share_nonzero": float((np.abs(v) > 1e-9).mean())}


R["by_format"] = {}
for fmt in FMTS:
    evs = {"pre2023_C2": Model(GROUPS, ROWS[fmt], "2013-01-01", "2021-12-31", EVAL_END),
           "pre2023_skill": Model(["SLPAIR"], ROWS[fmt], "2013-01-01", "2021-12-31", EVAL_END)}
    F = {"nights": len(NIGHTS[fmt]), "excluded_test_matches": dict(EXCL[fmt])}
    # 1. global transition matrix (2023+ games, one row per game)
    tot = sum(TRANS[fmt].values())
    F["global_gate_removal_transition"] = {"games": tot, "matrix": {f"{a} -> {b}": n for (a, b), n in sorted(TRANS[fmt].items())},
                                           "changed_share": round(sum(n for (a, b), n in TRANS[fmt].items() if a != b) / tot, 4),
                                           "changed_from_non_unknown": sum(n for (a, b), n in TRANS[fmt].items() if a != b and a != "Unknown")}
    setups = [(ev, opp, wf) for ev in ("pre2023_C2", "pre2023_skill") for opp in ("adversarial", "top_first") for wf in (True, False)]
    variants = ["reversed", "random_tiebreak_s1", "random_tiebreak_s2", "random_tiebreak_s3", "gate_removed_global", "gate_removed_unknown_only"]
    paired = defaultdict(lambda: defaultdict(list)); decisions = defaultdict(list); incomplete = Counter()
    for nt in NIGHTS[fmt]:
        keys = list(nt["cross"]); xs = [nt["cross"][k][0] for k in keys]
        evv_all = {name: {k: {"points": float(v)} for k, v in zip(keys, ev.p(xs))} for name, ev in evs.items()}
        for ev, opp, wf in setups:
            tag = f"{ev}|{opp}|{'we_lead_first' if wf else 'they_lead_first'}"
            dlog = []
            base = play(nt, list(nt["hp"]), "lv", evv_all[ev], opp, wf, log_decisions=dlog)
            if base is None:
                incomplete[(tag, "production")] += 1; continue
            decisions[tag] += dlog
            for vname in variants:
                if vname == "reversed":
                    v = play(nt, list(reversed(nt["hp"])), "lv", evv_all[ev], opp, wf)
                elif vname.startswith("random_tiebreak"):
                    v = play(nt, list(nt["hp"]), "lv", evv_all[ev], opp, wf, random.Random(seed(vname, nt["mid"], tag)))
                elif vname == "gate_removed_global":
                    v = play(nt, list(nt["hp"]), "lv_global", evv_all[ev], opp, wf)
                else:
                    v = play(nt, list(nt["hp"]), "lv_unknown_only", evv_all[ev], opp, wf)
                if v is None:
                    incomplete[(tag, vname)] += 1; continue
                d = paired[(tag, vname)]
                d["eg"].append(v["eg"] - base["eg"]); d["p3"].append(v["p3"] - base["p3"])
                d["seq_changed"].append(v["seq"] != base["seq"]); d["cap_ok"].append(v["cap_ok"])
                d["top_shift"].append(v["top_game"] - base["top_game"])
                # type of the first decision that differs
                first_diff = next((s1[0] for s1, s2 in zip(base["seq"], v["seq"]) if s1 != s2), None)
                d["first_diff_type"].append("none" if first_diff is None else ("LEAD" if first_diff else "RESPONSE"))
    F["incomplete_simulations"] = {f"{a} || {b}": n for (a, b), n in incomplete.items()}
    F["paired_variants"] = {}
    for (tag, vname), d in paired.items():
        F["paired_variants"][f"{tag} || {vname}"] = {
            "plan_changed_share": float(np.mean(d["seq_changed"])), "first_divergence_type": dict(Counter(d["first_diff_type"])),
            "expected_games_diff": dist(d["eg"]), "simulated_3_of_5_probability_diff": dist(d["p3"]),
            "cap_compliance": float(np.mean(d["cap_ok"])), "top_player_game_shift": dist(d["top_shift"])}
    F["decision_types"] = {}
    for tag, dl in decisions.items():
        out = {}
        for typ in ("LEAD", "RESPONSE"):
            ds = [e for e in dl if e["type"] == typ]
            ties = [e for e in ds if e["tied"] > 1]
            out[typ] = {"decisions": len(ds), "tie_share": round(len(ties) / max(1, len(ds)), 4),
                        "tie_size": dict(Counter(e["tied"] for e in ties)),
                        "evaluator_spread_among_tied": dist([e["eval_spread"] for e in ties]) if ties else None,
                        "production_pick_minus_random_tied_pick": dist([e["prod_minus_random_expected"] for e in ties]) if ties else None,
                        "production_pick_minus_best_tied": dist([e["prod_minus_best_tied"] for e in ties]) if ties else None,
                        "top_player_chosen_share_when_available": round(sum(e["top_chosen"] for e in ds if e["top_available"]) /
                                                                        max(1, sum(e["top_available"] for e in ds)), 4)}
        F["decision_types"][tag] = out
    R["by_format"][fmt] = F
    print(fmt, "done", len(NIGHTS[fmt]))
name = "focused_controls_" + "_".join(FMTS) + f"_{POLICY}.json"
(OUT / name).write_text(json.dumps(R, indent=1))
print("wrote", OUT / name)
