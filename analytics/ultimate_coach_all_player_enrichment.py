"""Offline all-player descriptive enrichment for Ultimate Coach.

Only actual, verified archive games are summarized. This module never imputes
history, mixes APA formats, trains a model, or publishes matchup probability.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping

TRUSTED = frozenset({"VERIFIED_UNIQUE"})
_ALLOWED = frozenset({"EIGHT", "NINE"})


def _fmt(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"EIGHT", "8", "8-BALL", "8 BALL", "EIGHT_BALL"}:
        return "EIGHT"
    if text in {"NINE", "9", "9-BALL", "9 BALL", "NINE_BALL"}:
        return "NINE"
    return text


def _aware_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _canonical_id(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _valid_outcome(game: Mapping[str, Any], a_id: int, b_id: int) -> bool:
    winner, loser = game.get("winner_id"), game.get("loser_id")
    return winner in {a_id, b_id} and loser in {a_id, b_id} and winner != loser


def build_all_player_enrichment(
    all_games: list[dict[str, Any]],
    identity_status: Mapping[int, str],
    fmt: str,
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Build deterministic factual profiles from verified historical evidence.

    ``as_of`` is an exclusive UTC-normalized boundary. Games at exactly that
    instant are excluded, so simultaneous matches cannot leak into one another.
    Identity ambiguity fails closed: only integer IDs explicitly marked
    VERIFIED_UNIQUE are eligible for profiles or evidence.
    """
    wanted = _fmt(fmt)
    if wanted not in _ALLOWED:
        raise ValueError("format must resolve to EIGHT or NINE")
    cutoff = _aware_time(as_of) if as_of is not None else None
    if as_of is not None and cutoff is None:
        raise ValueError("as_of must be an offset-aware ISO timestamp")

    verified_ids = {
        player_id for player_id, status in identity_status.items()
        if _canonical_id(player_id) is not None and status in TRUSTED
    }
    scoped = [g for g in all_games if _fmt(g.get("format")) == wanted]
    key_counts = Counter(str(g.get("game_key") or "").strip() for g in scoped)
    excluded: dict[str, int] = defaultdict(int)
    accepted: list[tuple[datetime, dict[str, Any], int, int]] = []

    for game in scoped:
        key = str(game.get("game_key") or "").strip()
        if not key:
            excluded["MISSING_GAME_KEY"] += 1
            continue
        if key_counts[key] > 1:
            excluded["DUPLICATE_GAME_KEY"] += 1
            continue
        if game.get("mirror_status") not in TRUSTED:
            excluded["UNVERIFIED_GAME_EVIDENCE"] += 1
            continue
        when = _aware_time(game.get("match_date"))
        if when is None:
            excluded["MISSING_INVALID_OR_NAIVE_TIME"] += 1
            continue
        if cutoff is not None and when >= cutoff:
            excluded["AT_OR_AFTER_AS_OF"] += 1
            continue
        a_id = _canonical_id(game.get("participant_a_id"))
        b_id = _canonical_id(game.get("participant_b_id"))
        if a_id is None or b_id is None or a_id == b_id:
            excluded["INVALID_PARTICIPANT_IDENTITY"] += 1
            continue
        if a_id not in verified_ids or b_id not in verified_ids:
            excluded["AMBIGUOUS_OR_UNVERIFIED_IDENTITY"] += 1
            continue
        if not _valid_outcome(game, a_id, b_id):
            excluded["INCONSISTENT_OUTCOME"] += 1
            continue
        accepted.append((when, game, a_id, b_id))

    accepted.sort(key=lambda row: (row[0], str(row[1]["game_key"])))
    profiles = []
    for player_id in sorted(verified_ids):
        rows = [(when, game, a, b) for when, game, a, b in accepted if player_id in {a, b}]
        wins = sum(game.get("winner_id") == player_id for _, game, _, _ in rows)
        losses = sum(game.get("loser_id") == player_id for _, game, _, _ in rows)
        opponents = sorted({b if a == player_id else a for _, _, a, b in rows})
        profiles.append({
            "player_id": player_id,
            "identity_status": "VERIFIED_UNIQUE",
            "format": wanted,
            "history_status": "VERIFIED" if rows else "NO_RECORDED_HISTORY",
            "games": len(rows),
            "wins": wins if rows else None,
            "losses": losses if rows else None,
            "opponent_ids": opponents,
            "game_keys": [game["game_key"] for _, game, _, _ in rows],
            "first_match_time": rows[0][0].isoformat() if rows else None,
            "last_match_time": rows[-1][0].isoformat() if rows else None,
            "matchup_probability": None,
            "predictive_confidence": None,
            "probability_publication": "FORBIDDEN",
        })

    return {
        "schema": "ultimate-coach-all-player-enrichment-v1",
        "format": wanted,
        "as_of_exclusive": cutoff.isoformat() if cutoff else None,
        "profiles": profiles,
        "accepted_game_keys": [game["game_key"] for _, game, _, _ in accepted],
        "excluded": dict(sorted(excluded.items())),
        "matchup_probability": None,
        "predictive_confidence": None,
        "probability_publication": "FORBIDDEN",
    }
