"""Wire the verified identity manifest and namespace audit into the actual
Ultimate Coach Scout & Compare cockpit payload.

Gap this closes: analytics.ultimate_coach_scout_compare already requires a
VERIFIED_UNIQUE canonical identity and only ever gets asked to compare two
specific players at a time -- but the payload the real HTML page was built
from (analytics.ultimate_coach_payload) selected every Player row and every
raw H2H evidence row directly from the data contract, with no identity or
namespace-audit gate at all. A SUSPECT-classified participant or a player
with no roster-backed provenance could still appear in the player selector
and in direct/shared evidence.

This module makes the trust contract real end-to-end:
  data contract -> verified identity manifest -> identity namespace audit
  -> only VERIFIED_UNIQUE identities are selectable
  -> only identity_verified_game_keys (mirror-safe AND identity-verified)
     ever become player-vs-player evidence

Unsafe/ambiguous/quarantined games are never dropped silently -- they are
counted and surfaced in the payload's own "trust" section so the cockpit can
disclose its own evidence limitations, never hide them.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from analytics.ultimate_coach_data_contract import build_contract
from analytics.ultimate_coach_identity_manifest import build_verified_identity_manifest
from analytics.ultimate_coach_identity_namespace_audit import audit_identity_namespace


def _result_for_perspective(all_games_row: dict[str, Any], player_id: int) -> str:
    winner = all_games_row.get("winner_id")
    loser = all_games_row.get("loser_id")
    if winner == player_id:
        return "W"
    if loser == player_id:
        return "L"
    return ""


def build_verified_cockpit_payload(db: Session) -> dict[str, Any]:
    """Return the cockpit payload, gated end-to-end by verified identity.

    Every step is deterministic given identical database content: the same
    contract -> manifest -> audit chain the offline analytics/export layer
    and any future re-run would independently reproduce.
    """
    contract = build_contract(db)
    manifest = build_verified_identity_manifest(contract)
    audit = audit_identity_namespace(\n        contract, manifest=manifest, include_participant_details=False\n    )

    verified_game_keys = set(audit["identity_verified_game_keys"])
    quarantined_game_keys = set(audit["quarantined_game_keys"])
    verified_player_ids = {identity["player_id"] for identity in manifest["identities"]}

    tables = contract["tables"]

    history_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in tables["team_history"]:
        history_by_player[int(row["player_id"])].append(
            {
                "team_external_id": row["team_external_id"],
                "team_name": row["team_name"] or "",
                "division_id": row["division_id"] or "",
                "session_name": row["session_name"] or "",
                "is_current": bool(row["is_current"]),
                "skill_level": row["skill_level"],
                "matches_won": row["matches_won"],
                "matches_played": row["matches_played"],
            }
        )

    career_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in tables["career_stats"]:
        career_by_player[int(row["player_id"])].append(
            {
                "league_id": row["league_id"],
                "league_slug": row["league_slug"] or "",
                "alias_external_id": row["alias_external_id"],
                "format": row["format"],
                "matches_won": row["matches_won"],
                "matches_played": row["matches_played"],
                "defensive_shot_avg": row["defensive_shot_avg"],
                "match_count_last_two_yrs": row["match_count_last_two_yrs"],
                "last_played": row["last_played"],
                "on_break_count": row["on_break_count"],
                "break_and_runs": row["break_and_runs"],
                "mini_slams": row["mini_slams"],
                "rackless": row["rackless"],
                "skunks": row["skunks"],
            }
        )

    # current_skill_level/current_matches_* are live-roster fields the
    # identity manifest never carries (it's about identity provenance, not
    # current stats) -- pull them from the contract's own players table,
    # indexed by the same internal player_id the manifest already verified.
    current_stats_by_player: dict[int, dict[str, Any]] = {
        int(row["player_id"]): row for row in tables["players"] if row.get("player_id") is not None
    }

    players: list[dict[str, Any]] = []
    for identity in manifest["identities"]:
        pid = identity["player_id"]
        current = current_stats_by_player.get(pid, {})
        players.append(
            {
                "id": pid,
                "external_id": identity["member_external_id"],
                "name": identity["player_name"],
                "identity_status": identity["status"],
                "current_skill_level": current.get("current_skill_level"),
                "current_matches_won": current.get("current_matches_won"),
                "current_matches_played": current.get("current_matches_played"),
                "team_history": history_by_player.get(pid, []),
                "career_stats": career_by_player.get(pid, []),
            }
        )
    players.sort(key=lambda row: row["id"])

    # Build directional per-perspective evidence rows ONLY from games that
    # are both mirror-safe (VERIFIED_UNIQUE in the data contract) AND
    # identity-verified by the namespace audit (EXACT_ROSTER_SCOPE on both
    # sides) -- audit_identity_namespace already enforces both conditions
    # when it adds a key to identity_verified_game_keys, so membership in
    # that set is sufficient; no re-derivation of the mirror check here.
    evidence: list[dict[str, Any]] = []
    for row in tables["all_games"]:
        game_key = row.get("game_key")
        if game_key not in verified_game_keys:
            continue
        a_id, b_id = row.get("participant_a_id"), row.get("participant_b_id")
        if a_id not in verified_player_ids or b_id not in verified_player_ids:
            # Should be unreachable -- the namespace audit only marks a key
            # identity_verified_game_keys when both participants resolved
            # EXACT_ROSTER_SCOPE against this same manifest -- but the
            # payload must never trust that invariant silently. Skip rather
            # than emit evidence for an unverified id.
            continue
        result_a = row.get("participant_a_result") or ""
        result_b = "L" if result_a == "W" else "W" if result_a == "L" else ""
        evidence.append(
            {
                "player_id": a_id,
                "opponent_id": b_id,
                "match_id": row.get("match_id"),
                "match_external_id": row.get("match_external_id"),
                "match_date": row.get("match_date") or "",
                "session_name": row.get("session_name") or "",
                "format": row.get("format"),
                "result": result_a,
                "own_skill_level": row.get("participant_a_skill_level"),
                "opponent_skill_level": row.get("participant_b_skill_level"),
                "points_earned": row.get("participant_a_points_earned"),
                "nine_ball_points": row.get("participant_a_nine_ball_points"),
                "game_key": game_key,
            }
        )
        evidence.append(
            {
                "player_id": b_id,
                "opponent_id": a_id,
                "match_id": row.get("match_id"),
                "match_external_id": row.get("match_external_id"),
                "match_date": row.get("match_date") or "",
                "session_name": row.get("session_name") or "",
                "format": row.get("format"),
                "result": result_b,
                "own_skill_level": row.get("participant_b_skill_level"),
                "opponent_skill_level": row.get("participant_a_skill_level"),
                # all_games stores only participant A's own points/nine-ball
                # count for this game row (see ultimate_coach_data_contract's
                # own "one canonical individual-game row" rule) -- B's own
                # points figure is genuinely not captured at this layer.
                # Missing stays missing; it is never copied from A's value
                # or fabricated as zero.
                "points_earned": None,
                "nine_ball_points": None,
                "game_key": game_key,
            }
        )

    trust = {
        "verified_identity_count": manifest["counts"]["verified_identities"],
        "identity_exclusion_count": manifest["counts"]["identity_exclusions"],
        "identity_verified_game_count": audit["counts"]["identity_verified_games"],
        "quarantined_game_count": audit["counts"]["quarantined_games"],
        "suspect_participant_count": audit["counts"]["suspect_participants"],
        "indeterminate_participant_count": audit["counts"]["indeterminate_participants"],
        "source_coverage_issue_count": contract["counts"]["coverage_issues"],
        "total_all_games_rows": len(tables["all_games"]),
        "quarantined_game_keys_sample": sorted(quarantined_game_keys)[:25],
    }

    return {
        "schema": "ultimate-coach-verified-cockpit-v1",
        "source_contract_schema": contract["schema"],
        "source_identity_manifest_schema": manifest["schema"],
        "source_namespace_audit_schema": audit["schema"],
        "probability_status": "NOT_CALIBRATED",
        "identity_policy": "ROSTER_PROVENANCE_REQUIRED",
        "players": players,
        "evidence": evidence,
        "trust": trust,
        "counts": {
            "players": len(players),
            "head_to_head_rows": len(evidence),
            "all_games": len(tables["all_games"]),
        },
        "matchup_probability": None,
        "predictive_confidence": None,
        "probability_publication": "FORBIDDEN",
        "requires_live_apa_login": False,
        "database_mutated": False,
        "name_matching_used": False,
    }
