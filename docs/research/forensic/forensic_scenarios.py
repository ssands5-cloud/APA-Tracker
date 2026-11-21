"""Forensic adversarial scenarios: run the production level rule, M3 planner and live evidence ordering on
synthetic inputs (no real data). Prints a table of expected-vs-actual behaviour."""
import json
import sys
from pathlib import Path

REPO = next(a for a in Path(__file__).resolve().parents if (a / "analytics" / "ultimate_coach_confidence.py").exists())
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")
from analytics.ultimate_coach_confidence import pair_confidence, LEVEL_POINTS  # noqa: E402
from analytics.match_night_engine import _Night, match_plan  # noqa: E402
from analytics.ultimate_coach_matchup_evidence import rank_vs_opponent  # noqa: E402
from analytics.head_to_head import skill_only_win_probability  # noqa: E402

out = {}


def lvl(direct=None, own=(0, 0), opp=(0, 0), shared=None, ch=False):
    return pair_confidence(direct, own_overall=own, opp_overall=opp, shared=shared, sl_changed=ch)


STRONG_SL7 = (691, 1084)          # a 64% opponent
S = {}
S["S1 newcomer SL3 (7 games, 5-2) vs strong SL7"] = lvl(None, (5, 7), STRONG_SL7)
S["S2 experienced SL3 (60-90) vs strong SL7"] = lvl(None, (60, 150), STRONG_SL7)
S["S3 experienced SL6 (264-183) vs strong SL7"] = lvl(None, (264, 447), STRONG_SL7)
S["S4 newcomer SL2 (0 games) vs strong SL7"] = lvl(None, (0, 0), STRONG_SL7)
S["S5 one lucky 1-0 vs strong SL7, weak form"] = lvl((1, 1), (60, 150), STRONG_SL7)
S["S6 1-0 vs SL7, newcomer (no form compare)"] = lvl((1, 1), (3, 5), STRONG_SL7)
S["S7 3-0 direct but much weaker form"] = lvl((3, 3), (60, 150), STRONG_SL7)
S["S8 9-1 direct, strong form"] = lvl((9, 10), (400, 600), (300, 600))
S["S9 9-1 direct, skill changed since"] = lvl((9, 10), (400, 600), (300, 600), ch=True)
S["S10 0-1 direct, much stronger form"] = lvl((0, 1), (400, 600), (100, 300))
S["S11 equal records, no history (both 20+)"] = lvl(None, (100, 200), (100, 200))
S["S12 shared opponents 3, edge for us"] = lvl(None, (5, 10), (5, 10), shared=(8, 10, 3, 10, 3))
out["levels"] = {k: {"level": v["level"], "points": v["points"], "why": v["why"]} for k, v in S.items()}

# skill-only probability used by legacy Lineup Lab / opponent risk (format-blind) vs archive rates (issue #119 tables)
out["legacy_skill_only_probability"] = {f"SL{a} vs SL7": skill_only_win_probability(a, 7) for a in (2, 3, 4, 5, 6)}

# Planner scenarios ---------------------------------------------------------------
def plan(ours, theirs, levels, cap=23, opp_cap=23, games=5):
    value = {}
    for (i, j), L in levels.items():
        value[(ours[i]["id"], theirs[j]["id"])] = {"level": L, "points": LEVEL_POINTS[L], "why": L, "text": L}
    return value


def roster(prefix, sls):
    return [{"id": f"{prefix}{k}", "name": f"{prefix}{k}(SL{s})", "sl": s} for k, s in enumerate(sls)]


