"""Refresh the CURRENT session's real APA results into a COPY of the Ultimate Coach staging DB.

Why this exists: the staging DB is built by the league-wide archive, whose ``--resume`` skips every division
it has already checkpointed -- so new scores never arrive -- and whose fresh run re-crawls every session and
replaces the database. Neither adds "Monday's scores" safely. This command:

1. copies the source staging DB (opened read-only; its SHA256 must be unchanged afterwards) to a NEW file
   inside the canonical repository (scripts/repo_boundary.py), so the previous database and every workbook
   built from it are preserved;
2. re-syncs only the catalog's current-session divisions (``--mine-only``: just the viewer's own) through the
   existing, audited ``sync_division_wide(resume=True)``: rosters and schedules are always re-fetched and a
   scoresheet is fetched only for a scored match that has none yet. Existing history is upserted, never
   dropped;
3. writes a before/after report -- date range checked, matches added, newly scored, changed, scoresheet rows
   added, and every gap (scored match without a scoresheet, denied division, coverage problem). Ids and counts
   only: no player names.

Authentication is the project's existing token path (``APA_ACCESS_TOKEN`` or apa_config.yaml); the usual way
to supply it is ``python tools/capture_apa_graphql.py --refresh-ultimate-coach``, where Paul logs in himself
and the token stays in memory. No token value is ever printed or written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path(r"C:\Users\ssand\Desktop\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker-Ultimate-Coach-Live"
                      r"\data\ultimate_coach_staging.db")
DEFAULT_CATALOG = DEFAULT_SOURCE.with_name("ultimate_coach_historical_catalog.json")
REPORT_SCHEMA = "ultimate-coach-current-session-refresh-v1"


class RefreshError(RuntimeError):
    """A safety condition that stops the refresh before (or instead of) writing anything further."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def copy_read_only(source: Path, dest: Path) -> None:
    """A consistent copy via SQLite's backup API, reading the source strictly read-only."""
    if dest.exists():
        raise RefreshError(f"refusing to overwrite an existing database: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(Path(source).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        out = sqlite3.connect(dest)
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()


def current_divisions(catalog: dict[str, Any], *, mine_only: bool = False) -> list[dict[str, Any]]:
    """The catalog divisions whose session IS the division's current session (deduplicated, stable order)."""
    from scraper.historical_archive import division_plan

    out = []
    for row in division_plan(catalog):
        current = str(row.get("current_session_id") or "")
        if current and current == row["catalog_session_id"] and (row.get("is_mine") or not mine_only):
            out.append(row)
    return out


def snapshot(db_path: Path, session_names: set[str]) -> dict[str, Any]:
    """Per-match state for the given sessions, keyed by APA match id, plus scoresheet row counts."""
    con = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        marks = ",".join("?" * len(session_names)) or "''"
        rows = con.execute(
            f"SELECT m.external_id, substr(m.match_date,1,10), m.status, m.is_scored, m.home_score, m.away_score,"
            f" COALESCE(s.n, 0) FROM matches m LEFT JOIN (SELECT match_id, COUNT(*) AS n FROM player_matches"
            f" GROUP BY match_id) s ON s.match_id = m.id WHERE m.session_name IN ({marks})",
            sorted(session_names)).fetchall()
        totals = dict(zip(("matches", "player_matches", "players"), (
            con.execute("SELECT COUNT(*) FROM matches").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM player_matches").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM players").fetchone()[0])))
    finally:
        con.close()
    matches = {str(r[0]): {"date": r[1], "status": r[2], "is_scored": bool(r[3]), "home_score": r[4],
                           "away_score": r[5], "scoresheet_rows": r[6]} for r in rows}
    return {"matches": matches, "totals": totals}


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    b, a = before["matches"], after["matches"]
    added = sorted(set(a) - set(b))
    removed = sorted(set(b) - set(a))
    newly_scored = sorted(k for k in a if a[k]["is_scored"] and not (b.get(k) or {}).get("is_scored"))
    changed = sorted(k for k in set(a) & set(b) if b[k]["is_scored"] and a[k]["is_scored"]
                     and (b[k]["home_score"], b[k]["away_score"]) != (a[k]["home_score"], a[k]["away_score"]))
    sheets = {k: a[k]["scoresheet_rows"] - (b.get(k) or {}).get("scoresheet_rows", 0) for k in a}
    scored_without_sheet = sorted(k for k in a if a[k]["is_scored"] and a[k]["scoresheet_rows"] == 0)
    dates = sorted(v["date"] for v in a.values() if v["date"])
    scored_dates = sorted(v["date"] for v in a.values() if v["is_scored"] and v["date"])
    return {
        "date_range_checked": [dates[0], dates[-1]] if dates else None,
        "latest_scored_date_before": max((v["date"] for v in b.values() if v["is_scored"] and v["date"]), default=None),
        "latest_scored_date_after": scored_dates[-1] if scored_dates else None,
        "matches_added": added,
        "matches_missing_after_refresh": removed,
        "matches_newly_scored": newly_scored,
        "matches_score_changed": changed,
        "scoresheet_rows_added": sum(v for v in sheets.values() if v > 0),
        "scoresheet_rows_removed": -sum(v for v in sheets.values() if v < 0),
        "scored_matches_without_scoresheet": scored_without_sheet,
        "totals_before": before["totals"],
        "totals_after": after["totals"],
    }


