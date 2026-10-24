"""Compare ordering rules on the same chronological replay (strictly earlier evidence only).

For each rule, "order accuracy" is the share of (winner row, loser row) pairs the rule ranks
correctly, ties counted half (an AUC). 0.50 = no better than a coin flip. Internal review only.
"""
import json
import pathlib
import sqlite3
import sys
from collections import defaultdict

DB = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2])
FORMATS = {"8-Ball Open": "EIGHT", "9-Ball Open": "NINE"}
con = sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True)
rows = con.execute(
    """select h.player_id, h.opponent_id, h.result, h.format, m.match_date, h.match_id
       from player_head_to_head h join matches m on m.id = h.match_id
       where h.result in ('W','L') and h.format in ('8-Ball Open','9-Ball Open')""").fetchall()
team_of = {(p, mid): t for p, mid, t in con.execute(
    "select player_id, match_id, team_id from player_matches where match_id is not null and team_id is not null")}
games = defaultdict(list)
for p, o, res, fmt, date, mid in rows:
    games[(FORMATS[fmt], date[:10])].append((p, o, res == "W", mid))


def auc(scores, labels):
    """Probability a random winner row outscores a random loser row (ties half)."""
    items = sorted(zip(scores, labels))
    pos = sum(labels)
    neg = len(labels) - pos
    if not pos or not neg:
        return None
    rank_sum = 0.0
    i = 0
    while i < len(items):
        j = i
        while j < len(items) and items[j][0] == items[i][0]:
            j += 1
        avg = (i + 1 + j) / 2
        rank_sum += avg * sum(1 for k in range(i, j) if items[k][1])
        i = j
    return round((rank_sum - pos * (pos + 1) / 2) / (pos * neg), 4)


feat = defaultdict(lambda: defaultdict(list))   # (fmt, subset) -> name -> scores ; plus "y"
pair, overall, roster = {}, {}, defaultdict(set)


def form(fmt, p):
    w, g = overall.get((fmt, p), (0, 0))
    return (w + 5) / (g + 10)          # shrunk toward .500 so new players are not extreme


for (fmt, date) in sorted(games):
    day = games[(fmt, date)]
    for p, o, won, mid in day:
        w, g = pair.get((fmt, p, o), (0, 0))
        gap = form(fmt, p) - form(fmt, o)
        cat = 0 if g == 0 else (1 if w > g - w else -1 if w < g - w else 0)
        smooth = (w + 1) / (g + 2)
        coach = (2, w / g, g) if cat == 1 or (g and cat == 0) else (0, 0, 0) if g == 0 else (-1, w / g, -g)
        subsets = ["all"] + (["has direct"] if g else []) + (["single meeting"] if g == 1 else [])
        for s in subsets:
            f = feat[(fmt, s)]
            f["y"].append(int(won))
            f["coach category (G>E/X>R)"].append(cat)
            f["coach order (win% then meetings)"].append(coach)
            f["smoothed direct (w+1)/(g+2)"].append(smooth)
            f["overall form gap"].append(round(gap, 6))
            f["smoothed direct + form gap"].append(round(smooth - 0.5 + gap, 6))
        # blind send: our record vs the other team's roster (who they might put up)
        oteam = team_of.get((o, mid))
        if oteam is not None:
            G = R = 0
            for opp in roster[oteam]:
                rw, rg = pair.get((fmt, p, opp), (0, 0))
                if rg:
                    G += rw > rg - rw
                    R += rw < rg - rw
            f = feat[(fmt, "blind")]
            f["y"].append(int(won))
            f["coach blind (fewest R, most G)"].append((-R, G))
            f["own overall form"].append(round(form(fmt, p), 6))
            f["form + (G-R)/10"].append(round(form(fmt, p) + (G - R) / 10, 6))
    for p, o, won, mid in day:
        w, g = pair.get((fmt, p, o), (0, 0))
        pair[(fmt, p, o)] = (w + int(won), g + 1)
        ow, og = overall.get((fmt, p), (0, 0))
        overall[(fmt, p)] = (ow + int(won), og + 1)
        t = team_of.get((p, mid))
        if t is not None:
            roster[t].add(p)

out = {}
for (fmt, s), f in sorted(feat.items()):
    y = f.pop("y")
    out[f"{fmt} {s} (n={len(y)})"] = {name: auc(sc, y) for name, sc in f.items()}
OUT.write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
