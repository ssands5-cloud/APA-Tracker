"""Build a verified, offline Ultimate Coach production candidate.

This is intentionally a READ-ONLY publication boundary. It never authenticates
to APA, never writes the source database, and never promotes/replaces
data/apa_tracker.db. A consistent SQLite backup is used as the immutable build
snapshot; the snapshot is deleted after the standalone HTML and verification
manifest are finalized.

Usage:
    python scripts/build_ultimate_coach_production.py
    python scripts/build_ultimate_coach_production.py --db data/ultimate_coach_staging.db
    python scripts/build_ultimate_coach_production.py --out ultimate-coach-runs/match-night
"""

from __future__ import annotations

import argparse
import sys
import hashlib
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from analytics.ultimate_coach_cockpit_identity_bridge import build_verified_cockpit_payload
from database.engine import create_db_engine
from ui.ultimate_coach import render

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_RUN_ROOT = PROJECT_ROOT / "ultimate-coach-runs"
HTML_NAME = "ultimate_coach.html"
MANIFEST_NAME = "manifest.json"
READY_NAME = "READY"
MANIFEST_SCHEMA = "ultimate-coach-production-candidate-v1"


class CandidateError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_uri(path: Path) -> str:
    # sqlite3 accepts a file: URI with forward slashes on Windows as well as
    # POSIX. Quote only the path component characters SQLite actually needs.
    return "file:" + path.resolve().as_posix() + "?mode=ro"


def _snapshot_sqlite(source: Path, destination: Path) -> tuple[str, str]:
    """Create a consistent read-only snapshot and prove the source stayed stable.

    The live Stage-3/Stage-4 crawler may have the source file open. SQLite's
    backup API is the safe way to take a coherent point-in-time copy without
    stopping that process. We additionally require the source file hash to be
    identical before/after the backup so a production candidate is never
    silently built across a changing source generation.
    """
    before = _sha256(source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(_sqlite_uri(source), uri=True)
    dst = sqlite3.connect(str(destination))
    try:
        src.backup(dst)
        row = dst.execute("PRAGMA integrity_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise CandidateError(f"snapshot integrity_check failed: {row!r}")
    finally:
        dst.close()
        src.close()

    after = _sha256(source)
    if before != after:
        destination.unlink(missing_ok=True)
        raise CandidateError(
            "source staging database changed during snapshot; no candidate published"
        )
    return before, _sha256(destination)


def _build_payload(snapshot: Path) -> dict:
    engine = create_db_engine(
        {"database": {"path": str(snapshot)}},
        create_tables=False,
    )
    try:
        with Session(engine) as db:
            return build_verified_cockpit_payload(db)
    finally:
        engine.dispose()


def _verify_payload(payload: dict) -> None:
    required = {
        "probability_publication": "FORBIDDEN",
        "matchup_probability": None,
        "predictive_confidence": None,
        "requires_live_apa_login": False,
        "database_mutated": False,
        "name_matching_used": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise CandidateError(
                f"payload safety invariant failed: {key}={payload.get(key)!r}, expected {expected!r}"
            )

    counts = payload.get("counts") or {}
    if int(counts.get("players") or 0) <= 0:
        raise CandidateError("verified cockpit contains no selectable players")
    if int(counts.get("head_to_head_rows") or 0) <= 0:
        raise CandidateError("verified cockpit contains no head-to-head evidence")


def _default_run_dir(run_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return run_root / f"candidate-{stamp}"


def build_candidate(source_db: Path, out_dir: Path) -> Path:
    source_db = source_db.resolve()
    out_dir = out_dir.resolve()

    if not source_db.is_file():
        raise CandidateError(f"Ultimate Coach source DB does not exist: {source_db}")
    if out_dir.exists():
        raise CandidateError(f"output directory already exists: {out_dir}")

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=".uc-candidate-", dir=out_dir.parent))
    snapshot = temp_dir / "build_snapshot.db"

    try:
        source_sha, snapshot_sha = _snapshot_sqlite(source_db, snapshot)
        payload = _build_payload(snapshot)
        _verify_payload(payload)

        built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        html_path = temp_dir / HTML_NAME
        html_path.write_text(
            render(payload, built_at=built_at, consume_evidence=True),
            encoding="utf-8",
        )

        html_sha = _sha256(html_path)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_database": source_db.name,
            "source_database_sha256": source_sha,
            "build_snapshot_sha256": snapshot_sha,
            "html": HTML_NAME,
            "html_sha256": html_sha,
            "counts": payload["counts"],
            "trust": payload.get("trust") or {},
            "safety": {
                "probability_publication": payload["probability_publication"],
                "matchup_probability": payload["matchup_probability"],
                "predictive_confidence": payload["predictive_confidence"],
                "requires_live_apa_login": payload["requires_live_apa_login"],
                "database_mutated": payload["database_mutated"],
                "name_matching_used": payload["name_matching_used"],
                "source_database_promoted": False,
            },
        }
        manifest_path = temp_dir / MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # Snapshot was a private build input, not an artifact. Remove it before
        # READY so the published candidate cannot be mistaken for a promoted DB.
        snapshot.unlink()

        ready = {
            "schema": MANIFEST_SCHEMA,
            "manifest_sha256": _sha256(manifest_path),
            "html_sha256": html_sha,
        }
        (temp_dir / READY_NAME).write_text(
            json.dumps(ready, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        temp_dir.replace(out_dir)
        return out_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    out_dir = args.out or _default_run_dir(args.run_root)
    try:
        completed = build_candidate(args.db, out_dir)
    except CandidateError as exc:
        print(f"ULTIMATE COACH CANDIDATE BLOCKED: {exc}")
        return 1

    print("ULTIMATE COACH PRODUCTION CANDIDATE READY")
    print(f"  open: {completed / HTML_NAME}")
    print(f"  manifest: {completed / MANIFEST_NAME}")
    print("  source database was not promoted or replaced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
