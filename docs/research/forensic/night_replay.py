"""Historical match-night replay: current M3 planner vs the same planner fed skill+evidence probabilities.

Read-only research. Neither planner is tuned here: M3 uses its production level points; the candidate uses the
issue #119 C2 model (skill pair + direct, shared-opponent, last-10 and lifetime records) fitted on 2023-01 to
2025-08 with the penalty chosen on 2025-03 to 2025-08, exactly as in issue119_experiment.py. Both planners run the
production search (analytics.match_night_engine._Night) on the identical test nights (2025-09 onward; the ten
players who actually played, cap 23 both teams, production roster order) and play all five games against the same
opponent policy, for both possible first leaders.

Outcomes of unplayed pairings are never observed, so every game is scored by an evaluator fitted only on
2013-2022 games (two evaluators: skill+evidence and skill-only). Results are model-dependent by construction.
Writes night_replay_<policy>.json.

Usage: python -I night_replay.py --db <archive_snapshot.sqlite> --out <dir> [--policy clean]
"""
import hashlib, json, math, sqlite3, sys
from collections import defaultdict, deque, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_common as _rc  # noqa: E402
DB, OUT, POLICY, SNAP = _rc.setup(__doc__)
import numpy as np  # noqa: E402
from analytics.ultimate_coach_confidence import pair_confidence, sl_changed_since_last_meeting, LEVEL_POINTS, FORM_MIN_GAMES  # noqa: E402
from analytics.match_night_engine import _Night  # noqa: E402
from replay_confidence_levels import FORMATS, local_day  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
START, FIT_END, VAL_END, EVAL_END = "2023-01-01", "2025-02-28", "2025-08-31", "2022-12-31"
rng = np.random.default_rng(20261124)
R = {"policy": POLICY, "snapshot": SNAP}
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
    if res in ("W", "L") and fmt in FORMATS and p != o:
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
    lv = pair_confidence((rec[0], rec[1]) if rec else None, own_overall=op, opp_overall=oo, shared=shared, sl_changed=ch)["level"]
    thresh = lv == "Unknown" and rec is None and (op[1] < FORM_MIN_GAMES or oo[1] < FORM_MIN_GAMES)
    dw, dg = (rec[0], rec[1]) if rec else (0, 0)
    rp, ro = recent[(fmt, p)], recent[(fmt, o)]
    x = {"SLPAIR": [float(slp == a and slo == b) for a in range(1, 10) for b in range(1, 10)],
         "DIRECT": [sh(dw, dg, 2) - .5, math.log1p(dg), float(dg > 0)],
         "SHARED": [(sh(shared[0], shared[1]) - sh(shared[2], shared[3])) if shared else 0.0, float(shared[4]) if shared else 0.0],
         "RECENT": [sh(sum(rp), len(rp)) - .5, sh(sum(ro), len(ro)) - .5],
         "FORM": [sh(*op) - .5, sh(*oo) - .5, math.log1p(op[1]), math.log1p(oo[1])]}
    return x, {"lv": lv, "thresh": thresh, "dg": dg}


ROWS = {"EIGHT": [], "NINE": []}; NIGHTS = {"EIGHT": [], "NINE": []}
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
                                "actual_games": sum(int(g[2]) for g in gl if g[0] in hp)})
    if "2013-01-01" <= day <= VAL_END:
        for p, o, won, slp, slo, mid in obs:
            if (hashlib.md5(f"{mid}|{min(p,o)}|{max(p,o)}".encode()).digest()[0] & 1) != (1 if p < o else 0) or not slp or not slo:
                continue
            x, _ = features(fmt, p, o, slp, slo)
            ROWS[fmt].append((day, x, int(won)))
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
    """L2 logistic; penalty chosen on the validation window only (same procedure as issue119_experiment.py)."""
    def __init__(self, gs, rows, lo, fit_end, val_end):
        self.gs = gs
        sel = [r for r in rows if lo <= r[0] <= val_end]
        X = np.array([np.concatenate([r[1][g] for g in gs]) for r in sel]); y = np.array([r[2] for r in sel], float)
        d = np.array([r[0] for r in sel]); fi, va = d <= fit_end, d > fit_end
        self.keep = X.std(0) > 0; X = X[:, self.keep]; self.mu, self.sd = X.mean(0), X.std(0); Z = (X - self.mu) / self.sd
        best = min(((llv(y[va], 1 / (1 + np.exp(-(np.c_[np.ones(va.sum()), Z[va]] @ fit(Z[fi], y[fi], lam))))).mean(), lam)
                    for lam in (0.1, 1, 10, 100, 1000)))
        self.b = fit(Z, y, best[1])

    def p(self, xs):
        X = np.array([np.concatenate([x[g] for g in self.gs]) for x in xs])[:, self.keep]
        return 1 / (1 + np.exp(-(np.c_[np.ones(len(X)), (X - self.mu) / self.sd] @ self.b)))


