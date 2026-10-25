"""How much do Match Night Engine decisions depend on the point scale? (synthetic, deterministic)

Random nights with realistic sizes (5-8 a side), skill levels, a 23 cap, and pairing levels drawn with
the frequencies seen in the 8-Ball chronological replay. Each night is planned under several plausible
monotone scales; we report how often the lead pick and the response table agree with the history-anchored
default (6/3/1/0/0/-3). Usage: python scripts/match_night_scale_sensitivity.py [nights]
"""
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analytics.match_night_engine import match_plan  # noqa: E402

# 8-Ball replay frequencies of each level (docs/recommendation_review/replay_confidence_levels.json).
FREQ = {"Strong": 17232, "Solid": 83802, "Thin": 79427, "Unknown": 124874, "Conflicted": 20682, "Caution": 159963}
SCALES = {
    "history 6/3/1/0/-3 (default)": {"Strong": 6, "Solid": 3, "Thin": 1, "Unknown": 0, "Conflicted": 0, "Caution": -3},
    "even steps 4/2/1/0/-2": {"Strong": 4, "Solid": 2, "Thin": 1, "Unknown": 0, "Conflicted": 0, "Caution": -2},
    "linear 3/2/1/0/-1": {"Strong": 3, "Solid": 2, "Thin": 1, "Unknown": 0, "Conflicted": 0, "Caution": -1},
    "loss-averse 6/3/1/0/-6": {"Strong": 6, "Solid": 3, "Thin": 1, "Unknown": 0, "Conflicted": 0, "Caution": -6},
}


def night(rng):
    levels, weights = zip(*FREQ.items())
    no, nt = rng.randint(5, 8), rng.randint(5, 8)
    ours = [{"id": f"o{i}", "name": f"O{i}", "sl": rng.choice([2, 3, 3, 4, 4, 5, 5, 6, 7])} for i in range(no)]
    theirs = [{"id": f"t{j}", "name": f"T{j}", "sl": rng.choice([2, 3, 3, 4, 4, 5, 5, 6, 7])} for j in range(nt)]
    grid = {(o["id"], t["id"]): rng.choices(levels, weights)[0] for o in ours for t in theirs}
    return ours, theirs, grid


def plan(ours, theirs, grid, scale):
    value = {k: {"level": lv, "points": scale[lv], "why": lv, "text": lv} for k, lv in grid.items()}
    return match_plan(ours, theirs, value, games_left=5, cap=23)


def main(n):
    rng = random.Random(20261018)
    base_name = next(iter(SCALES))
    agree = {name: {"lead": 0, "responses": 0, "plan_compared": 0} for name in SCALES}
    slowest = 0.0
    for _ in range(n):
        ours, theirs, grid = night(rng)
        t = time.perf_counter()
        base = plan(ours, theirs, grid, SCALES[base_name])
        slowest = max(slowest, time.perf_counter() - t)
        if base["lead"] is None:
            continue
        for name, scale in SCALES.items():
            other = plan(ours, theirs, grid, scale)
            a = agree[name]
            a["plan_compared"] += 1
            a["lead"] += other["lead"] and other["lead"]["our"] == base["lead"]["our"]
            a["responses"] += [r["our"] for r in other["responses"]] == [r["our"] for r in base["responses"]]
    out = {name: {"same_lead": round(a["lead"] / a["plan_compared"], 3),
                  "same_full_response_table": round(a["responses"] / a["plan_compared"], 3),
                  "nights": a["plan_compared"]} for name, a in agree.items()}
    out["slowest_full_plan_seconds_python"] = round(slowest, 3)
    print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 300)
