"""Check a rule-based captain confidence framework against history (read-only replay).

Each candidate pairing (our player p vs their player o) gets a confidence level from plain,
stated rules over six inputs: direct record, meeting count, recency, skill-level change,
overall record and shared-opponent evidence. No probability, no fitted weights, no model.

The replay only asks whether the levels mean what they say: does a "Strong" send win its next
game more often than a "Solid" one, "Solid" more than "Thin", and is "Conflicted" really mixed?
Every game is judged from games on strictly earlier dates. Internal review output only.

Usage: python scripts/replay_confidence_levels.py <staging.db> <out.json>
"""
import json
import pathlib
import sqlite3
import sys
from collections import defaultdict
from datetime import date as Date

FORMATS = {"8-Ball Open": "EIGHT", "9-Ball Open": "NINE"}
FORM_MIN_GAMES = 20       # an overall record needs this many games to count
SHRINK = 5                # overall form pulled toward .500 by 5 wins and 5 losses


def form(rec):
    w, g = rec
    return (w + SHRINK) / (g + 2 * SHRINK)


def level(direct, same_sl, age_days, own, opp, shared):
    """The framework. Returns (level, reasons). Direction = is p a good send against o?

    direct: (wins, meetings) for p vs o; own/opp: overall (wins, games);
    shared: (our rate vs shared opponents - their rate vs the same opponents, number shared) or None.
    """
    w, g = direct
    reasons = []
    known_form = own[1] >= FORM_MIN_GAMES and opp[1] >= FORM_MIN_GAMES
    gap = form(own) - form(opp) if known_form else 0.0
    form_for, form_against = known_form and gap >= 0.05, known_form and gap <= -0.05
    strong_form = known_form and gap >= 0.15

    if g:
        rate = w / g
        fav, unf = w > g - w, w < g - w
        deep = g >= 5
        mid = 3 <= g <= 4
        if fav and form_against or unf and form_for:
            return "Conflicted", ["direct record and overall form point opposite ways"]
        if unf:
            return "Caution", ["losing direct record"]
        if not fav:
            base = "Thin"
            reasons.append("even direct record")
        elif deep and rate >= 0.7 or g >= 3 and form_for:
            base = "Strong"
        elif mid or deep or form_for:
            base = "Solid"
        else:
            base = "Thin"
            reasons.append(f"only {g} meeting{'s' if g > 1 else ''}")
        if not same_sl and base in ("Strong", "Solid"):
            base = {"Strong": "Solid", "Solid": "Thin"}[base]
            reasons.append("skill levels changed since they last met")
        if age_days > 3 * 365 and base == "Strong":
            base = "Solid"
            reasons.append("last meeting over 3 years ago")
        return base, reasons
    # no direct history: overall form, then shared opponents
    if strong_form:
        return "Strong", ["much stronger overall record; no direct history"]
    if form_for:
        return "Solid", ["stronger overall record; no direct history"]
    if form_against:
        return "Caution", ["weaker overall record; no direct history"]
    if shared and shared[0] >= 0.10:
        if shared[1] >= 3:
            return "Solid", [f"shared-opponent results favor us across {shared[1]} common opponents"]
        return "Thin", ["shared-opponent results favor us, but through only 1-2 common opponents"]
    if shared and shared[0] <= -0.10:
        return "Caution", ["shared-opponent results favor them"]
    return "Unknown", ["no direct history and no clear overall or shared-opponent edge"]


def main(db, out):
    con = sqlite3.connect(pathlib.Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    rows = con.execute(
        """select h.player_id, h.opponent_id, h.result, h.own_skill_level, h.opponent_skill_level,
                  h.format, m.match_date
           from player_head_to_head h join matches m on m.id = h.match_id
           where h.result in ('W','L') and h.format in ('8-Ball Open','9-Ball Open')""").fetchall()
    games = defaultdict(list)
    for p, o, res, slp, slo, fmt, d in rows:
        games[(FORMATS[fmt], d[:10])].append((p, o, res == "W", slp, slo))

    tally = defaultdict(lambda: [0, 0])
    shared_tally = defaultdict(lambda: [0, 0])
    pairs = defaultdict(dict)      # (fmt, p) -> {o: [w, g, last_date, slp, slo]}
    overall = defaultdict(lambda: [0, 0])
    for (fmt, d) in sorted(games):
        day = games[(fmt, d)]
        today = Date.fromisoformat(d)
        for p, o, won, slp, slo in day:
            mine, theirs = pairs[(fmt, p)], pairs[(fmt, o)]
            rec = mine.get(o)
            shared = None
            if rec is None:
                # shared-opponent evidence, as the coach computes it: our record vs common opponents
                # against their record vs the same opponents (bounded to keep the replay fast)
                small, big = (mine, theirs) if len(mine) <= len(theirs) else (theirs, mine)
                common = [x for x in small if x in big and x not in (p, o)][:200]
                if common:
                    ow = sum(mine[x][0] for x in common); og = sum(mine[x][1] for x in common)
                    tw = sum(theirs[x][0] for x in common); tg = sum(theirs[x][1] for x in common)
                    shared = (ow / og - tw / tg, len(common))
                    sb = ("ours better" if shared[0] >= 0.10 else "theirs better" if shared[0] <= -0.10 else "level") + \
                         (" 1-2 shared" if len(common) < 3 else " 3+ shared")
                    shared_tally[(fmt, sb)][0] += won
                    shared_tally[(fmt, sb)][1] += 1
            direct = (rec[0], rec[1]) if rec else (0, 0)
            same_sl = bool(rec) and (rec[3], rec[4]) == (slp, slo)
            age = (today - Date.fromisoformat(rec[2])).days if rec else 0
            lv, _ = level(direct, same_sl, age, overall[(fmt, p)], overall[(fmt, o)], shared)
            tally[(fmt, lv)][0] += won
            tally[(fmt, lv)][1] += 1
        for p, o, won, slp, slo in day:
            r = pairs[(fmt, p)].setdefault(o, [0, 0, d, slp, slo])
            r[0] += int(won); r[1] += 1; r[2] = d; r[3] = slp; r[4] = slo
            overall[(fmt, p)][0] += int(won); overall[(fmt, p)][1] += 1

    def dump(t):
        return {f"{k[0]} {k[1]}": {"n": n, "won_next": round(w / n, 4)} for k, (w, n) in sorted(t.items())}
    result = {"levels": dump(tally), "shared_opponent_no_direct": dump(shared_tally)}
    pathlib.Path(out).write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