def verify_fixtures(db_path: Path, member_id: str, on_date: str, sessions: set[str]) -> list[dict[str, Any]]:
    """The viewer's refreshed-session team fixtures on one date: scored? scoresheet rows? (ids only)."""
    con = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = con.execute(
            "WITH day AS (SELECT * FROM matches WHERE substr(match_date,1,10) = ?) "
            "SELECT m.external_id, m.format, m.status, m.is_scored, m.home_score, m.away_score,"
            " (SELECT COUNT(*) FROM player_matches pm WHERE pm.match_id = m.id),"
            " (SELECT COUNT(*) FROM player_matches pm JOIN players p ON p.id = pm.player_id"
            "   WHERE pm.match_id = m.id AND p.external_id = ?) "
            # matches.home_team_id / away_team_id hold the APA team external id (as player_team_history does)
            "FROM day m WHERE m.home_team_id IN mine OR m.away_team_id IN mine ORDER BY m.external_id"
            .replace("mine", "(SELECT h.team_external_id FROM player_team_history h JOIN players p ON p.id = h.player_id"
                             f" WHERE p.external_id = ? AND h.session_name IN ({','.join('?' * len(sessions))}))"),
            (on_date, member_id, member_id, *sorted(sessions), member_id, *sorted(sessions))).fetchall()
    finally:
        con.close()
    return [{"match_id": str(r[0]), "format": r[1], "status": r[2], "is_scored": bool(r[3]), "home_score": r[4],
             "away_score": r[5], "scoresheet_rows": r[6], "viewer_rows": r[7]} for r in rows]


