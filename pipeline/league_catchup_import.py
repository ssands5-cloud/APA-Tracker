"""Offline import of League Catch-up captures into a COPY of the archive DB.

``tools/league_catchup.py`` saves the raw output of the same three APA calls
``scheduler.graphql_sync.sync_division_wide`` makes (division rosters,
division schedule, match scoresheet). This module replays that unmodified
sync against those saved files instead of APA, so identity resolution and
every ingest helper run exactly as they did when the archive was built.

Safety properties:
  * never contacts APA (the three fetch functions are swapped for file reads
    for the duration of the import and restored afterwards);
  * never writes the source archive: it is opened read-only, copied with
    SQLite's backup API, and its SHA-256 is checked before and after;
  * existing game evidence is fingerprinted before and after the import and
    must be byte-for-byte unchanged (resume mode skips matches that already
    have scoresheet rows, so only missing games are added).
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import event
from sqlalchemy.orm import Session

from analytics.matchup_builder import build_matchups
from database.engine import create_db_engine
from scheduler import graphql_sync as sync
from scraper.graphql_scraper import division_schedule_rows, head_to_head_rows

logger = logging.getLogger(__name__)

REPORT_SCHEMA = "league-catchup-import-v1"
BUSY_TIMEOUT_MS = 120_000
GAME_TABLES = ("player_head_to_head", "player_matches")
COUNT_TABLES = ("matches", "players", "teams", "player_matches", "player_head_to_head",
                "player_team_history", "player_matchups")


class CatchupImportError(RuntimeError):
    """A structural or safety failure; the import must stop."""


class MissingCapture(LookupError):
    """A capture the sync asked for is not in any catch-up store."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class OfflineCatchupSource:
    """Answers the three division-wide APA calls from saved catch-up files.

    Stores are searched in order; the first store holding a file wins, so the
    newest store (league-catchup) must come first.
    """

    def __init__(self, stores: list[Path]):
        self.stores = [Path(s) for s in stores]
        if not self.stores:
            raise CatchupImportError("no catch-up stores given")
        for store in self.stores:
            if not (store / "matches").is_dir():
                raise CatchupImportError(f"not a catch-up store (no matches/ folder): {store}")
        self.misses: list[tuple[str, str]] = []
        self.served = Counter()

    def _find(self, kind: str, key: str) -> Path | None:
        for store in self.stores:
            path = store / kind / f"{key}.json"
            if path.is_file():
                return path
        return None

    def _load(self, kind: str, key: str) -> Any:
        path = self._find(kind, str(key))
        if path is None:
            self.misses.append((kind, str(key)))
            raise MissingCapture(f"no saved {kind} capture for {key}")
        self.served[kind] += 1
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload["match"] if kind == "matches" else payload

    def division_rosters(self, config, division_id):
        return self._load("rosters", division_id)

    def division_schedule(self, config, division_id):
        return self._load("divisions", division_id)

    def match_detail(self, config, match_id):
        match = self._load("matches", match_id)
        if not match or str(match.get("id")) != str(match_id):
            # sync_division_wide logs and skips any non-auth error, so record it as a miss too.
            self.misses.append(("matches", str(match_id)))
            raise CatchupImportError(f"saved scoresheet {match_id} is empty or has a different id")
        return match

    def schedules(self) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for store in self.stores:
            for path in sorted((store / "divisions").glob("*.json")):
                found.setdefault(path.stem, path)
        return found

    def scoresheet(self, match_id: str) -> dict | None:
        path = self._find("matches", match_id)
        if path is None:
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("match")


@contextmanager
def offline_fetches(source: OfflineCatchupSource) -> Iterator[None]:
    """Point sync_division_wide's three fetch calls at saved files, then restore them."""
    names = ("fetch_division_rosters", "fetch_division_schedule", "fetch_match_detail")
    saved = {name: getattr(sync, name) for name in names}
    sync.fetch_division_rosters = source.division_rosters
    sync.fetch_division_schedule = source.division_schedule
    sync.fetch_match_detail = source.match_detail
    try:
        yield
    finally:
        for name, fn in saved.items():
            setattr(sync, name, fn)


def scoresheet_games(match: dict | None) -> int:
    if not match:
        return 0
    return sum(1 for r in head_to_head_rows(match) if r["result"] in ("W", "L")) // 2


