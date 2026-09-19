"""Fail-closed canonical identity manifest for Ultimate Coach.

The manifest is derived offline from the canonical data-contract tables.
A Player row is considered verified only when its APA member id is numeric,
unique, and backed by at least one complete PlayerTeamHistory roster scope.
Display names are never identity keys.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

SUPPORTED_CONTRACT_SCHEMAS = frozenset({"ultimate-coach-data-contract-v1"})


def _canonical_internal_id(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _canonical_member_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text.isdigit() else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tables(contract: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(contract, dict):
        raise ValueError("contract must be a mapping")
    schema = contract.get("schema")
    if schema not in SUPPORTED_CONTRACT_SCHEMAS:
        raise ValueError(f"unsupported Ultimate Coach data-contract schema: {schema!r}")
    tables = contract.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("contract tables must be a mapping")
    players = tables.get("players")
    history = tables.get("team_history")
    if not isinstance(players, list) or not isinstance(history, list):
        raise ValueError("contract must contain players and team_history lists")
    return players, history


def build_verified_identity_manifest(contract: dict[str, Any]) -> dict[str, Any]:
    """Return roster-proven canonical identities and explicit exclusions.

    A complete roster provenance scope requires exact internal player id,
    matching numeric APA member id, team id, division id, and session name.
    The name field is display metadata only and never participates in identity
    resolution.
    """
    players, history = _tables(contract)

    exclusions: list[dict[str, Any]] = []
    structural_issues: list[dict[str, Any]] = []

    player_rows_by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(players):
        if not isinstance(row, dict):
            exclusions.append(
                {
                    "player_row_index": index,
                    "player_id": None,
                    "reason": "PLAYER_ROW_NOT_MAPPING",
                }
            )
            continue
        player_id = _canonical_internal_id(row.get("player_id"))
        if player_id is None:
            exclusions.append(
                {
                    "player_row_index": index,
                    "player_id": row.get("player_id"),
                    "reason": "INVALID_INTERNAL_PLAYER_ID",
                }
            )
            continue
        player_rows_by_id[player_id].append(row)

    candidate_rows: dict[int, dict[str, Any]] = {}
    for player_id in sorted(player_rows_by_id):
        rows = player_rows_by_id[player_id]
        if len(rows) != 1:
            exclusions.append(
                {
                    "player_id": player_id,
                    "reason": "DUPLICATE_PLAYER_ROW",
                    "row_count": len(rows),
                }
            )
            continue
        row = rows[0]
        member_id = _canonical_member_id(row.get("member_external_id"))
        if member_id is None:
            exclusions.append(
                {
                    "player_id": player_id,
                    "member_external_id": row.get("member_external_id"),
                    "reason": "INVALID_APA_MEMBER_ID",
                }
            )
            continue
        candidate_rows[player_id] = row

    member_to_players: dict[str, list[int]] = defaultdict(list)
    for player_id, row in candidate_rows.items():
        member_to_players[_canonical_member_id(row.get("member_external_id"))].append(player_id)

    duplicate_member_players: set[int] = set()
    for member_id, player_ids in sorted(member_to_players.items()):
        if len(player_ids) <= 1:
            continue
        for player_id in sorted(player_ids):
            duplicate_member_players.add(player_id)
            exclusions.append(
                {
                    "player_id": player_id,
                    "member_external_id": member_id,
                    "reason": "APA_MEMBER_ID_MAPS_TO_MULTIPLE_PLAYERS",
                    "conflicting_player_ids": sorted(player_ids),
                }
            )

    history_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    orphan_history_rows = 0
    invalid_history_rows = 0
    known_player_ids = set(player_rows_by_id)

    for index, row in enumerate(history):
        if not isinstance(row, dict):
            invalid_history_rows += 1
            structural_issues.append(
                {
                    "team_history_row_index": index,
                    "reason": "TEAM_HISTORY_ROW_NOT_MAPPING",
                }
            )
            continue
        player_id = _canonical_internal_id(row.get("player_id"))
        if player_id is None:
            invalid_history_rows += 1
            structural_issues.append(
                {
                    "team_history_row_index": index,
                    "player_id": row.get("player_id"),
                    "reason": "INVALID_TEAM_HISTORY_PLAYER_ID",
                }
            )
            continue
        if player_id not in known_player_ids:
            orphan_history_rows += 1
            structural_issues.append(
                {
                    "team_history_row_index": index,
                    "player_id": player_id,
                    "reason": "ORPHAN_TEAM_HISTORY_PLAYER_ID",
                }
            )
            continue
        history_by_player[player_id].append(row)

    identities: list[dict[str, Any]] = []
    for player_id in sorted(candidate_rows):
        if player_id in duplicate_member_players:
            continue

        player = candidate_rows[player_id]
        member_id = _canonical_member_id(player.get("member_external_id"))
        rows = history_by_player.get(player_id, [])

        conflicting_rows = [
            row
            for row in rows
            if _text(row.get("member_external_id"))
            and _text(row.get("member_external_id")) != member_id
        ]
        if conflicting_rows:
            exclusions.append(
                {
                    "player_id": player_id,
                    "member_external_id": member_id,
                    "reason": "TEAM_HISTORY_MEMBER_ID_CONFLICT",
                    "conflicting_member_ids": sorted(
                        {_text(row.get("member_external_id")) for row in conflicting_rows}
                    ),
                }
            )
            continue

        scopes_by_key: dict[tuple[str, str, str, bool], dict[str, Any]] = {}
        invalid_scope_rows = 0
        for row in rows:
            if _text(row.get("member_external_id")) != member_id:
                invalid_scope_rows += 1
                continue
            team_id = _text(row.get("team_external_id"))
            division_id = _text(row.get("division_id"))
            session_name = _text(row.get("session_name"))
            if not team_id or not division_id or not session_name:
                invalid_scope_rows += 1
                continue
            is_current = bool(row.get("is_current"))
            key = (session_name, division_id, team_id, is_current)
            scopes_by_key[key] = {
                "team_external_id": team_id,
                "team_name": row.get("team_name"),
                "division_id": division_id,
                "session_name": session_name,
                "is_current": is_current,
                "is_tournament": bool(row.get("is_tournament")),
                "skill_level": row.get("skill_level"),
            }

        if not scopes_by_key:
            exclusions.append(
                {
                    "player_id": player_id,
                    "member_external_id": member_id,
                    "reason": "NO_COMPLETE_ROSTER_PROVENANCE",
                    "team_history_rows_seen": len(rows),
                    "invalid_scope_rows": invalid_scope_rows,
                }
            )
            continue

        scopes = [
            scopes_by_key[key]
            for key in sorted(
                scopes_by_key,
                key=lambda value: (value[0], value[1], value[2], value[3]),
            )
        ]
        identities.append(
            {
                "player_id": player_id,
                "member_external_id": member_id,
                "player_name": player.get("player_name"),
                "status": "VERIFIED_UNIQUE",
                "verification_basis": "ROSTER_BACKED_PLAYER_TEAM_HISTORY",
                "roster_provenance_scopes": scopes,
                "roster_provenance_scope_count": len(scopes),
                "invalid_or_incomplete_history_rows_ignored": invalid_scope_rows,
            }
        )

    identities.sort(key=lambda row: row["player_id"])
    exclusions.sort(
        key=lambda row: (
            str(row.get("player_id")),
            str(row.get("reason")),
            str(row.get("player_row_index")),
        )
    )
    structural_issues.sort(
        key=lambda row: (
            str(row.get("team_history_row_index")),
            str(row.get("reason")),
        )
    )

    return {
        "schema": "ultimate-coach-identity-manifest-v1",
        "source_contract_schema": contract["schema"],
        "identity_policy": "ROSTER_PROVENANCE_REQUIRED",
        "identities": identities,
        "identity_count": len(identities),
        "identity_exclusions": exclusions,
        "identity_exclusion_count": len(exclusions),
        "structural_issues": structural_issues,
        "counts": {
            "source_player_rows": len(players),
            "source_team_history_rows": len(history),
            "verified_identities": len(identities),
            "identity_exclusions": len(exclusions),
            "orphan_team_history_rows": orphan_history_rows,
            "invalid_team_history_rows": invalid_history_rows,
        },
        "name_matching_used": False,
        "requires_live_apa_login": False,
        "probability_publication": "FORBIDDEN",
    }
