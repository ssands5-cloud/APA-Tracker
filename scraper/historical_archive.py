"""Resumable league-wide historical archive builder for Ultimate Coach.

Consumes a previously verified historical catalog and walks every exposed
division through the existing division-wide ingestion pipeline. The archive is
real-source-only: source limitations are recorded, never reconstructed.

There is intentionally NO production promotion path in this module.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from analytics.matchup_builder import build_matchups
from database.engine import create_db_engine
from scheduler.graphql_sync import reconcile_division_wide_coverage, sync_division_wide

CATALOG_SCHEMA = "ultimate-coach-historical-catalog-v1"
CATALOG_SCHEMAS = {CATALOG_SCHEMA, "ultimate-coach-historical-catalog-v2"}
REPORT_SCHEMA = "ultimate-coach-archive-v1"


class ArchiveError(RuntimeError):
    """A structural/safety error that must stop the archive crawl."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_catalog(path: Path) -> dict[str, Any]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema") not in CATALOG_SCHEMAS:
        raise ArchiveError(
            f"unsupported catalog schema {catalog.get('schema')!r}; "
            f"expected one of {sorted(CATALOG_SCHEMAS)!r}"
        )
    if not isinstance(catalog.get("divisions"), list):
        raise ArchiveError("catalog divisions must be a list")
    return catalog


def prepare_staging(staging_db: Path, *, resume: bool, seed_db: Path | None) -> str:
    """Prepare a separate Ultimate Coach DB without ever mutating the seed."""
    staging_db.parent.mkdir(parents=True, exist_ok=True)
    if resume:
        if not staging_db.is_file():
            raise ArchiveError(f"--resume requested but staging DB does not exist: {staging_db}")
        return "resumed existing Ultimate Coach staging database"

    if staging_db.exists():
        staging_db.unlink()

    if seed_db is not None and seed_db.is_file() and seed_db.stat().st_size:
        shutil.copy2(seed_db, staging_db)
        return f"seeded from {seed_db}"

    return "started from an empty Ultimate Coach staging database"


def _division_key(row: dict[str, Any]) -> str:
    """League-aware checkpoint key.

    APA ids are treated as source identifiers, not assumed globally unique
    across leagues. Including league context prevents an unrelated league from
    being skipped on resume if it happens to reuse a session/division number.
    """
    league = row.get("league_slug") or row.get("league_id") or ""
    session = row.get("catalog_session_id") or row.get("session_id") or ""
    division = row.get("division_id") or ""
    return f"{league}:{session}:{division}"


