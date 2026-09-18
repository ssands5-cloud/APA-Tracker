"""Canonical Ultimate Coach data contract shared by Excel, HTML and analytics.

SQLite remains the source of truth. This module projects that relational data
into flat, auditable datasets suitable for an offline workbook or cockpit.

Key rule: never hide source ambiguity. Raw H2H evidence is preserved verbatim
(as normalized columns), while All Games emits one player-pair row per observed
individual game and carries a mirror verification status.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy.orm import Session

from database.models import (
    Match,
    Player,
    PlayerHeadToHead,
    PlayerLeagueCareerStats,
    PlayerMatch,
    PlayerTeamHistory,
)


def normalize_format(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if "EIGHT" in text or text in {"8", "8-BALL", "8 BALL", "EIGHT_BALL"}:
        return "EIGHT"
    if "NINE" in text or text in {"9", "9-BALL", "9 BALL", "NINE_BALL"}:
        return "NINE"
    return text


def _result(value: str | None) -> str:
    text = str(value or "").strip().upper()
    return text if text in {"W", "L"} else ""


def _opposite(result: str) -> str:
    return "L" if result == "W" else "W" if result == "L" else ""


def _player_match_index(rows: list[PlayerMatch]) -> tuple[dict[tuple[int, int], PlayerMatch], list[dict[str, Any]]]:
    grouped: dict[tuple[int, int], list[PlayerMatch]] = defaultdict(list)
    for row in rows:
        if row.match_id is not None:
            grouped[(row.match_id, row.player_id)].append(row)

    index: dict[tuple[int, int], PlayerMatch] = {}
    issues: list[dict[str, Any]] = []
    for key, values in grouped.items():
        if len(values) == 1:
            index[key] = values[0]
        else:
            issues.append(
                {
                    "category": "PLAYER_MATCH_AMBIGUITY",
                    "match_id": key[0],
                    "player_id": key[1],
                    "detail": f"{len(values)} PlayerMatch rows exist for one player/match scope",
                }
            )
    return index, issues


def _normalized_low_signature(row: PlayerHeadToHead, match: Match, *, reverse: bool) -> tuple[Any, ...]:
    fmt = normalize_format(row.format or match.format)
    session = row.session_name or match.session_name or ""
    result = _result(row.result)
    if reverse:
        return (
            _opposite(result),
            row.opponent_skill_level,
            row.own_skill_level,
            fmt,
            session,
        )
    return (
        result,
        row.own_skill_level,
        row.opponent_skill_level,
        fmt,
        session,
    )


def build_contract(db: Session) -> dict[str, Any]:
    players = db.query(Player).order_by(Player.name, Player.id).all()
    matches = db.query(Match).order_by(Match.match_date, Match.id).all()
    player_matches = (
        db.query(PlayerMatch)
        .filter(PlayerMatch.match_id.isnot(None))
        .order_by(PlayerMatch.match_id, PlayerMatch.player_id, PlayerMatch.id)
        .all()
    )
    h2h_rows = (
        db.query(PlayerHeadToHead)
        .join(Match, PlayerHeadToHead.match_id == Match.id)
        .order_by(Match.match_date, Match.id, PlayerHeadToHead.id)
        .all()
    )
    career_rows = (
        db.query(PlayerLeagueCareerStats)
        .order_by(
            PlayerLeagueCareerStats.player_id,
            PlayerLeagueCareerStats.league_id,
            PlayerLeagueCareerStats.format,
        )
        .all()
    )
    history_rows = (
        db.query(PlayerTeamHistory)
        .order_by(
            PlayerTeamHistory.player_id,
            PlayerTeamHistory.session_name,
            PlayerTeamHistory.team_name,
            PlayerTeamHistory.id,
        )
        .all()
    )

    player_by_id = {row.id: row for row in players}
    match_by_id = {row.id: row for row in matches}
    pm_index, coverage_issues = _player_match_index(player_matches)

    player_table = [
        {
            "player_id": row.id,
            "member_external_id": row.external_id,
            "player_name": row.name,
            "current_skill_level": row.skill_level,
            "current_matches_won": row.matches_won,
            "current_matches_played": row.matches_played,
            "current_win_pct": row.win_pct,
            "current_ppm": row.ppm,
            "current_pa": row.pa,
        }
        for row in players
    ]

    team_match_table = [
        {
            "match_id": row.id,
            "match_external_id": row.external_id,
            "match_date": row.match_date,
            "session_name": row.session_name,
            "format": normalize_format(row.format),
            "week": row.week,
            "status": row.status,
            "location": row.location,
            "home_team_id": row.home_team_id,
            "home_team_name": row.home_team_name,
            "away_team_id": row.away_team_id,
            "away_team_name": row.away_team_name,
            "home_score": row.home_score,
            "away_score": row.away_score,
            "is_bye": bool(row.is_bye),
            "is_scored": bool(row.is_scored),
            "is_finalized": bool(row.is_finalized),
        }
        for row in matches
    ]

    player_match_table = []
    for row in player_matches:
        player = player_by_id.get(row.player_id)
        match = match_by_id.get(row.match_id)
        player_match_table.append(
            {
                "player_match_id": row.id,
                "match_id": row.match_id,
                "match_external_id": match.external_id if match else "",
                "match_date": match.match_date if match else row.match_date,
                "session_name": match.session_name if match else "",
                "format": normalize_format(match.format if match else ""),
                "player_id": row.player_id,
                "member_external_id": player.external_id if player else "",
                "player_name": player.name if player else "",
                "team_id": row.team_id,
                "team_name": row.team_name,
                "skill_level": row.skill_level,
                "points_earned": row.points_earned,
                "result": _result(row.result),
                "eight_on_break": row.eight_on_break,
                "eight_break_and_run": row.eight_break_and_run,
                "nine_on_snap": row.nine_on_snap,
                "nine_break_and_run": row.nine_break_and_run,
            }
        )

    raw_h2h_table = []
    grouped: dict[tuple[int, int, int], list[PlayerHeadToHead]] = defaultdict(list)
    for row in h2h_rows:
        player = player_by_id.get(row.player_id)
        opponent = player_by_id.get(row.opponent_id)
        match = match_by_id.get(row.match_id)
        fmt = normalize_format(row.format or (match.format if match else ""))
        raw_h2h_table.append(
            {
                "h2h_id": row.id,
                "match_id": row.match_id,
                "match_external_id": match.external_id if match else "",
                "match_date": match.match_date if match else "",
                "session_name": row.session_name or (match.session_name if match else ""),
                "format": fmt,
                "player_id": row.player_id,
                "player_external_id": player.external_id if player else "",
                "player_name": player.name if player else "",
                "opponent_id": row.opponent_id,
                "opponent_external_id": opponent.external_id if opponent else "",
                "opponent_name": opponent.name if opponent else "",
                "own_skill_level": row.own_skill_level,
                "opponent_skill_level": row.opponent_skill_level,
                "result": _result(row.result),
                "points_earned": row.points_earned,
                "nine_ball_points": row.nine_ball_points,
            }
        )
        low, high = sorted((row.player_id, row.opponent_id))
        grouped[(row.match_id, low, high)].append(row)

    all_games: list[dict[str, Any]] = []
    game_seq = 0

    for (match_id, low_id, high_id), rows in sorted(grouped.items()):
        match = match_by_id.get(match_id)
        if match is None:
            coverage_issues.append(
                {
                    "category": "H2H_MATCH_MISSING",
                    "match_id": match_id,
                    "player_id": low_id,
                    "detail": "PlayerHeadToHead rows reference a missing Match row",
                }
            )
            continue

        low_rows = [
            row for row in rows
            if row.player_id == low_id and row.opponent_id == high_id and _result(row.result)
        ]
        high_rows = [
            row for row in rows
            if row.player_id == high_id and row.opponent_id == low_id and _result(row.result)
        ]

        low_counter = Counter(
            _normalized_low_signature(row, match, reverse=False) for row in low_rows
        )
        high_counter = Counter(
            _normalized_low_signature(row, match, reverse=True) for row in high_rows
        )

        if low_rows and low_counter == high_counter:
            mirror_status = "VERIFIED_UNIQUE" if len(low_rows) == 1 else "VERIFIED_COUNT_ONLY"
        elif low_rows and not high_rows:
            mirror_status = "MISSING_REVERSE"
        elif low_rows:
            mirror_status = "MIRROR_MISMATCH"
        else:
            mirror_status = "REVERSE_ONLY"

        if mirror_status != "VERIFIED_UNIQUE":
            coverage_issues.append(
                {
                    "category": "GAME_MIRROR_STATUS",
                    "match_id": match_id,
                    "player_id": low_id,
                    "opponent_id": high_id,
                    "detail": (
                        f"{mirror_status}: low_rows={len(low_rows)}, high_rows={len(high_rows)}"
                    ),
                }
            )

        source_rows = low_rows if low_rows else high_rows
        for occurrence, row in enumerate(source_rows, start=1):
            if low_rows:
                a_id, b_id = low_id, high_id
                a_row = row
                result_a = _result(row.result)
                a_sl = row.own_skill_level
                b_sl = row.opponent_skill_level
            else:
                a_id, b_id = high_id, low_id
                a_row = row
                result_a = _result(row.result)
                a_sl = row.own_skill_level
                b_sl = row.opponent_skill_level

            a = player_by_id.get(a_id)
            b = player_by_id.get(b_id)
            a_pm = pm_index.get((match_id, a_id))
            b_pm = pm_index.get((match_id, b_id))

            game_seq += 1
            all_games.append(
                {
                    "game_key": f"{match.external_id}:{a_id}:{b_id}:{occurrence}",
                    "game_sequence": game_seq,
                    "match_id": match_id,
                    "match_external_id": match.external_id,
                    "match_date": match.match_date,
                    "session_name": row.session_name or match.session_name or "",
                    "format": normalize_format(row.format or match.format),
                    "week": match.week,
                    "location": match.location,
                    "participant_a_id": a_id,
                    "participant_a_external_id": a.external_id if a else "",
                    "participant_a_name": a.name if a else "",
                    "participant_a_team_id": a_pm.team_id if a_pm else "",
                    "participant_a_team_name": a_pm.team_name if a_pm else "",
                    "participant_a_skill_level": a_sl,
                    "participant_a_result": result_a,
                    "participant_a_points_earned": a_row.points_earned,
                    "participant_a_nine_ball_points": a_row.nine_ball_points,
                    "participant_b_id": b_id,
                    "participant_b_external_id": b.external_id if b else "",
                    "participant_b_name": b.name if b else "",
                    "participant_b_team_id": b_pm.team_id if b_pm else "",
                    "participant_b_team_name": b_pm.team_name if b_pm else "",
                    "participant_b_skill_level": b_sl,
                    "winner_id": a_id if result_a == "W" else b_id if result_a == "L" else None,
                    "winner_name": (
                        a.name if result_a == "W" and a
                        else b.name if result_a == "L" and b
                        else ""
                    ),
                    "loser_id": b_id if result_a == "W" else a_id if result_a == "L" else None,
                    "loser_name": (
                        b.name if result_a == "W" and b
                        else a.name if result_a == "L" and a
                        else ""
                    ),
                    "mirror_status": mirror_status,
                }
            )

    career_table = []
    for row in career_rows:
        player = player_by_id.get(row.player_id)
        career_table.append(
            {
                "player_id": row.player_id,
                "member_external_id": player.external_id if player else "",
                "player_name": player.name if player else "",
                "league_id": row.league_id,
                "league_slug": row.league_slug,
                "alias_external_id": row.alias_external_id,
                "format": normalize_format(row.format),
                "matches_won": row.matches_won,
                "matches_played": row.matches_played,
                "cla": row.cla,
                "defensive_shot_avg": row.defensive_shot_avg,
                "match_count_last_two_yrs": row.match_count_last_two_yrs,
                "last_played": row.last_played,
                "on_break_count": row.on_break_count,
                "break_and_runs": row.break_and_runs,
                "mini_slams": row.mini_slams,
                "rackless": row.rackless,
                "skunks": row.skunks,
            }
        )

    history_table = []
    for row in history_rows:
        player = player_by_id.get(row.player_id)
        history_table.append(
            {
                "player_id": row.player_id,
                "member_external_id": player.external_id if player else "",
                "player_name": player.name if player else "",
                "team_external_id": row.team_external_id,
                "team_name": row.team_name,
                "division_id": row.division_id,
                "session_name": row.session_name,
                "is_current": bool(row.is_current),
                "is_tournament": bool(row.is_tournament),
                "skill_level": row.skill_level,
                "rank": row.rank,
                "matches_won": row.matches_won,
                "matches_played": row.matches_played,
            }
        )

    tables = {
        "players": player_table,
        "team_matches": team_match_table,
        "player_match_stats": player_match_table,
        "raw_h2h_evidence": raw_h2h_table,
        "all_games": all_games,
        "career_stats": career_table,
        "team_history": history_table,
        "coverage_issues": coverage_issues,
    }
    return {
        "schema": "ultimate-coach-data-contract-v1",
        "tables": tables,
        "counts": {name: len(rows) for name, rows in tables.items()},
        "notes": {
            "source_of_truth": "SQLite",
            "all_games_rule": (
                "One canonical individual-game row from recorded H2H evidence; "
                "mirror_status makes reconciliation quality explicit."
            ),
            "raw_h2h_rule": "Every stored directional H2H row is preserved.",
        },
    }