P = {}
# P1: all Unknown -> every answer ties; tie-break is roster order
ours = roster("O", [6, 5, 4, 4, 3, 3, 3]); theirs = roster("T", [7, 6, 4, 4, 2])
lv = {(i, j): "Unknown" for i in range(len(ours)) for j in range(len(theirs))}
n = _Night(ours, theirs, plan(ours, theirs, lv), 5, 23, 0, 23, 0)
tot = {ours[i]["name"]: n.pair(i, 0) + n.solve(n.full_ours & ~(1 << i), n.full_theirs & ~1, True) for i in n.legal_ours(n.full_ours)}
P["P1 no evidence anywhere: answer to SL7"] = {"totals": tot, "answer": ours[n.best_answer(n.full_ours, n.full_theirs, 0)[0]]["name"]}
ours_rev = list(reversed(ours))
n = _Night(ours_rev, theirs, plan(ours_rev, theirs, {(i, j): "Unknown" for i in range(7) for j in range(5)}), 5, 23, 0, 23, 0)
P["P1b same, roster listed low-to-high"] = {"answer": ours_rev[n.best_answer(n.full_ours, n.full_theirs, 0)[0]]["name"]}
# P2: newcomer SL3 Unknown, everyone else Caution vs SL7, otherwise Unknown
lv = {(i, j): "Unknown" for i in range(7) for j in range(5)}
for i in range(7):
    lv[(i, 0)] = "Caution"
lv[(4, 0)] = "Unknown"
n = _Night(ours, theirs, plan(ours, theirs, lv), 5, 23, 0, 23, 0)
P["P2 only the SL3 newcomer avoids Caution vs SL7"] = {"answer": ours[n.best_answer(n.full_ours, n.full_theirs, 0)[0]]["name"]}
# P3: cap-constrained: our five strongest exceed 23; the plan must save a low player
ours3 = roster("O", [7, 6, 6, 5, 2, 2]); theirs3 = roster("T", [5, 5, 4, 4, 4])
lv3 = {(i, j): "Solid" if ours3[i]["sl"] >= 5 else "Caution" for i in range(6) for j in range(5)}
mp = match_plan(ours3, theirs3, plan(ours3, theirs3, lv3), games_left=5, cap=23)
board = mp.get("bestBoard") or mp.get("best_board") or []
P["P3 cap 23 with 7,6,6,5,2,2"] = {"lead": mp["lead"]["our"], "cap": mp.get("cap"),
                                    "best_board": [b.get("our") for b in board] if isinstance(board, list) else str(board)[:120]}
# P4: Conflicted 3-0 vs Thin 1-1: which answer?
ours4 = roster("O", [5, 5]); theirs4 = roster("T", [6])
lv4 = {(0, 0): "Conflicted", (1, 0): "Thin"}
n = _Night(ours4, theirs4, plan(ours4, theirs4, lv4), 1, None, 0)
P["P4 Conflicted (3-0 direct, weaker form) vs Thin (1-1)"] = {"answer": ours4[n.best_answer(n.full_ours, n.full_theirs, 0)[0]]["name"]}
out["planner"] = P

# Live Next Send ordering (direct rate first, then meetings) ----------------------
members = [{"id": "a", "name": "A one-game 1-0", "skill_level": 3}, {"id": "b", "name": "B nine-one 9-1", "skill_level": 6},
           {"id": "c", "name": "C two-oh 2-0", "skill_level": 5}, {"id": "d", "name": "D shared only", "skill_level": 6}]
index = {("a", "EIGHT"): {"x": (1, 1)}, ("b", "EIGHT"): {"x": (9, 10)}, ("c", "EIGHT"): {"x": (2, 2)},
         ("d", "EIGHT"): {"z": (5, 6)}, ("x", "EIGHT"): {"a": (0, 1), "b": (1, 10), "c": (0, 2), "z": (3, 6)}}
r = rank_vs_opponent(members, {"id": "x", "name": "X"}, index, "EIGHT")
out["next_send_order"] = [(row.get("player") or row["member"]["name"], row.get("rank"), row.get("direct_text")) for row in r["rows"]]
print(json.dumps(out, indent=1, default=str))
Path(__file__).with_name("scenarios.json").write_text(json.dumps(out, indent=1, default=str))
