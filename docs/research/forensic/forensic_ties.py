"""Forensic: tie-break and missing-data effects in M3's game-one decisions on historical test nights.

Read-only. Same replay discipline as issue119_experiment.py (strictly earlier dates, clean record policy).
For each test night (the ten players who played; the bench is unrecorded) it solves M3 for (a) our answer
to their highest-level player and (b) our lead, with our roster in production display order (skill level
high to low, missing last). It measures how often the decision is an exact tie, what the roster-order
tie-break picks, how the pick changes under other tie-breaks, and the value of those changes under two
evaluators fitted only on pre-2023 games (model-dependent). Writes forensic_ties_<policy>.json.

Usage: python -I forensic_ties.py --db <archive_snapshot.sqlite> --out <dir> [--policy clean]
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
VAL_END, EVAL_END = "2025-08-31", "2022-12-31"
LEVELS = ["Strong", "Solid", "Thin", "Unknown", "Conflicted", "Caution"]
rng = np.random.default_rng(20261123)
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


TRAIN = {"EIGHT": [], "NINE": []}; NIGHTS = {"EIGHT": [], "NINE": []}
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
            hp = [g for g in {g[0] for g in gl if pt.get((g[0], mid)) == m[0]}]
            ap = [g for g in {g[0] for g in gl if pt.get((g[0], mid)) == m[1]}]
            if len(hp) != 5 or len(ap) != 5 or any(not sl.get(x) for x in hp + ap):
                continue
            hp.sort(key=lambda x: (-sl[x], x)); ap.sort(key=lambda x: (-sl[x], x))     # production display order
            NIGHTS[fmt].append({"hp": hp, "ap": ap, "sl": {x: sl[x] for x in hp + ap},
                                "cross": {(h, a): features(fmt, h, a, sl[h], sl[a]) for h in hp for a in ap}})
    if "2013-01-01" <= day <= EVAL_END:
        for p, o, won, slp, slo, mid in obs:
            if (hashlib.md5(f"{mid}|{min(p,o)}|{max(p,o)}".encode()).digest()[0] & 1) != (1 if p < o else 0) or not slp or not slo:
                continue
            x, _ = features(fmt, p, o, slp, slo)
            TRAIN[fmt].append((day, x, int(won)))
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


class Ev:
    def __init__(self, gs, data, lam=10):
        self.gs = gs
        X = np.array([np.concatenate([x[g] for g in gs]) for _, x, _ in data]); y = np.array([w for _, _, w in data], float)
        self.keep = X.std(0) > 0; X = X[:, self.keep]; self.mu, self.sd = X.mean(0), X.std(0)
        self.b = fit((X - self.mu) / self.sd, y, lam)

    def p(self, xs):
        X = np.array([np.concatenate([x[g] for g in self.gs]) for x in xs])[:, self.keep]
        return 1 / (1 + np.exp(-(np.c_[np.ones(len(X)), (X - self.mu) / self.sd] @ self.b)))


for fmt in ("EIGHT", "NINE"):
    evs = {"pre2023_C2": Ev(["SLPAIR", "DIRECT", "SHARED", "RECENT", "FORM"], TRAIN[fmt]), "pre2023_skill": Ev(["SLPAIR"], TRAIN[fmt])}
    st = Counter(); gain = defaultdict(list); tie_sizes = Counter(); unk_share = []
    for nt in NIGHTS[fmt]:
        hp, ap, sl = nt["hp"], nt["ap"], nt["sl"]
        ours = [{"id": h, "name": str(h), "sl": sl[h]} for h in hp]; theirs = [{"id": a, "name": str(a), "sl": sl[a]} for a in ap]
        keys = [(h, a) for h in hp for a in ap]
        m3 = {k: {"points": LEVEL_POINTS[nt["cross"][k][1]["lv"]]} for k in keys}
        unk_share.append(sum(nt["cross"][k][1]["lv"] == "Unknown" for k in keys) / 25)
        top = 0                                  # their highest level (display order), ties to the first listed
        n = _Night(ours, theirs, m3, 5, 23, 0, 23, 0)
        leg = n.legal_ours(n.full_ours)
        if not leg:
            continue
        st["nights"] += 1
        tot = {i: n.pair(i, top) + n.solve(n.full_ours & ~(1 << i), n.full_theirs & ~(1 << top), True) for i in leg}
        best = max(tot.values()); tied = [i for i in leg if tot[i] == best]
        pick = n.best_answer(n.full_ours, n.full_theirs, top)[0]
        tie_sizes[len(tied)] += 1
        meta = nt["cross"][(hp[pick], ap[top])][1]
        st["answer_unknown"] += meta["lv"] == "Unknown"; st["answer_20game_unknown"] += meta["thresh"]
        if len(tied) > 1:
            st["answer_tied"] += 1
            st["tiebreak_picks_highest_sl_among_tied"] += sl[hp[pick]] == max(sl[hp[i]] for i in tied)
            st["tied_candidates_differ_in_sl"] += len({sl[hp[i]] for i in tied}) > 1
            low = min(tied, key=lambda i: (sl[hp[i]], -i))
            xs = [nt["cross"][k][0] for k in keys]
            for name, ev in evs.items():
                vals = {k: {"points": float(v)} for k, v in zip(keys, ev.p(xs))}
                ne = _Night(ours, theirs, vals, 5, 23, 0, 23, 0)
                val = lambda i: ne.pair(i, top) + ne.solve(ne.full_ours & ~(1 << i), ne.full_theirs & ~(1 << top), True)  # noqa: E731
                vbest = max(val(i) for i in tied)
                gain[f"{name}_best_tied_minus_roster_first"].append(vbest - val(pick))
                gain[f"{name}_lowest_sl_tied_minus_roster_first"].append(val(low) - val(pick))
        # lead decision ties
        lead_tot = []
        replies = n.legal_theirs(n.full_ours, n.full_theirs)
        if replies:
            for i in leg:
                lead_tot.append(min(n.pair(i, j) + n.solve(n.full_ours & ~(1 << i), n.full_theirs & ~(1 << j), False) for j in replies))
            st["lead_nights"] += 1
            st["lead_tied"] += sum(1 for v in lead_tot if v == max(lead_tot)) > 1

    def mci(v):
        v = np.array(v, float)
        if not len(v):
            return None
        bs = [rng.choice(v, len(v)).mean() for _ in range(300)]
        return {"n": int(len(v)), "mean": float(v.mean()), "ci": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
                "share_positive": float((v > 1e-9).mean())}
    R[fmt] = {**{k: int(v) for k, v in st.items()}, "tie_size_distribution": {str(k): v for k, v in sorted(tie_sizes.items())},
              "mean_share_of_25_pairings_unknown": float(np.mean(unk_share)),
              "model_dependent_value_of_other_tiebreaks": {k: mci(v) for k, v in gain.items()}}
(OUT / f"forensic_ties_{POLICY}.json").write_text(json.dumps(R, indent=1))
print(json.dumps(R, indent=1))
