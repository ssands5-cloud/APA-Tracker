"""Fit the Ultimate Coach V2 pairing model (win probability per pairing) from a local archive snapshot.

V2 replaces M3's six evidence levels with a calibrated win probability for each (our player, their player)
pairing. The model is the "C2 skill + evidence" logistic model validated in docs/research/issue119
(chronological replay, strictly earlier dates, clean record policy):

  SLPAIR   one indicator per (our SL, their SL) pair in this format (9 x 9)
  DIRECT   shrunk direct win rate - 0.5, log(1 + meetings), any meeting
  SHARED   shared-opponent edge (only when there is no direct record), number of shared opponents
  RECENT   last-10 shrunk win rate - 0.5, ours and theirs
  FORM     recorded career shrunk win rate - 0.5, ours and theirs, and log(1 + games) for each

Steps: replay every decided game in date order, building features only from earlier dates; choose the L2
penalty on a validation window; report test-window log loss / Brier / calibration; refit on everything from
2023 onward for production. Also fits APA team points per individual match win and loss from scored matches.

Writes analytics/uc_v2_model.json: coefficients, standardization, metrics and counts only (no player, team or
match identifiers). Real archive data stays local; only the aggregate model file is committed.

Usage: python -I scripts/fit_uc_v2_pair_model.py --db <archive_snapshot.sqlite> [--out analytics/uc_v2_model.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

REPO = Path(__file__).resolve().parents[1]
FORMATS = {"EIGHT": "EIGHT", "NINE": "NINE", "8-Ball Open": "EIGHT", "9-Ball Open": "NINE"}
START, FIT_END, VAL_END = "2023-01-01", "2025-02-28", "2025-08-31"
LAMBDAS = (0.1, 1, 10, 100, 1000)


def local_day(value) -> str:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt.astimezone(ZoneInfo("America/Denver")) if dt.tzinfo else dt).date().isoformat()


def sh(w, n, k=6):
    return (w + k / 2) / (n + k)


def feature_vector(slp, slo, direct, shared, recent_p, recent_o, form_p, form_o) -> list[float]:
    """The V2 feature vector. Mirrored exactly by analytics/uc_v2_pair_model.py and ui/ultimate_coach_war_room.js."""
    sl = [float(slp == a and slo == b) for a in range(1, 10) for b in range(1, 10)]
    dw, dg = direct if direct else (0, 0)
    x = sl + [sh(dw, dg, 2) - .5, math.log1p(dg), float(dg > 0)]
    if shared and not dg:
        x += [sh(shared[0], shared[1]) - sh(shared[2], shared[3]), float(shared[4])]
    else:
        x += [0.0, 0.0]
    x += [sh(recent_p[0], recent_p[1]) - .5, sh(recent_o[0], recent_o[1]) - .5]
    x += [sh(*form_p) - .5, sh(*form_o) - .5, math.log1p(form_p[1]), math.log1p(form_o[1])]
    return x


def fit(X, y, lam, it=30):
    X1 = np.c_[np.ones(len(X)), X]
    b = np.zeros(X1.shape[1])
    pen = np.eye(len(b)) * lam
    pen[0, 0] = 0
    for _ in range(it):
        p = 1 / (1 + np.exp(-X1 @ b))
        W = p * (1 - p) + 1e-9
        b = b + np.linalg.solve(X1.T @ (X1 * W[:, None]) + pen, X1.T @ (y - p) - pen @ b)
    return b


def predict(b, Z):
    return 1 / (1 + np.exp(-(np.c_[np.ones(len(Z)), Z] @ b)))


def logloss(y, p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def calib(y, p):
    z = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
    b = fit(z[:, None], y, 0.0)
    return round(float(b[0]), 4), round(float(b[1]), 4)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default=str(REPO / "analytics" / "uc_v2_model.json"))
    a = ap.parse_args()
    db = Path(a.db).resolve()
    con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    raw = con.execute("""SELECT h.player_id,h.opponent_id,h.result,h.own_skill_level,h.opponent_skill_level,h.format,
                                m.match_date,h.match_id FROM player_head_to_head h JOIN matches m ON m.id=h.match_id
                         ORDER BY h.rowid""").fetchall()
    # Clean record policy (as in the research): drop repeats; drop both rows of conflicting repeats.
    by_key = defaultdict(list)
    for r in raw:
        by_key[(r[7], r[0], r[1])].append(r)
    identical = {k for k, v in by_key.items() if len(v) > 1 and len({(x[2], x[3], x[4]) for x in v}) == 1}
    conflicting = {k for k, v in by_key.items() if len(v) > 1 and k not in identical}
    kept, seen = [], set()
    for r in raw:
        k = (r[7], r[0], r[1])
        if k in conflicting:
            continue
        if k in identical:
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

    pairs = defaultdict(dict)
    overall = defaultdict(lambda: [0, 0])
    recent = defaultdict(lambda: deque(maxlen=10))
    rows = {"EIGHT": [], "NINE": []}
    for (fmt, day), obs in sorted(games.items()):
        for p, o, won, slp, slo, mid in obs:
            # one orientation per game, chosen by a fixed hash (both mirrored rows describe the same game)
            if (hashlib.md5(f"{mid}|{min(p, o)}|{max(p, o)}".encode()).digest()[0] & 1) != (1 if p < o else 0):
                continue
            if not slp or not slo or day < START:
                continue
            mine, theirs = pairs[(fmt, p)], pairs[(fmt, o)]
            rec = mine.get(o)
            shared = None
            if rec is None:
                common = mine.keys() & theirs.keys() - {p, o}
                if common:
                    shared = (sum(mine[x][0] for x in common), sum(mine[x][1] for x in common),
                              sum(theirs[x][0] for x in common), sum(theirs[x][1] for x in common), len(common))
            rp, ro = recent[(fmt, p)], recent[(fmt, o)]
            x = feature_vector(slp, slo, (rec[0], rec[1]) if rec else None, shared, (sum(rp), len(rp)), (sum(ro), len(ro)),
                               tuple(overall[(fmt, p)]), tuple(overall[(fmt, o)]))
            rows[fmt].append((day, int(won), x))
        for p, o, won, slp, slo, mid in obs:   # update after the whole day: features use strictly earlier dates
            rec = pairs[(fmt, p)].setdefault(o, [0, 0])
            rec[0] += int(won)
            rec[1] += 1
            overall[(fmt, p)][0] += int(won)
            overall[(fmt, p)][1] += 1
            recent[(fmt, p)].append(int(won))

    # APA team points per individual win / loss, from scored matches (least squares, per format)
    mt = {r[0]: r[1:] for r in con.execute("SELECT id,home_team_id,away_team_id,home_score,away_score,format FROM matches "
                                           "WHERE is_scored=1 AND (is_bye=0 OR is_bye IS NULL)")}
    team = {(r[0], r[1]): r[2] for r in con.execute("SELECT player_id,match_id,team_id FROM player_matches")}
    wins = defaultdict(lambda: [0, 0])          # (match, side) -> [wins, games]
    for p, o, res, slp, slo, fmt, day, mid in kept:
        if res not in ("W", "L") or mid not in mt:
            continue
        side = team.get((p, mid))
        if side is None:
            continue
        w = wins[(mid, side)]
        w[0] += int(res == "W")
        w[1] += 1
    pts = {"EIGHT": [], "NINE": []}
    for (mid, side), (w, g) in wins.items():
        home, away, hs, as_, fmt = mt[mid]
        f = FORMATS.get(fmt)
        if f is None or hs is None or as_ is None or g == 0 or local_day(mt_date(con, mid)) < START:
            continue
        score = hs if side == home else as_ if side == away else None
        if score is not None:
            pts[f].append((w, g - w, float(score)))

    out = {"model": "uc_v2_pairing_win_probability", "version": 1,
           "description": "Logistic win probability per pairing (issue #119 C2 skill+evidence model). Aggregates only.",
           "snapshot_sha256": hashlib.sha256(db.read_bytes()).hexdigest(),
           "features": ["SLPAIR[81]", "DIRECT_RATE", "DIRECT_LOGN", "DIRECT_ANY", "SHARED_EDGE", "SHARED_N",
                        "RECENT_OURS", "RECENT_THEIRS", "FORM_OURS", "FORM_THEIRS", "FORM_LOGN_OURS", "FORM_LOGN_THEIRS"],
           "formats": {}}
    for fmt in ("EIGHT", "NINE"):
        days = np.array([r[0] for r in rows[fmt]])
        y = np.array([r[1] for r in rows[fmt]], float)
        X = np.array([r[2] for r in rows[fmt]], float)
        fit_m, val_m = days <= FIT_END, (days > FIT_END) & (days <= VAL_END)
        train_m, test_m = days <= VAL_END, days > VAL_END
        mu, sd = X[train_m].mean(0), X[train_m].std(0)
        sd[sd == 0] = 1.0
        Z = (X - mu) / sd
        best = min(LAMBDAS, key=lambda lam: logloss(y[val_m], predict(fit(Z[fit_m], y[fit_m], lam), Z[val_m])))
        b = fit(Z[train_m], y[train_m], best)
        pt = predict(b, Z[test_m])
        base = np.full(test_m.sum(), y[train_m].mean())
        metrics = {"lambda": best, "train_games": int(train_m.sum()), "test_games": int(test_m.sum()),
                   "test_window": f"{VAL_END} < day", "test_logloss": round(logloss(y[test_m], pt), 5),
                   "test_logloss_constant": round(logloss(y[test_m], base), 5),
                   "test_brier": round(float(((pt - y[test_m]) ** 2).mean()), 5),
                   "test_calibration_intercept_slope": calib(y[test_m], pt)}
        # production refit on every game from START onward, same penalty and standardization rule
        mu_all, sd_all = X.mean(0), X.std(0)
        sd_all[sd_all == 0] = 1.0
        b_all = fit((X - mu_all) / sd_all, y, best)
        P = np.array(pts[fmt], float)
        A = np.c_[P[:, 0], P[:, 1]]
        coef, *_ = np.linalg.lstsq(A, P[:, 2], rcond=None)
        out["formats"][fmt] = {"intercept": round(float(b_all[0]), 6), "coef": [round(float(c), 6) for c in b_all[1:]],
                               "mu": [round(float(v), 6) for v in mu_all], "sd": [round(float(v), 6) for v in sd_all],
                               "games": int(len(y)), "holdout": metrics,
                               "team_points": {"per_individual_win": round(float(coef[0]), 4),
                                               "per_individual_loss": round(float(coef[1]), 4),
                                               "team_nights": int(len(P))}}
        print(fmt, json.dumps(metrics), out["formats"][fmt]["team_points"])
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print("wrote", a.out)


_DATES: dict = {}


def mt_date(con, mid):
    if not _DATES:
        _DATES.update(dict(con.execute("SELECT id,match_date FROM matches")))
    return _DATES[mid]


if __name__ == "__main__":
    sys.exit(main())
