"""One end-user refresh: APA -> private fixtures -> existing ingest -> both Ultimate Coach outputs.

Full and quick use the same correctness path. Quick always checks live results,
including every scored sheet, then reuses only artifacts whose dependencies
and bytes still match. No automatic production DB promotion or web publishing.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import threading
import time
import uuid

from pipeline.refresh_progress import progress_span
from pipeline.refresh_sources import ResponseFixtures, acquire_current_sources, digest, encoded, sha256

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "ultimate-coach-complete-refresh-v1"


class RefreshFailed(RuntimeError):
    pass


def atomic_json(path: Path, document):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_bytes(encoded(document))
    os.replace(temp, path)


def code_signature(groups):
    files = {}
    for group in groups:
        for path in (ROOT / group).rglob("*.py"):
            files[path.relative_to(ROOT).as_posix()] = sha256(path)
    return digest(files)


@contextmanager
def run_lock(root: Path):
    path = root / "REFRESH.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RefreshFailed("another refresh is active, or an interrupted REFRESH.lock needs review") from None
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


def copy_database(source: Path | None, target: Path):
    if not source:
        return
    src = sqlite3.connect(Path(source).resolve().as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def previous_bundle(root: Path, check):
    pointer = root / "CURRENT.json"
    if not pointer.is_file():
        return None
    previous = json.loads(pointer.read_text(encoding="utf-8"))
    run = previous.get("run")
    if previous.get("schema") != SCHEMA or not isinstance(run, str) or Path(run).name != run or run in (".", ".."):
        raise RefreshFailed("invalid current-refresh pointer; previous files were not replaced")
    folder = root / run
    check(folder)
    manifest = folder / "manifest.json"
    ready = json.loads((folder / "READY").read_text(encoding="utf-8"))
    if sha256(manifest) != ready.get("manifest_sha256") or json.loads(manifest.read_text(encoding="utf-8")) != previous:
        raise RefreshFailed("current-refresh manifest/READY/pointer binding is invalid")
    return previous


def fixture_identity_resolver(store, catalog, division):
    """Supplement current-roster resolution only with an exact captured ID chain.

    Departed membership stays historical. Require the exact team, division and
    session membership as well as career-source league/session/format ownership.
    """
    from database.models import Player, PlayerTeamHistory
    from scheduler.graphql_sync import resolve_scoresheet_identities
    links = store.exact_player_members()
    contexts = {(str(d.get('league_id') or ''),
                 str(d.get('catalog_session_id') or d.get('session_id') or ''))
                for d in catalog.get('divisions') or []
                if str(d.get('division_id')) == str(division['division_id'])
                and (d.get('catalog_session_name') or d.get('session_name')) == division['session_name']
                and (d.get('type') or d.get('format')) == division['format']}

    def resolve(db, session_name, scores, *, current_only=True):
        mapping, _, _ = resolve_scoresheet_identities(db, session_name, scores, current_only=current_only)
        if len(contexts) == 1 and session_name == division['session_name']:
            league, session = next(iter(contexts))
            for row in scores:
                alias = str(row.get('player_id') or '')
                if not alias or not row.get('team_id'):
                    continue
                members = links.get((league, session, division['format'], alias))
                if not members:
                    continue
                if len(members) != 1:
                    mapping.pop(alias, None)
                    continue
                member = next(iter(members))
                candidates = db.query(Player).join(PlayerTeamHistory).filter(
                    Player.external_id == member,
                    PlayerTeamHistory.team_external_id == str(row.get('team_id') or ''),
                    PlayerTeamHistory.division_id == str(division['division_id']),
                    PlayerTeamHistory.session_name == session_name).all()
                if len(candidates) != 1:
                    mapping.pop(alias, None)
                elif alias in mapping and mapping[alias] != member:
                    raise RefreshFailed('captured member identity conflicts with current roster identity')
                else:
                    mapping[alias] = member
        identities = {str(row['player_id']) for row in scores if row.get('player_id')}
        return mapping, len(identities & mapping.keys()), len(identities - mapping.keys())
    return resolve


def replay_ingest(config, fixtures: Path, scope, database: Path, directory: Path, *, progress=None):
    from sqlalchemy.orm import Session
    from auth.graphql_client import use_fixture_provider
    from database.engine import create_db_engine
    from database.ingest import ingest_standings
    from database.models import StandingsSnapshot
    from sqlalchemy import func
    from scheduler import graphql_sync as sync
    from scraper import graphql_scraper as api
    from scraper.player_enrichment import enrich_all_players
    from scripts.refresh_ultimate_coach_current_session import reconcile_match, _match_gap

    run_config = {**config, "database": {"path": str(database)},
                  "apa": {**(config.get("apa") or {}), "access_token": "fixture-replay-only"}}
    engine = create_db_engine(run_config)
    gaps, counts, reconciled = [], [], []
    catalog = directory / "catalog.json"
    catalog.write_bytes(encoded(scope["catalog"]))
    try:
        store = ResponseFixtures(fixtures, replay=True)
        with use_fixture_provider(store), Session(engine) as db:
            for team_number, team_id in enumerate(scope["team_ids"], 1):
                if progress:
                    progress(f"INGEST TEAM {team_number}/{len(scope['team_ids'])}")
                sync.ingest_team_data(db, api.fetch_team_data(run_config, team_id))
            # One refresh is one standings snapshot across ALL current divisions.
            # Timestamp it after team fallback snapshots, so latest_standings sees
            # every division rather than only the final per-division write.
            standings_at = datetime.now(timezone.utc).replace(tzinfo=None)
            standings_expected = 0
            for division_number, division in enumerate(scope["divisions"], 1):
                if progress:
                    progress(f"INGEST DIVISION {division_number}/{len(scope['divisions'])}")
                did, fmt, session = division["division_id"], division["format"], division["session_name"]
                # Division standings are a separate APA response, not part of
                # fetch_team_data. Persist them explicitly after team fallback
                # snapshots so the latest snapshot uses the authoritative table.
                standings = api.division_standings_rows(api.fetch_division_standings(run_config, did))
                if not standings:
                    raise RefreshFailed("current division standings are unreadable; previous bundle retained")
                standings_expected += ingest_standings(db, standings, captured_at=standings_at)
                totals = sync.sync_division_wide(run_config, db, did, fmt, session, resume=False,
                                                roster_is_current=True, identity_current_only=True)
                counts.append(totals)
                gaps.extend(sync.reconcile_division_wide_coverage(totals))
                matches = [m for m in api.division_schedule_rows(api.fetch_division_schedule(run_config, did))
                           if m["is_scored"] and not m["is_bye"]]
                resolve = fixture_identity_resolver(store, scope['catalog'], division)
                for match_number, match in enumerate(matches, 1):
                    if progress:
                        progress(f"RECONCILE SCORESHEET {match_number}/{len(matches)} in current division")
                    if match["is_scored"] and not match["is_bye"]:
                        result = reconcile_match(run_config, db, match["match_id"], session, resolve=resolve)
                        reconciled.append(result)
                        if result["status"] == "not_in_db":
                            gaps.append("authoritative match missing after fixture ingestion")
                        elif problem := _match_gap(result):
                            gaps.append(problem)
            latest_at = db.query(func.max(StandingsSnapshot.captured_at)).scalar()
            latest_count = db.query(StandingsSnapshot).filter(StandingsSnapshot.captured_at == latest_at).count()
            if latest_at != standings_at or latest_count != standings_expected:
                raise RefreshFailed("latest standings snapshot does not contain all captured division rows")
            if progress:
                progress(f"STANDINGS VERIFIED - {len(scope['divisions'])} divisions in one latest snapshot")
            if progress:
                progress("INGEST CAREER STATS from captured responses")
            enrichment = enrich_all_players(run_config, db, catalog=scope["catalog"], catalog_path=catalog,
                                            staging_db=database, report_path=directory / "career_refresh.json")
            db.commit()
    finally:
        engine.dispose()
    report = {"scope": scope["divisions"], "divisions": counts, "reconciled": reconciled,
              "gaps": gaps, "coverage": "partial" if gaps else "complete",
              "career_counts": enrichment["counts"],
              "historical_scope": "Existing historical games retained; current listed divisions and resolvable career contexts rechecked."}
    (directory / "refresh_report.json").write_bytes(encoded(report))
    if gaps:
        if progress:
            unresolved = [r for r in reconciled if r.get("status") == "unresolved_identity_partial"]
            if unresolved:
                identities = sum(r.get("unresolved_identities", 0) for r in unresolved)
                progress(f"SOURCE REVIEW REQUIRED - {len(unresolved)} scoresheets contain {identities} unresolved row identities; no identity was guessed")
            progress("Coverage details: " + str(directory / "refresh_report.json"))
        raise RefreshFailed(f"source coverage incomplete ({len(gaps)} gaps); no new workbook or HTML built; previous bundle retained")
    return report


def rebuild_database(config, database):
    from sqlalchemy.orm import Session
    from database.engine import create_db_engine
    from pipeline.ingest import rebuild_matchups, rebuild_analytics
    from database.models import PlayerH2HAdvantage
    engine = create_db_engine({"database": {"path": str(database)}})
    try:
        with Session(engine) as db:
            # This is a derived table in this private candidate. The legacy
            # upsert-only builder otherwise retains pairings whose last source
            # game was removed by authoritative reconciliation.
            db.query(PlayerH2HAdvantage).delete(synchronize_session=False)
            results = {"matchups": rebuild_matchups(db), **rebuild_analytics(db)}
            db.commit()
            return results
    finally:
        engine.dispose()


def build_payload(database, settings):
    from sqlalchemy.orm import Session
    from database.engine import create_db_engine
    from analytics.ultimate_coach_cockpit_identity_bridge import build_verified_cockpit_payload
    engine = create_db_engine({"database": {"path": str(database)}}, create_tables=False)
    try:
        with Session(engine) as db:
            payload = build_verified_cockpit_payload(db, match_day_timezone=settings.timezone)
    finally:
        engine.dispose()
    if not payload.get("players") or payload.get("probability_publication") != "FORBIDDEN":
        raise RefreshFailed("verified Ultimate Coach payload is empty or has invalid evidence invariants")
    return payload


def check_database(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RefreshFailed("database integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise RefreshFailed("database contains unresolved foreign keys")


def run_refresh(*, mode="full", config_path=None, run_root=None, fixture_source=None,
                acquire=acquire_current_sources, workbook_validator=None, html_validator=None,
                boundary=None, token_loader=None):
    started = time.monotonic()
    from pipeline.refresh_summary import completion_counts, completion_summary
    from analytics.ultimate_coach_match_day import load_match_day_settings
    from scheduler.graphql_sync import load_config
    from scripts.repo_boundary import check_output_root
    from pipeline.refresh_workbook import recalculate_and_validate, validate_html, preflight
    from ui.export_excel_ultimate_coach import write_workbook
    from ui.ultimate_coach import render

    root = Path(run_root or ROOT / "ultimate-coach-runs" / "refresh").absolute()
    config_path = Path(config_path or ROOT / "apa_config.yaml").absolute()
    check = boundary or (lambda p: check_output_root(p, ROOT))
    check(root)
    check(config_path)
    root.mkdir(parents=True, exist_ok=True)
    need_preflight = workbook_validator is None or html_validator is None
    workbook_validator = workbook_validator or recalculate_and_validate
    html_validator = html_validator or validate_html
    pointer = root / "CURRENT.json"
    status_path = root / "REFRESH_STATUS.txt"
    step = "1 CONFIGURATION"
    directory = root / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])

    status_lock = threading.RLock()
    def status(message, *, required=True):
        with status_lock:
            print(message, flush=True)
            try:
                with status_path.open("a", encoding="utf-8") as stream:
                    stream.write(message + "\n")
            except OSError:
                if required:
                    raise
                print("Completed bundle is current; status log could not be updated.", flush=True)

    with run_lock(root):
        check(directory)
        directory.mkdir()
        status_path.write_text(f"{mode.upper()} REFRESH {directory.name}\n", encoding="utf-8")
        try:
            status("STEP 1/8 - configuration and validator prerequisites")
            if need_preflight:
                with progress_span(status, "validator prerequisite check"):
                    preflight()
            config = load_config(str(config_path))
            if mode not in ("full", "quick"):
                raise RefreshFailed("refresh mode must be full or quick")
            settings = load_match_day_settings(config_path)
            config = {**config, "apa": {**(config.get("apa") or {})}}
            base_setting = (config.get("refresh") or {}).get("source_database")
            base = Path(base_setting) if base_setting else ROOT / "data" / "ultimate_coach_staging.db"
            if not base.is_absolute():
                base = ROOT / base
            if not base.is_file() and not base_setting:
                base = ROOT / "data" / "apa_tracker.db"
            if base_setting and not base.is_file():
                raise RefreshFailed("configured refresh source database does not exist")
            if base.is_file():
                check(base)
                base = base.resolve()
            else:
                base = None
            base_sha = sha256(base) if base else None
            previous = previous_bundle(root, check)
            seed = base
            if previous and previous.get("base_sha256") == base_sha:
                candidate = root / previous["run"] / "ultimate_coach_staging.db"
                check(candidate)
                if not candidate.is_file() or sha256(candidate) != previous["artifacts"]["ultimate_coach_staging.db"]:
                    raise RefreshFailed("last completed database is missing or changed; restore its verified backup before refreshing")
                seed = candidate
            source_sha = sha256(seed) if seed else None
            step = "2 SCRAPE APA SOURCES"
            status("STEP 2/8 - authenticate, then capture APA sources; requests are logged below")
            fixtures = directory / "fixtures"
            if fixture_source:
                # Explicit offline verification input. End-user launchers never
                # supply this option or advertise an offline run as live.
                source = Path(fixture_source).absolute()
                check(source)
                with progress_span(status, "load and verify offline source fixtures"):
                    shutil.copytree(source, fixtures)
                    store = ResponseFixtures(fixtures, replay=True)
                    scope = json.loads((fixtures / "scope.json").read_text(encoding="utf-8"))
                live = False
            else:
                from scraper.graphql_scraper import AccessTokenExpired, AccessTokenMissing
                if token_loader is None:
                    from tools.run_ultimate_coach_browser import capture_access_token
                    token_loader = lambda: capture_access_token(progress=status)
                store = ResponseFixtures(fixtures, progress=status)
                for attempt in range(4):
                    token = os.environ.get("APA_ACCESS_TOKEN") if attempt == 0 else None
                    token = token or token_loader()
                    if not token:
                        raise RefreshFailed("APA login did not supply an authenticated session")
                    status("[AUTH] Authorization available in memory; starting authenticated APA API queries")
                    config["apa"]["access_token"] = token
                    try:
                        with progress_span(status, "capture APA source fixtures"):
                            scope = acquire(config, seed, store)
                        break
                    except (AccessTokenExpired, AccessTokenMissing):
                        if attempt == 3:
                            raise
                        status("APA session expired; sign in again to continue this capture")
                store.save_index()
                (fixtures / "scope.json").write_bytes(encoded(scope))
                live = True
            status("SCRAPE COMPLETE" + (" (OFFLINE VALIDATION INPUT)" if not live else ""))
            if previous and not live and previous.get("live_sources_checked"):
                raise RefreshFailed("offline verification cannot replace a live current bundle; select a separate run root")
            input_key = digest({"sources": store.content_sha256, "scope": digest(scope),
                                "ingestion": code_signature(["auth", "scraper", "parser", "database", "scheduler", "analytics"]),
                                "pipeline": code_signature(["pipeline"]),
                                "reconcile": sha256(ROOT / "scripts/refresh_ultimate_coach_current_session.py"),
                                "h2h_builder": sha256(ROOT / "scripts/build_head_to_head.py"),
                                "trends_builder": sha256(ROOT / "scripts/build_player_trends.py"), "base": base_sha})
            data_same = bool(mode == "quick" and previous and previous.get("input_sha256") == input_key and seed != base)
            step = "3 DATABASE INGESTION"
            status("STEP 3/8 - database fixture ingestion and reconciliation")
            database = directory / "ultimate_coach_staging.db"
            with progress_span(status, "copy source database into private candidate"):
                copy_database(seed, database)
            if data_same:
                prior_report = root / previous["run"] / "refresh_report.json"
                if sha256(prior_report) != previous["report_sha256"]:
                    raise RefreshFailed("previous coverage report checksum mismatch")
                report = json.loads(prior_report.read_text(encoding="utf-8"))
                (directory / "refresh_report.json").write_bytes(encoded(report))
                status("DATABASE UP TO DATE - unchanged source content")
            else:
                with progress_span(status, "database ingestion and scoresheet reconciliation"):
                    report = replay_ingest(config, fixtures, scope, database, directory, progress=status)
                status("DATABASE UPDATED")
            status("SOURCE SCOPE: current dashboard divisions; existing older games retained, not recrawled")
            career = report["career_counts"]
            status(f"CAREER STATS: {career['league_stat_format_rows_written']} format rows; "
                   f"{career['unresolved_scopes']} unresolved scopes; "
                   f"{career['players_without_catalog_context']} players without proven league context")
            settings_key = {"timezone": settings.timezone, "viewer": settings.viewer_member_external_id,
                            "card": settings.viewer_card_number}
            step = "4 MATCHUPS AND TRENDS"
            status("STEP 4/8 - matchups and trends")
            if data_same:
                derived = previous["derived"]
                # Keep the exact already-verified generation when fresh API
                # content is identical; timestamp-only ingest writes are not
                # promoted as a new source generation.
                # SQLite backup can change file bytes. Reuse the exact verified
                # database as well as its derived generation on this fast path.
                shutil.copyfile(seed, database)
                status("MATCHUPS UP TO DATE - unchanged source content")
                status("TRENDS UP TO DATE - unchanged source content")
            else:
                with progress_span(status, "rebuild matchups and trends"):
                    derived = rebuild_database(config, database)
                status("MATCHUPS REBUILT")
                status("TRENDS REBUILT")
            step = "5 RECOMMENDATIONS"
            status("STEP 5/8 - verified recommendation payload")
            with progress_span(status, "build verified recommendations"):
                payload = build_payload(database, settings)
            payload_key = digest(payload)
            status("RECOMMENDATIONS UPDATED")
            built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            common = {"payload": payload_key, "settings": settings_key, "date": built_at[:10],
                      "analytics": code_signature(["analytics"])}
            keys = {"Ultimate_Coach.xlsx": digest({**common, "exporter": sha256(ROOT / "ui/export_excel_ultimate_coach.py"),
                      "engine": sha256(ROOT / "ui/excel_war_room.py")}),
                    "ultimate_coach.html": digest({**common, "renderer": sha256(ROOT / "ui/ultimate_coach.py"),
                      "runtime": sha256(ROOT / "ui/ultimate_coach_war_room.js")})}
            validations, reused = {}, []
            for name, key in keys.items():
                step = "6 WORKBOOK" if name.endswith("xlsx") else "7 HTML"
                status("STEP 6/8 - workbook generation and native Excel validation" if name.endswith("xlsx")
                       else "STEP 7/8 - HTML generation and browser validation")
                target = directory / name
                old = root / previous["run"] / name if previous else None
                if old:
                    check(old)
                reuse = bool(mode == "quick" and previous and previous.get("dependencies", {}).get(name) == key
                             and old.is_file() and sha256(old) == previous["artifacts"].get(name))
                if reuse:
                    shutil.copyfile(old, target)
                    reused.append(name)
                    validations[name] = previous["validations"][name]
                    status(("WORKBOOK" if name.endswith("xlsx") else "HTML") + " UP TO DATE - verified bytes reused")
                elif name.endswith("xlsx"):
                    with progress_span(status, "generate Ultimate Coach workbook"):
                        write_workbook(payload, target, built_at=built_at, source_db=database.name,
                                       viewer_member_external_id=settings.viewer_member_external_id,
                                       viewer_card_number=settings.viewer_card_number)
                    with progress_span(status, "native Excel recalculation and workbook validation"):
                        validations[name] = workbook_validator(target)
                    status("WORKBOOK REBUILT")
                else:
                    # Workbook consumes/derives its data first; HTML may release
                    # evidence memory only after the shared payload is used.
                    with progress_span(status, "generate Ultimate Coach HTML"):
                        target.write_text(render(payload, built_at=built_at, consume_evidence=False,
                            viewer_member_external_id=settings.viewer_member_external_id,
                            viewer_card_number=settings.viewer_card_number), encoding="utf-8")
                    with progress_span(status, "Chromium HTML validation"):
                        validations[name] = html_validator(target)
                    status("HTML REBUILT")
            step = "8 VALIDATION AND COMPLETION"
            status("STEP 8/8 - database integrity, source preservation and completion bindings")
            with progress_span(status, "database integrity and foreign-key validation"):
                check_database(database)
            with progress_span(status, "verify source and artifact bindings; prepare completed bundle"):
                if seed and sha256(seed) != source_sha:
                    raise RefreshFailed("source database changed during the refresh")
                if base and sha256(base) != base_sha:
                    raise RefreshFailed("configured base database changed during the refresh")
                summary_counts = completion_counts(store, scope)
                artifacts = {name: sha256(directory / name) for name in (*keys, "ultimate_coach_staging.db")}
                manifest = {"schema": SCHEMA, "run": directory.name, "mode": mode, "live_sources_checked": live,
                            "checked_at": datetime.now(timezone.utc).isoformat(), "base_sha256": base_sha,
                            "input_sha256": input_key, "payload_sha256": payload_key, "source_sha256": store.content_sha256,
                            "dependencies": keys, "artifacts": artifacts, "validations": validations,
                            "derived": derived, "reused": reused, "scope": report["scope"],
                            "coverage": report["coverage"], "career_counts": report["career_counts"],
                            "report_sha256": sha256(directory / "refresh_report.json"),
                            "historical_scope": report["historical_scope"], "production_database_promoted": False}
                atomic_json(directory / "manifest.json", manifest)
                atomic_json(directory / "READY", {"manifest_sha256": sha256(directory / "manifest.json")})
            # Finish required progress writes before committing the pointer.
            # A later unavailable status log must not turn success into failure.
            # One pointer commits the DB/workbook/HTML generation together.
            atomic_json(pointer, manifest)
            status("ALL REFRESH TASKS COMPLETE" + (" (OFFLINE VALIDATION)" if not live else ""), required=False)
            status("Workbook: " + str(directory / "Ultimate_Coach.xlsx"), required=False)
            status("HTML: " + str(directory / "ultimate_coach.html"), required=False)
            status(completion_summary(summary_counts, live=live, data_reused=data_same, reused=reused,
                                      directory=directory, elapsed=time.monotonic()-started), required=False)
            return manifest
        except BaseException as exc:
            from scripts.refresh_ultimate_coach_current_session import _scrub
            exc._refresh_step_logged = True
            status(f"FAILED AT STEP {step}: {_scrub(str(exc))}")
            atomic_json(directory / "FAILED.json", {"step": step, "error_type": type(exc).__name__})
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("full", "quick"), default="full")
    parser.add_argument("--config", type=Path, default=ROOT / "apa_config.yaml")
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--fixtures", type=Path, help="explicit offline verification input; not a live refresh")
    parser.add_argument("--open", action="store_true", help="open the completed workbook and HTML")
    parser.add_argument("--no-open", dest="open", action="store_false", help="leave completed files closed")
    parser.set_defaults(open=False)
    args = parser.parse_args(argv)
    try:
        manifest = run_refresh(mode=args.mode, config_path=args.config, run_root=args.run_root, fixture_source=args.fixtures)
    except (Exception, KeyboardInterrupt) as exc:
        if not getattr(exc, "_refresh_step_logged", False):
            print(f"FAILED AT STEP 1 INITIALIZATION: {type(exc).__name__}; no completed files replaced.", flush=True)
        print("Refresh stopped. See the failed step and REFRESH_STATUS.txt when available. Previous completed files preserved.", flush=True)
        return 1
    if args.open:
        root = args.run_root or ROOT / "ultimate-coach-runs" / "refresh"
        for name in ("Ultimate_Coach.xlsx", "ultimate_coach.html"):
            try:
                os.startfile(str((root / manifest["run"] / name).resolve()))
            except OSError:
                print(f"Refresh complete; could not open {name}. Use the completed path printed above.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
