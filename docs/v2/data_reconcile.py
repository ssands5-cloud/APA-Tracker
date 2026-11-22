"""Data-integrity reconciliation: statistics shown in a built Ultimate Coach HTML vs the source archive records.

For every player on the two given teams (by roster scope key), recompute from the archive SQLite, independently of
the application code: recorded games and wins per format, last-10, direct records against every opponent player,
and duplicate / conflicting rows; compare with what the page's own data (rowsFor / V2 inputs) holds. Real data stays
local: --out gets the detailed table, --summary only counts (safe to publish).

    python -I docs/v2/data_reconcile.py --html <HTML> --db <archive.sqlite> --ours <scope key> --theirs <scope key> --format EIGHT --out r.json --summary s.json
"""
import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright

FMT = {"EIGHT": ("EIGHT", "8-Ball Open"), "NINE": ("NINE", "9-Ball Open")}




def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--ours", required=True)
    ap.add_argument("--theirs", required=True)
    ap.add_argument("--format", default="EIGHT")
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary")
    a = ap.parse_args()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(Path(a.html).resolve().as_uri())
        page.wait_for_selector("#bc-team-a")
        data = page.evaluate("([a, b, f]) => window.__ucReconcileData(a, b, f)", [a.ours, a.theirs, a.format])
        browser.close()
    con = sqlite3.connect(Path(a.db).resolve().as_uri() + "?mode=ro", uri=True)
    fmts = FMT[a.format]
    q = ("SELECT h.player_id,h.opponent_id,h.result,h.match_id,m.match_date FROM player_head_to_head h JOIN matches m ON m.id=h.match_id "
         "WHERE h.format IN (%s) AND h.player_id=?" % ",".join("?" * len(fmts)))
    rows_out, mism = [], defaultdict(int)
    ids = [p["id"] for p in data["ours"] + data["theirs"]]
    theirs_ids = {p["id"] for p in data["theirs"]}
    for p in data["ours"] + data["theirs"]:
        raw = con.execute(q, (*fmts, p["id"])).fetchall()
        keys = defaultdict(list)
        for r in raw:
            keys[(r[3], r[1])].append(r[2])
        dup = sum(1 for v in keys.values() if len(v) > 1 and len(set(v)) == 1)
        conflict = sum(1 for v in keys.values() if len(set(v)) > 1)
        decided = [(r[4], r[3], r[1], r[2]) for r in raw if r[2] in ("W", "L")]
        # one row per (match, opponent): what an independent reader would count
        uniq = {}
        for d in decided:
            uniq.setdefault((d[1], d[2]), d)
        games = sorted(uniq.values())
        w = sum(1 for g in games if g[3] == "W")
        last = games[-10:]
        rec = {"id": p["id"], "name": p["name"], "archive_games": len(games), "archive_wins": w,
               "archive_last10": [sum(1 for g in last if g[3] == "W"), len(last)],
               "page_games": p["form"][1], "page_wins": p["form"][0], "page_last10": p["recent"],
               "duplicate_keys": dup, "conflicting_keys": conflict, "direct": {}}
        if p["id"] not in theirs_ids:
            for o in data["theirs"]:
                dg = [g for g in games if g[2] == o["id"]]
                arch = [sum(1 for g in dg if g[3] == "W"), len(dg)]
                pg = p["direct"].get(str(o["id"])) or [0, 0]
                rec["direct"][o["name"]] = {"archive": arch, "page": pg}
                if arch != list(pg):
                    mism["direct_record"] += 1
        for k, ak, pk in (("games", "archive_games", "page_games"), ("wins", "archive_wins", "page_wins")):
            if rec[ak] != rec[pk]:
                mism["recorded_" + k] += 1
        if rec["archive_last10"] != list(rec["page_last10"]):
            mism["last10"] += 1
        rows_out.append(rec)
    summary = {"players_checked": len(rows_out), "direct_pairs_checked": sum(len(r["direct"]) for r in rows_out),
               "mismatches": dict(mism), "players_with_duplicate_rows": sum(1 for r in rows_out if r["duplicate_keys"]),
               "players_with_conflicting_rows": sum(1 for r in rows_out if r["conflicting_keys"]),
               "page_duplicate_rows": sum(p.get("pageDuplicateRows", 0) for p in data["ours"] + data["theirs"]),
               "archive_latest_match": con.execute("SELECT max(match_date) FROM matches WHERE is_scored=1").fetchone()[0][:10],
               "page_latest_result": data.get("latest")}
    Path(a.out).write_text(json.dumps({"summary": summary, "players": rows_out}, indent=1), encoding="utf-8")
    if a.summary:
        Path(a.summary).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
