"""Evidence-quality gates for Ultimate Coach factual matchup summaries.

This module never creates predictions. It grades whether recorded evidence is
safe enough to summarize and exposes exact All Games keys for traceability.
Ambiguous or unreconciled evidence fails closed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

TRUSTED_MIRROR_STATUSES = frozenset({"VERIFIED_UNIQUE"})
_ALLOWED_FORMATS = frozenset({"EIGHT", "NINE"})


def _fmt(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if text in {"EIGHT", "8", "8-BALL", "8 BALL", "EIGHT_BALL"}:
        return "EIGHT"
    if text in {"NINE", "9", "9-BALL", "9 BALL", "NINE_BALL"}:
        return "NINE"
    return text


def _required_format(value: str | None) -> str:
    wanted = _fmt(value)
    if wanted not in _ALLOWED_FORMATS:
        raise ValueError("format must resolve to EIGHT or NINE")
    return wanted


def _required_player_id(value: Any, label: str) -> int:
    """Require a canonical integer identity; bool must never alias player 0/1."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer canonical player identity")
    return value


def _perspective(game: dict[str, Any], player_id: int) -> tuple[int | None, str]:
    if game.get("participant_a_id") == player_id:
        return game.get("participant_b_id"), str(game.get("participant_a_result") or "").upper()
    if game.get("participant_b_id") == player_id:
        result = str(game.get("participant_a_result") or "").upper()
        return game.get("participant_a_id"), "L" if result == "W" else "W" if result == "L" else ""
    return None, ""


def _unsafe_keys(games: list[dict[str, Any]]) -> tuple[str | None, list[Any]]:
    """Return a fail-closed reason and attributable keys, if evidence is unsafe."""
    keys = [g.get("game_key") for g in games]
    normalized = [str(key or "").strip() for key in keys]
    if any(not key for key in normalized):
        return "MISSING_GAME_KEY", keys
    duplicate_keys = {key for key, count in Counter(normalized).items() if count > 1}
    if duplicate_keys:
        return "DUPLICATE_GAME_KEY", [key for key in keys if str(key).strip() in duplicate_keys]
    unverified = [g.get("game_key") for g in games if g.get("mirror_status") not in TRUSTED_MIRROR_STATUSES]
    if unverified:
        return "UNVERIFIED_GAME_EVIDENCE", unverified
    return None, []


def direct_evidence(all_games: list[dict[str, Any]], player_id: int, opponent_id: int, fmt: str) -> dict[str, Any]:
    """Return a traceable direct record, or fail closed on unsafe evidence."""
    wanted = _required_format(fmt)
    player_id = _required_player_id(player_id, "player_id")
    opponent_id = _required_player_id(opponent_id, "opponent_id")
    if player_id == opponent_id:
        raise ValueError("two distinct canonical player identities are required")

    candidates: list[dict[str, Any]] = []
    for game in all_games:
        other, result = _perspective(game, player_id)
        if other == opponent_id and _fmt(game.get("format")) == wanted and result in {"W", "L"}:
            candidates.append(game)

    reason, unsafe_keys = _unsafe_keys(candidates)
    if reason:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": reason,
            "format": wanted,
            "games": len(candidates),
            "game_keys": [g.get("game_key") for g in candidates],
            "unsafe_game_keys": unsafe_keys,
            "wins": None,
            "losses": None,
            "probability_publication": "FORBIDDEN",
        }

    wins = losses = 0
    for game in candidates:
        _, result = _perspective(game, player_id)
        wins += result == "W"
        losses += result == "L"
    return {
        "status": "VERIFIED" if candidates else "NO_RECORDED_HISTORY",
        "reason": None,
        "format": wanted,
        "games": len(candidates),
        "game_keys": [g.get("game_key") for g in candidates],
        "unsafe_game_keys": [],
        "wins": wins,
        "losses": losses,
        "probability_publication": "FORBIDDEN",
    }


def shared_opponent_evidence(all_games: list[dict[str, Any]], player_a_id: int, player_b_id: int, fmt: str) -> dict[str, Any]:
    """Return common-opponent factual records with exact source game keys.

    Any unsafe provenance used by either player's record against a common
    opponent makes that opponent's comparison unavailable rather than allowing
    uncertain evidence to leak into a coaching recommendation.
    """
    wanted = _required_format(fmt)
    player_a_id = _required_player_id(player_a_id, "player_a_id")
    player_b_id = _required_player_id(player_b_id, "player_b_id")
    if player_a_id == player_b_id:
        raise ValueError("two distinct canonical player identities are required")

    by_player: dict[int, dict[int, list[tuple[dict[str, Any], str]]]] = defaultdict(lambda: defaultdict(list))
    for game in all_games:
        if _fmt(game.get("format")) != wanted:
            continue
        for player_id in (player_a_id, player_b_id):
            other, result = _perspective(game, player_id)
            if other is not None and result in {"W", "L"}:
                by_player[player_id][other].append((game, result))

    common = sorted((set(by_player[player_a_id]) & set(by_player[player_b_id])) - {player_a_id, player_b_id})
    rows = []
    for opponent_id in common:
        a_rows = by_player[player_a_id][opponent_id]
        b_rows = by_player[player_b_id][opponent_id]
        evidence_games = [g for g, _ in a_rows + b_rows]
        reason, unsafe_keys = _unsafe_keys(evidence_games)
        if reason:
            rows.append({
                "opponent_id": opponent_id,
                "status": "INSUFFICIENT_EVIDENCE",
                "reason": reason,
                "player_a_record": None,
                "player_b_record": None,
                "player_a_game_keys": [g.get("game_key") for g, _ in a_rows],
                "player_b_game_keys": [g.get("game_key") for g, _ in b_rows],
                "unsafe_game_keys": unsafe_keys,
                "probability_publication": "FORBIDDEN",
            })
            continue
        rows.append({
            "opponent_id": opponent_id,
            "status": "VERIFIED",
            "reason": None,
            "player_a_record": {"wins": sum(r == "W" for _, r in a_rows), "losses": sum(r == "L" for _, r in a_rows)},
            "player_b_record": {"wins": sum(r == "W" for _, r in b_rows), "losses": sum(r == "L" for _, r in b_rows)},
            "player_a_game_keys": [g.get("game_key") for g, _ in a_rows],
            "player_b_game_keys": [g.get("game_key") for g, _ in b_rows],
            "unsafe_game_keys": [],
            "probability_publication": "FORBIDDEN",
        })
    return {
        "format": wanted,
        "shared_opponents": rows,
        "count": len(rows),
        "probability_publication": "FORBIDDEN",
    }