def find_pending(db_path: Path, source: OfflineCatchupSource, since: str, today: str) -> dict[str, dict]:
    """Played matches with a saved scoresheet holding games the DB has no games for.

    Returns {match_id: {"division_id", "date", "games", "in_db"}}.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        with_games = {r[0] for r in con.execute("select distinct match_id from player_head_to_head")}
        by_ext = {str(ext): pk for pk, ext in con.execute("select id, external_id from matches")}
    finally:
        con.close()
    pending: dict[str, dict] = {}
    for division_id, path in source.schedules().items():
        for row in division_schedule_rows(json.loads(path.read_text(encoding="utf-8"))):
            mid, when = row["match_id"], str(row["date"] or "")[:10]
            if not mid or row["is_bye"] or not row["is_scored"] or not (since <= when <= today):
                continue
            if by_ext.get(mid) in with_games:
                continue
            games = scoresheet_games(source.scoresheet(mid))
            if games:
                pending[mid] = {"division_id": division_id, "date": when, "games": games,
                                "in_db": mid in by_ext}
    return pending


def catalog_divisions(catalog_path: Path, division_ids: set[str]) -> dict[str, dict]:
    """Session/format for each division, exactly as the archive runner derives them."""
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    found: dict[str, dict] = {}
    for row in catalog.get("divisions") or []:
        did = str(row.get("division_id") or "")
        if did not in division_ids:
            continue
        session_id = str(row.get("catalog_session_id") or row.get("session_id") or "")
        meta = {
            "division_id": did,
            "session_id": session_id,
            "session_name": str(row.get("catalog_session_name") or row.get("session_name") or ""),
            "format": str(row.get("format") or row.get("type") or ""),
            "is_current": bool(row.get("current_session_id")
                               and str(row.get("current_session_id")) == session_id),
        }
        if not meta["session_name"] or not meta["format"]:
            continue
        previous = found.get(did)
        if previous and (previous["session_name"], previous["format"]) != (meta["session_name"], meta["format"]):
            raise CatchupImportError(f"catalog disagrees about division {did}: {previous} vs {meta}")
        found[did] = meta
    missing = sorted(division_ids - set(found))
    if missing:
        raise CatchupImportError(f"divisions not in catalog (session/format unknown): {missing}")
    return found


def game_fingerprint(db_path: Path) -> dict[str, dict]:
    """Row count + SHA-256 of every row of the game-evidence tables, ordered by id."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out = {}
    try:
        for table in GAME_TABLES:
            digest, n = hashlib.sha256(), 0
            for row in con.execute(f"select * from {table} order by id"):
                digest.update(repr(row).encode("utf-8"))
                n += 1
            out[table] = {"rows": n, "sha256": digest.hexdigest()}
    finally:
        con.close()
    return out


