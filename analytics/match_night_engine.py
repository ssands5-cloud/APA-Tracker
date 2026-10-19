"""Match Night Engine (M3): a dynamic captain plan, not a fixed board.

APA captains alternate putting players up, so the opposing captain controls half the matchups. This engine
plays the rest of the night out the way a strong captain thinks about it:

* each pairing is worth its captain confidence level (analytics.ultimate_coach_confidence): Strong 4,
  Solid 2, Thin 1, Unknown/Conflicted 0, Caution -2 -- recorded evidence only, never a probability;
* put-ups alternate; the other captain is assumed to make the choice that hurts us most (minimax), so the
  plan holds up against their best reply rather than hoping for a cooperative one;
* every choice of ours must keep the rest of the night under the team skill cap when one is entered. A
  missing skill level never counts as 0: it cannot be checked, so the cap check is reported incomplete.

It answers the six captain questions -- lead pick, response table, hold-backs, sacrifices, what a choice
costs later, and the game plan -- plus the best-case and safest boards, match confidence, fragility and cap
safety. Deterministic: candidates are tried in roster order and only a strictly better value replaces the
current choice, so ui/ultimate_coach_war_room.js (which mirrors this module) produces the identical plan.
"""

from __future__ import annotations

from itertools import combinations, permutations
from typing import Any

GAMES_PER_MATCH = 5          # APA 8-Ball / 9-Ball singles team match
LEVEL_ORDER = ("Strong", "Solid", "Thin", "Unknown", "Conflicted", "Caution")


def _known(sl: Any) -> bool:
    return type(sl) in (int, float) and sl > 0


