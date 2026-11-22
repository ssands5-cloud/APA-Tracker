"""Captain-facing V2 wording, identical to the browser's (v2Pct, v2Wins, v2OptionsText, v2PairValue text).

Works on `analytics.uc_v2_policy.V2Policy.trace()` output plus display names keyed by stable ID. Numbers are rounded
exactly as JavaScript does (Math.round and Number.prototype.toFixed round halves up), not with Python's half-even.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from analytics.uc_v2_pair_model import band

PLAN_TIE_TEXT = "0.02"        # String(V2_PLAN_TIE) in the page
MIN_GAIN_TEXT = "0.10"        # V2_STRATEGIC_MIN_GAIN.toFixed(2)


def js_round(x: float) -> int:
    return math.floor(x + 0.5)


def js_fixed(x: float, digits: int) -> str:
    """Number.prototype.toFixed: exact binary value, halves away from zero; -0 prints as 0."""
    return str(Decimal(0.0 if x == 0 else x).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def pct(p: float) -> str:
    return f"{js_round(100 * p)}%"


def wins(x: float) -> str:
    return ("+" if x >= 0 else "") + js_fixed(x, 3)


def pair_text(p: float, gaps: list[str]) -> str:
    """v2PairValue text: '<band> — <n>% estimated win chance[ · gap; gap]'."""
    why = f"{js_round(100 * p)}% estimated win chance" + (" · " + "; ".join(gaps) if gaps else "")
    return f"{band(p)} — {why}"


def options_text(resp: dict[str, Any], our_names: dict[str, str], their_names: dict[str, str]) -> str:
    """v2OptionsText for one put-up: resp = trace()['responses'][their_id]."""
    rows = {r["our_id"]: r for r in resp["rows"]}
    nm = lambda oid: our_names[oid]
    def later(oid):
        return ", ".join(f"{our_names[g['our_id']]} vs {their_names[g['their_id']]}" for g in rows[oid]["later"][:2])
    tied = [nm(r["our_id"]) for r in resp["rows"] if r.get("tiedNow")]
    equal = [nm(r["our_id"]) for r in resp["rows"] if r.get("equalPlan")]
    tie = ((" Practically tied now with " + ", ".join(tied) + " (within 1 point).") if tied else "") + \
          ((" Practically equal plan with " + ", ".join(equal) + f" instead (within {PLAN_TIE_TEXT} expected wins either way); your read decides.") if equal else "")
    pick, now, strat = resp["pick"], resp["now"], resp["strat"]
    pn, ps = rows[now]["p"], rows[strat]["p"]
    if pick == now and strat == now:
        return f"Strongest matchup available ({pct(pn)}) and also the best plan for the rest of the night." + tie
    if pick == now:
        return (f"Strongest matchup available ({pct(pn)})." + tie + f" Strategic alternative: {nm(strat)} ({pct(ps)}) keeps {nm(now)}"
                f" for later ({later(strat)}): {wins(resp['gainWorst'])} expected wins only if they always make their most damaging choice, "
                f"{wins(resp['gainAvg'])} if they choose evenly. Not enough to give up the stronger matchup (needs {MIN_GAIN_TEXT} under both).")
    return (f"Strategic choice: {nm(strat)} ({pct(ps)}) instead of the strongest matchup {nm(now)} ({pct(pn)}). It keeps {nm(now)}"
            f" for later ({later(strat)}): {wins(resp['gainWorst'])} expected wins if they make their most damaging choices, "
            f"{wins(resp['gainAvg'])} if they choose evenly." + tie + " The captain may prefer the stronger matchup now.")
