"""Leakage-safe chronological examples for matchup model backtesting.

Each example represents one real individual player pairing in a finalized,
scored APA team match. Features are computed ONLY from matches that occurred
before the current team match. All individual pairings inside the same team
match are withheld together, so one lineup slot cannot leak into another slot
from the same night.

No model is fit here. This module only constructs auditable historical examples.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import groupby
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Match, PlayerHeadToHead


class BacktestDataError(RuntimeError):
    """Historical evidence cannot be made internally consistent without guessing."""


@dataclass(frozen=True)
class BacktestExample:
    match_id: int
    match_external_id: str
    match_date: str
    format: str
    session_name: str
    player_id: int
    opponent_id: int
    outcome_win: int
    own_skill_level: Optional[int]
    opponent_skill_level: Optional[int]
    skill_delta: Optional[int]
    direct_games_before: int
    direct_win_rate_before: Optional[float]
    player_games_before: int
    player_win_rate_before: Optional[float]
    opponent_games_before: int
    opponent_win_rate_before: Optional[float]
    player_recent5_win_rate: Optional[float]
    opponent_recent5_win_rate: Optional[float]
    shared_opponent_count_before: int
    player_shared_games_before: int
    player_shared_win_rate_before: Optional[float]
    opponent_shared_games_before: int
    opponent_shared_win_rate_before: Optional[float]


@dataclass(frozen=True)
class _Outcome:
    opponent_id: int
    won: bool


@dataclass(frozen=True)
class _CanonicalGame:
    player_id: int
    opponent_id: int
    won: bool
    own_skill_level: Optional[int]
    opponent_skill_level: Optional[int]
    format: str
    session_name: str


def _parse_match_datetime(value: str | None) -> Optional[datetime]:
    """Return a timezone-aware ISO timestamp, or None when chronology is unsafe.

    Live APA GraphQL startTime values are timezone-aware ISO-8601. Legacy
    scraped/text rows can use other shapes. Backtesting excludes those rather
    than guessing a timezone or relying on lexicographic string order.
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


def _format_name(value: str | None) -> Optional[str]:
    text = str(value or "").strip().upper()
    if text in {"EIGHT", "8-BALL", "EIGHT_BALL"} or "EIGHT" in text:
        return "EIGHT"
    if text in {"NINE", "9-BALL", "NINE_BALL"} or "NINE" in text:
        return "NINE"
    return None


def _result(value) -> Optional[bool]:
    text = str(value or "").strip().upper()
    if text == "W":
        return True
    if text == "L":
        return False
    return None


def _rate(outcomes: list[_Outcome]) -> Optional[float]:
    if not outcomes:
        return None
    return round(sum(1 for row in outcomes if row.won) / len(outcomes), 4)


def _canonical_games(rows: list[PlayerHeadToHead], match: Match) -> list[_CanonicalGame]:
    """One canonical orientation per unordered player pair in this team match."""
    grouped: dict[tuple[int, int], list[PlayerHeadToHead]] = {}
    for row in rows:
        if _result(row.result) is None:
            continue
        low, high = sorted((row.player_id, row.opponent_id))
        if low == high:
            continue
        grouped.setdefault((low, high), []).append(row)

    games: list[_CanonicalGame] = []
    for (low, high), pair_rows in sorted(grouped.items()):
        low_rows = [
            row for row in pair_rows
            if row.player_id == low and row.opponent_id == high and _result(row.result) is not None
        ]
        high_rows = [
            row for row in pair_rows
            if row.player_id == high and row.opponent_id == low and _result(row.result) is not None
        ]

        low_facts = {
            (_result(row.result), row.own_skill_level, row.opponent_skill_level)
            for row in low_rows
        }
        if len(low_facts) > 1:
            raise BacktestDataError(
                f"conflicting canonical outcomes for match {match.external_id}, pair {low}/{high}"
            )

        if low_rows:
            row = low_rows[0]
            won = bool(_result(row.result))
            own_sl = row.own_skill_level
            opp_sl = row.opponent_skill_level
            fmt = _format_name(row.format or match.format)
            session = row.session_name or match.session_name or ""
        elif high_rows:
            facts = {
                (_result(row.result), row.own_skill_level, row.opponent_skill_level)
                for row in high_rows
            }
            if len(facts) > 1:
                raise BacktestDataError(
                    f"conflicting reverse outcomes for match {match.external_id}, pair {low}/{high}"
                )
            row = high_rows[0]
            won = not bool(_result(row.result))
            own_sl = row.opponent_skill_level
            opp_sl = row.own_skill_level
            fmt = _format_name(row.format or match.format)
            session = row.session_name or match.session_name or ""
        else:
            continue

        if fmt is None:
            continue

        if low_rows and high_rows:
            low_result = _result(low_rows[0].result)
            high_result = _result(high_rows[0].result)
            if low_result is None or high_result is None or low_result == high_result:
                raise BacktestDataError(
                    f"paired directions disagree for match {match.external_id}, pair {low}/{high}"
                )

        games.append(
            _CanonicalGame(
                player_id=low,
                opponent_id=high,
                won=won,
                own_skill_level=own_sl,
                opponent_skill_level=opp_sl,
                format=fmt,
                session_name=session,
            )
        )
    return games