def poisson_binomial_at_least(ps, k):
    dist = [1.0]
    for p in ps:
        dist = [a * (1 - p) + (dist[i - 1] * p if i else 0) for i, a in enumerate(dist + [0.0])]
    return sum(dist[k:])


def play(nt, pol_vals, ev_vals, opp, we_first):
    """Play five games. pol_vals drive our planner; ev_vals score games and drive the adversarial opponent."""
    hp, ap, sl = nt["hp"], nt["ap"], nt["sl"]
    ours = [{"id": h, "name": str(h), "sl": sl[h]} for h in hp]; theirs = [{"id": a, "name": str(a), "sl": sl[a]} for a in ap]
    npol = _Night(ours, theirs, pol_vals, 5, 23, 0, 23, 0); nev = _Night(ours, theirs, ev_vals, 5, 23, 0, 23, 0)
    om, tm = npol.full_ours, npol.full_theirs
    log, ties, margins = [], 0, []
    for k in range(5):
        we_lead = (k % 2 == 0) == we_first
        lo, lt = npol.legal_ours(om), npol.legal_theirs(om, tm)
        if not lo or not lt:
            return None
        if we_lead:
            scored = sorted((min(npol.pair(i, j) + npol.solve(om & ~(1 << i), tm & ~(1 << j), False) for j in lt), -i, i) for i in lo)[::-1]
            i = scored[0][2]
            if len(scored) > 1:
                ties += scored[0][0] == scored[1][0]; margins.append(scored[0][0] - scored[1][0])
            if opp == "adversarial":
                j = min(lt, key=lambda jj: (nev.pair(i, jj) + nev.solve(om & ~(1 << i), tm & ~(1 << jj), False), jj))
            else:
                j = min(lt, key=lambda jj: (nev.pair(i, jj), jj))
        else:
            if opp == "adversarial":
                j = min(lt, key=lambda jj: (max(nev.pair(ii, jj) + nev.solve(om & ~(1 << ii), tm & ~(1 << jj), True) for ii in lo), jj))
            else:
                j = lt[0]                                    # their highest-level legal player
            scored = sorted(((npol.pair(ii, j) + npol.solve(om & ~(1 << ii), tm & ~(1 << j), True)), -ii, ii) for ii in lo)[::-1]
            i = scored[0][2]
            if len(scored) > 1:
                ties += scored[0][0] == scored[1][0]; margins.append(scored[0][0] - scored[1][0])
        log.append((k, we_lead, i, j))
        om, tm = om & ~(1 << i), tm & ~(1 << j)
    ps = [nev.pair(i, j) for _, _, i, j in log]
    used_ours = sum(sl[hp[i]] for _, _, i, _ in log); used_theirs = sum(sl[ap[j]] for _, _, _, j in log)
    top = 0
    top_game = next(kk for kk, _, i, _ in log if i == top)
    answers = [(i, j) for kk, wl, i, j in log if not wl]
    best_resp = []
    om2, tm2 = nev.full_ours, nev.full_theirs
    for kk, wl, i, j in log:                                 # response quality: this game's evaluator p vs the best legal answer
        if not wl:
            lo2 = nev.legal_ours(om2)
            best_resp.append(max(nev.pair(ii, j) for ii in lo2) - nev.pair(i, j))
        om2, tm2 = om2 & ~(1 << i), tm2 & ~(1 << j)
    first_answer = next(((i, j) for kk, wl, i, j in log if not wl), None)
    return {"expected_games": float(sum(ps)), "night_win_p": poisson_binomial_at_least(ps, 3),
            "cap_ok": used_ours <= 23 and used_theirs <= 23, "top_player_game": top_game + 1,
            "ties": ties, "margins": margins, "first_answer": first_answer,
            "resp_regret_this_game": best_resp, "pairs": [(hp[i], ap[j]) for _, _, i, j in log]}


