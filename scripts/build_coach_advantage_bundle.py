"""Coach Advantage Bundle Builder.

Turns one real database snapshot into one verified bundle of the Coach
Advantage Tools: Player Matchup Engine, Team Matchup Engine, and the
static Coach Dashboard. A COORDINATION boundary, like
``scripts/build_full_production_demo.py``: it calls existing acquisition
and analytics entry points and copies none of their logic.

Real scope discovery and per-scope evidence classification are NOT
reimplemented here -- ``scripts.build_captain_first_edge.build_match_scopes``
already does exactly this (every real scheduled match for the configured
team, classified via ``analytics.pairing_evidence``, with
``analytics.lineup_lab``'s approved lineup attached or its real failure
reason). This builder is a thin layer on top: for each real scope it
already resolved, it builds a ``PlayerMatchupReport`` per pairing and one
``TeamMatchupReport``, then renders HTML/Excel/JSON and the combined
dashboard.

Phases, in order, each stopping the build on failure:

    1. preflight   canonical repository root/boundary id, contained and
                   new output directory
    2. acquire     open the database read-only and lock its SHA-256; never
                   scrapes, never requires a token (see --source-db in
                   scripts/build_full_production_demo.py for the same
                   already-established convention)
    3. compute     real scope discovery, per-scope pairing/team reports,
                   whole-division Opponent Risk Profile
    4. render      HTML/Excel/JSON per engine, plus the combined dashboard
    5. verify      reconcile evidence counts against each scope's own
                   already-reconciled matrix
    6. finalize    write manifest and checksums, re-read and verify them
                   from disk, then write READY last

A failed phase leaves no READY marker, so no partial bundle is ever
promotable or presentable.

Usage:
    python scripts/build_coach_advantage_bundle.py
    python scripts/build_coach_advantage_bundle.py --db data/apa_tracker.db
    python scripts/build_coach_advantage_bundle.py --our-team-id 13082948
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from analytics.opponent_risk_profile import build_profile as build_opponent_risk_profile
from analytics.pairing_evidence import PairingEvidenceMatrix
from analytics.player_matchup_engine import (
    PlayerMatchupReport,
    build_player_matchup_report,
    skill_trend_for,
)
from analytics.team_matchup_engine import TeamMatchupReport, build_team_matchup_report
from database.queries import skill_level_history
from scripts.build_captain_first_edge import (
    _configured_our_team_id,
    _team_name,
    build_match_scopes,
    real_matches_for_scope,
)
from scripts.build_captains_edge import NoDatabaseError, connect_read_only, resolve_db_path
from scripts.build_full_production_demo import (
    BOUNDARY_FILE,
    BOUNDARY_ID,
    BuildError,
    resolve_contained,
    sha256_file,
)
from ui import dashboard as dashboard_module
from ui.export_excel_player_matchup_engine import write_workbook as write_player_workbook
from ui.export_excel_team_matchup_engine import write_workbook as write_team_workbook
from ui.export_html_player_matchup_engine import render as render_player_html
from ui.export_html_team_matchup_engine import render as render_team_html
from ui.export_json_coach_advantage import (
    player_matchup_report_to_dict,
    team_matchup_report_to_dict,
)

logger = logging.getLogger("build_coach_advantage_bundle")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUN_ROOT = PROJECT_ROOT / "coach-advantage-runs"

MANIFEST_SCHEMA_VERSION = "coach-advantage-manifest-v1"
EVENT_SCHEMA_VERSION = "coach-advantage-event-v1"
MANIFEST_NAME = "manifest.json"
CHECKSUMS_NAME = "checksums.sha256"
READY_NAME = "READY"

EXIT_OK = 0
EXIT_PREFLIGHT = 2
EXIT_ACQUIRE = 4
EXIT_COMPUTE = 10
EXIT_RENDER = 11
EXIT_FINALIZE = 12
EXIT_INTERRUPT = 130


@dataclass
class PhaseResult:
    name: str
    status: str
    detail: str = ""


class EventSink:
    """Versioned, redacted JSONL events for automation -- this bundle's own
    schema (``coach-advantage-event-v1``), NOT
    scripts.build_full_production_demo's ``demo-event-v1``: reusing that
    module's EventSink verbatim would tag every event from this different
    bundle type as if it came from the Full Production Demo Builder."""

    def __init__(self, path: Optional[Path]):
        self.path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def emit(self, phase: str, status: str, **fields) -> None:
        if self.path is None:
            return
        event = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "status": status,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


@dataclass
class ComputedScope:
    opponent_team_external_id: str
    opponent_team_name: str
    format: str
    session_name: str
    matrix: Optional[PairingEvidenceMatrix]
    unavailable_reason: Optional[str]
    player_reports: tuple[PlayerMatchupReport, ...]
    team_report: Optional[TeamMatchupReport]


def preflight(run_dir: Path, run_root: Path) -> PhaseResult:
    if not BOUNDARY_FILE.is_file() or BOUNDARY_FILE.read_text(encoding="utf-8").strip() != BOUNDARY_ID:
        raise BuildError(
            f"not the canonical APA-Tracker repository: {BOUNDARY_FILE} must contain {BOUNDARY_ID!r}",
            EXIT_PREFLIGHT,
        )
    resolve_contained(run_root, PROJECT_ROOT)
    resolved_run = resolve_contained(run_dir, run_root)
    if resolved_run.exists() and any(resolved_run.iterdir()):
        raise BuildError(f"run directory is not empty: {resolved_run}", EXIT_PREFLIGHT)
    return PhaseResult("preflight", "ok", f"run directory {resolved_run.name}")


def acquire(db_path: Path) -> tuple[Path, PhaseResult]:
    """Open the database read-only and lock its hash. Never scrapes, never
    requires a token -- the same already-acquired-database convention
    scripts/build_full_production_demo.py's --source-db established."""
    if not db_path.is_file() or db_path.stat().st_size == 0:
        raise BuildError(f"no database at {db_path}", EXIT_ACQUIRE)
    return db_path, PhaseResult("acquire", "ok", f"using {db_path.name} (read-only, no rescrape)")