def run_refresh(config: dict, *, source_db: Path, catalog_path: Path, out_dir: Path, mine_only: bool = False,
                verify_member: str | None = None, verify_date: str | None = None,
                sync: Callable[..., dict[str, int]] | None = None,
                rebuild_matchups: Callable[[Any], Any] | None = None,
                now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> dict[str, Any]:
    from sqlalchemy.orm import Session

    from database.engine import create_db_engine
    from scheduler.graphql_sync import reconcile_division_wide_coverage
    from scraper.auth_classification import ConfirmedScopeDenial, call_with_confirmed_denial_retry

    if sync is None:
        from scheduler.graphql_sync import sync_division_wide as sync
    if rebuild_matchups is None:
        from analytics.matchup_builder import build_matchups as rebuild_matchups

    source_db, catalog_path, out_dir = Path(source_db), Path(catalog_path), Path(out_dir)
    if not source_db.is_file():
        raise RefreshError(f"source staging DB not found: {source_db}")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    divisions = current_divisions(catalog, mine_only=mine_only)
    if not divisions:
        raise RefreshError("the catalog lists no current-session divisions; nothing to refresh")
    sessions = {d["catalog_session_name"] for d in divisions}

    started = now()
    source_sha_before = sha256_file(source_db)
    dest = out_dir / "ultimate_coach_staging.db"
    copy_read_only(source_db, dest)
    copy_sha_before = sha256_file(dest)
    before = snapshot(dest, sessions)

    run_config = dict(config)
    run_config["database"] = dict(config.get("database") or {})
    run_config["database"]["path"] = str(dest)
    engine = create_db_engine(run_config)
    results, gaps = [], []
    try:
        with Session(engine) as db:
            for d in divisions:
                base = {"division_id": d["division_id"], "session_name": d["catalog_session_name"],
                        "format": d["format"], "is_mine": bool(d.get("is_mine"))}
                try:
                    counts = call_with_confirmed_denial_retry(run_config, lambda d=d: sync(
                        run_config, db, d["division_id"], d["format"], d["catalog_session_name"], resume=True,
                        roster_is_current=True, identity_current_only=True))
                except ConfirmedScopeDenial as denial:
                    db.rollback()
                    gaps.append(f"division {d['division_id']} ({d['format']}): APA denied access twice "
                                f"({type(denial).__name__}); any rows it left are partial")
                    results.append({**base, "confirmed_denial": True})
                    continue
                db.commit()
                problems = reconcile_division_wide_coverage(counts)
                gaps += [f"division {d['division_id']} ({d['format']}): {p}" for p in problems]
                results.append({**base, "coverage_observations": problems, **counts})
            matchups = rebuild_matchups(db)
            db.commit()
    finally:
        engine.dispose()

    after = snapshot(dest, sessions)
    change = diff(before, after)
    gaps += [f"match {k}: scored but no scoresheet rows" for k in change["scored_matches_without_scoresheet"]]
    gaps += [f"match {k}: present before the refresh but not after" for k in change["matches_missing_after_refresh"]]
    source_sha_after = sha256_file(source_db)
    if source_sha_after != source_sha_before:
        raise RefreshError("the SOURCE staging DB changed during the refresh; do not use this copy")
    report = {
        "schema": REPORT_SCHEMA,
        "started_utc": started.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "finished_utc": now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "provenance": {
            "method": "APA GraphQL via scheduler.graphql_sync.sync_division_wide(resume=True), current session only",
            "source_db": str(source_db), "source_db_sha256": source_sha_before,
            "source_db_sha256_after": source_sha_after,
            "catalog": str(catalog_path), "catalog_sha256": sha256_file(catalog_path),
            "refreshed_db": str(dest), "refreshed_db_sha256_before_sync": copy_sha_before,
            "refreshed_db_sha256": sha256_file(dest),
        },
        "scope": {"sessions": sorted(sessions), "mine_only": mine_only, "divisions": len(divisions)},
        "changes": change,
        "matchups_rebuilt": len(matchups) if matchups is not None else None,
        "divisions": results,
        "gaps": gaps,
    }
    if verify_member and verify_date:
        report["verify"] = {"date": verify_date, "viewer_fixtures": verify_fixtures(dest, verify_member, verify_date, sessions)}
        if not report["verify"]["viewer_fixtures"]:
            gaps.append(f"no fixture for the viewer's current teams on {verify_date}")
        for f in report["verify"]["viewer_fixtures"]:
            if not f["is_scored"]:
                gaps.append(f"viewer fixture {f['match_id']} on {verify_date} is still not scored in APA's data")
            elif not f["scoresheet_rows"]:
                gaps.append(f"viewer fixture {f['match_id']} on {verify_date} is scored but has no scoresheet rows")
    (out_dir / "refresh_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    from scheduler.graphql_sync import load_config
    from scraper.graphql_scraper import AccessTokenExpired, AccessTokenMissing
    from scripts.repo_boundary import BoundaryRefused, check_output_root

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=str(PROJECT_ROOT / "apa_config.yaml"))
    parser.add_argument("--source-db", default=str(DEFAULT_SOURCE))
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--out-root", default=str(PROJECT_ROOT / "tmp" / "refresh"))
    parser.add_argument("--mine-only", action="store_true", help="only the viewer's own current divisions")
    parser.add_argument("--verify-member", help="APA member id whose current-team fixtures to verify")
    parser.add_argument("--verify-date", help="YYYY-MM-DD of the fixtures to verify (e.g. Monday's)")
    args = parser.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    out_dir = Path(args.out_root) / f"refresh-{stamp}"
    try:
        check_output_root(out_dir, PROJECT_ROOT)
    except BoundaryRefused as exc:
        print(f"Refused: {exc}")
        return 2
    try:
        report = run_refresh(load_config(args.config), source_db=Path(args.source_db), catalog_path=Path(args.catalog),
                             out_dir=out_dir, mine_only=args.mine_only, verify_member=args.verify_member,
                             verify_date=args.verify_date)
    except (AccessTokenMissing, AccessTokenExpired) as exc:
        print(f"APA login needed: {type(exc).__name__}. Run tools/capture_apa_graphql.py --refresh-ultimate-coach "
              "and log in yourself; nothing was promoted and the source DB is untouched.")
        return 3
    except RefreshError as exc:
        print(f"Refresh stopped: {exc}")
        return 4
    c = report["changes"]
    print(f"Refreshed copy: {report['provenance']['refreshed_db']}")
    print(f"  SHA256 {report['provenance']['refreshed_db_sha256']} (source {report['provenance']['source_db_sha256']}, unchanged)")
    print(f"  checked {c['date_range_checked']}; latest scored {c['latest_scored_date_before']} -> {c['latest_scored_date_after']}")
    print(f"  added {len(c['matches_added'])} · newly scored {len(c['matches_newly_scored'])} · score changed "
          f"{len(c['matches_score_changed'])} · scoresheet rows +{c['scoresheet_rows_added']}")
    print(f"  gaps: {len(report['gaps'])} (see refresh_report.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