R["by_format"] = {}
for fmt in ("EIGHT", "NINE"):
    cand = Model(GROUPS, ROWS[fmt], START, FIT_END, VAL_END)
    evs = {"pre2023_C2": Model(GROUPS, ROWS[fmt], "2013-01-01", "2021-12-31", EVAL_END),
           "pre2023_skill": Model(["SLPAIR"], ROWS[fmt], "2013-01-01", "2021-12-31", EVAL_END)}
    agg = defaultdict(lambda: defaultdict(list)); first_diff = Counter(); expl = defaultdict(Counter)
    for nt in NIGHTS[fmt]:
        keys = [(h, a) for h in nt["hp"] for a in nt["ap"]]; xs = [nt["cross"][k][0] for k in keys]
        m3 = {k: {"points": LEVEL_POINTS[nt["cross"][k][1]["lv"]]} for k in keys}
        c2 = {k: {"points": float(v)} for k, v in zip(keys, cand.p(xs))}
        evv = {name: {k: {"points": float(v)} for k, v in zip(keys, ev.p(xs))} for name, ev in evs.items()}
        for evname, ev_vals in evv.items():
            for opp in ("adversarial", "top_first"):
                for we_first in (True, False):
                    tag = f"{evname}|{opp}|{'we_lead_first' if we_first else 'they_lead_first'}"
                    a = play(nt, m3, ev_vals, opp, we_first); b = play(nt, c2, ev_vals, opp, we_first)
                    if a is None or b is None:
                        continue
                    for key in ("expected_games", "night_win_p"):
                        agg[tag][f"m3_{key}"].append(a[key]); agg[tag][f"c2_{key}"].append(b[key])
                    agg[tag]["m3_cap_ok"].append(a["cap_ok"]); agg[tag]["c2_cap_ok"].append(b["cap_ok"])
                    agg[tag]["m3_top_game"].append(a["top_player_game"]); agg[tag]["c2_top_game"].append(b["top_player_game"])
                    agg[tag]["m3_resp_regret"] += a["resp_regret_this_game"]; agg[tag]["c2_resp_regret"] += b["resp_regret_this_game"]
                    agg[tag]["same_board"].append(sorted(a["pairs"]) == sorted(b["pairs"]))
                    if evname == "pre2023_C2" and opp == "adversarial" and not we_first:
                        first_diff["nights"] += 1; first_diff["first_answer_differs"] += a["first_answer"] != b["first_answer"]
                    if evname == "pre2023_C2" and opp == "adversarial":
                        expl["m3"]["decisions"] += 5; expl["m3"]["ties"] += a["ties"]
                        expl["c2"]["decisions"] += 5; expl["c2"]["ties"] += b["ties"]
                        expl["c2"]["margin_lt_0.02"] += sum(1 for mg in b["margins"] if mg < 0.02)
                        for h, x in a["pairs"]:
                            meta = nt["cross"][(h, x)][1]
                            expl["m3"]["pair_has_direct"] += meta["dg"] > 0; expl["m3"]["pair_unknown"] += meta["lv"] == "Unknown"
                            expl["m3"]["pairs"] += 1
                        for h, x in b["pairs"]:
                            meta = nt["cross"][(h, x)][1]
                            expl["c2"]["pair_has_direct"] += meta["dg"] > 0; expl["c2"]["pair_unknown"] += meta["lv"] == "Unknown"
                            expl["c2"]["pairs"] += 1

    def paired(a, b):
        d = np.array(b, float) - np.array(a, float); bs = [rng.choice(d, len(d)).mean() for _ in range(300)]
        return {"m3_mean": float(np.mean(a)), "c2_mean": float(np.mean(b)), "diff": float(d.mean()),
                "ci": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))], "c2_better_share": float((d > 1e-9).mean()),
                "m3_better_share": float((d < -1e-9).mean())}
    out = {"nights": len(NIGHTS[fmt]), "first_answer": dict(first_diff),
           "explainability": {k: dict(v) for k, v in expl.items()}, "scenarios": {}}
    for tag, d in agg.items():
        out["scenarios"][tag] = {"n": len(d["m3_expected_games"]),
                                 "expected_games": paired(d["m3_expected_games"], d["c2_expected_games"]),
                                 "night_win_probability": paired(d["m3_night_win_p"], d["c2_night_win_p"]),
                                 "cap_compliance": {"m3": float(np.mean(d["m3_cap_ok"])), "c2": float(np.mean(d["c2_cap_ok"]))},
                                 "game_our_top_player_played": {"m3_mean": float(np.mean(d["m3_top_game"])), "c2_mean": float(np.mean(d["c2_top_game"]))},
                                 "response_regret_this_game": {"m3_mean": float(np.mean(d["m3_resp_regret"])), "c2_mean": float(np.mean(d["c2_resp_regret"]))},
                                 "identical_board_share": float(np.mean(d["same_board"]))}
    R["by_format"][fmt] = out
    print(fmt, json.dumps(out["scenarios"].get("pre2023_C2|adversarial|they_lead_first", {}), indent=0)[:900])
(OUT / f"night_replay_{POLICY}.json").write_text(json.dumps(R, indent=1))
print("wrote", OUT / f"night_replay_{POLICY}.json")
