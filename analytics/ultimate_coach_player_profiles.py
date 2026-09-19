"""Offline all-player factual profiles for Ultimate Coach.

Profiles are built only from the preserved canonical All Games contract.
They are descriptive, format-isolated, provenance-bearing, and optionally
historical as-of snapshots. No model, probability, confidence score, or live
APA access is involved here.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

TRUSTED_MIRROR_STATUSES = frozenset({"VERIFIED_UNIQUE"})
_ALLOWED_FORMATS = frozenset({"EIGHT", "NINE"})
_ALLOWED_IDENTITY_STATUSES = frozenset({"VERIFIED_UNIQUE"})


def _fmt(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"EIGHT", "8", "8-BALL", "8 BALL", "EIGHT_BALL"}:
        return "EIGHT"
    if text in {"NINE", "9", "9-BALL", "9 BALL", "NINE_BALL"}:
        return "NINE"
    return text


def _required_format(value: Any) -> str:
    wanted = _fmt(value)
    if wanted not in _ALLOWED_FORMATS:
        raise ValueError("format must resolve to EIGHT or NINE")
    return wanted


def _aware_time(value: Any, *, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{label} must be an offset-aware ISO timestamp")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{label} must be an offset-aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be an offset-aware ISO timestamp")
    return parsed


def _optional_event_time(value: Any) -> datetime | None:
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


def _canonical_identity(identity: dict[str, Any], label: str = "player") -> tuple[int, str | None]:
    if not isinstance(identity, dict):
        raise ValueError(f"{label} identity must be a mapping")
    status = str(identity.get("status") or "").strip().upper()
    player_id = identity.get("player_id")
    if status not in _ALLOWED_IDENTITY_STATUSES:
        raise ValueError(f"{label} identity must be VERIFIED_UNIQUE")
    if not isinstance(player_id, int) or isinstance(player_id, bool):
        raise ValueError(f"{label} player_id must be an integer canonical player identity")
    name = identity.get("player_name")
    if name is not None:
        name = str(name)
    return player_id, name


def _participants(game: dict[str, Any]) -> tuple[Any, Any]:
    return game.get("participant_a_id"), game.get("participant_b_id")


def _canonical_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _perspective(game: dict[str, Any], player_id: int) -> dict[str, Any] | None:
    a_id, b_id = _participants(game)
    if a_id == player_id:
        result = str(game.get("participant_a_result") or "").strip().upper()
        return {
            "opponent_id": b_id,
            "result": result,
            "own_skill_level": game.get("participant_a_skill_level"),
            "opponent_skill_level": game.get("participant_b_skill_level"),
        }
    if b_id == player_id:
        a_result = str(game.get("participant_a_result") or "").strip().upper()
        result = "L" if a_result == "W" else "W" if a_result == "L" else ""
        return {
            "opponent_id": a_id,
            "result": result,
            "own_skill_level": game.get("participant_b_skill_level"),
            "opponent_skill_level": game.get("participant_a_skill_level"),
        }
    return None


def _outcome_consistent(game: dict[str, Any]) -> bool:
    a_id, b_id = _participants(game)
    if not _canonical_int(a_id) or not _canonical_int(b_id) or a_id == b_id:
        return False
    winner = game.get("winner_id")
    loser = game.get("loser_id")
    if winner not in {a_id, b_id} or loser not in {a_id, b_id} or winner == loser:
        return False
    a_result = str(game.get("participant_a_result") or "").strip().upper()
    expected_a = "W" if winner == a_id else "L"
    return a_result == expected_a


def _exclude(
    counts: defaultdict[str, int],
    keys: defaultdict[str, list[Any]],
    reason: str,
    game_key: Any,
) -> None:
    counts[reason] += 1
    keys[reason].append(game_key)


def build_player_profile(
    all_games: list[dict[str, Any]],
    identity: dict[str, Any],
    fmt: str,
    *,
    as_of: str | datetime | None = None,
) -> dict[str, Any]:
    """Build one verified factual player profile.

    Historical snapshots use a strict event_time < as_of boundary so games
    occurring at the same instant as the boundary cannot leak into the profile.
    Candidate rows with unsafe provenance are quarantined and reported instead
    of being silently repaired or zero-filled.
    """
    player_id, player_name = _canonical_identity(identity)
    wanted = _required_format(fmt)
    boundary = _aware_time(as_of, label="as_of") if as_of is not None else None

    scoped = [game for game in all_games if _fmt(game.get("format")) == wanted]
    key_counts = Counter(str(game.get("game_key") or "").strip() for game in scoped)

    candidates = [game for game in scoped if player_id in _participants(game)]
    verified: list[tuple[datetime, str, dict[str, Any], dict[str, Any]]] = []
    excluded_counts: defaultdict[str, int] = defaultdict(int)
    excluded_keys: defaultdict[str, list[Any]] = defaultdict(list)
    outside_as_of = 0

    for game in candidates:
        raw_key = game.get("game_key")
        key = str(raw_key or "").strip()
        if not key:
            _exclude(excluded_counts, excluded_keys, "MISSING_GAME_KEY", raw_key)
            continue
        if key_counts[key] > 1:
            _exclude(excluded_counts, excluded_keys, "DUPLICATE_GAME_KEY", raw_key)
            continue
        if game.get("mirror_status") not in TRUSTED_MIRROR_STATUSES:
            _exclude(excluded_counts, excluded_keys, "UNVERIFIED_GAME_EVIDENCE", raw_key)
            continue

        when = _optional_event_time(game.get("match_date"))
        if when is None:
            _exclude(excluded_counts, excluded_keys, "MISSING_INVALID_OR_NAIVE_TIME", raw_key)
            continue
        if boundary is not None and not (when < boundary):
            outside_as_of += 1
            continue

        perspective = _perspective(game, player_id)
        if perspective is None:
            _exclude(excluded_counts, excluded_keys, "PLAYER_NOT_IN_GAME", raw_key)
            continue
        opponent_id = perspective["opponent_id"]
        if not _canonical_int(opponent_id) or opponent_id == player_id:
            _exclude(excluded_counts, excluded_keys, "INVALID_OPPONENT_IDENTITY", raw_key)
            continue
        if perspective["result"] not in {"W", "L"} or not _outcome_consistent(game):
            _exclude(excluded_counts, excluded_keys, "INCOMPLETE_OR_INCONSISTENT_OUTCOME", raw_key)
            continue

        verified.append((when, key, game, perspective))

    verified.sort(key=lambda item: (item[0], item[1]))

    wins = sum(perspective["result"] == "W" for _, _, _, perspective in verified)
    losses = sum(perspective["result"] == "L" for _, _, _, perspective in verified)

    opponent_rows: dict[int, list[tuple[datetime, str, dict[str, Any]]]] = defaultdict(list)
    skill_history = []
    for when, key, game, perspective in verified:
        opponent_id = int(perspective["opponent_id"])
        opponent_rows[opponent_id].append((when, key, perspective))
        skill_history.append(
            {
                "game_key": key,
                "event_time": when.isoformat(),
                "opponent_id": opponent_id,
                "skill_level": perspective["own_skill_level"],
                "opponent_skill_level": perspective["opponent_skill_level"],
                "result": perspective["result"],
            }
        )

    opponent_history = []
    for opponent_id in sorted(opponent_rows):
        rows = opponent_rows[opponent_id]
        opponent_history.append(
            {
                "opponent_id": opponent_id,
                "evidence_type": "DIRECT_OBSERVED",
                "games": len(rows),
                "wins": sum(p["result"] == "W" for _, _, p in rows),
                "losses": sum(p["result"] == "L" for _, _, p in rows),
                "first_event_time": rows[0][0].isoformat(),
                "last_event_time": rows[-1][0].isoformat(),
                "game_keys": [key for _, key, _ in rows],
            }
        )

    excluded_total = sum(excluded_counts.values())
    if verified and excluded_total:
        evidence_status = "PARTIAL"
    elif verified:
        evidence_status = "VERIFIED"
    elif candidates and excluded_total:
        evidence_status = "INSUFFICIENT_EVIDENCE"
    else:
        evidence_status = "NO_RECORDED_EVIDENCE"

    source_keys = [key for _, key, _, _ in verified]
    observed_record = {
        "games": len(verified),
        "wins": wins if verified else None,
        "losses": losses if verified else None,
        "first_event_time": verified[0][0].isoformat() if verified else None,
        "last_event_time": verified[-1][0].isoformat() if verified else None,
        "game_keys": source_keys,
    }

    return {
        "schema": "ultimate-coach-player-profile-v1",
        "player_id": player_id,
        "player_name": player_name,
        "identity_status": "VERIFIED_UNIQUE",
        "format": wanted,
        "as_of": boundary.isoformat() if boundary is not None else None,
        "history_boundary_rule": (
            "STRICTLY_BEFORE_AS_OF" if boundary is not None else "ALL_VERIFIED_ARCHIVE_EVIDENCE"
        ),
        "evidence_status": evidence_status,
        "verified_observed_record": observed_record,
        "skill_level_history": skill_history,
        "opponent_history": opponent_history,
        "source_game_keys": source_keys,
        "excluded_candidate_count": excluded_total,
        "exclusions": {
            "counts": dict(sorted(excluded_counts.items())),
            "game_keys_by_reason": {
                reason: values for reason, values in sorted(excluded_keys.items())
            },
        },
        "outside_as_of_count": outside_as_of,
        "matchup_probability": None,
        "predictive_confidence": None,
        "probability_publication": "FORBIDDEN",
        "requires_live_apa_login": False,
    }


def build_all_player_profiles(
    all_games: list[dict[str, Any]],
    identities: list[dict[str, Any]],
    fmt: str,
    *,
    as_of: str | datetime | None = None,
) -> dict[str, Any]:
    """Build profiles only for verified-unique, non-duplicated identities.

    Invalid, ambiguous, unresolved, or duplicate identity declarations are
    omitted from the profile set and surfaced explicitly.
    """
    wanted = _required_format(fmt)
    boundary = _aware_time(as_of, label="as_of") if as_of is not None else None

    canonical_records: list[tuple[int, str | None, dict[str, Any]]] = []
    identity_exclusions: list[dict[str, Any]] = []

    for index, identity in enumerate(identities):
        try:
            player_id, player_name = _canonical_identity(identity, f"identity[{index}]")
        except ValueError as exc:
            identity_exclusions.append(
                {
                    "index": index,
                    "player_id": identity.get("player_id") if isinstance(identity, dict) else None,
                    "reason": str(exc),
                }
            )
            continue
        canonical_records.append((player_id, player_name, identity))

    id_counts = Counter(player_id for player_id, _, _ in canonical_records)
    profiles = []
    for player_id, player_name, identity in sorted(canonical_records, key=lambda row: row[0]):
        if id_counts[player_id] > 1:
            continue
        normalized_identity = {
            "player_id": player_id,
            "player_name": player_name,
            "status": "VERIFIED_UNIQUE",
        }
        profiles.append(
            build_player_profile(
                all_games,
                normalized_identity,
                wanted,
                as_of=boundary,
            )
        )

    for player_id in sorted(pid for pid, count in id_counts.items() if count > 1):
        identity_exclusions.append(
            {
                "player_id": player_id,
                "reason": "duplicate VERIFIED_UNIQUE identity declarations",
            }
        )

    profiles.sort(key=lambda row: row["player_id"])
    identity_exclusions.sort(key=lambda row: (str(row.get("player_id")), str(row.get("reason"))))

    return {
        "schema": "ultimate-coach-all-player-profiles-v1",
        "format": wanted,
        "as_of": boundary.isoformat() if boundary is not None else None,
        "profiles": profiles,
        "profile_count": len(profiles),
        "identity_exclusions": identity_exclusions,
        "identity_exclusion_count": len(identity_exclusions),
        "matchup_probability": None,
        "predictive_confidence": None,
        "probability_publication": "FORBIDDEN",
        "requires_live_apa_login": False,
    }
