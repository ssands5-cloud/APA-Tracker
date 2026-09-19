"""Leakage-safe prequential feature snapshots for future Ultimate Coach backtests.

This module emits descriptive features only. For a target game, every feature
is derived exclusively from VERIFIED_UNIQUE games strictly earlier than that
game's timestamp and from the same APA format. It does not train a model,
score a matchup, or emit a probability.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

TRUSTED = frozenset({"VERIFIED_UNIQUE"})


def _fmt(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"EIGHT", "8", "8-BALL", "8 BALL", "EIGHT_BALL"}:
        return "EIGHT"
    if text in {"NINE", "9", "9-BALL", "9 BALL", "NINE_BALL"}:
        return "NINE"
    return text


def _time(value: Any) -> datetime | None:
    """Parse only offset-aware ISO timestamps.

    A naive timestamp cannot be placed safely on one global chronological
    axis beside offset-aware APA timestamps. Treating it as local or UTC would
    be an invented fact, so historical backtesting excludes it.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _participants(game: dict[str, Any]) -> tuple[int | None, int | None]:
    return game.get("participant_a_id"), game.get("participant_b_id")


def _result_for(game: dict[str, Any], player_id: int) -> int | None:
    if game.get("winner_id") == player_id:
        return 1
    if game.get("loser_id") == player_id:
        return 0
    return None


def _record(history: list[dict[str, Any]], player_id: int) -> tuple[int, int]:
    wins = losses = 0
    for game in history:
        result = _result_for(game, player_id)
        if result == 1:
            wins += 1
        elif result == 0:
            losses += 1
    return wins, losses


def _complete_target(game: dict[str, Any]) -> bool:
    a_id, b_id = _participants(game)
    winner = game.get("winner_id")
    loser = game.get("loser_id")
    return (
        a_id is not None
        and b_id is not None
        and a_id != b_id
        and winner in {a_id, b_id}
        and loser in {a_id, b_id}
        and winner != loser
    )


def build_prequential_feature_rows(
    all_games: list[dict[str, Any]], fmt: str
) -> dict[str, Any]:
    """Return one auditable pre-game feature row per trusted target game.

    Same-timestamp games cannot see one another: the history boundary is
    strictly ``prior_time < target_time``. Duplicate or blank game keys,
    timezone-naive timestamps, self-pairings and inconsistent outcomes all
    fail closed instead of being repaired or ordered heuristically.
    """
    wanted = _fmt(fmt)
    if wanted not in {"EIGHT", "NINE"}:
        raise ValueError("format must resolve to EIGHT or NINE")

    scoped = [game for game in all_games if _fmt(game.get("format")) == wanted]
    key_counts = Counter(str(game.get("game_key") or "").strip() for game in scoped)

    eligible: list[tuple[datetime, dict[str, Any]]] = []
    excluded = defaultdict(int)
    for game in scoped:
        key = str(game.get("game_key") or "").strip()
        if not key:
            excluded["MISSING_GAME_KEY"] += 1
            continue
        if key_counts[key] > 1:
            excluded["DUPLICATE_GAME_KEY"] += 1
            continue
        if game.get("mirror_status") not in TRUSTED:
            excluded["UNVERIFIED_EVIDENCE"] += 1
            continue
        when = _time(game.get("match_date"))
        if when is None:
            excluded["MISSING_INVALID_OR_NAIVE_TIME"] += 1
            continue
        if not _complete_target(game):
            excluded["INCOMPLETE_OR_INCONSISTENT_TARGET"] += 1
            continue
        eligible.append((when, game))

    eligible.sort(key=lambda item: (item[0], str(item[1]["game_key"])))
    rows: list[dict[str, Any]] = []

    for target_time, target in eligible:
        a_id, b_id = _participants(target)
        prior = [game for when, game in eligible if when < target_time]
        a_history = [g for g in prior if a_id in _participants(g)]
        b_history = [g for g in prior if b_id in _participants(g)]
        direct = [g for g in prior if set(_participants(g)) == {a_id, b_id}]
        a_wins, a_losses = _record(a_history, a_id)
        b_wins, b_losses = _record(b_history, b_id)
        direct_a_wins, direct_a_losses = _record(direct, a_id)

        a_opponents = {
            other for g in a_history for other in _participants(g)
            if other is not None and other != a_id
        }
        b_opponents = {
            other for g in b_history for other in _participants(g)
            if other is not None and other != b_id
        }
        shared = sorted(a_opponents & b_opponents)

        rows.append({
            "target_game_key": target["game_key"],
            "target_time": target_time.isoformat(),
            "format": wanted,
            "participant_a_id": a_id,
            "participant_b_id": b_id,
            "observed_winner_id": target.get("winner_id"),
            "probability_publication": "FORBIDDEN",
            "history_cutoff_rule": "STRICTLY_BEFORE_TARGET_TIME",
            "participant_a_prior_games": len(a_history),
            "participant_a_prior_wins": a_wins,
            "participant_a_prior_losses": a_losses,
            "participant_b_prior_games": len(b_history),
            "participant_b_prior_wins": b_wins,
            "participant_b_prior_losses": b_losses,
            "direct_prior_games": len(direct),
            "direct_a_prior_wins": direct_a_wins,
            "direct_a_prior_losses": direct_a_losses,
            "shared_opponent_count": len(shared),
            "shared_opponent_ids": shared,
            "prior_game_keys": [g["game_key"] for g in prior],
            "direct_prior_game_keys": [g["game_key"] for g in direct],
        })

    return {
        "schema": "ultimate-coach-prequential-features-v2",
        "format": wanted,
        "probability_publication": "FORBIDDEN",
        "feature_rows": rows,
        "excluded": dict(sorted(excluded.items())),
    }