def _features(
    history: dict[tuple[int, str], list[_Outcome]],
    *,
    player_id: int,
    opponent_id: int,
    format_name: str,
) -> dict:
    player_history = history.get((player_id, format_name), [])
    opponent_history = history.get((opponent_id, format_name), [])
    direct = [row for row in player_history if row.opponent_id == opponent_id]

    player_by_opp: dict[int, list[_Outcome]] = {}
    opponent_by_opp: dict[int, list[_Outcome]] = {}
    for row in player_history:
        player_by_opp.setdefault(row.opponent_id, []).append(row)
    for row in opponent_history:
        opponent_by_opp.setdefault(row.opponent_id, []).append(row)

    shared_ids = (
        set(player_by_opp) & set(opponent_by_opp)
    ) - {player_id, opponent_id}
    player_shared = [
        row
        for shared_id in shared_ids
        for row in player_by_opp[shared_id]
    ]
    opponent_shared = [
        row
        for shared_id in shared_ids
        for row in opponent_by_opp[shared_id]
    ]

    return {
        "direct_games_before": len(direct),
        "direct_win_rate_before": _rate(direct),
        "player_games_before": len(player_history),
        "player_win_rate_before": _rate(player_history),
        "opponent_games_before": len(opponent_history),
        "opponent_win_rate_before": _rate(opponent_history),
        "player_recent5_win_rate": _rate(player_history[-5:]),
        "opponent_recent5_win_rate": _rate(opponent_history[-5:]),
        "shared_opponent_count_before": len(shared_ids),
        "player_shared_games_before": len(player_shared),
        "player_shared_win_rate_before": _rate(player_shared),
        "opponent_shared_games_before": len(opponent_shared),
        "opponent_shared_win_rate_before": _rate(opponent_shared),
    }


def build_backtest_examples(db: Session) -> list[BacktestExample]:
    """Build chronologically ordered examples from authoritative outcomes."""
    joined = (
        db.query(PlayerHeadToHead, Match)
        .join(Match, PlayerHeadToHead.match_id == Match.id)
        .filter(
            PlayerHeadToHead.result.in_(("W", "L")),
            Match.is_scored.is_(True),
            Match.is_finalized.is_(True),
            Match.is_bye.is_(False),
            Match.match_date.isnot(None),
        )
        .order_by(Match.match_date, Match.id, PlayerHeadToHead.id)
        .all()
    )

    by_match: dict[int, tuple[Match, list[PlayerHeadToHead]]] = {}
    for row, match in joined:
        bucket = by_match.setdefault(match.id, (match, []))
        bucket[1].append(row)

    dated_matches: list[tuple[datetime, Match, list[PlayerHeadToHead]]] = []
    for match, rows in by_match.values():
        when = _parse_match_datetime(match.match_date)
        if when is None:
            continue
        dated_matches.append((when, match, rows))
    dated_matches.sort(key=lambda item: (item[0], item[1].id))

    history: dict[tuple[int, str], list[_Outcome]] = {}
    examples: list[BacktestExample] = []

    # IMPORTANT: withhold every team match sharing the same real timestamp as
    # one batch. That is stricter than withholding just one team match and
    # prevents simultaneous/doubleheader rows from becoming future evidence
    # for another match at the same recorded time.
    for _, timestamp_group in groupby(dated_matches, key=lambda item: item[0]):
        batch = list(timestamp_group)
        batch_games: list[tuple[Match, list[_CanonicalGame]]] = [
            (match, _canonical_games(rows, match))
            for _, match, rows in batch
        ]

        for match, games in batch_games:
            for game in games:
                features = _features(
                    history,
                    player_id=game.player_id,
                    opponent_id=game.opponent_id,
                    format_name=game.format,
                )
                skill_delta = (
                    game.own_skill_level - game.opponent_skill_level
                    if game.own_skill_level is not None and game.opponent_skill_level is not None
                    else None
                )
                examples.append(
                    BacktestExample(
                        match_id=match.id,
                        match_external_id=match.external_id,
                        match_date=str(match.match_date),
                        format=game.format,
                        session_name=game.session_name,
                        player_id=game.player_id,
                        opponent_id=game.opponent_id,
                        outcome_win=1 if game.won else 0,
                        own_skill_level=game.own_skill_level,
                        opponent_skill_level=game.opponent_skill_level,
                        skill_delta=skill_delta,
                        **features,
                    )
                )

        for _, games in batch_games:
            for game in games:
                history.setdefault((game.player_id, game.format), []).append(
                    _Outcome(opponent_id=game.opponent_id, won=game.won)
                )
                history.setdefault((game.opponent_id, game.format), []).append(
                    _Outcome(opponent_id=game.player_id, won=not game.won)
                )

    return examples
