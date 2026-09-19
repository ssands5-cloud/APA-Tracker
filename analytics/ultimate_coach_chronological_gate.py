"""Leakage-safe chronological archive readiness gate for Ultimate Coach.

This module does not train a model and does not emit matchup odds. It answers
whether verified real-game archive rows are structurally ready for a future
chronological backtest. Splits are time-ordered and format-isolated.
"""

from __future__ import annotations

from collections import Counter
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
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def chronological_archive_gate(
    all_games: list[dict[str, Any]],
    fmt: str,
    *,
    holdout_fraction: float = 0.20,
    min_verified_games: int = 100,
    min_holdout_games: int = 20,
) -> dict[str, Any]:
    """Build a deterministic train/holdout boundary from verified real games.

    No random split is allowed. Any row with ambiguous mirror evidence,
    missing/unparseable time, wrong format, or unknown outcome is excluded with
    an explicit reason. The gate is readiness evidence only, never permission
    to publish probabilities.
    """
    wanted = _fmt(fmt)
    if wanted not in {"EIGHT", "NINE"}:
        raise ValueError("format must resolve to EIGHT or NINE")
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")

    accepted: list[tuple[datetime, dict[str, Any]]] = []
    excluded = Counter()
    for game in all_games:
        if _fmt(game.get("format")) != wanted:
            continue
        if game.get("mirror_status") not in TRUSTED:
            excluded["UNVERIFIED_EVIDENCE"] += 1
            continue
        when = _time(game.get("match_date"))
        if when is None:
            excluded["MISSING_OR_INVALID_TIME"] += 1
            continue
        if game.get("winner_id") is None or game.get("loser_id") is None:
            excluded["UNKNOWN_OUTCOME"] += 1
            continue
        accepted.append((when, game))

    accepted.sort(key=lambda item: (item[0], str(item[1].get("game_key") or "")))
    total = len(accepted)
    holdout_count = max(1, int(total * holdout_fraction)) if total else 0
    split_at = total - holdout_count
    train = accepted[:split_at]
    holdout = accepted[split_at:]

    chronology_ok = bool(train and holdout and train[-1][0] <= holdout[0][0])
    reasons: list[str] = []
    if total < min_verified_games:
        reasons.append("INSUFFICIENT_VERIFIED_GAMES")
    if len(holdout) < min_holdout_games:
        reasons.append("INSUFFICIENT_HOLDOUT_GAMES")
    if not chronology_ok:
        reasons.append("CHRONOLOGICAL_SPLIT_UNAVAILABLE")

    status = "READY_FOR_BACKTEST" if not reasons else "NOT_READY"
    return {
        "status": status,
        "format": wanted,
        "probability_publication": "FORBIDDEN",
        "verified_games": total,
        "train_games": len(train),
        "holdout_games": len(holdout),
        "train_game_keys": [g.get("game_key") for _, g in train],
        "holdout_game_keys": [g.get("game_key") for _, g in holdout],
        "train_end": train[-1][0].isoformat() if train else None,
        "holdout_start": holdout[0][0].isoformat() if holdout else None,
        "chronology_ok": chronology_ok,
        "excluded": dict(sorted(excluded.items())),
        "reasons": reasons,
    }
