"""Evidence-quality gates for Ultimate Coach factual matchup summaries.

This module never creates predictions. It grades whether recorded evidence is
safe enough to summarize and exposes exact All Games keys for traceability.
Ambiguous or unreconciled evidence fails closed.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

TRUSTED_MIRROR_STATUSES = frozenset({"VERIFIED_UNIQUE"})


def _fmt(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if text in {"EIGHT", "8", "8-BALL", "8 BALL", "EIGHT_BALL"}:
        return "EIGHT"
    if text in {"NINE", "9", "9-BALL", "9 BALL", "NINE_BALL"}:
        return "NINE"
    return text


def _perspective(game: dict[str, Any], player_id: int) -> tuple[int | None, str]:
    if game.get("participant_a_id") == player_id:
        return game.get("participant_b_id"), str(game.get("participant_a_result") or "").upper()
    if game.get("participant_b_id") == player_id:
        result = str(game.get("participant_a_result") or "").upper()
        return game.get("participant_a_id"), "L" if result == "W" else "W" if result == "L" else ""
    return None, ""


def direct_evidence(all_games: list[dict[str, Any]], player_id: int, opponent_id: int, fmt: str) -> dict[str, Any]:
    """Return a traceable direct record, or fail closed on unsafe evidence."""
    wanted = _fmt(fmt)
    candidates: list[dict[str, Any]] = []
    for game in all_games:
        other, result = _perspective(game, player_id)
        if other == opponent_id and _fmt(game.get("format")) == wanted and result in {"W", "L"}:
            candidates.append(game)

    unsafe = [g for g in candidates if g.get("mirror_status") not in TRUSTED_MIRROR_STATUSES]
    if unsafe:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "UNVERIFIED_GAME_EVIDENCE",
            "format": wanted,
            "games": len(candidates),
            "game_keys": [g.get("game_key") for g in candidates],
            "unsafe_game_keys": [g.get("game_key") for g in unsafe],
            "wins": None,
            "losses": None,
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
    }


def shared_opponent_evidence(all_games: list[dict[str, Any]], player_a_id: int, player_b_id: int, fmt: str) -> dict[str, Any]:
    """Return common-opponent factual records with exact source game keys.

    Any unverified game used by either player's record against a common
    opponent makes that opponent's comparison unavailable rather than allowing
    uncertain evidence to leak into a coaching recommendation.
    """
    wanted = _fmt(fmt)
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
        unsafe = [g for g, _ in a_rows + b_rows if g.get("mirror_status") not in TRUSTED_MIRROR_STATUSES]
        if unsafe:
            rows.append({
                "opponent_id": opponent_id,
                "status": "INSUFFICIENT_EVIDENCE",
                "reason": "UNVERIFIED_GAME_EVIDENCE",
                "player_a_record": None,
                "player_b_record": None,
                "player_a_game_keys": [g.get("game_key") for g, _ in a_rows],
                "player_b_game_keys": [g.get("game_key") for g, _ in b_rows],
                "unsafe_game_keys": [g.get("game_key") for g in unsafe],
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
        })
    return {"format": wanted, "shared_opponents": rows, "count": len(rows)}
