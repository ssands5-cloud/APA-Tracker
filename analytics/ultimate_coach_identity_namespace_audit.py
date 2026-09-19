"""Read-only namespace collision/coalescence audit for Ultimate Coach.

The archive historically stores canonical APA member ids and unresolved
scoresheet alias ids in the same Player.external_id column. This audit does not
guess whether a suspicious row is recoverable. It compares every All Games
participant against roster-backed canonical identity provenance and quarantines
mismatches for review.

No database writes, name matching, model output, or probability publication.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from analytics.ultimate_coach_identity_manifest import (
    build_verified_identity_manifest,
)

_SUPPORTED_CONTRACT_SCHEMAS = frozenset({"ultimate-coach-data-contract-v1"})
_SUPPORTED_MANIFEST_SCHEMAS = frozenset({"ultimate-coach-identity-manifest-v1"})
_TRUSTED_MIRROR_STATUS = "VERIFIED_UNIQUE"


def _int_id(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _numeric_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value.isdigit() else None


def _validate_contract(contract: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(contract, dict):
        raise ValueError("contract must be a mapping")
    if contract.get("schema") not in _SUPPORTED_CONTRACT_SCHEMAS:
        raise ValueError(f"unsupported data-contract schema: {contract.get('schema')!r}")
    tables = contract.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("contract tables must be a mapping")
    games = tables.get("all_games")
    team_matches = tables.get("team_matches")
    if not isinstance(games, list) or not isinstance(team_matches, list):
        raise ValueError("contract must contain all_games and team_matches lists")
    return games, team_matches


def _validate_manifest(manifest: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a mapping")
    if manifest.get("schema") not in _SUPPORTED_MANIFEST_SCHEMAS:
        raise ValueError(f"unsupported identity-manifest schema: {manifest.get('schema')!r}")
    if manifest.get("source_contract_schema") != contract.get("schema"):
        raise ValueError("identity manifest was not built from this contract schema")
    identities = manifest.get("identities")
    if not isinstance(identities, list):
        raise ValueError("identity manifest identities must be a list")
    return identities


def _team_match_index(team_matches: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    index: dict[int, dict[str, Any]] = {}
    duplicates: set[int] = set()
    for row in team_matches:
        if not isinstance(row, dict):
            continue
        match_id = _int_id(row.get("match_id"))
        if match_id is None:
            continue
        if match_id in index:
            duplicates.add(match_id)
            continue
        index[match_id] = row
    for match_id in duplicates:
        index.pop(match_id, None)
    return index


def _identity_index(identities: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], set[int]]:
    index: dict[int, dict[str, Any]] = {}
    duplicates: set[int] = set()
    for row in identities:
        if not isinstance(row, dict):
            continue
        player_id = _int_id(row.get("player_id"))
        if player_id is None:
            continue
        if player_id in index:
            duplicates.add(player_id)
            continue
        index[player_id] = row
    for player_id in duplicates:
        index.pop(player_id, None)
    return index, duplicates


def _participant_audit(
    game: dict[str, Any],
    side: str,
    *,
    identity_by_id: dict[int, dict[str, Any]],
    duplicate_manifest_ids: set[int],
    team_match: dict[str, Any] | None,
) -> dict[str, Any]:
    prefix = f"participant_{side}"
    player_id = _int_id(game.get(f"{prefix}_id"))
    external_id = game.get(f"{prefix}_external_id")
    team_id = _text(game.get(f"{prefix}_team_id"))
    session_name = _text(game.get("session_name"))
    game_key = _text(game.get("game_key"))

    result = {
        "side": side.upper(),
        "game_key": game_key or None,
        "match_id": game.get("match_id"),
        "player_id": game.get(f"{prefix}_id"),
        "player_external_id": external_id,
        "player_name": game.get(f"{prefix}_name"),
        "team_id": team_id or None,
        "session_name": session_name or None,
        "status": None,
        "reason": None,
        "matched_roster_scope": None,
    }

    if player_id is None:
        result["status"] = "INDETERMINATE"
        result["reason"] = "INVALID_INTERNAL_PLAYER_ID"
        return result

    if player_id in duplicate_manifest_ids:
        result["status"] = "INDETERMINATE"
        result["reason"] = "DUPLICATE_IDENTITY_MANIFEST_PLAYER_ID"
        return result

    identity = identity_by_id.get(player_id)
    if identity is None:
        result["status"] = "INDETERMINATE"
        result["reason"] = "PLAYER_NOT_ROSTER_VERIFIED"
        return result

    canonical_member_id = _numeric_string(identity.get("member_external_id"))
    observed_member_id = _numeric_string(external_id)
    if canonical_member_id is None or observed_member_id is None:
        result["status"] = "SUSPECT"
        result["reason"] = "INVALID_OR_MISSING_MEMBER_ID"
        return result
    if observed_member_id != canonical_member_id:
        result["status"] = "SUSPECT"
        result["reason"] = "EXTERNAL_ID_MISMATCH"
        result["canonical_member_external_id"] = canonical_member_id
        return result

    if not team_id or not session_name:
        result["status"] = "INDETERMINATE"
        result["reason"] = "MISSING_GAME_TEAM_OR_SESSION_SCOPE"
        return result

    scopes = identity.get("roster_provenance_scopes")
    if not isinstance(scopes, list) or not scopes:
        result["status"] = "INDETERMINATE"
        result["reason"] = "IDENTITY_HAS_NO_ROSTER_PROVENANCE_SCOPES"
        return result

    exact_scopes = [
        scope for scope in scopes
        if isinstance(scope, dict)
        and _text(scope.get("team_external_id")) == team_id
        and _text(scope.get("session_name")) == session_name
    ]
    if exact_scopes:
        if team_match is not None:
            legal_match_teams = {
                _text(team_match.get("home_team_id")),
                _text(team_match.get("away_team_id")),
            }
            legal_match_teams.discard("")
            if legal_match_teams and team_id not in legal_match_teams:
                result["status"] = "SUSPECT"
                result["reason"] = "PARTICIPANT_TEAM_NOT_IN_TEAM_MATCH"
                result["team_match_teams"] = sorted(legal_match_teams)
                return result

        result["status"] = "EXACT_ROSTER_SCOPE"
        result["reason"] = "PLAYER_MEMBER_TEAM_SESSION_RECONCILED"
        result["matched_roster_scope"] = sorted(
            [
                {
                    "team_external_id": _text(scope.get("team_external_id")),
                    "division_id": _text(scope.get("division_id")),
                    "session_name": _text(scope.get("session_name")),
                    "is_current": bool(scope.get("is_current")),
                }
                for scope in exact_scopes
            ],
            key=lambda row: (
                row["session_name"],
                row["division_id"],
                row["team_external_id"],
                row["is_current"],
            ),
        )[0]
        return result

    same_session_teams = sorted(
        {
            _text(scope.get("team_external_id"))
            for scope in scopes
            if isinstance(scope, dict)
            and _text(scope.get("session_name")) == session_name
            and _text(scope.get("team_external_id"))
        }
    )
    result["status"] = "SUSPECT"
    if same_session_teams:
        result["reason"] = "TEAM_MISMATCH_WITHIN_ROSTERED_SESSION"
        result["rostered_teams_for_session"] = same_session_teams
    else:
        result["reason"] = "NO_ROSTER_PROVENANCE_FOR_GAME_SESSION"
    return result


def audit_identity_namespace(
    contract: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit participant identity provenance without changing any source data.

    SUSPECT means the stored identity conflicts with available roster-backed
    provenance. It is not an assertion that a namespace collision definitely
    occurred, because the archive itself may have incomplete historical roster
    coverage.

    INDETERMINATE means the audit lacks enough source scope to decide.
    """
    games, team_matches = _validate_contract(contract)
    manifest = manifest or build_verified_identity_manifest(contract)
    identities = _validate_manifest(manifest, contract)

    identity_by_id, duplicate_manifest_ids = _identity_index(identities)
    team_match_by_id = _team_match_index(team_matches)

    game_key_counts = Counter(_text(row.get("game_key")) for row in games if isinstance(row, dict))
    participant_rows: list[dict[str, Any]] = []
    quarantined_game_keys: set[str] = set()
    identity_verified_game_keys: set[str] = set()
    structural_issues: list[dict[str, Any]] = []

    for index, game in enumerate(games):
        if not isinstance(game, dict):
            structural_issues.append(
                {"game_row_index": index, "reason": "GAME_ROW_NOT_MAPPING"}
            )
            continue

        game_key = _text(game.get("game_key"))
        if not game_key:
            structural_issues.append(
                {"game_row_index": index, "reason": "MISSING_GAME_KEY"}
            )
            continue
        if game_key_counts[game_key] != 1:
            structural_issues.append(
                {
                    "game_row_index": index,
                    "game_key": game_key,
                    "reason": "DUPLICATE_GAME_KEY",
                    "row_count": game_key_counts[game_key],
                }
            )
            quarantined_game_keys.add(game_key)
            continue

        a_id = _int_id(game.get("participant_a_id"))
        b_id = _int_id(game.get("participant_b_id"))
        if a_id is not None and b_id is not None and a_id == b_id:
            structural_issues.append(
                {
                    "game_row_index": index,
                    "game_key": game_key,
                    "player_id": a_id,
                    "reason": "SELF_PAIRING",
                }
            )
            quarantined_game_keys.add(game_key)
            continue

        match_id = _int_id(game.get("match_id"))
        team_match = team_match_by_id.get(match_id) if match_id is not None else None

        a = _participant_audit(
            game,
            "a",
            identity_by_id=identity_by_id,
            duplicate_manifest_ids=duplicate_manifest_ids,
            team_match=team_match,
        )
        b = _participant_audit(
            game,
            "b",
            identity_by_id=identity_by_id,
            duplicate_manifest_ids=duplicate_manifest_ids,
            team_match=team_match,
        )
        participant_rows.extend([a, b])

        statuses = {a["status"], b["status"]}
        mirror_ok = game.get("mirror_status") == _TRUSTED_MIRROR_STATUS

        if "SUSPECT" in statuses:
            quarantined_game_keys.add(game_key)
        elif statuses == {"EXACT_ROSTER_SCOPE"} and mirror_ok:
            identity_verified_game_keys.add(game_key)

    status_counts = Counter(row["status"] for row in participant_rows)
    reason_counts = Counter(row["reason"] for row in participant_rows)

    suspect_rows = [row for row in participant_rows if row["status"] == "SUSPECT"]
    indeterminate_rows = [row for row in participant_rows if row["status"] == "INDETERMINATE"]
    exact_rows = [row for row in participant_rows if row["status"] == "EXACT_ROSTER_SCOPE"]

    return {
        "schema": "ultimate-coach-identity-namespace-audit-v1",
        "source_contract_schema": contract["schema"],
        "source_identity_manifest_schema": manifest["schema"],
        "audit_mode": "READ_ONLY_FAIL_CLOSED",
        "interpretation": (
            "SUSPECT marks a conflict with available roster-backed provenance; "
            "it does not by itself prove a numeric namespace collision."
        ),
        "participant_audits": sorted(
            participant_rows,
            key=lambda row: (
                str(row.get("game_key")),
                str(row.get("side")),
                str(row.get("player_id")),
            ),
        ),
        "suspect_participants": sorted(
            suspect_rows,
            key=lambda row: (
                str(row.get("game_key")),
                str(row.get("side")),
                str(row.get("player_id")),
            ),
        ),
        "indeterminate_participants": sorted(
            indeterminate_rows,
            key=lambda row: (
                str(row.get("game_key")),
                str(row.get("side")),
                str(row.get("player_id")),
            ),
        ),
        "structural_issues": sorted(
            structural_issues,
            key=lambda row: (
                str(row.get("game_key")),
                str(row.get("game_row_index")),
                str(row.get("reason")),
            ),
        ),
        "identity_verified_game_keys": sorted(identity_verified_game_keys),
        "quarantined_game_keys": sorted(quarantined_game_keys),
        "counts": {
            "all_games_rows": len(games),
            "participant_audits": len(participant_rows),
            "exact_roster_scope_participants": len(exact_rows),
            "suspect_participants": len(suspect_rows),
            "indeterminate_participants": len(indeterminate_rows),
            "structural_issues": len(structural_issues),
            "identity_verified_games": len(identity_verified_game_keys),
            "quarantined_games": len(quarantined_game_keys),
            "duplicate_manifest_player_ids": len(duplicate_manifest_ids),
        },
        "participant_status_counts": dict(sorted(status_counts.items())),
        "participant_reason_counts": dict(sorted(reason_counts.items())),
        "database_mutated": False,
        "name_matching_used": False,
        "requires_live_apa_login": False,
        "matchup_probability": None,
        "probability_publication": "FORBIDDEN",
    }