def _skill_trends(db: Session) -> dict[int, "object"]:
    """Every player's real skill-level trend, grouped by player_id -- one
    query, reused for every report this build produces. Mirrors
    ui/export_json.py's own ``_skill_level_summary`` grouping."""
    by_player: dict[int, list] = {}
    for row in skill_level_history(db):
        by_player.setdefault(row.player_id, []).append(row)
    return {player_id: skill_trend_for(matches) for player_id, matches in by_player.items()}


def compute(
    db: Session, our_team_external_id: str, our_team_name: str,
) -> tuple[list[ComputedScope], list, PhaseResult]:
    """Real scope discovery (scripts.build_captain_first_edge) plus this
    builder's own Coach Mode aggregation on top -- no scope discovery or
    evidence classification is reimplemented here."""
    trends = _skill_trends(db)
    match_scopes = build_match_scopes(db, our_team_external_id)

    computed: list[ComputedScope] = []
    risk_inputs = []
    for scope in match_scopes:
        if scope.matrix is None:
            computed.append(ComputedScope(
                opponent_team_external_id=scope.opponent_team_external_id,
                opponent_team_name=scope.opponent_team_name,
                format=scope.format, session_name=scope.session_name,
                matrix=None, unavailable_reason=scope.unavailable_reason,
                player_reports=(), team_report=None,
            ))
            continue

        player_reports = tuple(
            build_player_matchup_report(
                pairing,
                our_team_external_id,
                scope.opponent_team_external_id,
                player_trend=trends.get(pairing.player_id),
                opponent_trend=trends.get(pairing.opponent_id),
                opponent_team_name=scope.opponent_team_name,
            )
            for pairing in scope.matrix.pairings
        )
        our_trends = {p.player_id: p.player_trend for p in player_reports}
        opponent_trends = {p.opponent_id: p.opponent_trend for p in player_reports}
        real_matches = real_matches_for_scope(
            db, our_team_external_id, scope.opponent_team_external_id,
            scope.format, scope.session_name,
        )
        team_report = build_team_matchup_report(
            scope.matrix, our_team_name, scope.opponent_team_name,
            lineup_result=scope.lineup_result, lineup_error=scope.lineup_error,
            our_trends=our_trends, opponent_trends=opponent_trends,
            real_matches=real_matches,
        )
        computed.append(ComputedScope(
            opponent_team_external_id=scope.opponent_team_external_id,
            opponent_team_name=scope.opponent_team_name,
            format=scope.format, session_name=scope.session_name,
            matrix=scope.matrix, unavailable_reason=None,
            player_reports=player_reports, team_report=team_report,
        ))
        risk_inputs.append((scope.opponent_team_external_id, scope.opponent_team_name, scope.matrix))

    if not computed:
        raise BuildError(
            f"no real scheduled match found for team {our_team_external_id}", EXIT_COMPUTE,
        )

    risk_profile = build_opponent_risk_profile(risk_inputs)
    usable = sum(1 for c in computed if c.matrix is not None)
    return computed, list(risk_profile), PhaseResult(
        "compute", "ok", f"{usable}/{len(computed)} real scope(s) usable"
    )


