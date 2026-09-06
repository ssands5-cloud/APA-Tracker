"""Shared post-ingest reconciliation and production delivery.

Every ingest entry point leaves the same derived tables stale.  This module
is the single boundary that rebuilds them in dependency order, commits those
rows, and only then publishes the captain-facing artifact set.  Fixture,
live GraphQL, and scheduled HTML runs all call the same functions so a new
analytics module cannot accidentally ship in only one path.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from analytics.matchup_builder import build_matchups

logger = logging.getLogger(__name__)

MANIFEST_NAME = "refresh_manifest.json"


def rebuild_matchups(db: Session) -> int:
    """Recompute and reconcile Matchup Advantage rows."""
    return len(build_matchups(db))


def rebuild_analytics(db: Session) -> dict[str, int]:
    """Recompute and reconcile Head-to-Head Advantage and Player Trends.

    Imports stay local because both command-line builders import the live
    scheduler for configuration.  Keeping them out of module import time
    prevents a scheduler -> refresh -> builder -> scheduler cycle.
    """
    from database.ingest import (
        ingest_h2h_advantage,
        ingest_player_trends,
        prune_h2h_advantage_not_in,
        prune_player_trends_not_in,
    )
    from scripts.build_head_to_head import (
        build_rows as build_h2h_rows,
        group_by_pairing,
        ordered_rows,
    )
    from scripts.build_player_trends import build_rows as build_trend_rows
    from scripts.build_player_trends import grouped_history

    h2h_groups = group_by_pairing(ordered_rows(db))
    h2h_rows = build_h2h_rows(db)
    trend_rows = build_trend_rows(db)

    counts = {
        "h2h_advantage": ingest_h2h_advantage(db, h2h_rows) if h2h_rows else 0,
        "h2h_pruned": prune_h2h_advantage_not_in(db, set(h2h_groups)),
        "player_trends": ingest_player_trends(db, trend_rows) if trend_rows else 0,
        "trends_pruned": prune_player_trends_not_in(db, set(grouped_history(db))),
    }
    return counts


def rebuild_derived(db: Session) -> dict[str, int]:
    """Rebuild every derived table, in dependency order."""
    counts = {"matchups": rebuild_matchups(db)}
    counts.update(rebuild_analytics(db))
    db.commit()
    return counts


def publish(config: dict[str, Any], engine: Engine, *, captains: bool = True) -> list[tuple[str, str]]:
    """Publish every configured artifact from the committed database."""
    from pipeline.exports import run as export_run

    return export_run(config, engine, captains=captains)


def finalize(
    config: dict[str, Any],
    engine: Engine,
    *,
    export: bool = True,
    captains: bool = True,
) -> tuple[dict[str, int], list[tuple[str, str]]]:
    """Reconcile derived state and optionally publish one complete run.

    The ingest caller's session is intentionally not reused.  Entering here
    after that session closes guarantees every read-only builder sees the
    committed raw rows.  The manifest is written last; if any exporter fails,
    the previous manifest remains the last known complete run and the error
    still propagates to the scheduler.
    """
    started_at = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())

    with Session(engine) as db:
        counts = rebuild_derived(db)

    if not export:
        return counts, []

    artifacts = publish(config, engine, captains=captains)
    manifest_path = write_manifest(
        run_id=run_id,
        started_at=started_at,
        counts=counts,
        artifacts=artifacts,
    )
    artifacts.append(("refresh manifest", str(manifest_path)))
    return counts, artifacts


def _artifact_record(label: str, path: str) -> dict[str, Any]:
    artifact = Path(path).resolve()
    record: dict[str, Any] = {
        "label": label,
        "path": str(artifact),
        "exists": artifact.is_file(),
        "size_bytes": None,
        "sha256": None,
    }
    if artifact.is_file():
        digest = hashlib.sha256()
        with artifact.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        record["size_bytes"] = artifact.stat().st_size
        record["sha256"] = digest.hexdigest()
    return record


def write_manifest(
    *,
    run_id: str,
    started_at: datetime,
    counts: dict[str, int],
    artifacts: list[tuple[str, str]],
    output_dir: Path | None = None,
) -> Path:
    """Atomically mark the last fully completed production refresh."""
    from pipeline.exports import EXPORTS_DIR

    directory = (output_dir or EXPORTS_DIR).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / MANIFEST_NAME
    artifact_records = [_artifact_record(label, path) for label, path in artifacts]
    missing = [record["label"] for record in artifact_records if not record["exists"]]
    if missing:
        raise FileNotFoundError(
            "Production refresh did not create every reported artifact: "
            + ", ".join(missing)
        )
    document = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at.astimezone(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "derived_counts": dict(sorted(counts.items())),
        "artifacts": artifact_records,
    }

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{MANIFEST_NAME}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    logger.info("Production refresh manifest written to %s", destination)
    return destination
