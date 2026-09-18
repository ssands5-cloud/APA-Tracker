"""Recursively expand the Ultimate Coach historical catalog through real players.

The seed catalog starts from sessions directly exposed by the authenticated
member's own league aliases. That is useful but not necessarily the whole
league history.

This module expands outward without guessing ids:

seed sessions/divisions
  -> division rosters
  -> real roster member ids
  -> each member's real alias in that same league
  -> that alias's real historical sessions
  -> every division APA exposes for each newly discovered session
  -> repeat until no new divisions remain

No session/division/member id is synthesized or brute-forced.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from pathlib import Path
from typing import Any

from scraper.graphql_scraper import (
    alias_session_rows,
    fetch_alias_sessions,
    fetch_division_rosters,
    fetch_formats_by_member_id,
    fetch_league_divisions,
    league_division_rows,
    member_aliases_rows,
)

EXPANDED_SCHEMA = "ultimate-coach-historical-catalog-v2"
REPORT_SCHEMA = "ultimate-coach-history-graph-v1"
_SUPPORTED_FORMATS = {"EIGHT", "NINE", "MASTERS"}


class HistoryGraphError(RuntimeError):
    """A structural/resume safety problem that must stop graph expansion."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _session_key(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("league_slug") or ""),
        str(row.get("session_id") or row.get("catalog_session_id") or ""),
    )


def _division_key(row: dict[str, Any]) -> tuple[str, str, str]:
    league_slug = str(row.get("league_slug") or "")
    session_id = str(row.get("catalog_session_id") or row.get("session_id") or "")
    division_id = str(row.get("division_id") or "")
    return (league_slug, session_id, division_id)


def _clean_formats(values) -> list[str]:
    return sorted(
        {
            str(value).strip().upper()
            for value in (values or [])
            if str(value).strip().upper() in _SUPPORTED_FORMATS
        }
    )


def _catalog_indexes(seed: dict[str, Any]):
    sessions: dict[tuple[str, str], dict[str, Any]] = {}
    divisions: dict[tuple[str, str, str], dict[str, Any]] = {}

    for raw in seed.get("sessions") or []:
        row = dict(raw or {})
        key = _session_key(row)
        if not all(key):
            continue
        row.setdefault("discovery_source", "authenticated_member_alias")
        sessions[key] = row

    for raw in seed.get("divisions") or []:
        row = dict(raw or {})
        key = _division_key(row)
        if not all(key):
            continue
        row.setdefault("discovery_source", "authenticated_member_alias")
        divisions[key] = row

    return sessions, divisions


def _explicit_roster_member_ids(division: dict[str, Any]) -> tuple[list[str], int]:
    """Return only canonical roster[].member.id values from a division roster.

    The existing division_roster_team_rows() mapper intentionally falls back to
    the roster row's own id when member.id is absent. That fallback must NOT be
    used here: FormatsByMemberId requires the canonical member id, and a roster
    entry id is a different identifier. Missing/non-numeric member ids are
    skipped and counted rather than reinterpreted.
    """
    member_ids: set[str] = set()
    missing = 0
    for team in division.get("teams") or []:
        team = team or {}
        if team.get("isBye"):
            continue
        for player in team.get("roster") or []:
            player = player or {}
            member_id = str((player.get("member") or {}).get("id") or "").strip()
            if not member_id.isdigit():
                missing += 1
                continue
            member_ids.add(member_id)
    return sorted(member_ids, key=int), missing


def _same_league_aliases(
    aliases: list[dict[str, Any]],
    *,
    league_id: str,
    league_slug: str,
) -> list[dict[str, Any]]:
    """Return aliases proven to belong to the exact roster league.

    Prefer id equality. Slug is a corroborating/fallback field only when one
    side lacks an id. Conflicting id/slug evidence is rejected.
    """
    matches = []
    for alias in aliases:
        alias_id = str(alias.get("league_id") or "")
        alias_slug = str(alias.get("league_slug") or "")

        if league_id and alias_id:
            if alias_id != league_id:
                continue
            if league_slug and alias_slug and alias_slug != league_slug:
                continue
            matches.append(alias)
            continue

        if league_slug and alias_slug == league_slug:
            matches.append(alias)

    return matches


