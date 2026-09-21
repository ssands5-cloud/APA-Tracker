"""Offline Scout & Compare cockpit for Ultimate Coach.

This module composes factual, provenance-bearing evidence only. It never
computes matchup odds or predictive confidence and requires canonical identity
resolution to have succeeded before rendering a comparison.
"""

from __future__ import annotations

from typing import Any

from analytics.ultimate_coach_evidence_quality import direct_evidence, shared_opponent_evidence

_ALLOWED_IDENTITY_STATUSES = frozenset({"VERIFIED_UNIQUE"})


def _canonical_id(identity: dict[str, Any], label: str) -> int:
    status = str(identity.get("status") or "").strip().upper()
    player_id = identity.get("player_id")
    if status not in _ALLOWED_IDENTITY_STATUSES or not isinstance(player_id, int) or isinstance(player_id, bool):
        raise ValueError(f"{label} identity must be VERIFIED_UNIQUE with an integer canonical player_id")
    return player_id


def build_scout_compare(
    all_games: list[dict[str, Any]],
    player_a_identity: dict[str, Any],
    player_b_identity: dict[str, Any],
    fmt: str,
) -> dict[str, Any]:
    """Build a deterministic offline factual comparison.

    The caller supplies canonical identity-resolution records and actual archive
    rows. Ambiguous/unverified identities fail closed. Evidence-quality failures
    remain visible in the nested evidence objects rather than being converted to
    zeros, estimates, or neutral defaults.
    """
    player_a_id = _canonical_id(player_a_identity, "player_a")
    player_b_id = _canonical_id(player_b_identity, "player_b")
    if player_a_id == player_b_id:
        raise ValueError("Scout & Compare requires two distinct canonical players")

    direct = direct_evidence(all_games, player_a_id, player_b_id, fmt)
    shared = shared_opponent_evidence(all_games, player_a_id, player_b_id, fmt)
    resolved_format = direct["format"]

    evidence_status = "VERIFIED"
    blockers: list[str] = []
    if direct["status"] == "INSUFFICIENT_EVIDENCE":
        evidence_status = "PARTIAL"
        blockers.append(f"DIRECT:{direct['reason']}")
    unsafe_shared = [row for row in shared["shared_opponents"] if row["status"] != "VERIFIED"]
    if unsafe_shared:
        evidence_status = "PARTIAL"
        blockers.extend(f"SHARED:{row['opponent_id']}:{row['reason']}" for row in unsafe_shared)
    if direct["status"] == "NO_RECORDED_HISTORY" and not shared["shared_opponents"]:
        evidence_status = "NO_RECORDED_EVIDENCE"

    return {
        "cockpit": "ULTIMATE_COACH_SCOUT_COMPARE_OFFLINE",
        "format": resolved_format,
        "player_a_id": player_a_id,
        "player_b_id": player_b_id,
        "identity_status": "VERIFIED_UNIQUE",
        "evidence_status": evidence_status,
        "evidence_blockers": blockers,
        "direct_history": direct,
        "shared_opponent_history": shared,
        "predictive_confidence": None,
        "matchup_probability": None,
        "probability_publication": "FORBIDDEN",
        "requires_live_apa_login": False,
    }
