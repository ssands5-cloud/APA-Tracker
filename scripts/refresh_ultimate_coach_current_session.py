"""Refresh the CURRENT session's real APA results into a COPY of the Ultimate Coach staging DB.

Why this exists: the staging DB is built by the league-wide archive, whose ``--resume`` skips every division
it has already checkpointed -- so new scores never arrive -- and whose fresh run re-crawls every session and
replaces the database. Neither adds "Monday's scores" safely. This command:

1. copies the source staging DB (opened read-only; its SHA256 must be unchanged afterwards) to a NEW file
   inside the canonical repository (scripts/repo_boundary.py), so the previous database and every workbook
   built from it are preserved;
2. re-syncs only the catalog's current-session divisions (``--mine-only``: just the viewer's own) through the
   existing, audited ``sync_division_wide(resume=True)``: rosters and schedules are always re-fetched and a
   scoresheet is fetched only for a scored match that has none yet. Then, in the default ``--mode reconcile``
   (GPT audit 4874e4b), every scored match that ALREADY had rows is re-fetched and its player results
   reconciled -- corrections updated, missing rows added, rows absent from the authoritative sheet removed --
   refusing removal on an empty sheet or an unresolved identity. ``--mode missing-only`` keeps the old
   fetch-only-what-is-missing behaviour and never reports complete coverage. Earlier sessions and other matches
   are never touched;
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


RESULT_FIELDS = ("result", "points_earned", "skill_level", "team_id", "eight_on_break", "eight_break_and_run",
                 "nine_on_snap", "nine_break_and_run")


def _player_rows(db, match_pk: int) -> dict[str, dict[str, Any]]:
    """This match's PlayerMatch rows keyed by the player's APA external id (the identity the sheet is mapped to)."""
    from database.models import Player, PlayerMatch

    rows = db.query(PlayerMatch, Player.external_id).join(Player, Player.id == PlayerMatch.player_id).filter(
        PlayerMatch.match_id == match_pk).all()
    return {str(ext): {f: getattr(pm, f) for f in RESULT_FIELDS} for pm, ext in rows}


def default_scoresheet(config: dict, match_id: str) -> tuple[list[dict], list[dict]]:
    """The authoritative GraphQL scoresheet for one match: (per-player score rows, head-to-head rows)."""
    from scheduler import graphql_sync as gs

    detail = gs.fetch_match_detail(config, int(match_id))
    return gs.match_player_scores(detail), gs.head_to_head_rows(detail)


def reconcile_match(config: dict, db, match_id: str, session_name: str, *,
                    scoresheet: Callable[[dict, str], tuple[list[dict], list[dict]]] = default_scoresheet,
                    resolve: Callable[..., tuple[dict, int, int]] | None = None) -> dict[str, Any]:
    """Re-fetch ONE scored match's authoritative scoresheet and reconcile its player-result rows.

    Rows are matched on (player, match) after the scoresheet's alias ids are mapped to canonical identities, so a
    repeat run adds nothing twice. Changed fields are updated and recorded field by field; players missing from
    the authoritative sheet are removed. Removal is REFUSED, and reported, when the sheet came back with no
    player rows (an empty answer is not proof the old rows are wrong) or when any identity is unresolved (an
    unmapped alias would replace a canonical player). Head-to-head is reconciled with the same guards. Nothing
    outside this one match is touched.
    """
    from database.ingest import ingest_head_to_head, ingest_match_scores
    from database.models import Match, PlayerMatch, Player
    from scheduler import graphql_sync as gs

    resolve = resolve or gs.resolve_scoresheet_identities
    match = db.query(Match).filter_by(external_id=str(match_id)).one_or_none()
    if match is None:
        return {"match_id": str(match_id), "status": "not_in_db"}
    before = _player_rows(db, match.id)
    scores, h2h = scoresheet(config, str(match_id))
    # Provenance of exactly what was applied: when the authoritative sheet was fetched, and a digest of the
    # canonical rows as received (ids and results only, so the report stays name-free).
    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    digest = hashlib.sha256(json.dumps(sorted(
        [str(s.get("player_id") or ""), str(s.get("team_id") or ""), str(s.get("result") or ""),
         str(s.get("points_earned") or ""), str(s.get("skill_level") or "")] for s in scores),
        separators=(",", ":")).encode("utf-8")).hexdigest()
    mapping, _resolved, unresolved = resolve(db, session_name, scores, current_only=True)
    scores = gs.apply_identity_mapping(scores, mapping, ("player_id",))
    h2h = gs.apply_identity_mapping(h2h, mapping, ("player_id", "opponent_id"))
    authoritative = {str(s["player_id"]) for s in scores if s.get("player_id")}
    out: dict[str, Any] = {"match_id": str(match_id), "rows_before": len(before), "fetched_utc": fetched,
                           "scoresheet_rows_received": len(scores), "scoresheet_sha256": digest}
    if not authoritative:
        out.update(status="empty_scoresheet_kept", rows_after=len(before))
        return out
    ingest_match_scores(db, match_id, scores)
    removed: list[str] = []
    if unresolved:
        out["unresolved_identities"] = unresolved
    else:
        for ext in sorted(set(before) - authoritative):
            player = db.query(Player).filter_by(external_id=ext).one()
            db.query(PlayerMatch).filter_by(player_id=player.id, match_id=match.id).delete()
            removed.append(ext)
        ingest_head_to_head(db, match_id, h2h)
    db.commit()
    after = _player_rows(db, match.id)
    changed = [{"player": ext, "changes": {f: [before[ext][f], after[ext][f]] for f in RESULT_FIELDS
                                           if before[ext][f] != after[ext][f]}}
               for ext in sorted(set(before) & set(after)) if before[ext] != after[ext]]
    out.update(rows_after=len(after), added=sorted(set(after) - set(before)), removed=removed, changed=changed,
               status=("unresolved_identity_partial" if unresolved else
                       "changed" if (changed or removed or set(after) - set(before)) else "unchanged"))
    return out


def run_refresh(config: dict, *, source_db: Path, catalog_path: Path, out_dir: Path, mine_only: bool = False,
                verify_member: str | None = None, verify_date: str | None = None,
                sync: Callable[..., dict[str, int]] | None = None,
                rebuild_matchups: Callable[[Any], Any] | None = None, mode: str = "reconcile",
                schedule: Callable[[dict, str], list[dict]] | None = None,
                scoresheet: Callable[[dict, str], tuple[list[dict], list[dict]]] = default_scoresheet,
                resolve: Callable[..., tuple[dict, int, int]] | None = None,
                now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> dict[str, Any]:
    from sqlalchemy.orm import Session

    from database.engine import create_db_engine
    from scheduler.graphql_sync import reconcile_division_wide_coverage
    from scraper.auth_classification import ConfirmedScopeDenial, call_with_confirmed_denial_retry
    from scraper.graphql_scraper import AccessTokenExpired, AccessTokenMissing

    if mode not in ("reconcile", "missing-only"):
        raise RefreshError(f"unknown mode {mode!r}")
    if sync is None:
        from scheduler.graphql_sync import sync_division_wide as sync
    if schedule is None:
        def schedule(cfg, division_id):
            from scheduler import graphql_sync as gs
            return gs.division_schedule_rows(gs.fetch_division_schedule(cfg, division_id))
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
    results, gaps, checked = [], [], []
    had_rows = {k for k, v in before["matches"].items() if v["scoresheet_rows"] > 0}
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
                result = {**base, "coverage_observations": problems, **counts}
                if mode == "reconcile":
                    # The sync above (resume=True) fetched every MISSING scoresheet. Matches that already had rows
                    # were skipped by its checkpoint, so re-fetch each of them and reconcile its player results.
                    try:
                        rows = call_with_confirmed_denial_retry(run_config, lambda d=d: schedule(run_config, d["division_id"]))
                    except ConfirmedScopeDenial:
                        rows = None
                        gaps.append(f"division {d['division_id']} ({d['format']}): schedule denied; its existing "
                                    "scoresheets were NOT re-checked")
                    except (AccessTokenMissing, AccessTokenExpired):
                        raise
                    except Exception as exc:
                        rows = None
                        gaps.append(f"division {d['division_id']} ({d['format']}): schedule unavailable "
                                    f"({type(exc).__name__}); its existing scoresheets were NOT re-checked")
                    targets = [str(m["match_id"]) for m in rows or []
                               if m.get("is_scored") and not m.get("is_bye") and str(m["match_id"]) in had_rows]
                    result["reconcile_targets"] = len(targets)
                    for mid in targets:
                        try:
                            outcome = call_with_confirmed_denial_retry(run_config, lambda mid=mid: reconcile_match(
                                run_config, db, mid, d["catalog_session_name"], scoresheet=scoresheet, resolve=resolve))
                        except ConfirmedScopeDenial:
                            db.rollback()
                            outcome = {"match_id": mid, "status": "denied"}
                        except (AccessTokenMissing, AccessTokenExpired):
                            raise
                        except Exception as exc:
                            db.rollback()
                            outcome = {"match_id": mid, "status": "fetch_failed", "error": type(exc).__name__}
                        outcome["division_id"] = d["division_id"]
                        checked.append(outcome)
                        if outcome["status"] in ("denied", "fetch_failed"):
                            gaps.append(f"match {mid}: scoresheet {outcome['status'].replace('_', ' ')}; existing rows "
                                        "kept unverified")
                        elif outcome["status"] == "empty_scoresheet_kept":
                            gaps.append(f"match {mid}: APA returned no player rows; {outcome['rows_before']} existing "
                                        "row(s) kept unverified")
                        elif outcome["status"] == "unresolved_identity_partial":
                            gaps.append(f"match {mid}: {outcome['unresolved_identities']} scoresheet identity(ies) "
                                        "unresolved; rows updated/added only, nothing removed")
                results.append(result)
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
            "method": ("APA GraphQL: sync_division_wide(resume=True) for rosters, schedules and missing scoresheets"
                       + ("; then every already-captured scored match re-fetched and its player results reconciled"
                          if mode == "reconcile" else "; existing scoresheets NOT re-checked (missing-only)")),
            "mode": mode,
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
        "reconciliation": {
            "matches_checked": [c["match_id"] for c in checked if c["status"] not in ("denied", "fetch_failed")],
            "matches_failed": [c["match_id"] for c in checked if c["status"] in ("denied", "fetch_failed")],
            "player_results_changed": [{"match_id": c["match_id"], **x} for c in checked for x in c.get("changed", [])],
            "player_results_added": [{"match_id": c["match_id"], "player": p} for c in checked for p in c.get("added", [])],
            "player_results_removed": [{"match_id": c["match_id"], "player": p} for c in checked
                                       for p in c.get("removed", [])],
            "outcomes": checked,
        },
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
    # Complete only when nothing was denied, failed, refused or left uncovered -- and only for the scope above.
    report["coverage"] = "partial" if gaps or mode != "reconcile" else "complete"
    (out_dir / "refresh_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _write_failure(out_dir: Path, exc: BaseException, scrub: Callable[[Any], str], tb: str) -> None:
    """refresh_error.json: what stopped the run (type, message, scrubbed traceback). Never a token."""
    (out_dir / "refresh_error.json").write_text(json.dumps({
        "schema": "ultimate-coach-current-session-refresh-error-v1",
        "failed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "error_type": type(exc).__name__, "message": scrub(exc)[:2000], "traceback": scrub(tb)[-6000:],
        "note": "No refresh report was written; this copy is NOT a refreshed database. The source DB is untouched.",
    }, indent=2), encoding="utf-8")


def describe_source(db_path: Path) -> dict[str, Any]:
    """What a build is about to read: an archived DB, or a refreshed copy -- and if refreshed, whether its report
    still describes this exact file and whether its coverage was complete. Only a complete reconcile refresh whose
    report matches the file's hash is ``accepted_current_data``; a partial one must never pass as current."""
    db_path = Path(db_path)
    report_path = db_path.with_name("refresh_report.json")
    if not report_path.is_file():
        return {"refreshed": False, "accepted_current_data": False,
                "note": "no refresh_report.json beside the source DB: data as originally archived, not refreshed"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    matches = (report.get("provenance") or {}).get("refreshed_db_sha256") == sha256_file(db_path)
    coverage = report.get("coverage") or "partial"
    return {
        "refreshed": True, "report": str(report_path), "report_sha256": sha256_file(report_path),
        "report_matches_db": matches, "mode": (report.get("provenance") or {}).get("mode"),
        "coverage": coverage, "gaps": len(report.get("gaps") or []), "scope": report.get("scope"),
        "started_utc": report.get("started_utc"), "finished_utc": report.get("finished_utc"),
        "accepted_current_data": bool(matches and coverage == "complete"),
    }


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
    parser.add_argument("--mode", choices=("reconcile", "missing-only"), default="reconcile",
                        help="reconcile (default): also re-fetch and reconcile every already-captured scored match; "
                             "missing-only: fetch only scoresheets the copy lacks (interrupted-acquisition style)")
    parser.add_argument("--verify-member", help="APA member id whose current-team fixtures to verify")
    parser.add_argument("--verify-date", help="YYYY-MM-DD of the fixtures to verify (e.g. Monday's)")
    parser.add_argument("--describe-source", metavar="DB",
                        help="print (JSON) whether DB is a refreshed copy and whether it is accepted current data; "
                             "no network, nothing written")
    args = parser.parse_args(argv)

    if args.describe_source:
        print(json.dumps(describe_source(Path(args.describe_source))))
        return 0
    if args.verify_date and not args.verify_member:
        # Default to the configured viewer (apa_config.yaml / apa_config.local.yaml), never a guess.
        from analytics.ultimate_coach_match_day import load_match_day_settings

        args.verify_member = load_match_day_settings(Path(args.config)).viewer_member_external_id
        if not args.verify_member:
            print("--verify-date needs --verify-member (no viewer is configured)")
            return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    out_dir = Path(args.out_root) / f"refresh-{stamp}"
    try:
        check_output_root(out_dir, PROJECT_ROOT)
    except BoundaryRefused as exc:
        print(f"Refused: {exc}")
        return 2
    # A progress log beside the copy: the first real run (2026-10-08 15:43 UTC) died after copying with only a
    # console traceback, so nothing on disk said why. Scrubbed of anything token-like before it is written.
    import logging
    import re
    import traceback

    out_dir.mkdir(parents=True, exist_ok=True)
    scrub = lambda text: re.sub(r"(?i)(bearer\s+)?eyJ[\w-]+\.[\w-]+\.[\w-]+|bearer\s+\S+", "[redacted]", str(text))  # noqa: E731

    class _Scrubbed(logging.Formatter):
        def format(self, record):
            return scrub(super().format(record))

    handler = logging.FileHandler(out_dir / "refresh.log", encoding="utf-8")
    handler.setFormatter(_Scrubbed("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    try:
        report = run_refresh(load_config(args.config), source_db=Path(args.source_db), catalog_path=Path(args.catalog),
                             out_dir=out_dir, mine_only=args.mine_only, verify_member=args.verify_member, mode=args.mode,
                             verify_date=args.verify_date)
    except (AccessTokenMissing, AccessTokenExpired) as exc:
        print(f"APA login needed: {type(exc).__name__}. Run tools/capture_apa_graphql.py --refresh-ultimate-coach "
              "and log in yourself; nothing was promoted and the source DB is untouched.")
        _write_failure(out_dir, exc, scrub, traceback.format_exc())
        return 3
    except RefreshError as exc:
        print(f"Refresh stopped: {exc}")
        _write_failure(out_dir, exc, scrub, traceback.format_exc())
        return 4
    except Exception as exc:   # anything else: record it on disk, never as a silent console-only traceback
        _write_failure(out_dir, exc, scrub, traceback.format_exc())
        print(f"Refresh FAILED: {type(exc).__name__}: {scrub(exc)[:400]}\n"
              f"  details: {out_dir / 'refresh_error.json'} · nothing was promoted; the source DB is untouched.")
        return 5
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
    c = report["changes"]
    print(f"Refreshed copy: {report['provenance']['refreshed_db']}")
    print(f"  SHA256 {report['provenance']['refreshed_db_sha256']} (source {report['provenance']['source_db_sha256']}, unchanged)")
    print(f"  checked {c['date_range_checked']}; latest scored {c['latest_scored_date_before']} -> {c['latest_scored_date_after']}")
    print(f"  added {len(c['matches_added'])} · newly scored {len(c['matches_newly_scored'])} · score changed "
          f"{len(c['matches_score_changed'])} · scoresheet rows +{c['scoresheet_rows_added']}")
    r = report["reconciliation"]
    print(f"  reconciled {len(r['matches_checked'])} already-captured match(es), {len(r['matches_failed'])} failed/denied ·"
          f" player results changed {len(r['player_results_changed'])} · added {len(r['player_results_added'])} ·"
          f" removed {len(r['player_results_removed'])}")
    print(f"  coverage: {report['coverage'].upper()} for {report['scope']['divisions']} division(s) ·"
          f" gaps: {len(report['gaps'])} (see refresh_report.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