def _checkpoint(
    path: Path | None,
    *,
    seed_catalog_path: Path,
    seed_sha256: str,
    processed_divisions: set[str],
    processed_member_leagues: set[str],
    sessions: dict[tuple[str, str], dict[str, Any]],
    divisions: dict[tuple[str, str, str], dict[str, Any]],
    source_limitations: list[str],
    status: str,
) -> dict[str, Any]:
    report = {
        "schema": REPORT_SCHEMA,
        "status": status,
        "seed_catalog_path": str(seed_catalog_path),
        "seed_catalog_sha256": seed_sha256,
        "processed_division_keys": sorted(processed_divisions),
        "processed_member_league_keys": sorted(processed_member_leagues),
        "counts": {
            "sessions": len(sessions),
            "divisions": len(divisions),
            "processed_divisions": len(processed_divisions),
            "processed_member_league_scopes": len(processed_member_leagues),
            "source_limitations": len(set(source_limitations)),
        },
        "source_limitations": sorted(set(source_limitations)),
    }
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def expand_historical_catalog(
    config: dict,
    *,
    seed_catalog: dict[str, Any],
    seed_catalog_path: Path,
    output_path: Path,
    report_path: Path | None = None,
    resume: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Expand real league history until no new roster-connected sessions appear."""
    seed_sha = sha256_file(seed_catalog_path)
    sessions, divisions = _catalog_indexes(seed_catalog)
    if not sessions or not divisions:
        raise HistoryGraphError("seed catalog must contain at least one real session and division")

    processed_divisions: set[str] = set()
    processed_member_leagues: set[str] = set()
    source_limitations = list(seed_catalog.get("source_limitations") or [])

    if resume and report_path is not None and report_path.is_file():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        previous_sha = previous.get("seed_catalog_sha256")
        if previous_sha and previous_sha != seed_sha:
            raise HistoryGraphError(
                "seed catalog changed since prior graph expansion; refusing stale checkpoints"
            )
        processed_divisions = set(previous.get("processed_division_keys") or [])
        processed_member_leagues = set(previous.get("processed_member_league_keys") or [])

        if output_path.is_file():
            previous_catalog = json.loads(output_path.read_text(encoding="utf-8"))
            if previous_catalog.get("schema") != EXPANDED_SCHEMA:
                raise HistoryGraphError("resume catalog has an unexpected schema")
            sessions, divisions = _catalog_indexes(previous_catalog)
            source_limitations.extend(previous_catalog.get("source_limitations") or [])

    queue = deque(
        key for key in sorted(divisions) if "|".join(key) not in processed_divisions
    )

    while queue:
        key = queue.popleft()
        key_text = "|".join(key)
        division = divisions[key]
        league_slug, session_id, division_id = key
        league_id = str(division.get("league_id") or "")

        if not league_id:
            source_limitations.append(
                f"division {division_id} session {session_id}: missing league id; cannot expand members safely"
            )
            processed_divisions.add(key_text)
            continue

        roster_payload = fetch_division_rosters(config, division_id)
        real_teams = [
            team for team in (roster_payload.get("teams") or [])
            if not (team or {}).get("isBye")
        ]
        if not real_teams:
            source_limitations.append(
                f"division {division_id} session {session_id}: APA returned zero roster teams during graph expansion"
            )
            processed_divisions.add(key_text)
            _checkpoint(
                report_path,
                seed_catalog_path=seed_catalog_path,
                seed_sha256=seed_sha,
                processed_divisions=processed_divisions,
                processed_member_leagues=processed_member_leagues,
                sessions=sessions,
                divisions=divisions,
                source_limitations=source_limitations,
                status="expansion_in_progress",
            )
            continue

        member_ids, missing_member_ids = _explicit_roster_member_ids(roster_payload)
        if missing_member_ids:
            source_limitations.append(
                f"division {division_id} session {session_id}: "
                f"{missing_member_ids} roster row(s) lacked a canonical numeric member.id "
                "and were excluded from history-graph expansion"
            )

        for member_id in member_ids:
            scope_key = f"{member_id}|{league_id}|{league_slug}"
            if scope_key in processed_member_leagues:
                continue

            member = fetch_formats_by_member_id(config, int(member_id))
            aliases = member_aliases_rows(member)
            candidates = _same_league_aliases(
                aliases,
                league_id=league_id,
                league_slug=league_slug,
            )
            if len(candidates) != 1:
                source_limitations.append(
                    f"member {member_id} league {league_id}/{league_slug}: "
                    f"expected one exact league alias, found {len(candidates)}"
                )
                processed_member_leagues.add(scope_key)
                continue

            alias = candidates[0]
            alias_id = alias.get("alias_id")
            formats = _clean_formats(alias.get("formats"))
            if not alias_id or not formats:
                source_limitations.append(
                    f"member {member_id} league {league_id}/{league_slug}: "
                    "resolved alias lacks id or supported formats"
                )
                processed_member_leagues.add(scope_key)
                continue

            discovered_rows: list[dict[str, Any]] = []
            for format_name in formats:
                alias_sessions = fetch_alias_sessions(config, int(alias_id), format_name)
                discovered_rows.extend(alias_session_rows(alias_sessions, format_name))

            unique_session_ids = sorted(
                {
                    str(row.get("session_id") or "")
                    for row in discovered_rows
                    if str(row.get("session_id") or "").isdigit()
                },
                key=int,
            )

            for discovered_session_id in unique_session_ids:
                session_rows = [
                    row
                    for row in discovered_rows
                    if str(row.get("session_id") or "") == discovered_session_id
                ]
                discovered_name = next(
                    (str(row.get("session_name") or "") for row in session_rows if row.get("session_name")),
                    "",
                )
                session_key = (league_slug, discovered_session_id)
                if session_key not in sessions:
                    sessions[session_key] = {
                        "league_id": league_id,
                        "league_slug": league_slug,
                        "session_id": discovered_session_id,
                        "session_name": discovered_name,
                        "formats_discovered": sorted(
                            {str(row.get("format") or "") for row in session_rows if row.get("format")}
                        ),
                        "alias_ids": [str(alias_id)],
                        "discovery_source": "roster_member_alias_graph",
                    }

                # Calling leagueDivisions for an already-known session is
                # unnecessary. New sessions are expanded exactly once.
                known_divisions_for_session = any(
                    dkey[0] == league_slug and dkey[1] == discovered_session_id
                    for dkey in divisions
                )
                if known_divisions_for_session:
                    continue

                league = fetch_league_divisions(
                    config,
                    league_slug,
                    int(discovered_session_id),
                )
                new_rows = league_division_rows(league)
                if not new_rows:
                    source_limitations.append(
                        f"league {league_slug} session {discovered_session_id} "
                        f"({discovered_name}): APA returned zero divisions during graph expansion"
                    )
                    continue

                for new_division in new_rows:
                    returned_session = str(new_division.get("session_id") or "")
                    if returned_session and returned_session != discovered_session_id:
                        source_limitations.append(
                            f"division {new_division.get('division_id')}: requested session "
                            f"{discovered_session_id} but APA labeled it {returned_session}"
                        )
                        continue

                    enriched = dict(new_division)
                    enriched["league_slug"] = league_slug
                    enriched["league_id"] = str(new_division.get("league_id") or league_id)
                    enriched["catalog_session_id"] = discovered_session_id
                    enriched["catalog_session_name"] = (
                        new_division.get("session_name") or discovered_name
                    )
                    enriched["discovery_source"] = "roster_member_alias_graph"
                    dkey = _division_key(enriched)
                    if not all(dkey):
                        continue
                    if dkey not in divisions:
                        divisions[dkey] = enriched
                        queue.append(dkey)

            processed_member_leagues.add(scope_key)

        processed_divisions.add(key_text)

        expanded = {
            "schema": EXPANDED_SCHEMA,
            "member_id": str(seed_catalog.get("member_id") or ""),
            "discovery_mode": "recursive_roster_member_alias_graph",
            "seed_schema": seed_catalog.get("schema"),
            "seed_catalog_sha256": seed_sha,
            "aliases": list(seed_catalog.get("aliases") or []),
            "sessions": [
                sessions[key] for key in sorted(sessions, key=lambda x: (x[0], int(x[1])))
            ],
            "divisions": [
                divisions[key]
                for key in sorted(divisions, key=lambda x: (x[0], int(x[1]), int(x[2])))
            ],
            "source_limitations": sorted(set(source_limitations)),
            "counts": {
                "aliases": len(seed_catalog.get("aliases") or []),
                "sessions": len(sessions),
                "divisions": len(divisions),
            },
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(expanded, indent=2, sort_keys=True), encoding="utf-8")
        _checkpoint(
            report_path,
            seed_catalog_path=seed_catalog_path,
            seed_sha256=seed_sha,
            processed_divisions=processed_divisions,
            processed_member_leagues=processed_member_leagues,
            sessions=sessions,
            divisions=divisions,
            source_limitations=source_limitations,
            status="expansion_in_progress",
        )

    expanded = {
        "schema": EXPANDED_SCHEMA,
        "member_id": str(seed_catalog.get("member_id") or ""),
        "discovery_mode": "recursive_roster_member_alias_graph",
        "seed_schema": seed_catalog.get("schema"),
        "seed_catalog_sha256": seed_sha,
        "aliases": list(seed_catalog.get("aliases") or []),
        "sessions": [
            sessions[key] for key in sorted(sessions, key=lambda x: (x[0], int(x[1])))
        ],
        "divisions": [
            divisions[key]
            for key in sorted(divisions, key=lambda x: (x[0], int(x[1]), int(x[2])))
        ],
        "source_limitations": sorted(set(source_limitations)),
        "counts": {
            "aliases": len(seed_catalog.get("aliases") or []),
            "sessions": len(sessions),
            "divisions": len(divisions),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(expanded, indent=2, sort_keys=True), encoding="utf-8")
    report = _checkpoint(
        report_path,
        seed_catalog_path=seed_catalog_path,
        seed_sha256=seed_sha,
        processed_divisions=processed_divisions,
        processed_member_leagues=processed_member_leagues,
        sessions=sessions,
        divisions=divisions,
        source_limitations=source_limitations,
        status="expansion_complete",
    )
    return expanded, report