def division_plan(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a deterministic, duplicate-free division crawl plan."""
    planned: dict[str, dict[str, Any]] = {}
    for row in catalog.get("divisions") or []:
        row = dict(row or {})
        division_id = str(row.get("division_id") or "").strip()
        session_id = str(row.get("catalog_session_id") or row.get("session_id") or "").strip()
        session_name = str(row.get("catalog_session_name") or row.get("session_name") or "").strip()
        format_name = str(row.get("format") or row.get("type") or "").strip()
        if not division_id or not session_id or not session_name or not format_name:
            continue
        row["division_id"] = division_id
        row["catalog_session_id"] = session_id
        row["catalog_session_name"] = session_name
        row["format"] = format_name
        planned[_division_key(row)] = row

    def sort_key(item: dict[str, Any]) -> tuple[int, int]:
        try:
            session_n = int(item["catalog_session_id"])
        except (TypeError, ValueError):
            session_n = 10**12
        try:
            division_n = int(item["division_id"])
        except (TypeError, ValueError):
            division_n = 10**12
        return (session_n, division_n)

    return sorted(planned.values(), key=sort_key)


def _checkpoint(
    report_path: Path,
    *,
    status: str,
    staging_db: Path,
    catalog_path: Path,
    catalog_sha256: str,
    preparation: str,
    completed_keys: set[str],
    division_results: list[dict[str, Any]],
    catalog_source_limitations: list[str],
    matchups_rebuilt: int | None = None,
) -> dict[str, Any]:
    coverage_observations = [
        {
            "division_id": row["division_id"],
            "session_name": row["session_name"],
            "observations": row["coverage_observations"],
        }
        for row in division_results
        if row.get("coverage_observations")
    ]
    report = {
        "schema": REPORT_SCHEMA,
        "status": status,
        "preparation": preparation,
        "catalog_path": str(catalog_path),
        "catalog_sha256": catalog_sha256,
        "staging_db": str(staging_db),
        "completed_division_keys": sorted(completed_keys),
        "divisions_crawled": len(completed_keys),
        "division_results": division_results,
        "catalog_source_limitations": catalog_source_limitations,
        "coverage_observations": coverage_observations,
        "matchups_rebuilt": matchups_rebuilt,
    }
    if staging_db.is_file():
        report["staging_sha256"] = sha256_file(staging_db)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def run_archive(
    config: dict,
    *,
    catalog_path: Path,
    staging_db: Path,
    report_path: Path,
    seed_db: Path | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Crawl every valid catalog division into the separate staging DB.

    A division is marked completed after its full sync call returns, even if APA
    reports irreducible missing historical rows. Those observations remain in
    the report but are not fabricated or retried forever. If auth expires
    during a division, that division is not checkpointed and a resume safely
    revisits it with sync_division_wide(resume=True).
    """
    catalog = load_catalog(catalog_path)
    catalog_sha = sha256_file(catalog_path)
    preparation = prepare_staging(staging_db, resume=resume, seed_db=seed_db)

    completed_keys: set[str] = set()
    division_results: list[dict[str, Any]] = []

    if resume and report_path.is_file():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        previous_sha = previous.get("catalog_sha256")
        if previous_sha and previous_sha != catalog_sha:
            raise ArchiveError(
                "catalog changed since the prior archive run; refusing to reuse completed checkpoints"
            )
        completed_keys = set(previous.get("completed_division_keys") or [])
        division_results = list(previous.get("division_results") or [])

    run_config = dict(config)
    run_config["database"] = dict(config.get("database") or {})
    run_config["database"]["path"] = str(staging_db)

    engine = create_db_engine(run_config)
    try:
        with Session(engine) as db:
            for division in division_plan(catalog):
                key = _division_key(division)
                if key in completed_keys:
                    continue

                division_id = division["division_id"]
                session_id = division["catalog_session_id"]
                session_name = division["catalog_session_name"]
                format_name = division["format"]
                current_session_id = str(division.get("current_session_id") or "")
                is_current = bool(current_session_id and current_session_id == session_id)

                counts = sync_division_wide(
                    run_config,
                    db,
                    division_id,
                    format_name,
                    session_name,
                    resume=True,
                    roster_is_current=is_current,
                    identity_current_only=is_current,
                )
                db.commit()
                observations = reconcile_division_wide_coverage(counts)
                result = {
                    "division_id": division_id,
                    "session_id": session_id,
                    "session_name": session_name,
                    "format": format_name,
                    "is_current_session": is_current,
                    "coverage_observations": observations,
                    **counts,
                }
                division_results.append(result)
                completed_keys.add(key)
                _checkpoint(
                    report_path,
                    status="crawl_in_progress",
                    staging_db=staging_db,
                    catalog_path=catalog_path,
                    catalog_sha256=catalog_sha,
                    preparation=preparation,
                    completed_keys=completed_keys,
                    division_results=division_results,
                    catalog_source_limitations=list(catalog.get("source_limitations") or []),
                )

            matchup_rows = build_matchups(db)
            db.commit()

        return _checkpoint(
            report_path,
            status="crawl_complete",
            staging_db=staging_db,
            catalog_path=catalog_path,
            catalog_sha256=catalog_sha,
            preparation=preparation,
            completed_keys=completed_keys,
            division_results=division_results,
            catalog_source_limitations=list(catalog.get("source_limitations") or []),
            matchups_rebuilt=len(matchup_rows),
        )
    finally:
        engine.dispose()