def render(
    run_dir: Path, computed: list[ComputedScope], risk_profile: list, our_team_name: str,
    built_at: str,
) -> PhaseResult:
    all_player_reports = [r for c in computed for r in c.player_reports]
    all_team_reports = [c.team_report for c in computed if c.team_report is not None]

    html_dir = run_dir / "html"
    excel_dir = run_dir / "excel"
    json_dir = run_dir / "json"
    for directory in (html_dir, excel_dir, json_dir):
        directory.mkdir(parents=True, exist_ok=True)

    (html_dir / "player_matchup_engine.html").write_text(
        render_player_html(all_player_reports), encoding="utf-8"
    )
    (html_dir / "team_matchup_engine.html").write_text(
        render_team_html(all_team_reports), encoding="utf-8"
    )
    (html_dir / "dashboard.html").write_text(
        dashboard_module.render(
            all_player_reports, all_team_reports, risk_profile, our_team_name, built_at=built_at,
        ),
        encoding="utf-8",
    )

    write_player_workbook(all_player_reports, excel_dir / "player_matchup_engine.xlsx")
    write_team_workbook(all_team_reports, excel_dir / "team_matchup_engine.xlsx")

    (json_dir / "player_matchup_engine.json").write_text(
        json.dumps([player_matchup_report_to_dict(r) for r in all_player_reports], indent=2),
        encoding="utf-8",
    )
    (json_dir / "team_matchup_engine.json").write_text(
        json.dumps([team_matchup_report_to_dict(r) for r in all_team_reports], indent=2),
        encoding="utf-8",
    )

    artifacts = [
        "html/player_matchup_engine.html", "html/team_matchup_engine.html", "html/dashboard.html",
        "excel/player_matchup_engine.xlsx", "excel/team_matchup_engine.xlsx",
        "json/player_matchup_engine.json", "json/team_matchup_engine.json",
    ]
    return PhaseResult("render", "ok", f"{len(artifacts)} artifact(s)"), artifacts


def verify(computed: list[ComputedScope]) -> PhaseResult:
    """Reconcile every usable scope's own evidence counts -- each matrix
    was already reconciled against its own feasible-pair set at build time
    (analytics.pairing_evidence.build_pairing_matrix raises on mismatch),
    so this is a defensive re-check, not the only gate."""
    problems: list[str] = []
    for scope in computed:
        if scope.matrix is None:
            continue
        counts = scope.matrix.counts
        total = counts.get("DIRECT", 0) + counts.get("INDIRECT", 0) + counts.get("UNKNOWN", 0)
        if total != counts.get("total_feasible_pairings", 0):
            problems.append(
                f"{scope.opponent_team_name}: evidence counts {total} do not sum to "
                f"{counts.get('total_feasible_pairings', 0)} feasible pairings"
            )
        if len(scope.player_reports) != counts.get("total_feasible_pairings", 0):
            problems.append(
                f"{scope.opponent_team_name}: {len(scope.player_reports)} player report(s) "
                f"but {counts.get('total_feasible_pairings', 0)} feasible pairings"
            )
    if problems:
        raise BuildError("; ".join(problems), EXIT_RENDER)
    return PhaseResult("verify", "ok", f"{len(computed)} scope(s) reconciled")


