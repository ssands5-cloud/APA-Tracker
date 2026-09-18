"""One-time APA career-history backfill, then preserve it forever.

The normal game-night sync intentionally follows current viewer teams/divisions.
That is correct for a fast refresh but cannot discover every historical season
the viewer ever played. This command starts from the viewer's per-league APA
aliases, paginates TeamStat pastTeams, walks every distinct historical
division, and reuses the existing division-wide roster/schedule/scoresheet
pipeline to ingest real player-vs-player history.

Safety contract:
- never stores or prints APA_ACCESS_TOKEN;
- stages into a separate database by default;
- seeds that staging database from the current production database when one
  exists, so the backfill adds history rather than replacing known-good data;
- historical roster memberships are is_current=False;
- identity resolution is still exact team + session + display name;
- scored matches already present in the staged database are skipped;
- incomplete historical coverage is reported and blocks --promote;
- --promote is explicit and reuses the existing backup-and-promote contract.

After one complete backfill, ordinary game-night refreshes should be
incremental: they seed staging from the career-complete production database
and fetch only new/current records that are not already present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from analytics.matchup_builder import build_matchups
from database.engine import create_db_engine
from database.ingest import ingest_player_team_history
from database.models import Player
from scheduler.graphql_sync import (
    load_config,
    reconcile_division_wide_coverage,
    sync_division_wide,
)
from scraper.graphql_scraper import (
    AccessTokenExpired,
    AccessTokenMissing,
    fetch_dashboard_teams,
    fetch_formats_by_member_id,
    fetch_team_data,
    fetch_team_stat,
    member_aliases_rows,
    team_row,
    team_stat_rows,
)

logger = logging.getLogger("backfill_career_history")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_DB = PROJECT_ROOT / "data" / "apa_tracker.db"
DEFAULT_STAGING_DB = PROJECT_ROOT / "data" / "apa_tracker_career_staging.db"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "apa_tracker_career_backfill_report.json"
DEFAULT_PAGE_SIZE = 50
MAX_TEAM_STAT_PAGES = 200


class CareerBackfillError(RuntimeError):
    """Fail-closed career backfill error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_complete_team_history(
    config: dict,
    alias_id: int,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Paginate every TeamStat pastTeams row for one per-league alias.

    currentTeams is included from the first page only because APA returns it
    independently of pastTeams' limit/offset. Natural-key deduplication makes
    an interrupted/retried call harmless.
    """
    if page_size < 1:
        raise ValueError("page_size must be positive")

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, bool]] = set()
    offset = 0

    for page_number in range(MAX_TEAM_STAT_PAGES):
        alias = fetch_team_stat(config, alias_id, limit=page_size, offset=offset)
        past = list(alias.get("pastTeams") or [])
        current = list(alias.get("currentTeams") or []) if page_number == 0 else []
        page_payload = {"pastTeams": past, "currentTeams": current}

        for row in team_stat_rows(page_payload):
            key = (
                str(row.get("team_id") or ""),
                str(row.get("division_id") or ""),
                str(row.get("session_name") or ""),
                bool(row.get("is_current")),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

        if len(past) < page_size:
            return rows
        offset += page_size

    raise CareerBackfillError(
        f"TeamStat pagination exceeded {MAX_TEAM_STAT_PAGES} pages for alias {alias_id}; "
        "refusing to guess that history is complete."
    )


def collect_career_team_history(config: dict, member_id: int) -> tuple[list[dict], list[dict]]:
    """Return (alias_rows, deduplicated complete team-history rows)."""
    member = fetch_formats_by_member_id(config, member_id)
    aliases = member_aliases_rows(member)
    if not aliases:
        raise CareerBackfillError("APA returned no per-league aliases for the viewer")

    history: list[dict] = []
    seen: set[tuple[str, str, str, bool]] = set()
    for alias in aliases:
        alias_id = alias.get("alias_id")
        if not alias_id:
            continue
        for row in fetch_complete_team_history(config, int(alias_id)):
            key = (
                str(row.get("team_id") or ""),
                str(row.get("division_id") or ""),
                str(row.get("session_name") or ""),
                bool(row.get("is_current")),
            )
            if key in seen:
                continue
            seen.add(key)
            enriched = dict(row)
            enriched["league_id"] = alias.get("league_id") or ""
            enriched["league_slug"] = alias.get("league_slug") or ""
            enriched["alias_id"] = alias_id
            history.append(enriched)

    if not history:
        raise CareerBackfillError("APA aliases resolved but TeamStat returned no team history")
    return aliases, history


def prepare_staging(staging_db: Path, *, resume: bool, production_db: Path = PRODUCTION_DB) -> str:
    """Prepare staging without ever mutating production in place."""
    staging_db.parent.mkdir(parents=True, exist_ok=True)
    if resume:
        if not staging_db.is_file():
            raise CareerBackfillError(
                f"--resume requested but staging database does not exist: {staging_db}"
            )
        return "resumed existing career staging database"

    if staging_db.exists():
        staging_db.unlink()

    if production_db.is_file() and production_db.stat().st_size:
        shutil.copy2(production_db, staging_db)
        return "seeded career staging from current production database"
    return "started career staging from an empty database"


def _division_groups(history: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in history:
        division_id = str(row.get("division_id") or "").strip()
        team_id = str(row.get("team_id") or "").strip()
        if not division_id or not team_id:
            continue
        groups[division_id].append(row)
    return dict(groups)


def run_backfill(
    config_path: str,
    staging_db: Path,
    *,
    resume: bool = False,
    report_path: Path = DEFAULT_REPORT,
    promote: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    config.setdefault("database", {})["path"] = str(staging_db)

    preparation = prepare_staging(staging_db, resume=resume)

    viewer = fetch_dashboard_teams(config)
    member_id = viewer.get("id")
    if not member_id:
        raise CareerBackfillError("dashboardTeams returned no viewer member id")

    aliases, history = collect_career_team_history(config, int(member_id))
    divisions = _division_groups(history)
    if not divisions:
        raise CareerBackfillError("career history contains no usable historical division ids")

    engine = create_db_engine(config)
    totals = {
        "teams_discovered": 0,
        "teams_ingested": 0,
        "roster_players_discovered": 0,
        "roster_players_ingested": 0,
        "matches_discovered": 0,
        "matches_ingested": 0,
        "scored_matches_discovered": 0,
        "scored_matches_with_scoresheet": 0,
        "head_to_head_rows": 0,
        "identity_resolved": 0,
        "identity_unresolved": 0,
    }
    coverage_gaps: list[str] = []
    division_results: list[dict[str, Any]] = []

    try:
        with Session(engine) as db:
            for division_id in sorted(divisions):
                rows = divisions[division_id]
                representative = next(
                    (row for row in rows if row.get("team_id")),
                    None,
                )
                if representative is None:
                    coverage_gaps.append(f"division {division_id}: no representative team id")
                    continue

                # TEAM_PAGE_QUERY is the authoritative exact format/session
                # context. fetch_team_data also returns roster/schedule, but
                # sync_division_wide deliberately refetches division-wide
                # data because identity resolution needs every opponent.
                try:
                    team_data = fetch_team_data(config, team_id=representative["team_id"])
                except (AccessTokenMissing, AccessTokenExpired):
                    raise
                except Exception as exc:  # noqa: BLE001
                    coverage_gaps.append(
                        f"division {division_id}: team context fetch failed "
                        f"({type(exc).__name__})"
                    )
                    continue

                context = team_row(team_data)
                format_name = context.get("format") or ""
                session_name = context.get("session_name") or representative.get("session_name") or ""
                if not format_name or not session_name:
                    coverage_gaps.append(
                        f"division {division_id}: missing exact format/session context"
                    )
                    continue

                is_current_division = any(bool(row.get("is_current")) for row in rows)
                counts = sync_division_wide(
                    config,
                    db,
                    division_id,
                    format_name,
                    session_name,
                    resume=True,
                    roster_is_current=is_current_division,
                    identity_current_only=is_current_division,
                )
                local_gaps = reconcile_division_wide_coverage(counts)
                if counts["teams_discovered"] == 0:
                    local_gaps.append("historical division returned zero roster teams")
                coverage_gaps.extend(
                    f"division {division_id} ({session_name}, {format_name}): {gap}"
                    for gap in local_gaps
                )
                division_results.append(
                    {
                        "division_id": division_id,
                        "session_name": session_name,
                        "format": format_name,
                        "is_current": is_current_division,
                        **counts,
                    }
                )
                for key in totals:
                    totals[key] += counts[key]

            # Preserve the viewer's own authoritative TeamStat history across
            # every alias after roster ingestion has established their Player.
            viewer_player = (
                db.query(Player)
                .filter_by(external_id=str(member_id))
                .one_or_none()
            )
            viewer_history_rows = 0
            if viewer_player is not None:
                viewer_history_rows = ingest_player_team_history(db, viewer_player, history)
            else:
                coverage_gaps.append(
                    f"viewer Player row {member_id} was not resolved from historical rosters"
                )

            matchup_rows = build_matchups(db)
            db.commit()
    finally:
        engine.dispose()

    report = {
        "schema": "apa-career-backfill-v1",
        "status": "complete" if not coverage_gaps else "incomplete",
        "preparation": preparation,
        "viewer_member_id": str(member_id),
        "aliases_discovered": len(aliases),
        "team_history_rows_discovered": len(history),
        "divisions_discovered": len(divisions),
        "viewer_team_history_rows_written": viewer_history_rows,
        "matchups_rebuilt": len(matchup_rows),
        "totals": totals,
        "coverage_gaps": coverage_gaps,
        "divisions": division_results,
        "staging_db": str(staging_db),
        "staging_sha256": sha256_file(staging_db),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if coverage_gaps:
        raise CareerBackfillError(
            "career coverage is incomplete; promotion blocked. See "
            f"{report_path}: " + "; ".join(coverage_gaps[:5])
        )

    if promote:
        from scripts.build_full_production_demo import promote_live_database

        promote_live_database(staging_db)
        report["promoted"] = True
        report["production_sha256"] = sha256_file(PRODUCTION_DB)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "apa_config.yaml"))
    parser.add_argument("--staging-db", type=Path, default=DEFAULT_STAGING_DB)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue an interrupted career staging DB and skip captured scoresheets",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="After complete zero-gap coverage, backup and replace production DB",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        report = run_backfill(
            args.config,
            args.staging_db,
            resume=args.resume,
            report_path=args.report,
            promote=args.promote,
        )
    except (AccessTokenMissing, AccessTokenExpired, CareerBackfillError) as exc:
        logger.error("%s", exc)
        return 1

    logger.info(
        "Career backfill complete: %d historical team row(s), %d division(s), "
        "%d scored match(es) with scoresheets; staging SHA-256 %s",
        report["team_history_rows_discovered"],
        report["divisions_discovered"],
        report["totals"]["scored_matches_with_scoresheet"],
        report["staging_sha256"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
