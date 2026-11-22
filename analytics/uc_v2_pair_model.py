"""Ultimate Coach V2 candidate: calibrated win probability for one pairing.

V2 keeps M3's exact lineup search (cap rules, put-up order, opponent's best reply) and replaces only the value
of a pairing: instead of six evidence levels worth 6/3/1/0/0/-3 points, each pairing is worth its estimated
probability of winning, from the skill + evidence model validated in docs/research/issue119 (fitted by
scripts/fit_uc_v2_pair_model.py; coefficients in analytics/uc_v2_model.json).

Consequences, by construction and for every player:
- A skill gap counts by format (one coefficient per skill-level pair per format), so SL3 vs SL7 in 8-Ball is
  a large underdog even with no meetings, instead of "Unknown = even".
- Missing evidence is never "even": the skill pair and recorded form still inform the estimate; the evidence
  that is missing is disclosed.
- Direct history, shared opponents, last-10 form and recorded career all enter the same estimate.

This module is the reference implementation; ui/ultimate_coach_war_room.js mirrors it (tests check parity).
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

MODEL_PATH = Path(__file__).with_name("uc_v2_model.json")

# Win-probability bands shown to captains (percent for our player). Bands describe the estimate, not a promise.
BANDS = ((60, "Favored"), (53, "Edge"), (47, "Toss-up"), (40, "Underdog"), (0, "Long shot"))
V2_LEVEL_ORDER = ["Favored", "Edge", "Toss-up", "Underdog", "Long shot"]


@lru_cache(maxsize=1)
def load_model(path: str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or MODEL_PATH).read_text(encoding="utf-8"))


def _sh(w: float, n: float, k: float = 6) -> float:
    return (w + k / 2) / (n + k)


def feature_vector(slp, slo, direct, shared, recent_p, recent_o, form_p, form_o) -> list[float]:
    """Identical to scripts/fit_uc_v2_pair_model.feature_vector (checked by tests)."""
    sl = [float(slp == a and slo == b) for a in range(1, 10) for b in range(1, 10)]
    dw, dg = direct if direct else (0, 0)
    x = sl + [_sh(dw, dg, 2) - .5, math.log1p(dg), float(dg > 0)]
    if shared and not dg:
        x += [_sh(shared[0], shared[1]) - _sh(shared[2], shared[3]), float(shared[4])]
    else:
        x += [0.0, 0.0]
    x += [_sh(recent_p[0], recent_p[1]) - .5, _sh(recent_o[0], recent_o[1]) - .5]
    x += [_sh(*form_p) - .5, _sh(*form_o) - .5, math.log1p(form_p[1]), math.log1p(form_o[1])]
    return x


def _known(sl) -> bool:
    return isinstance(sl, (int, float)) and not isinstance(sl, bool) and 1 <= sl <= 9


def _one_side(m: dict[str, Any], x: list[float]) -> float:
    z = m["intercept"]
    for i, v in enumerate(x):
        z += m["coef"][i] * (v - m["mu"][i]) / m["sd"][i]
    return 1 / (1 + math.exp(-z))


def _raw(fmt, slp, slo, direct, shared, recent_p, recent_o, form_p, form_o, model) -> float:
    m = model["formats"][fmt]
    x = feature_vector(slp, slo, direct, shared, recent_p, recent_o, form_p, form_o)
    if not (_known(slp) and _known(slo)):
        # An unknown skill level: the skill-pair block takes its average (z = 0) rather than a pair it is not.
        for i in range(81):
            x[i] = m["mu"][i]
    return _one_side(m, x)


def win_probability(fmt: str, slp, slo, *, direct=None, shared=None, recent_p=(0, 0), recent_o=(0, 0),
                    form_p=(0, 0), form_o=(0, 0), model: dict[str, Any] | None = None) -> float | None:
    """Our player's estimated chance of winning this pairing, or None for formats without a V2 model.

    direct=(our wins, meetings); shared=(our wins, our games, their wins, their games, n opponents) vs shared
    opponents; recent_*=(wins, games) over the last 10; form_*=(wins, games) recorded in this format.
    Symmetric by construction: P(we win) = 1 - P(they win)."""
    model = model or load_model()
    if fmt not in model["formats"]:
        return None
    rev_direct = (direct[1] - direct[0], direct[1]) if direct else None
    rev_shared = (shared[2], shared[3], shared[0], shared[1], shared[4]) if shared else None
    a = _raw(fmt, slp, slo, direct, shared, recent_p, recent_o, form_p, form_o, model)
    b = _raw(fmt, slo, slp, rev_direct, rev_shared, recent_o, recent_p, form_o, form_p, model)
    return (a + (1 - b)) / 2


def band(p: float) -> str:
    pct = 100 * p
    for floor, name in BANDS:
        if pct >= floor:
            return name
    return BANDS[-1][1]


def evidence_gaps(direct, shared, form_p, form_o, slp, slo) -> list[str]:
    gaps = []
    if not (_known(slp) and _known(slo)):
        gaps.append("skill level missing")
    if not direct or not direct[1]:
        gaps.append("no direct meetings" + ("" if shared and shared[4] else ", no shared opponents"))
    if form_p[1] < 10 or form_o[1] < 10:
        gaps.append("fewer than 10 recorded games for " + ("both players" if form_p[1] < 10 and form_o[1] < 10
                                                            else "our player" if form_p[1] < 10 else "their player"))
    return gaps


def pair_value(fmt, slp, slo, **kw) -> dict[str, Any] | None:
    """The V2 value of a pairing in the shape the lineup search uses: points = floor(1000 * (p - 0.5) + 0.5) (tenths of a point), half-up as in the JS mirror."""
    p = win_probability(fmt, slp, slo, **kw)
    if p is None:
        return None
    lv = band(p)
    gaps = evidence_gaps(kw.get("direct"), kw.get("shared"), kw.get("form_p", (0, 0)), kw.get("form_o", (0, 0)), slp, slo)
    why = f"{round(100 * p)}% estimated win chance" + (" · " + "; ".join(gaps) if gaps else "")
    return {"level": lv, "points": math.floor(1000 * (p - 0.5) + 0.5), "p": p, "why": why, "text": f"{lv} — {why}", "v2": True,
            "gaps": gaps}


def team_points(fmt: str, p: float, model: dict[str, Any] | None = None) -> float | None:
    """Expected APA team points from one individual match won with probability p (archive least-squares fit)."""
    model = model or load_model()
    tp = model["formats"].get(fmt, {}).get("team_points")
    if not tp:
        return None
    return p * tp["per_individual_win"] + (1 - p) * tp["per_individual_loss"]
