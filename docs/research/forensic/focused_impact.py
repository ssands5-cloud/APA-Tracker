"""Focused forensic impact study (issue #119): ties and roster order, Unknown causes, format differences.

Evidence only: no fixes, no tuning, no new models. M3 is run unchanged (analytics.match_night_engine._Night,
production LEVEL_POINTS). Counterfactual planning runs use the same two pre-2023 evaluators as night_replay.py
(fitted on 2013-2021, penalty chosen on 2022; never on the test period) to score games that were never played.
Actual recorded outcomes are reported separately from simulated ones.

Set FOCUS_FORMAT=EIGHT or NINE to run one format (both run by default).
Usage: python -I focused_impact.py --db <archive_snapshot.sqlite> --out <dir> [--policy clean]
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
POINTS_9_SCALED = {"Strong": 8, "Solid": 3, "Thin": 1, "Unknown": 0, "Conflicted": 0, "Caution": -3}   # 9-Ball replay ratios, Thin = 1
R = {"policy": POLICY, "snapshot": SNAP, "formats": FMTS}
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


def level_nogate(direct, op, oo, shared, ch):
    saved = conf_mod.FORM_MIN_GAMES
    conf_mod.FORM_MIN_GAMES = 0
    try:
        return pair_confidence(direct, own_overall=op, opp_overall=oo, shared=shared, sl_changed=ch)["level"]
    finally:
        conf_mod.FORM_MIN_GAMES = saved


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
    lv0 = level_nogate(direct, op, oo, shared, ch) if lv == "Unknown" else lv
    dw, dg = (rec[0], rec[1]) if rec else (0, 0)
    rp, ro = recent[(fmt, p)], recent[(fmt, o)]
    x = {"SLPAIR": [float(slp == a and slo == b) for a in range(1, 10) for b in range(1, 10)],
         "DIRECT": [sh(dw, dg, 2) - .5, math.log1p(dg), float(dg > 0)],
         "SHARED": [(sh(shared[0], shared[1]) - sh(shared[2], shared[3])) if shared else 0.0, float(shared[4]) if shared else 0.0],
         "RECENT": [sh(sum(rp), len(rp)) - .5, sh(sum(ro), len(ro)) - .5],
         "FORM": [sh(*op) - .5, sh(*oo) - .5, math.log1p(op[1]), math.log1p(oo[1])]}
    low = min(op[1], oo[1]) < FORM_MIN_GAMES
    if lv != "Unknown":
        cause = "not_unknown"
    elif lv0 != "Unknown":
        cause = "unknown_caused_by_20_game_gate"
    elif low:
        cause = "unknown_gate_associated_not_causal"
    else:
        cause = "unknown_no_direct_records_too_close"
    return x, {"lv": lv, "lv_nogate": lv0, "cause": cause, "dg": dg, "og": op[1], "tg": oo[1]}


ROWS = {f: [] for f in FMTS}; NIGHTS = {f: [] for f in FMTS}; GAMES23 = {f: [] for f in FMTS}
for (fmt, day), obs in sorted(games.items()):
    bym = defaultdict(list)
    for g in obs:
        bym[g[5]].append(g)
    if day > VAL_END:
        for mid, gl in bym.items():
            m = mt.get(mid)
            if not m or len(gl) != 10 or not m[4] or m[5]:
                continue
            sl = {g[0]: g[3] for g in gl}
            hp = list({g[0] for g in gl if pt.get((g[0], mid)) == m[0]}); ap = list({g[0] for g in gl if pt.get((g[0], mid)) == m[1]})
            if len(hp) != 5 or len(ap) != 5 or any(not sl.get(x) for x in hp + ap):
                continue
            hp.sort(key=lambda x: (-sl[x], x)); ap.sort(key=lambda x: (-sl[x], x))
            NIGHTS[fmt].append({"hp": hp, "ap": ap, "sl": {x: sl[x] for x in hp + ap},
                                "cross": {(h, a): features(fmt, h, a, sl[h], sl[a]) for h in hp for a in ap},
                                "realized": [(g[0], g[1], int(g[2])) for g in gl if g[0] in hp]})
    for p, o, won, slp, slo, mid in obs:
        if (hashlib.md5(f"{mid}|{min(p,o)}|{max(p,o)}".encode()).digest()[0] & 1) != (1 if p < o else 0) or not slp or not slo:
            continue
        if "2013-01-01" <= day <= EVAL_END or day >= START:
            x, meta = features(fmt, p, o, slp, slo)
            if day <= EVAL_END:
                ROWS[fmt].append((day, x, int(won)))
            else:
                GAMES23[fmt].append({"day": day, "won": int(won), "gap": slp - slo, **meta})
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


def wilson(w, n, z=1.96):
    if not n:
        return [None, None]
    p = w / n; d = 1 + z * z / n; c = p + z * z / (2 * n); a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - a) / d, 4), round((c + a) / d, 4)]


def play(nt, ours_ids, points, ev_vals, opp, we_first, tie_rng=None):
    """M3 plays five games with our roster listed in ours_ids order. Ties go to the first listed (production
    behaviour) unless tie_rng is given, in which case one equally scored candidate is drawn at random."""
    sl = nt["sl"]; ap = nt["ap"]
    ours = [{"id": h, "name": str(h), "sl": sl[h]} for h in ours_ids]; theirs = [{"id": a, "name": str(a), "sl": sl[a]} for a in ap]
    vals = {k: {"points": points[nt["cross"][k][1]["lv_nogate" if points is GATE_OFF else "lv"]] if points is not GATE_OFF else
                LEVEL_POINTS[nt["cross"][k][1]["lv_nogate"]]} for k in nt["cross"]}
    npol = _Night(ours, theirs, vals, 5, 23, 0, 23, 0); nev = _Night(ours, theirs, ev_vals, 5, 23, 0, 23, 0)
    om, tm = npol.full_ours, npol.full_theirs
    log, tie_sets = [], []
    for k in range(5):
        we_lead = (k % 2 == 0) == we_first
        lo, lt = npol.legal_ours(om), npol.legal_theirs(om, tm)
        if not lo or not lt:
            return None
        if we_lead:
            sc = {i: min(npol.pair(i, j) + npol.solve(om & ~(1 << i), tm & ~(1 << j), False) for j in lt) for i in lo}
        else:
            if opp == "adversarial":
                j = min(lt, key=lambda jj: (max(nev.pair(ii, jj) + nev.solve(om & ~(1 << ii), tm & ~(1 << jj), True) for ii in lo), jj))
            else:
                j = lt[0]
            sc = {i: npol.pair(i, j) + npol.solve(om & ~(1 << i), tm & ~(1 << j), True) for i in lo}
        best = max(sc.values()); tied = [i for i in lo if sc[i] == best]
        i = tied[0] if tie_rng is None else tie_rng.choice(tied)
        if len(tied) > 1:
            if we_lead:
                ev = {t: min(nev.pair(t, jj) + nev.solve(om & ~(1 << t), tm & ~(1 << jj), False) for jj in lt) for t in tied}
            else:
                ev = {t: nev.pair(t, j) + nev.solve(om & ~(1 << t), tm & ~(1 << j), True) for t in tied}
            tie_sets.append(max(ev.values()) - min(ev.values()))
        if we_lead:
            if opp == "adversarial":
                j = min(lt, key=lambda jj: (nev.pair(i, jj) + nev.solve(om & ~(1 << i), tm & ~(1 << jj), False), jj))
            else:
                j = min(lt, key=lambda jj: (nev.pair(i, jj), jj))
        log.append((k, we_lead, ours_ids[i], ap[j], i, j))
        om, tm = om & ~(1 << i), tm & ~(1 << j)
    ps = [nev.pair(i, j) for *_, i, j in log]
    used = sum(sl[h] for _, _, h, _, _, _ in log)
    top = max(ours_ids, key=lambda h: (sl[h], -nt["hp"].index(h)))
    return {"eg": float(sum(ps)), "p3": at_least(ps, 3), "cap_ok": used <= 23,
            "board": tuple(sorted((h, a) for _, _, h, a, _, _ in log)), "order": tuple((h, a) for _, _, h, a, _, _ in log),
            "first": (log[0][2], log[0][3]), "top_game": next(k for k, _, h, _, _, _ in log if h == top) + 1, "tie_sets": tie_sets,
            "chosen_causes": [nt["cross"][(h, a)][1]["cause"] for _, _, h, a, _, _ in log],
            "chosen_levels": [nt["cross"][(h, a)][1]["lv"] for _, _, h, a, _, _ in log]}


GATE_OFF = object()
R["by_format"] = {}
for fmt in FMTS:
    evs = {"pre2023_C2": Model(GROUPS, ROWS[fmt], "2013-01-01", "2021-12-31", EVAL_END),
           "pre2023_skill": Model(["SLPAIR"], ROWS[fmt], "2013-01-01", "2021-12-31", EVAL_END)}
    F = {"nights": len(NIGHTS[fmt])}
    # ---- evaluator calibration on actual recorded test games (realized pairs) ----
    rx, ry = [], []
    for nt in NIGHTS[fmt]:
        for h, a, w in nt["realized"]:
            rx.append(nt["cross"][(h, a)][0]); ry.append(w)
    ry = np.array(ry, float); F["evaluator_check_on_actual_test_games"] = {}
    for name, ev in evs.items():
        p = ev.p(rx); z = np.log(p / (1 - p)); b = fit(z[:, None], ry, 0.0, 30)
        F["evaluator_check_on_actual_test_games"][name] = {"games": int(len(ry)), "logloss": float(llv(ry, p).mean()),
                                                         "base_rate_logloss": float(llv(ry, np.full(len(ry), ry.mean())).mean()),
                                                         "calib_intercept": float(b[0]), "calib_slope": float(b[1])}
    # ---- 1. roster order and tie-break ----
    rnd = random.Random(20261125)
    orders = {"production": lambda nt: list(nt["hp"]), "reversed": lambda nt: list(reversed(nt["hp"])),
              "player_id": lambda nt: sorted(nt["hp"])}
    for s in (1, 2, 3):
        orders[f"random_order_seed{s}"] = (lambda s: (lambda nt: random.Random(hash((s, tuple(nt["hp"]))) & 0xFFFFFFFF).sample(nt["hp"], 5)))(s)
    setups = [(ev, opp, wf) for ev in ("pre2023_C2",) for opp in ("adversarial", "top_first") for wf in (True, False)]
    setups_skill = [("pre2023_skill", opp, wf) for opp in ("adversarial",) for wf in (True, False)]
    res = defaultdict(lambda: defaultdict(list))
    tie_spreads = defaultdict(list)
    for nt in NIGHTS[fmt]:
        keys = list(nt["cross"]); xs = [nt["cross"][k][0] for k in keys]
        evv = {name: {k: {"points": float(v)} for k, v in zip(keys, ev.p(xs))} for name, ev in evs.items()}
        for ev, opp, wf in setups + setups_skill:
            base = play(nt, orders["production"](nt), LEVEL_POINTS, evv[ev], opp, wf)
            if base is None:
                continue
            tag = f"{ev}|{opp}|{'we_lead_first' if wf else 'they_lead_first'}"
            tie_spreads[tag] += base["tie_sets"]
            variants = {}
            if (ev, opp, wf) in setups:
                for oname, ofn in orders.items():
                    if oname != "production":
                        variants[oname] = play(nt, ofn(nt), LEVEL_POINTS, evv[ev], opp, wf)
                for s in (1, 2, 3):
                    variants[f"random_tiebreak_seed{s}"] = play(nt, orders["production"](nt), LEVEL_POINTS, evv[ev], opp, wf,
                                                                random.Random(hash((s, tuple(nt["hp"]), wf, opp)) & 0xFFFFFFFF))
                variants["no_20_game_gate"] = play(nt, orders["production"](nt), GATE_OFF, evv[ev], opp, wf)
                if fmt == "NINE":
                    variants["nine_ball_scaled_points"] = play(nt, orders["production"](nt), POINTS_9_SCALED, evv[ev], opp, wf)
            else:
                variants["reversed"] = play(nt, orders["reversed"](nt), LEVEL_POINTS, evv[ev], opp, wf)
                variants["random_tiebreak_seed1"] = play(nt, orders["production"](nt), LEVEL_POINTS, evv[ev], opp, wf,
                                                         random.Random(hash((1, tuple(nt["hp"]), wf, opp)) & 0xFFFFFFFF))
            for vname, v in variants.items():
                if v is None:
                    continue
                r = res[(tag, vname)]
                r["first_changed"].append(v["first"] != base["first"]); r["board_changed"].append(v["board"] != base["board"])
                r["order_changed"].append(v["order"] != base["order"])
                r["eg_diff"].append(v["eg"] - base["eg"]); r["p3_diff"].append(v["p3"] - base["p3"])
                r["cap_ok"].append(v["cap_ok"]); r["top_game_diff"].append(v["top_game"] - base["top_game"])
            res[(tag, "production")]["cap_ok"].append(base["cap_ok"])
            res[(tag, "production")]["chosen_causes"] += base["chosen_causes"]
            res[(tag, "production")]["chosen_levels"] += base["chosen_levels"]

    def summ(r):
        out = {"nights": len(r["eg_diff"])}
        for k in ("first_changed", "board_changed", "order_changed"):
            out[k] = float(np.mean(r[k])) if r[k] else None
        for k in ("eg_diff", "p3_diff"):
            v = np.array(r[k], float)
            if len(v):
                bs = [np.random.default_rng(7 + i).choice(v, len(v)).mean() for i in range(200)]
                out[k] = {"mean": float(v.mean()), "ci": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
                          "changed_share": float((np.abs(v) > 1e-9).mean()), "worst": float(v.min()), "best": float(v.max()),
                          "mean_abs": float(np.abs(v).mean())}
        out["cap_ok"] = float(np.mean(r["cap_ok"])) if r["cap_ok"] else None
        out["top_player_game_shift_mean"] = float(np.mean(r["top_game_diff"])) if r["top_game_diff"] else None
        return out
    F["roster_order"] = {f"{tag} || {vname}": summ(r) for (tag, vname), r in res.items() if vname != "production"}
    F["production_cap_ok"] = {tag: float(np.mean(r["cap_ok"])) for (tag, vname), r in res.items() if vname == "production"}
    F["tie_interchangeability"] = {tag: {"tie_decisions": len(v), "evaluator_spread_mean": float(np.mean(v)) if v else None,
                                         "share_spread_gt_0.02_games": float(np.mean(np.array(v) > 0.02)) if v else None,
                                         "share_spread_gt_0.05_games": float(np.mean(np.array(v) > 0.05)) if v else None,
                                         "share_spread_zero": float(np.mean(np.array(v) < 1e-9)) if v else None}
                                   for tag, v in tie_spreads.items()}
    pc = res[("pre2023_C2|adversarial|they_lead_first", "production")]
    F["chosen_pairing_causes_production_plan"] = {k: v / max(1, len(pc["chosen_causes"])) for k, v in Counter(pc["chosen_causes"]).items()}
    F["chosen_pairing_levels_production_plan"] = {k: v / max(1, len(pc["chosen_levels"])) for k, v in Counter(pc["chosen_levels"]).items()}

    # ---- 2. Unknown causes: frequency and actual recorded outcomes (2023+ games, one orientation) ----
    G = GAMES23[fmt]
    cnt = Counter(g["cause"] for g in G if g["lv"] == "Unknown")
    tot_unknown = sum(cnt.values())
    F["unknown_causes_all_games_2023plus"] = {"unknown_games": tot_unknown, **{k: {"n": v, "share": round(v / tot_unknown, 4)} for k, v in cnt.items()},
                                             "gate_caused_counterfactual_levels": dict(Counter(g["lv_nogate"] for g in G if g["cause"] == "unknown_caused_by_20_game_gate"))}
    tab = defaultdict(lambda: [0, 0])
    for g in G:
        gb = "<=-3" if g["gap"] <= -3 else str(g["gap"]) if -2 <= g["gap"] <= 2 else ">=+3"
        key = g["cause"] if g["lv"] == "Unknown" else g["lv"]
        t = tab[(key, gb)]; t[0] += g["won"]; t[1] += 1
    F["actual_win_rate_by_level_or_unknown_cause_and_gap"] = [{"group": k[0], "gap": k[1], "wins": w, "games": n, "rate": round(w / n, 4), "ci": wilson(w, n)}
                                                              for k, (w, n) in sorted(tab.items()) if n >= 30]
    lv_tab = defaultdict(lambda: [0, 0])
    for g in G:
        t = lv_tab[g["lv"]]; t[0] += g["won"]; t[1] += 1
    F["actual_win_rate_by_level"] = {k: {"wins": w, "games": n, "rate": round(w / n, 4), "ci": wilson(w, n)} for k, (w, n) in lv_tab.items()}
    R["by_format"][fmt] = F
    print(fmt, "done", len(NIGHTS[fmt]))

name = "focused_impact_" + ("_".join(FMTS)) + f"_{POLICY}.json"
(OUT / name).write_text(json.dumps(R, indent=1))
print("wrote", OUT / name)