def existing_game_fingerprint(db_path: Path, max_ids: dict[str, int]) -> dict[str, dict]:
    """Fingerprint of only the rows that existed before the import (id <= pre-import max)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out = {}
    try:
        for table in GAME_TABLES:
            digest, n = hashlib.sha256(), 0
            for row in con.execute(f"select * from {table} where id <= ? order by id", (max_ids[table],)):
                digest.update(repr(row).encode("utf-8"))
                n += 1
            out[table] = {"rows": n, "sha256": digest.hexdigest()}
    finally:
        con.close()
    return out


def table_counts(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in COUNT_TABLES}
    finally:
        con.close()


def max_ids(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {t: con.execute(f"select coalesce(max(id), 0) from {t}").fetchone()[0] for t in GAME_TABLES}
    finally:
        con.close()


def copy_database(source_db: Path, out_db: Path) -> None:
    if out_db.exists():
        raise CatchupImportError(f"output already exists, refusing to overwrite: {out_db}")
    if out_db.resolve() == source_db.resolve():
        raise CatchupImportError("output must be a different file from the source archive")
    out_db.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    dst = sqlite3.connect(str(out_db))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def drop_half_written_matches(out_db: Path, source_max_ids: dict[str, int]) -> list[dict]:
    """Remove scoresheet rows an interrupted run wrote for a match it never finished.

    Only rows created by this import are touched (id above the SOURCE archive's
    max id) and only for matches that have player-match rows but no
    head-to-head rows. Without this, resume mode would treat such a match as
    already imported and skip it forever.
    """
    con = sqlite3.connect(str(out_db))
    dropped = []
    try:
        rows = con.execute(
            "select pm.match_id, m.external_id, count(*), min(pm.id) from player_matches pm "
            "join matches m on m.id = pm.match_id "
            "where pm.match_id not in (select match_id from player_head_to_head) group by pm.match_id").fetchall()
        for match_pk, external_id, n, min_id in rows:
            if min_id <= source_max_ids["player_matches"]:
                raise CatchupImportError(
                    f"match {external_id} has pre-existing player-match rows without head-to-head; not touching it")
            con.execute("delete from player_matches where match_id = ? and id > ?",
                        (match_pk, source_max_ids["player_matches"]))
            dropped.append({"match": str(external_id), "player_match_rows": n})
        con.commit()
    finally:
        con.close()
    return dropped


def quick_check(db_path: Path) -> str:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return con.execute("pragma quick_check").fetchone()[0]
    finally:
        con.close()


def run_import(
    *,
    source_db: Path,
    out_db: Path,
    catalog_path: Path,
    stores: list[Path],
    since: str = "2024-01-01",
    today: str | None = None,
    dry_run: bool = False,
    rebuild_matchups: bool = True,
    resume: bool = False,
) -> dict[str, Any]:
    today = today or date.today().isoformat()
    source_db, out_db = Path(source_db), Path(out_db)
    if not source_db.is_file():
        raise CatchupImportError(f"source archive not found: {source_db}")
    source = OfflineCatchupSource(stores)
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "started": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run, "resume": resume, "since": since, "today": today,
        "source_db": str(source_db), "out_db": None if dry_run else str(out_db),
        "stores": [str(s) for s in source.stores],
        "catalog": str(catalog_path),
    }
    source_sha_before = sha256_file(source_db)
    report["source_sha256_before"] = source_sha_before

    pending = find_pending(source_db, source, since, today)
    division_ids = {p["division_id"] for p in pending.values()}
    divisions = catalog_divisions(catalog_path, division_ids)
    by_year = Counter(p["date"][:4] for p in pending.values())
    report["pending_before"] = {
        "matches": len(pending), "games": sum(p["games"] for p in pending.values()),
        "matches_already_in_db": sum(1 for p in pending.values() if p["in_db"]),
        "by_year": dict(sorted(by_year.items())), "divisions": len(division_ids),
    }
    logger.info("pending: %s", report["pending_before"])
    if dry_run or not pending:
        report["source_sha256_after"] = sha256_file(source_db)
        report["status"] = "dry_run" if dry_run else "nothing_to_import"
        return report

    # Baselines always come from the untouched source archive, so a resumed run
    # is checked against the original data, not against a partial copy.
    counts_before = table_counts(source_db)
    ids_before = max_ids(source_db)
    fingerprint_before = game_fingerprint(source_db)
    if resume:
        if not out_db.is_file():
            raise CatchupImportError(f"--resume requested but output does not exist: {out_db}")
        if out_db.resolve() == source_db.resolve():
            raise CatchupImportError("output must be a different file from the source archive")
        if quick_check(out_db) != "ok":
            raise CatchupImportError(f"partial output failed quick_check: {out_db}")
        if existing_game_fingerprint(out_db, ids_before) != fingerprint_before:
            raise CatchupImportError("partial output's pre-existing game rows differ from the source archive")
        report["resumed_from_counts"] = table_counts(out_db)
        report["half_written_matches_dropped"] = drop_half_written_matches(out_db, ids_before)
    else:
        copy_database(source_db, out_db)
    report["copy_quick_check"] = quick_check(out_db)

    engine = create_db_engine({"database": {"path": str(out_db)}})
    # A long offline run must survive another program (antivirus, backup,
    # indexer) briefly holding the file: wait up to 2 minutes for a lock
    # instead of SQLite's 5-second default. Dispose first so every pooled
    # connection is opened with the setting.
    engine.dispose()
    event.listen(engine, "connect", lambda conn, _record: conn.execute(f"pragma busy_timeout = {BUSY_TIMEOUT_MS}"))
    results = []
    try:
        with Session(engine) as db, offline_fetches(source):
            for n, did in enumerate(sorted(division_ids, key=int), 1):
                meta = divisions[did]
                counts = sync.sync_division_wide(
                    {}, db, did, meta["format"], meta["session_name"], resume=True,
                    roster_is_current=meta["is_current"], identity_current_only=meta["is_current"],
                )
                db.commit()
                results.append({**meta, **counts,
                                "coverage_observations": sync.reconcile_division_wide_coverage(counts)})
                logger.info("division %s (%d/%d) %s %s: %s h2h rows", did, n, len(division_ids),
                            meta["session_name"], meta["format"], counts["head_to_head_rows"])
            report["matchups_rebuilt"] = len(build_matchups(db)) if rebuild_matchups else None
            db.commit()
    finally:
        engine.dispose()

    remaining = find_pending(out_db, source, since, today)
    existing_after = existing_game_fingerprint(out_db, ids_before)
    counts_after = table_counts(out_db)
    report.update(
        division_results=results,
        captures_served=dict(source.served),
        capture_misses=[{"kind": k, "id": i} for k, i in source.misses],
        pending_after={"matches": len(remaining), "games": sum(p["games"] for p in remaining.values()),
                       "match_ids": sorted(remaining)[:50]},
        counts_before=counts_before, counts_after=counts_after,
        counts_delta={t: counts_after[t] - counts_before[t] for t in COUNT_TABLES},
        existing_games_before=fingerprint_before, existing_games_after=existing_after,
        existing_games_unchanged=existing_after == fingerprint_before,
        out_quick_check=quick_check(out_db),
        source_sha256_after=sha256_file(source_db),
        out_sha256=sha256_file(out_db),
        finished=datetime.now().isoformat(timespec="seconds"),
    )
    report["source_unchanged"] = report["source_sha256_after"] == source_sha_before
    problems = []
    if not report["source_unchanged"]:
        problems.append("source archive changed")
    if not report["existing_games_unchanged"]:
        problems.append("pre-existing game rows changed")
    if report["out_quick_check"] != "ok":
        problems.append(f"quick_check: {report['out_quick_check']}")
    if remaining:
        problems.append(f"{len(remaining)} pending matches still have no games")
    if source.misses:
        problems.append(f"{len(source.misses)} captures were missing")
    report["problems"] = problems
    report["status"] = "verified" if not problems else "needs_review"
    return report