def finalize(run_dir: Path, manifest: dict) -> PhaseResult:
    manifest_path = run_dir / MANIFEST_NAME
    checksums_path = run_dir / CHECKSUMS_NAME

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    lines = []
    for relative in sorted(manifest["artifacts"]):
        target = run_dir / relative
        lines.append(f"{sha256_file(target)}  {relative}")
    lines.append(f"{sha256_file(manifest_path)}  {MANIFEST_NAME}")
    checksums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if reloaded != manifest:
        raise BuildError("manifest did not survive the round trip to disk", EXIT_FINALIZE)
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        if sha256_file(run_dir / relative) != digest:
            raise BuildError(f"checksum mismatch for {relative}", EXIT_FINALIZE)

    (run_dir / READY_NAME).write_text(
        json.dumps(
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "run_id": manifest["run_id"],
                "manifest_sha256": sha256_file(manifest_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return PhaseResult("finalize", "ok", "manifest, checksums, READY")


def run_build(
    db_path: Path, our_team_external_id: str, run_dir: Path, run_root: Path,
    events: Optional[EventSink] = None,
) -> Path:
    events = events or EventSink(None)
    phases: list[PhaseResult] = [preflight(run_dir, run_root)]
    events.emit("preflight", "ok")

    db_path, acquire_result = acquire(db_path)
    phases.append(acquire_result)
    locked_hash = sha256_file(db_path)

    run_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine("sqlite://", creator=lambda: connect_read_only(db_path))
    db = Session(bind=engine)
    # Computed once and reused for both the dashboard's own "data as of"
    # display and the manifest below, rather than two independently-taken
    # timestamps for what should be the same real build moment.
    built_at = datetime.now(timezone.utc).isoformat()
    try:
        our_team_name = _team_name(db, our_team_external_id)
        computed, risk_profile, compute_result = compute(db, our_team_external_id, our_team_name)
        phases.append(compute_result)
        render_result, artifacts = render(run_dir, computed, risk_profile, our_team_name, built_at)
        phases.append(render_result)
        phases.append(verify(computed))
    finally:
        db.close()
        engine.dispose()

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "built_at": built_at,
        "database_sha256": locked_hash,
        "database_file": db_path.name,
        "our_team_id": our_team_external_id,
        "our_team_name": our_team_name,
        "scope_count": len(computed),
        "usable_scope_count": sum(1 for c in computed if c.matrix is not None),
        "artifacts": sorted(artifacts),
        "artifact_hashes": {
            relative: sha256_file(run_dir / relative) for relative in sorted(artifacts)
        },
        "phases": [{"name": p.name, "status": p.status, "detail": p.detail} for p in phases],
        "promotable": True,
    }
    phases.append(finalize(run_dir, manifest))

    events.emit(
        "complete", "ok",
        run_dir=str(run_dir.resolve().relative_to(PROJECT_ROOT).as_posix()),
        run_id=manifest["run_id"], artifact_count=len(manifest["artifacts"]),
    )
    return run_dir


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Build one verified Coach Advantage bundle.")
    parser.add_argument("--db", help="Path to the SQLite database (default: configured/fallback path)")
    parser.add_argument("--our-team-id", help="Override apa_config.yaml's team.team_id")
    parser.add_argument("--out", help="run directory (default: coach-advantage-runs/<utc timestamp>)")
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--events", help="write versioned JSONL events here")
    args = parser.parse_args(argv)

    try:
        db_path = resolve_db_path(args.db)
    except NoDatabaseError as exc:
        logger.error(str(exc))
        return 1

    our_team_external_id = args.our_team_id or _configured_our_team_id()
    if not our_team_external_id:
        logger.error("No team id given. Set apa_config.yaml's team.team_id, or pass --our-team-id.")
        return 1

    run_root = Path(args.run_root)
    if args.out:
        run_dir = Path(args.out)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = run_root / stamp

    events = EventSink(Path(args.events) if args.events else None)
    try:
        completed = run_build(db_path, our_team_external_id, run_dir, run_root, events=events)
    except BuildError as exc:
        logger.error("BUILD FAILED: %s", exc)
        events.emit("failed", "error", code=exc.code)
        return exc.code
    except KeyboardInterrupt:
        logger.error("interrupted")
        return EXIT_INTERRUPT

    logger.info("Run ready: %s", completed)
    logger.info("Open: %s", completed / "html" / "dashboard.html")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
