"""Reference port of the executed V2 captain-control policy.

This is the policy layer only, not a workbook integration or a new model.
Inputs are remaining players in browser roster order, an already computed
V2 probability matrix keyed by (stable player ID, stable opponent ID),
remaining games, cap and previously spent skill levels. Availability and
played-match state must be resolved by the calling adapter before this
function is called. Unknown skill levels retain the existing _Night
incomplete-cap semantics. Missing pair probabilities fail closed.
"""
from __future__ import annotations

from functools import lru_cache
from math import isfinite

from analytics.match_night_engine import _Night, _known

POLICY_VERSION = "v2-captain-control-683d5f5"
STRATEGIC_GAIN = 0.10
PRACTICAL_TIE = 0.01
PLAN_TIE = 0.02
EPS = 1e-12


def _best(rows, field):
    """JS reduce: keep first roster entry unless improvement exceeds EPS."""
    best = rows[0]
    for row in rows[1:]:
        if row[field] > best[field] + EPS:
            best = row
    return best


def classify(rows):
    """Mirror v2Classify, including strict tie boundaries and role priority."""
    now = _best(rows, "p")
    strat = _best(rows, "totalWorst")
    avg = _best(rows, "totalAvg")
    gain_w = strat["totalWorst"] - now["totalWorst"]
    gain_a = strat["totalAvg"] - now["totalAvg"]
    strategic = strat is not now and gain_w >= STRATEGIC_GAIN and gain_a >= STRATEGIC_GAIN
    pick = strat if strategic else now
    for r in rows:
        r["tiedNow"] = r is not now and now["p"] - r["p"] < PRACTICAL_TIE
        r["equalPlan"] = (r is not pick and abs(r["totalWorst"] - pick["totalWorst"]) < PLAN_TIE
                          and abs(r["totalAvg"] - pick["totalAvg"]) < PLAN_TIE)
        if r is pick:
            p = r["p"]
            if strategic:
                role = "Strategic choice (deliberate concession)" if p < .40 else "Strategic choice"
            elif p >= .47:
                role = "Recommended competitive matchup"
            elif p >= .40:
                role = "Recommended (underdog)"
            else:
                role = "Best available (every option is a long shot)"
        elif r is now:
            role = "Strongest matchup now"
        elif r is strat:
            role = "Strategic alternative"
        elif r is avg:
            role = "Best if they choose evenly"
        elif r["tiedNow"]:
            role = "Practically tied with the strongest"
        elif r["equalPlan"]:
            role = "Practically equal plan"
        else:
            role = ""
        r["role"] = role
    return dict(rows=rows, now=now, strat=strat, avgBest=avg, pick=pick,
                strategic=strategic, gainWorst=gain_w, gainAvg=gain_a)


