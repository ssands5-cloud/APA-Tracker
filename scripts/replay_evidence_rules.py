"""Chronological replay of Ultimate Coach evidence rules against what happened next.

Read-only. Every game is scored only from games dated strictly earlier (same-date games
never see each other). Descriptive frequencies for an internal decision review, not a
published probability.
"""
import json
import pathlib
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

DB = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2])
FORMATS = {"8-Ball Open": "EIGHT", "9-Ball Open": "NINE"}

con = sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True)
rows = con.execute(
    """select h.player_id, h.opponent_id, h.result, h.own_skill_level, h.opponent_skill_level,
              h.format, m.match_date, h.match_id
       from player_head_to_head h join matches m on m.id = h.match_id
       where h.result in ('W','L') and h.format in ('8-Ball Open','9-Ball Open')""").fetchall()
team_of = {(p, mid): t for p, mid, t in con.execute(
    "select player_id, match_id, team_id from player_matches where match_id is not null and team_id is not null")}

games = defaultdict(list)          # (fmt, date) -> rows
for p, o, res, slp, slo, fmt, date, mid in rows:
    games[(FORMATS[fmt], date[:10])].append((p, o, res == "W", slp, slo, mid))


class Tally:
    def __init__(self):
        self.d = defaultdict(lambda: [0, 0])

    def add(self, key, won):
        self.d[key][0] += int(won)
        self.d[key][1] += 1

    def dump(self):
        return {str(k): {"n": n, "win_rate": round(w / n, 4)} for k, (w, n) in sorted(self.d.items(), key=lambda kv: str(kv[0])) if n}


def rec_bucket(w, g):
    if g == 0:
        return "none"
    if g <= 2:
        return f"{w}-{g - w}"
    band = "G" if w > g - w else "R" if w < g - w else "E"
    size = "3-4" if g <= 4 else "5-9" if g <= 9 else "10+"
    rate = w / g
    rb = "<.3" if rate < .3 else "<.45" if rate < .45 else "<.55" if rate < .55 else "<.7" if rate < .7 else ">=.7"
    return f"{band} n{size} r{rb}"


def overall_band(w, g):
    if g < 20:
        return "thin(<20)"
    r = w / g
    return "<.40" if r < .40 else "<.47" if r < .47 else "<.53" if r < .53 else "<.60" if r < .60 else "<.67" if r < .67 else ">=.67"


T = defaultdict(Tally)
pair = {}        # (fmt,p,o) -> [w, g, last_date, last_slp, last_slo]
overall = {}     # (fmt,p) -> [w, g]
roster = defaultdict(set)   # team -> players seen on it so far

for (fmt, date) in sorted(games):
    day = games[(fmt, date)]
    dt = datetime.fromisoformat(date)
    for p, o, won, slp, slo, mid in day:
        w, g, last, lslp, lslo = pair.get((fmt, p, o), (0, 0, None, None, None))
        ow, og = overall.get((fmt, p), (0, 0))
        xw, xg = overall.get((fmt, o), (0, 0))
        pr = f"{fmt}"
        # 1. next result by prior direct record
        T[pr + " direct"].add(rec_bucket(w, g), won)
        # 2. category view the coach uses
        cat = "X" if g == 0 else "G" if w > g - w else "R" if w < g - w else "E"
        T[pr + " category"].add(cat, won)
        # 3. no direct history: own overall form vs opponent overall form
        if g == 0:
            T[pr + " nodirect own-overall"].add(overall_band(ow, og), won)
            if og >= 20 and xg >= 20:
                diff = ow / og - xw / xg
                db = "<-.15" if diff < -.15 else "<-.05" if diff < -.05 else "<.05" if diff < .05 else "<.15" if diff < .15 else ">=.15"
                T[pr + " nodirect overall-gap"].add(db, won)
        # 4. thin direct record crossed with overall form (1-0 / 0-1 vs form)
        if g == 1:
            T[pr + " single-meeting x own-overall"].add(f"{w}-{1 - w} | {overall_band(ow, og)}", won)
        # 5. stale or SL-changed direct evidence
        if g:
            age = (dt - datetime.fromisoformat(last)).days
            ab = "<1y" if age < 365 else "1-3y" if age < 3 * 365 else ">=3y"
            T[pr + " direct-age"].add(f"{cat} {ab}", won)
            same_sl = (lslp, lslo) == (slp, slo)
            T[pr + " direct-sl"].add(f"{cat} {'same SLs' if same_sl else 'SL changed'}", won)
        # 6. overall-gap when a thin favorable record exists (does form override a 1-0?)
        if g == 1 and og >= 20 and xg >= 20:
            diff = ow / og - xw / xg
            T[pr + " 1-meeting x overall-gap"].add(f"{w}-{1 - w} | gap {'+' if diff >= .05 else '-' if diff <= -.05 else '0'}", won)
        # 7. threat: opponent's prior record vs our player's current team roster
        team = team_of.get((p, mid))
        if team is not None:
            tw = tg = 0
            for mate in roster[team]:
                rw, rg, *_ = pair.get((fmt, o, mate), (0, 0))
                tw += rw
                tg += rg
            if tg:
                tb = ("threat" if tw > tg - tw else "not") + (" n<3" if tg < 3 else " n3-9" if tg < 10 else " n10+")
            else:
                tb = "unknown vs roster"
            T[pr + " opp-record-vs-our-roster"].add(tb, won)
            ob = overall_band(xw, xg)
            T[pr + " opp-overall (our result)"].add(ob, won)
    # update after the whole date
    for p, o, won, slp, slo, mid in day:
        w, g, *_ = pair.get((fmt, p, o), (0, 0, None, None, None))
        pair[(fmt, p, o)] = [w + int(won), g + 1, date, slp, slo]
        ow, og = overall.get((fmt, p), (0, 0))
        overall[(fmt, p)] = [ow + int(won), og + 1]
        team = team_of.get((p, mid))
        if team is not None:
            roster[team].add(p)

OUT.write_text(json.dumps({k: v.dump() for k, v in sorted(T.items())}, indent=1))
print("rows", len(rows), "dates", len(games))
