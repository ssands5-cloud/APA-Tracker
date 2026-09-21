"""Transparent scouting evidence built only from recorded APA outcomes.

This module is intentionally pre-model. It answers:
- have these two players actually played each other?
- which opponents have they both played?
- what were each player's real W/L results against those shared opponents?
- what skill levels were actually recorded in those games?

It does not emit a win probability. That belongs to a separately back-tested
and calibrated model built on top of this evidence layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Player, PlayerHeadToHead


@dataclass(frozen=True)
class ObservedRecord:
    wins: int
    losses: int
    games: int
    win_rate: Optional[float]
    avg_own_skill_level: Optional[float]
    avg_opponent_skill_level: Optional[float]


@dataclass(frozen=True)
class SharedOpponentEvidence:
    opponent_id: int
    opponent_external_id: str
    opponent_name: str
    player_record: ObservedRecord
    comparison_record: ObservedRecord


@dataclass(frozen=True)
class ScoutingEvidence:
    player_id: int
    player_external_id: str
    player_name: str
    comparison_player_id: int
    comparison_external_id: str
    comparison_name: str
    format: str
    direct_record: ObservedRecord
    shared_opponents: tuple[SharedOpponentEvidence, ...]
    shared_opponent_count: int
    player_shared_record: ObservedRecord
    comparison_shared_record: ObservedRecord
    probability_status: str = "NOT_CALIBRATED"


def _recognized_rows(rows: list[PlayerHeadToHead]) -> list[PlayerHeadToHead]:
    return [row for row in rows if str(row.result or "").strip().upper() in {"W", "L"}]


def observed_record(rows: list[PlayerHeadToHead]) -> ObservedRecord:
    recognized = _recognized_rows(rows)
    wins = sum(1 for row in recognized if str(row.result).strip().upper() == "W")
    losses = len(recognized) - wins
    own_levels = [row.own_skill_level for row in recognized if row.own_skill_level is not None]
    opponent_levels = [
        row.opponent_skill_level
        for row in recognized
        if row.opponent_skill_level is not None
    ]
    return ObservedRecord(
        wins=wins,
        losses=losses,
        games=len(recognized),
        win_rate=round(wins / len(recognized), 3) if recognized else None,
        avg_own_skill_level=(
            round(sum(own_levels) / len(own_levels), 2) if own_levels else None
        ),
        avg_opponent_skill_level=(
            round(sum(opponent_levels) / len(opponent_levels), 2)
            if opponent_levels
            else None
        ),
    )


def _rows_for_player(db: Session, player_id: int, format_name: str) -> list[PlayerHeadToHead]:
    return (
        db.query(PlayerHeadToHead)
        .filter(
            PlayerHeadToHead.player_id == player_id,
            PlayerHeadToHead.format == format_name,
            PlayerHeadToHead.result.in_(("W", "L")),
        )
        .order_by(PlayerHeadToHead.match_id, PlayerHeadToHead.id)
        .all()
    )


def _group_by_opponent(
    rows: list[PlayerHeadToHead],
) -> dict[int, list[PlayerHeadToHead]]:
    grouped: dict[int, list[PlayerHeadToHead]] = {}
    for row in rows:
        grouped.setdefault(row.opponent_id, []).append(row)
    return grouped


def build_scouting_evidence(
    db: Session,
    *,
    player_id: int,
    comparison_player_id: int,
    format_name: str,
) -> ScoutingEvidence:
    """Build career-to-date evidence for one exact format.

    Session boundaries are deliberately pooled here because this is a career
    scouting view, not a current-session lineup classifier. Each underlying
    row keeps its real match/session provenance in the database for future
    recency modeling.
    """
    format_name = str(format_name or "").strip().upper()
    if format_name not in {"EIGHT", "NINE"}:
        raise ValueError("format_name must be EIGHT or NINE")
    if player_id == comparison_player_id:
        raise ValueError("a player cannot be compared with themself")

    player = db.get(Player, player_id)
    comparison = db.get(Player, comparison_player_id)
    if player is None or comparison is None:
        raise ValueError("both player ids must resolve to canonical Player rows")

    player_rows = _rows_for_player(db, player_id, format_name)
    comparison_rows = _rows_for_player(db, comparison_player_id, format_name)
    by_player_opponent = _group_by_opponent(player_rows)
    by_comparison_opponent = _group_by_opponent(comparison_rows)

    direct = observed_record(by_player_opponent.get(comparison_player_id, []))

    shared_ids = sorted(
        (
            set(by_player_opponent)
            & set(by_comparison_opponent)
        )
        - {player_id, comparison_player_id}
    )

    shared: list[SharedOpponentEvidence] = []
    player_shared_rows: list[PlayerHeadToHead] = []
    comparison_shared_rows: list[PlayerHeadToHead] = []

    for shared_id in shared_ids:
        shared_player = db.get(Player, shared_id)
        if shared_player is None:
            continue
        left_rows = by_player_opponent[shared_id]
        right_rows = by_comparison_opponent[shared_id]
        player_shared_rows.extend(left_rows)
        comparison_shared_rows.extend(right_rows)
        shared.append(
            SharedOpponentEvidence(
                opponent_id=shared_id,
                opponent_external_id=shared_player.external_id,
                opponent_name=shared_player.name,
                player_record=observed_record(left_rows),
                comparison_record=observed_record(right_rows),
            )
        )

    return ScoutingEvidence(
        player_id=player.id,
        player_external_id=player.external_id,
        player_name=player.name,
        comparison_player_id=comparison.id,
        comparison_external_id=comparison.external_id,
        comparison_name=comparison.name,
        format=format_name,
        direct_record=direct,
        shared_opponents=tuple(shared),
        shared_opponent_count=len(shared),
        player_shared_record=observed_record(player_shared_rows),
        comparison_shared_record=observed_record(comparison_shared_rows),
    )
