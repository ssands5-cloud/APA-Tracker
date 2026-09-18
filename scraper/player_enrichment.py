"""Resumable all-player APA career-stat enrichment for Ultimate Coach."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from database.ingest import ingest_player_league_career_stats
from database.models import Player, PlayerTeamHistory
from scraper.graphql_scraper import (
    eight_ball_stats_row,
    fetch_eight_ball_stats,
    fetch_formats_by_member_id,
    member_aliases_rows,
)

REPORT_SCHEMA = "ultimate-coach-player-enrichment-v1"


class EnrichmentError(RuntimeError):
    """Safety/structure error that must stop enrichment."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def catalog_context_index(catalog: dict[str, Any]) -> dict[tuple[str, str], dict[str, str]]:
    """Map exact (division id, session name) to its real league context."""
    index: dict[tuple[str, str], dict[str, str]] = {}
    for division in catalog.get("divisions") or []:
        division = division or {}
        division_id = str(division.get("division_id") or "")
        session_name = str(
            division.get("catalog_session_name") or division.get("session_name") or ""
        )
        league_id = str(division.get("league_id") or "")
        league_slug = str(division.get("league_slug") or "")
        if not division_id or not session_name or not league_id:
            continue
        key = (division_id, session_name)
        context = {"league_id": league_id, "league_slug": league_slug}
        existing = index.get(key)
        if existing is not None and existing != context:
            raise EnrichmentError(
                f"catalog maps division/session {key!r} to more than one league"
            )
        index[key] = context
    return index


def player_league_contexts(
    db: Session, catalog: dict[str, Any]
) -> dict[int, set[tuple[str, str]]]:
    """Resolve each canonical Player to leagues proven by team-history rows."""
    index = catalog_context_index(catalog)
    contexts: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for row in db.query(PlayerTeamHistory).all():
        context = index.get((str(row.division_id or ""), str(row.session_name or "")))
        if context:
            contexts[row.player_id].add((context["league_id"], context["league_slug"]))
    return dict(contexts)


def _write_report(
    report_path: Path,
    *,
    status: str,
    catalog_path: Path,
    catalog_sha256: str,
    staging_db: Path,
    completed_keys: set[str],
    rows: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    players_without_catalog_context: int,
) -> dict[str, Any]:
    report = {
        "schema": REPORT_SCHEMA,
        "status": status,
        "catalog_path": str(catalog_path),
        "catalog_sha256": catalog_sha256,
        "staging_db": str(staging_db),
        "completed_player_league_keys": sorted(completed_keys),
        "enrichment_rows": rows,
        "unresolved": unresolved,
        "counts": {
            "player_league_scopes_completed": len(completed_keys),
            "league_stat_format_rows_written": sum(
                int(row.get("formats_written") or 0) for row in rows
            ),
            "unresolved_scopes": len(unresolved),
            "players_without_catalog_context": players_without_catalog_context,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def enrich_all_players(
    config: dict,
    db: Session,
    *,
    catalog: dict[str, Any],
    catalog_path: Path,
    staging_db: Path,
    report_path: Path,
    resume: bool = False,
) -> dict[str, Any]:
    """Fetch league-scoped lifetime stats for every safely resolvable player."""
    catalog_sha = _sha256(catalog_path)
    contexts = player_league_contexts(db, catalog)

    completed: set[str] = set()
    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    if resume and report_path.is_file():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        previous_sha = previous.get("catalog_sha256")
        if previous_sha and previous_sha != catalog_sha:
            raise EnrichmentError(
                "catalog changed since the prior enrichment run; refusing to reuse checkpoints"
            )
        completed = set(previous.get("completed_player_league_keys") or [])
        rows = list(previous.get("enrichment_rows") or [])
        unresolved = list(previous.get("unresolved") or [])

    players = db.query(Player).order_by(Player.id).all()
    players_without_context = sum(1 for player in players if player.id not in contexts)

    for player in players:
        league_contexts = sorted(contexts.get(player.id) or [])
        if not league_contexts:
            continue

        external_id = str(player.external_id or "").strip()
        if not external_id.isdigit():
            for league_id, league_slug in league_contexts:
                key = f"{external_id}:{league_id}"
                if key in completed:
                    continue
                unresolved.append(
                    {
                        "player_external_id": external_id,
                        "player_name": player.name,
                        "league_id": league_id,
                        "league_slug": league_slug,
                        "reason": "canonical player id is not a numeric APA member id",
                    }
                )
                completed.add(key)
            continue

        member = fetch_formats_by_member_id(config, int(external_id))
        aliases = member_aliases_rows(member)

        for league_id, league_slug in league_contexts:
            key = f"{external_id}:{league_id}"
            if key in completed:
                continue

            candidates = [
                alias for alias in aliases
                if str(alias.get("league_id") or "") == str(league_id)
            ]
            if len(candidates) != 1:
                unresolved.append(
                    {
                        "player_external_id": external_id,
                        "player_name": player.name,
                        "league_id": league_id,
                        "league_slug": league_slug,
                        "candidate_alias_count": len(candidates),
                        "reason": "league alias did not resolve uniquely",
                    }
                )
                completed.add(key)
                _write_report(
                    report_path,
                    status="enrichment_in_progress",
                    catalog_path=catalog_path,
                    catalog_sha256=catalog_sha,
                    staging_db=staging_db,
                    completed_keys=completed,
                    rows=rows,
                    unresolved=unresolved,
                    players_without_catalog_context=players_without_context,
                )
                continue

            alias_id = candidates[0].get("alias_id")
            if not alias_id:
                unresolved.append(
                    {
                        "player_external_id": external_id,
                        "player_name": player.name,
                        "league_id": league_id,
                        "league_slug": league_slug,
                        "reason": "resolved league alias has no alias id",
                    }
                )
                completed.add(key)
                continue

            stats = fetch_eight_ball_stats(config, int(alias_id))
            stat_row = eight_ball_stats_row(stats)
            written = ingest_player_league_career_stats(
                db,
                player,
                league_id=league_id,
                league_slug=league_slug,
                alias_id=alias_id,
                stats_row=stat_row,
            )
            rows.append(
                {
                    "player_external_id": external_id,
                    "player_name": player.name,
                    "league_id": league_id,
                    "league_slug": league_slug,
                    "alias_id": str(alias_id),
                    "formats_written": written,
                }
            )
            if written == 0:
                unresolved.append(
                    {
                        "player_external_id": external_id,
                        "player_name": player.name,
                        "league_id": league_id,
                        "league_slug": league_slug,
                        "alias_id": str(alias_id),
                        "reason": "APA alias returned no lifetime format stats",
                    }
                )
            completed.add(key)
            _write_report(
                report_path,
                status="enrichment_in_progress",
                catalog_path=catalog_path,
                catalog_sha256=catalog_sha,
                staging_db=staging_db,
                completed_keys=completed,
                rows=rows,
                unresolved=unresolved,
                players_without_catalog_context=players_without_context,
            )

    return _write_report(
        report_path,
        status="enrichment_complete",
        catalog_path=catalog_path,
        catalog_sha256=catalog_sha,
        staging_db=staging_db,
        completed_keys=completed,
        rows=rows,
        unresolved=unresolved,
        players_without_catalog_context=players_without_context,
    )