class _Night:
    def __init__(self, ours, theirs, value, games_left, cap, used):
        self.ours, self.theirs, self.value = ours, theirs, value
        self.games_left, self.cap, self.used = games_left, cap, used
        self.full_ours = (1 << len(ours)) - 1
        self.full_theirs = (1 << len(theirs)) - 1
        self.memo: dict[tuple[int, int, bool], int] = {}

    # ---- skill cap ----
    def spent(self, om: int) -> int:
        """Known skill levels of our players already sent in this search."""
        return sum(int(p["sl"]) for i, p in enumerate(self.ours)
                   if not om >> i & 1 and _known(p["sl"]))

    def legal(self, om: int, i: int, games_after: int) -> bool:
        if self.cap is None or not _known(self.ours[i]["sl"]):
            return True
        rest = sorted(int(p["sl"]) for k, p in enumerate(self.ours)
                      if om >> k & 1 and k != i and _known(p["sl"]))
        unknown = sum(1 for k, p in enumerate(self.ours) if om >> k & 1 and k != i and not _known(p["sl"]))
        need = max(0, games_after - unknown)       # unknown SLs can fill slots but cannot be checked
        if need > len(rest):
            need = len(rest)
        return self.used + self.spent(om) + int(self.ours[i]["sl"]) + sum(rest[:need]) <= self.cap

    def games_remaining(self, om: int) -> int:
        played = bin(self.full_ours).count("1") - bin(om).count("1")
        return self.games_left - played

    # ---- minimax ----
    def solve(self, om: int, tm: int, we_lead: bool) -> int:
        key = (om, tm, we_lead)
        if key in self.memo:
            return self.memo[key]
        g = self.games_remaining(om)
        ours = [i for i in range(len(self.ours)) if om >> i & 1 and self.legal(om, i, g - 1)] if g > 0 else []
        theirs = [j for j in range(len(self.theirs)) if tm >> j & 1] if g > 0 else []
        if not ours or not theirs:
            self.memo[key] = 0
            return 0
        if we_lead:
            best = None
            for i in ours:
                worst = None
                for j in theirs:
                    v = self.pair(i, j) + self.solve(om & ~(1 << i), tm & ~(1 << j), False)
                    if worst is None or v < worst:
                        worst = v
                if best is None or worst > best:
                    best = worst
        else:
            best = None
            for j in theirs:
                top = None
                for i in ours:
                    v = self.pair(i, j) + self.solve(om & ~(1 << i), tm & ~(1 << j), True)
                    if top is None or v > top:
                        top = v
                if best is None or top < best:
                    best = top
        self.memo[key] = best
        return best

    def pair(self, i: int, j: int) -> int:
        return self.value[(self.ours[i]["id"], self.theirs[j]["id"])]["points"]

    def legal_ours(self, om: int) -> list[int]:
        g = self.games_remaining(om)
        return [i for i in range(len(self.ours)) if om >> i & 1 and self.legal(om, i, g - 1)] if g > 0 else []

    def best_answer(self, om: int, tm: int, j: int) -> tuple[int | None, int]:
        """Our best answer to their player j, looking ahead: (our index, plan total)."""
        best_i, best_v = None, None
        for i in self.legal_ours(om):
            v = self.pair(i, j) + self.solve(om & ~(1 << i), tm & ~(1 << j), True)
            if best_v is None or v > best_v:
                best_i, best_v = i, v
        return best_i, (best_v if best_v is not None else 0)

    def lead(self, om: int, tm: int) -> tuple[int | None, int | None, int]:
        """Our lead pick when we put up first: (our index, their most damaging reply, plan total)."""
        best = (None, None, None)
        for i in self.legal_ours(om):
            reply, worst = None, None
            for j in range(len(self.theirs)):
                if not tm >> j & 1:
                    continue
                v = self.pair(i, j) + self.solve(om & ~(1 << i), tm & ~(1 << j), False)
                if worst is None or v < worst:
                    reply, worst = j, v
            if reply is not None and (best[2] is None or worst > best[2]):
                best = (i, reply, worst)
        return best[0], best[1], (best[2] if best[2] is not None else 0)

    def principal_line(self, om: int, tm: int, we_lead: bool) -> list[dict[str, Any]]:
        """The game plan: both sides at their best from here, one entry per remaining game."""
        line = []
        while self.games_remaining(om) > 0 and self.legal_ours(om) and tm:
            if we_lead:
                i, j, _ = self.lead(om, tm)
            else:
                j, worst = None, None
                for jj in range(len(self.theirs)):
                    if not tm >> jj & 1:
                        continue
                    _, v = self.best_answer(om, tm, jj)
                    if worst is None or v < worst:
                        j, worst = jj, v
                i, _ = self.best_answer(om, tm, j)
            if i is None or j is None:
                break
            line.append({"leader": "us" if we_lead else "them", "our": i, "their": j})
            om, tm, we_lead = om & ~(1 << i), tm & ~(1 << j), not we_lead
        return line


def _board(night: _Night, k: int, safest: bool) -> list[tuple[int, int]]:
    """Best-case (highest total) or safest (best worst pairing, then total) board of k games under the cap."""
    best_key, best = None, []
    no, nt = len(night.ours), len(night.theirs)
    for their_set in combinations(range(nt), k):
        for our_seq in permutations(range(no), k):
            if night.cap is not None:
                known = [int(night.ours[i]["sl"]) for i in our_seq if _known(night.ours[i]["sl"])]
                if night.used + sum(known) > night.cap:
                    continue
            vals = [night.pair(i, j) for i, j in zip(our_seq, their_set)]
            key = (min(vals), sum(vals)) if safest else (sum(vals), min(vals))
            if best_key is None or key > best_key:
                best_key, best = key, list(zip(our_seq, their_set))
    return best