class V2Policy:
    """Same two-opponent-model rollouts and roster-order ties as browser V2."""

    def __init__(self, ours, theirs, probabilities, games, cap, used=0, opp_used=0):
        self.ours = tuple(dict(p, id=str(p["id"])) for p in ours)
        self.theirs = tuple(dict(p, id=str(p["id"])) for p in theirs)
        for roster in (self.ours, self.theirs):
            ids = [p["id"] for p in roster]
            if len(set(ids)) != len(ids) or any(not i for i in ids):
                raise ValueError("Ambiguous player ID")
        if type(games) is not int or not 0 <= games <= 5:
            raise ValueError("Invalid remaining game count")
        if any(type(v) not in (int, float) or not isfinite(v) or v < 0 for v in (used, opp_used)):
            raise ValueError("Invalid prior skill spend")
        if cap is not None and (type(cap) not in (int, float) or not isfinite(cap) or cap < 0):
            raise ValueError("Invalid cap")
        self.p = {}
        for i, o in enumerate(self.ours):
            for j, t in enumerate(self.theirs):
                key = (o["id"], t["id"])
                p = probabilities.get(key)
                if type(p) not in (float, int) or not isfinite(p) or not 0 <= p <= 1:
                    raise ValueError(f"Missing/invalid V2 probability for {key}")
                self.p[i, j] = float(p)
        self.night = _Night(self.ours, self.theirs, {}, games, cap, used, cap, opp_used)
        self.opponent_cap_relaxed = bool(cap is not None and games and
                                         not self.night.legal_theirs(self.night.full_ours, self.night.full_theirs))
        if self.opponent_cap_relaxed:
            self.night = _Night(self.ours, self.theirs, {}, games, cap, used, None, opp_used)
        # Per-instance caches: don't retain private rosters in a process-wide cache.
        self.state = lru_cache(maxsize=None)(self._state)
        self.respond = lru_cache(maxsize=None)(self._respond)

    def _state(self, om, tm, we_lead):
        ours = self.night.legal_ours(om)
        theirs = self.night.legal_theirs(om, tm)
        if not ours or not theirs:
            return dict(w=0., a=0.)
        if we_lead:
            rows = []
            for i in ours:
                w, a, reply = float("inf"), 0., None
                for j in theirs:
                    c = self.state(om & ~(1 << i), tm & ~(1 << j), False)
                    p = self.p[i, j]
                    if p + c["w"] < w:
                        w, reply = p + c["w"], j
                    a += (p + c["a"]) / len(theirs)
                rows.append(dict(i=i, w=w, a=a, reply=reply))
            top = max(r["w"] for r in rows)
            best = _best([r for r in rows if r["w"] >= top - PLAN_TIE], "a")
            return dict(w=best["w"], a=best["a"], lead=best, rows=rows)
        w, a, worst_j = float("inf"), 0., None
        for j in theirs:
            r = self.respond(om, tm, j)
            if r["w"] < w:
                w, worst_j = r["w"], j
            a += r["a"] / len(theirs)
        return dict(w=w, a=a, worstJ=worst_j)

    def _respond(self, om, tm, j):
        if j not in self.night.legal_theirs(om, tm):
            raise ValueError("Opponent is not legal in this state")
        rows = []
        for i in self.night.legal_ours(om):
            c = self.state(om & ~(1 << i), tm & ~(1 << j), True)
            p = self.p[i, j]
            rows.append(dict(i=i, p=p, restWorst=c["w"], restAvg=c["a"],
                             totalWorst=p+c["w"], totalAvg=p+c["a"]))
        if not rows:
            raise ValueError("No legal response")
        o = classify(rows)
        o.update(w=o["pick"]["totalWorst"], a=o["pick"]["totalAvg"], i=o["pick"]["i"])
        return o

    def line(self, om, tm, we_lead):
        out = []
        while self.night.legal_ours(om) and self.night.legal_theirs(om, tm):
            s = self.state(om, tm, we_lead)
            if we_lead:
                i, j = s["lead"]["i"], s["lead"]["reply"]
            else:
                j = s["worstJ"]
                i = self.respond(om, tm, j)["i"]
            out.append(dict(leader="us" if we_lead else "them", our_id=self.ours[i]["id"],
                            their_id=self.theirs[j]["id"], p=self.p[i, j]))
            om, tm, we_lead = om & ~(1 << i), tm & ~(1 << j), not we_lead
        return out

    def trace(self):
        """Stable-ID decision facts for workbook rendering and cross-runtime tests.

        Every opponent is keyed by ID, never display name. Rows retain roster
        order, not a newly invented rank. This deliberately does not expose
        M3, or claim support for shortened APA 4/19 play or actual team points.
        """
        n = self.night
        om, tm = n.full_ours, n.full_theirs
        L, T = self.state(om, tm, True), self.state(om, tm, False)
        out = dict(policy=POLICY_VERSION, opponent_cap_relaxed=self.opponent_cap_relaxed,
                   cap_incomplete=n.cap is not None and any(not _known(p["sl"]) for p in self.ours),
                   opponent_cap_incomplete=n.opp_cap is not None and any(not _known(p["sl"]) for p in self.theirs),
                   lead=None, responses={}, totals={"us": {"w": L["w"], "a": L["a"]},
                                                     "them": {"w": T["w"], "a": T["a"]}},
                   lines={"us": self.line(om, tm, True), "them": self.line(om, tm, False)})
        if "lead" not in L:
            return out
        def lead_row(r):
            return dict(our_id=self.ours[r["i"]]["id"], their_id=self.theirs[r["reply"]]["id"],
                        w=r["w"], a=r["a"], p=self.p[r["i"], r["reply"]])
        out["lead"] = lead_row(L["lead"])
        out["lead_options"] = [lead_row(r) for r in L["rows"]]
        out["lead_equal_ids"] = [self.ours[r["i"]]["id"] for r in L["rows"] if r is not L["lead"]
                                 and abs(r["w"]-L["lead"]["w"]) < PLAN_TIE
                                 and abs(r["a"]-L["lead"]["a"]) < PLAN_TIE]
        for j in n.legal_theirs(om, tm):
            r = self.respond(om, tm, j)
            ids = {k: self.ours[r[k]["i"]]["id"] for k in ("pick", "now", "strat", "avgBest")}
            rows = []
            for row in r["rows"]:
                i = row["i"]
                item = {k: v for k, v in row.items() if k != "i"}
                item.update(our_id=self.ours[i]["id"], later=self.line(om & ~(1 << i), tm & ~(1 << j), True))
                rows.append(item)
            out["responses"][self.theirs[j]["id"]] = dict(**ids, rows=rows, strategic=r["strategic"],
                                                            gainWorst=r["gainWorst"], gainAvg=r["gainAvg"])
        return out
