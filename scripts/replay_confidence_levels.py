"""Read-only chronological review of the production captain evidence levels.

Uses only results on strictly earlier America/Denver dates; never current career
snapshots (which would leak later results). Observed-history overall/shared records
are partial-capture proxies, not complete lifetime records. Counts describe played
pairings, not alternative-send wins, probabilities, or proof of better captain choices.
Usage: python scripts/replay_confidence_levels.py source.db review.json
       [--exclude-match-ids-file private-external-match-ids.json]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.ultimate_coach_confidence import pair_confidence, sl_changed_since_last_meeting

FORMATS = {"EIGHT": "EIGHT", "NINE": "NINE", "8-Ball Open": "EIGHT", "9-Ball Open": "NINE"}


def local_day(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt.astimezone(ZoneInfo("America/Denver")) if dt.tzinfo else dt).date().isoformat()


def main(db, out, *, exclude_match_external_ids=()):
    path = Path(db).resolve()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    excluded = {str(x) for x in exclude_match_external_ids}
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as con:
        rows = con.execute("""SELECT h.player_id,h.opponent_id,h.result,h.own_skill_level,
            h.opponent_skill_level,h.format,m.match_date,h.match_id,m.external_id
            FROM player_head_to_head h JOIN matches m ON m.id=h.match_id WHERE h.result IN ('W','L')""").fetchall()
    matched = {str(r[8]) for r in rows if str(r[8]) in excluded}
    if matched != excluded:
        raise ValueError("Exact excluded match ID not found in result observations")
    games = defaultdict(list)
    seen = set()
    excluded_rows = unsupported = 0
    for p, o, result, slp, slo, fmt, day, mid, external in rows:
        if str(external) in excluded:
            excluded_rows += 1
            continue
        if fmt not in FORMATS:
            unsupported += 1
            continue
        fmt = FORMATS[fmt]
        key = (fmt, mid, p, o)
        if key in seen or p == o:
            raise ValueError("Duplicate or self-pair result observation; review source before replay")
        seen.add(key)
        games[(fmt, local_day(day))].append((p, o, result == "W", slp, slo))
    if not seen:
        raise ValueError("No supported observations remain; no historical validation performed")
    tally = defaultdict(lambda: [0, 0])
    pairs = defaultdict(dict)
    overall = defaultdict(lambda: [0, 0])
    for (fmt, day), observations in sorted(games.items()):
        for p, o, won, slp, slo in observations:
            mine, theirs = pairs[(fmt, p)], pairs[(fmt, o)]
            rec = mine.get(o)
            shared = None
            if rec is None:
                common = mine.keys() & theirs.keys() - {p, o}
                if common:
                    shared = (sum(mine[x][0] for x in common), sum(mine[x][1] for x in common),
                              sum(theirs[x][0] for x in common), sum(theirs[x][1] for x in common), len(common))
            changed = sl_changed_since_last_meeting(
                [{"sort": rec[2], "own_sl": rec[3], "opp_sl": rec[4]}] if rec else [], slp, slo)
            level = pair_confidence((rec[0], rec[1]) if rec else None,
                                    own_overall=tuple(overall[(fmt, p)]), opp_overall=tuple(overall[(fmt, o)]),
                                    shared=shared, sl_changed=changed)["level"]
            tally[(fmt, level)][0] += int(won)
            tally[(fmt, level)][1] += 1
        # Every observation on this local date is evaluated before any is added to history.
        for p, o, won, slp, slo in observations:
            rec = pairs[(fmt, p)].setdefault(o, [0, 0, day, slp, slo])
            rec[0] += int(won); rec[1] += 1; rec[2:] = [day, slp, slo]
            overall[(fmt, p)][0] += int(won); overall[(fmt, p)][1] += 1
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise RuntimeError("Source database changed during read-only replay")
    result = {
        "production_rule": "analytics.ultimate_coach_confidence.pair_confidence",
        "source_sha256": before,
        "rule_sha256": hashlib.sha256(Path(sys.modules[pair_confidence.__module__].__file__).read_bytes()).hexdigest(),
        "excluded_matches": len(matched), "excluded_observations": excluded_rows,
        "unsupported_format_observations": unsupported,
        "observations": sum(n for _, n in tally.values()),
        "levels": {fmt + " " + lv: {"n": n, "observed_wins": w, "observed_losses": n-w}
                   for (fmt, lv), (w, n) in sorted(tally.items())},
        "limits": ["Incomplete captured history; earlier observed results proxy overall records",
                   "No declaration-order or unplayed-alternative outcomes",
                   "No estimated win probabilities or captain-selection effectiveness claim"],
    }
    Path(out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("output")
    parser.add_argument("--exclude-match-ids-file", type=Path)
    args = parser.parse_args()
    ids = json.loads(args.exclude_match_ids_file.read_text(encoding="utf-8")) if args.exclude_match_ids_file else []
    if not isinstance(ids, list) or any(type(x) not in (int, str) for x in ids):
        parser.error("Excluded match IDs must be a JSON list of exact external IDs")
    main(args.database, args.output, exclude_match_external_ids=ids)