def match_plan(ours: list[dict[str, Any]], theirs: list[dict[str, Any]],
               value: dict[tuple[Any, Any], dict[str, Any]], *, games_left: int,
               cap: int | None = None, used: int = 0) -> dict[str, Any]:
    """The captain's plan for the rest of the night.

    ours / theirs: remaining available players in roster order, each {"id", "name", "sl"}.
    value: (our id, their id) -> pair confidence ({"level", "points", "why", "text"}).
    games_left: games still to play tonight. cap / used: entered skill cap and SL already used (or None).
    """
    games_left = max(0, min(games_left, len(ours), len(theirs)))
    night = _Night(ours, theirs, value, games_left, cap, used)
    om, tm = night.full_ours, night.full_theirs
    name = lambda side, i: (night.ours if side == "our" else night.theirs)[i]["name"]   # noqa: E731
    conf = lambda i, j: night.value[(night.ours[i]["id"], night.theirs[j]["id"])]      # noqa: E731
    incomplete = cap is not None and any(not _known(p["sl"]) for p in ours)
    out: dict[str, Any] = {"games_left": games_left, "cap_incomplete": incomplete}
    if not games_left or not night.legal_ours(om):
        out.update(lead=None, responses=[], holds=[], sacrifices=[], plan_if_we_lead=[], plan_if_they_lead=[],
                   best_board=[], safest_board=[], confidence={}, fragility=None, cap=_cap_safety(night, om))
        return out

    # 1. Lead pick (if we put up first) and their most damaging reply.
    li, lj, _ = night.lead(om, tm)
    out["lead"] = {"our": name("our", li), "their_reply": name("their", lj), "level": conf(li, lj)["level"],
                   "why": conf(li, lj)["text"]}

    # 2. Response table (if they put up first), with what each answer costs later.
    total_if_they_lead = night.solve(om, tm, False)
    responses = []
    for j in range(len(theirs)):
        i, v = night.best_answer(om, tm, j)
        if i is None:
            continue
        # The evidence-only answer: best pairing tonight with no look-ahead (ties in roster order).
        naive = max(night.legal_ours(om), key=lambda x: (night.pair(x, j), -x))
        cost = ""
        if naive != i and night.pair(naive, j) > night.pair(i, j):
            later = v - (night.pair(naive, j) + night.solve(om & ~(1 << naive), tm & ~(1 << j), True))
            cost = (f"{name('our', naive)} is the stronger answer tonight ({conf(naive, j)['level']}), but sending "
                    f"them now costs more later; keep {name('our', naive)} for the rest of the night") if later > 0 else ""
        responses.append({"their": name("their", j), "our": name("our", i), "level": conf(i, j)["level"],
                          "why": conf(i, j)["text"], "cost_later": cost})
    out["responses"] = responses

    # 3/8. Hold-backs and one-player fragility: how much the plan drops without each of our players.
    base = night.solve(om, tm, True)
    drops = []
    for i in range(len(ours)):
        if not om >> i & 1:
            continue
        sub = _Night([p for k, p in enumerate(ours) if k != i], theirs, value, min(games_left, len(ours) - 1, len(theirs)),
                     cap, used)
        sub_val = sub.solve(sub.full_ours, sub.full_theirs, True)
        drops.append((base - sub_val, i))
    plan_lead = night.principal_line(om, tm, True)
    plan_them = night.principal_line(om, tm, False)
    def covers(i: int) -> list[int]:
        """Opponents this player is our only Strong/Solid answer to, strongest first."""
        good = ("Strong", "Solid")
        mine = [j for j in range(len(theirs)) if conf(i, j)["level"] in good
                and not any(conf(k, j)["level"] in good and conf(k, j)["points"] >= conf(i, j)["points"]
                            for k in range(len(ours)) if k != i)]
        return sorted(mine, key=lambda j: (-conf(i, j)["points"], j))

    holds = []
    for drop, i in sorted(drops, key=lambda d: (-d[0], d[1])):
        if drop <= 0:
            continue
        cov = covers(i)
        if cov:
            j = cov[0]
            why = f"our only {conf(i, j)['level']} answer to {name('their', j)} — {conf(i, j)['why']}"
        else:
            j = max(range(len(theirs)), key=lambda x: (conf(i, x)["points"], -x))
            why = (f"best answer to {name('their', j)} ({conf(i, j)['level']}); the plan is weaker without them"
                   if conf(i, j)["points"] > 0 else "the plan is weaker without them")
        holds.append({"our": name("our", i), "why": why, "covers": [name("their", x) for x in cov]})
    out["holds"] = [h for h in holds if h["our"] != out["lead"]["our"]][:3]
    kept = [h["our"] for h in out["holds"] if h["covers"]]
    out["lead"]["why_lead"] = (
        f"Lead {out['lead']['our']}: " + (f"keeps {', '.join(kept)} for their best answers; " if kept else "")
        + f"their most damaging reply is {out['lead']['their_reply']} ({out['lead']['level']} for us)")

    # 4. Sacrifices: the cheapest concessions -- planned pairings worth little, using players we lose least without.
    drop_of = {i: d for d, i in drops}
    weak = [p for p in plan_lead if conf(p["our"], p["their"])["points"] <= 0]
    weak.sort(key=lambda p: (drop_of.get(p["our"], 0), conf(p["our"], p["their"])["points"], p["our"]))
    out["sacrifices"] = [{"our": name("our", p["our"]), "their": name("their", p["their"]),
                          "level": conf(p["our"], p["their"])["level"],
                          "why": f"lowest-cost concession — {conf(p['our'], p['their'])['text']}"} for p in weak[:2]]

    # 7. Game plan both ways (coin toss decides who leads).
    def describe(line):
        return [{"game": n + 1, "leader": p["leader"], "our": name("our", p["our"]), "their": name("their", p["their"]),
                 "level": conf(p["our"], p["their"])["level"]} for n, p in enumerate(line)]
    out["plan_if_we_lead"], out["plan_if_they_lead"] = describe(plan_lead), describe(plan_them)

    # 5/6. Boards.
    def board(pairs):
        return [{"our": name("our", i), "their": name("their", j), "level": conf(i, j)["level"]} for i, j in pairs]
    out["best_board"] = board(_board(night, games_left, safest=False))
    out["safest_board"] = board(_board(night, games_left, safest=True))

    # 7. Match confidence: levels across the game plan (we lead), in a fixed order.
    counts = {lv: 0 for lv in LEVEL_ORDER}
    for p in plan_lead:
        counts[conf(p["our"], p["their"])["level"]] += 1
    out["confidence"] = {lv: n for lv, n in counts.items() if n}

    # 8. Fragility: the one player, the one thin pairing.
    worst_drop, worst_i = max(drops, key=lambda d: (d[0], -d[1])) if drops else (0, None)
    thin = [p for p in plan_lead if conf(p["our"], p["their"])["level"] in ("Thin", "Conflicted")]
    out["fragility"] = {
        "player": name("our", worst_i) if worst_drop > 0 else None,
        "player_drop": worst_drop,
        "thin_pairings": [f"{name('our', p['our'])} vs {name('their', p['their'])} ({conf(p['our'], p['their'])['level']})"
                          for p in thin],
        "rating": "High" if worst_drop >= 4 or len(thin) >= 2 else "Medium" if worst_drop >= 2 or thin else "Low",
    }
    # 9. Cap safety.
    out["cap"] = _cap_safety(night, om)
    out["total_if_we_lead"], out["total_if_they_lead"] = base, total_if_they_lead
    return out


def _cap_safety(night: _Night, om: int) -> dict[str, Any] | None:
    if night.cap is None:
        return None
    known = sorted(int(p["sl"]) for i, p in enumerate(night.ours) if om >> i & 1 and _known(p["sl"]))
    unknown = sum(1 for i, p in enumerate(night.ours) if om >> i & 1 and not _known(p["sl"]))
    need = min(night.games_left, len(known))
    cheapest = sum(known[:need])
    return {"cap": night.cap, "used": night.used, "cheapest_rest": cheapest,
            "slack": night.cap - night.used - cheapest, "incomplete": unknown > 0}
