"""Export ONE real division from a refresh run to the local-only showcase file.

Read-only on the run database. The output is REAL league data (names, records), so it is written
only to the git-ignored ``apps/ultimate-coach-web/private-snapshots/`` folder and is read only by
``next dev`` on localhost. It must never be committed, uploaded or deployed.

    python scripts/export_showcase_snapshot.py --run <refresh run folder> [--division 436647]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "apps" / "ultimate-coach-web" / "private-snapshots" / "showcase-real.json"
SCHEMA = "ultimate-coach-showcase-real-v1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def initials(name: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w and w.lower() not in ("the", "of", "and")]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def league_name(slug: str) -> str:
    m = re.fullmatch(r"(.+?)(county)", slug or "")
    return f"{m.group(1).title()} County" if m else (slug or "APA League")


def local_clock(value: str) -> dt.datetime:
    """The clock time as APA wrote it (offset kept in the string, not converted)."""
    return dt.datetime.fromisoformat(value).replace(tzinfo=None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="refresh run folder (contains ultimate_coach_staging.db)")
    parser.add_argument("--division", default=None, help="APA division id; default: the viewer's first division")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cap", type=int, default=23, help="reference skill cap (the cockpit uses 23)")
    args = parser.parse_args(argv)

    run = args.run.resolve()
    db_path = run / "ultimate_coach_staging.db"
    if not db_path.is_file():
        print(f"no database in {run}", file=sys.stderr)
        return 2
    out = args.out.resolve()
    if "private-snapshots" not in out.parts:
        print("refusing to write real data outside a private-snapshots folder", file=sys.stderr)
        return 2

    scope = json.loads((run / "fixtures" / "scope.json").read_text(encoding="utf-8"))
    catalog = json.loads((run / "catalog.json").read_text(encoding="utf-8")) if (run / "catalog.json").is_file() else {}

    # The viewer's own teams come from the captured dashboard response.
    viewer_teams = {}
    for path in (run / "fixtures" / "responses").glob("*.json"):
        body = json.loads(path.read_text(encoding="utf-8"))
        if body.get("operationName") == "dashboardTeams":
            for t in body["response"]["data"]["viewer"]["leagueTeams"]:
                viewer_teams[str(t["division"]["id"])] = {"team": str(t["id"]), "format": t["division"]["type"],
                                                           "league": (t.get("league") or {}).get("slug", ""),
                                                           "session": (t.get("session") or {}).get("name", "")}
    division = str(args.division or next(iter(viewer_teams)))
    if division not in {str(d["division_id"]) for d in scope["divisions"]}:
        print(f"division {division} is not in this run's scope", file=sys.stderr)
        return 2
    viewer = viewer_teams.get(division, {})

    con = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    q = lambda sql, *a: [dict(r) for r in con.execute(sql, a)]

    session = viewer.get("session") or q("select session_name s from player_team_history where division_id=? limit 1", division)[0]["s"]
    fmt = next(d["format"] for d in scope["divisions"] if str(d["division_id"]) == division)
    team_rows = q("select distinct team_external_id id, team_name name from player_team_history "
                  "where division_id=? and session_name=? order by team_name", division, session)
    team_ids = [t["id"] for t in team_rows]
    team_index = {t["id"]: i for i, t in enumerate(team_rows)}
    ph = ",".join("?" * len(team_ids))

    # ── Roster membership (this division and session only) ─────────────────────────────────────────────
    roster = q(f"select p.id pid, p.external_id ext, p.name, h.team_external_id team, h.skill_level sl, h.is_current cur "
               f"from player_team_history h join players p on p.id=h.player_id "
               f"where h.division_id=? and h.session_name=? and h.team_external_id in ({ph})", division, session, *team_ids)
    on_roster = {(r["pid"], r["team"]) for r in roster}
    by_team_name = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in roster:
        by_team_name[r["team"]][r["name"]].append(r["pid"])

    # ── Matches ────────────────────────────────────────────────────────────────────────────────────────
    matches = q(f"select * from matches where home_team_id in ({ph}) and away_team_id in ({ph}) and session_name=? "
                f"and is_bye=0 order by week, match_date", *team_ids, *team_ids, session)
    scored = [m for m in matches if m["is_scored"] and m["home_score"] is not None]
    weeks_all = sorted({m["week"] for m in matches})
    unplayed = [m for m in matches if not m["is_scored"]]
    current_week = min(m["week"] for m in unplayed) if unplayed else max(weeks_all) + 1

    # ── Resolve every scoresheet row to ONE canonical person ──────────────────────────────────────────
    # A scoresheet can carry a throwaway alias id for someone who is also on the roster. Merge only on an
    # exact team + exact name match to exactly one roster player; otherwise keep the id as a separate person.
    notes = collections.Counter()
    player_info: dict[int, dict] = {}
    for r in roster:
        player_info[r["pid"]] = {"ext": r["ext"], "name": r["name"], "team": r["team"], "sl": r["sl"], "roster": True}
    games_by_match = {}
    sl_log = collections.defaultdict(list)          # canonical pid -> [(week, sl)]
    non_roster = collections.Counter()
    for m in scored:
        rows = q("select pm.player_id pid, pm.team_id team, pm.skill_level sl, p.name, p.external_id ext "
                 "from player_matches pm join players p on p.id=pm.player_id where pm.match_id=?", m["id"])
        canon = {}
        for r in rows:
            team = r["team"]
            if (r["pid"], team) in on_roster:
                canon[r["pid"]] = r["pid"]
            else:
                same = by_team_name[team].get(r["name"], [])
                if len(same) == 1:
                    canon[r["pid"]] = same[0]
                    notes["alias rows merged into the roster player"] += 1
                else:
                    canon[r["pid"]] = r["pid"]
                    player_info.setdefault(r["pid"], {"ext": r["ext"], "name": r["name"], "team": team, "sl": r["sl"], "roster": False})
                    non_roster[(r["name"], team)] += 1
            sl_log[canon[r["pid"]]].append((m["week"], r["sl"]))
        h2h = q("select player_id a, opponent_id b, result, points_earned pts from player_head_to_head where match_id=?", m["id"])
        team_of = {canon[r["pid"]]: r["team"] for r in rows}
        pts = {}
        for h in h2h:
            a, b = canon.get(h["a"], h["a"]), canon.get(h["b"], h["b"])
            pts[(a, b)] = (h["result"], h["pts"])
        games, seen = [], set()
        for (a, b), (res, ap) in pts.items():
            if team_of.get(a) != m["home_team_id"] or team_of.get(b) != m["away_team_id"] or (a, b) in seen:
                continue
            seen.add((a, b))
            bp = pts.get((b, a), (None, 0.0))[1] or 0.0
            games.append({"home": a, "away": b, "homePts": ap or 0.0, "awayPts": bp, "winner": a if res == "W" else b})
        games_by_match[m["id"]] = games
        if len(games) != 5:
            notes[f"matches without exactly 5 pairings (match {m['external_id']}: {len(games)})"] += 1

    # ── Players: only people on a roster or in a scoresheet ───────────────────────────────────────────
    people = sorted(player_info)
    pid_key = {pid: f"m{player_info[pid]['ext']}" for pid in people}
    players = []
    for pid in people:
        info = player_info[pid]
        if info["team"] not in team_index:
            continue
        # APA 8-ball skill levels run 2-7. A recorded 0 or 1 means "not rated yet" in the source, not a real level.
        log = sorted((wk, lv) for wk, lv in sl_log.get(pid, []) if lv is not None and lv >= 2)
        sl = log[-1][1] if log else info["sl"]
        if sl is None or sl < 2:
            # Unrated and never on a scoresheet: cannot be projected or counted against the cap. Omit, and say so.
            notes["roster members omitted (unrated, no games)"] += 1
            continue
        start = log[0][1] if log else sl
        events, prev = [], start
        for week, level in log:
            if level is not None and prev is not None and level != prev:
                events.append({"week": week, "from": prev, "to": level})
            if level is not None:
                prev = level
        players.append({"id": pid_key[pid], "name": info["name"], "team": team_index[info["team"]],
                        "sl": int(sl), "startSl": int(start), "slEvents": events, "onRoster": info["roster"]})
    present = {p["id"] for p in players}

    # ── Played weeks ──────────────────────────────────────────────────────────────────────────────────
    weeks = []
    for week in sorted({m["week"] for m in scored}):
        out_matches = []
        for m in (x for x in scored if x["week"] == week):
            games = [g for g in games_by_match[m["id"]] if pid_key[g["home"]] in present and pid_key[g["away"]] in present]
            out_matches.append({"home": team_index[m["home_team_id"]], "away": team_index[m["away_team_id"]],
                                "homePts": m["home_score"], "awayPts": m["away_score"],
                                "homeWins": sum(1 for g in games if g["winner"] == g["home"]),
                                "awayWins": sum(1 for g in games if g["winner"] == g["away"]),
                                "date": m["match_date"],
                                "games": [{"home": pid_key[g["home"]], "away": pid_key[g["away"]], "homePts": g["homePts"],
                                           "awayPts": g["awayPts"], "winner": pid_key[g["winner"]]} for g in games]})
        weeks.append({"week": week, "matches": out_matches})

    upcoming = [{"home": team_index[m["home_team_id"]], "away": team_index[m["away_team_id"]], "date": m["match_date"]}
                for m in unplayed if m["week"] == current_week]
    my_team = team_index.get(viewer.get("team", ""), 0)
    my_fixture = next((u for u in upcoming if my_team in (u["home"], u["away"])), upcoming[0] if upcoming else None)
    when = local_clock(my_fixture["date"]) if my_fixture else None
    div_label = next((d.get("division_name") for d in catalog.get("divisions", []) if str(d.get("division_id")) == division), None)
    max_match = max([m["home_score"] for m in scored] + [m["away_score"] for m in scored] + [1])

    # APA's own standings (rank by session points, which include bye-week points). Authoritative for the table.
    apa_standings = []
    for path in (run / "fixtures" / "responses").glob("*.json"):
        body = json.loads(path.read_text(encoding="utf-8"))
        if body.get("operationName") == "divsionStandings" and str(body["variables"].get("id")) == division:
            for t in body["response"]["data"]["division"]["teams"]:
                if str(t["id"]) in team_index:
                    apa_standings.append({"team": team_index[str(t["id"])], "rank": t.get("standing"),
                                          "points": t.get("sessionTotalPoints"), "pointsLastWeek": t.get("pointsLastWeek"),
                                          "tied": bool(t.get("isTied")), "individualMatches": t.get("totalTeamMatchesPlayed")})

    sources = run / "fixtures" / "sources.json"
    captured = dt.datetime.fromtimestamp(sources.stat().st_mtime, dt.timezone.utc) if sources.is_file() else None
    snapshot = {
        "schema": SCHEMA,
        "provenance": {"run": run.name, "database": db_path.name, "databaseSha256": sha256(db_path),
                       "capturedAt": captured.isoformat() if captured else None,
                       "exportedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
                       "coverage": "partial" if (run / "FAILED.json").is_file() else "complete",
                       "note": "Local beta from a refresh run that stopped at its source-coverage gate; two scoresheet rows had unresolved identities."
                       if (run / "FAILED.json").is_file() else "Completed refresh run.",
                       "notes": dict(notes)},
        "league": {"name": league_name(viewer.get("league", "")), "division": div_label or f"Division {division}",
                   "season": session, "format": "8-Ball" if fmt == "EIGHT" else "9-Ball" if fmt == "NINE" else fmt,
                   "cap": args.cap, "currentWeek": current_week, "totalWeeks": max(weeks_all),
                   "matchDate": f"{when:%a %b} {when.day}, {when.year}" if when else "",
                   "matchTime": f"{(when.hour % 12) or 12}:{when:%M %p} MT" if when else "",
                   "maxMatchPoints": int(max_match), "maxGamePoints": 3, "venueKnown": any(m["location"] for m in matches)},
        "myTeam": my_team,
        "teams": [{"name": t["name"], "short": initials(t["name"]), "venue": None} for t in team_rows],
        "players": players,
        "weeks": weeks,
        "upcoming": upcoming,
        "apaStandings": apa_standings,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")

    # ── Plain report (no secrets) ────────────────────────────────────────────────────────────────────
    print(f"wrote {out}")
    print(f"division {division} {snapshot['league']['format']} · {session} · {len(team_rows)} teams · my team = {team_rows[my_team]['name']}")
    print(f"players {len(players)} (non-roster {sum(1 for p in players if not p['onRoster'])}) · weeks played {len(weeks)} · current week {current_week}/{max(weeks_all)}")
    print(f"team matches {sum(len(w['matches']) for w in weeks)} · games {sum(len(m['games']) for w in weeks for m in w['matches'])} · upcoming {len(upcoming)}")
    print("notes", dict(notes))
    print("non-roster scoresheet players:", [(n, team_rows[team_index[t]]['name'], c) for (n, t), c in non_roster.items()])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
