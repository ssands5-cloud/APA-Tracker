"""Build the offline Ultimate Coach scouting payload from verified APA data.

This is an evidence layer, not a prediction layer. It exposes:
- every stored player, with explicit identity quality
- 8-ball / 9-ball records kept separate
- direct opponent aggregates from PlayerHeadToHead
- shared-opponent-ready adjacency data
- league-scoped APA career stats
- team/session history with format mapped from the verified catalog
- current roster SL only when current membership proves one unambiguous value
- latest observed SL as a separately labelled fallback

No win probability is emitted here. Odds remain locked until the independent
chronological backtest/calibration gate is implemented and passes.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from database.models import (
    Match,
    Player,
    PlayerHeadToHead,
    PlayerLeagueCareerStats,
    PlayerTeamHistory,
)

SCHEMA = "ultimate-coach-scout-v1"
_FORMATS = ("EIGHT", "NINE")


def _format_name(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    if text in {"EIGHT", "8-BALL", "EIGHT_BALL"} or "EIGHT" in text:
        return "EIGHT"
    if text in {"NINE", "9-BALL", "NINE_BALL"} or "NINE" in text:
        return "NINE"
    return None


def _parse_aware_iso(value: str | None) -> datetime | None:
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


def _rate(wins: int, games: int) -> float | None:
    return round(wins / games, 4) if games else None


def _average(values: list[int | float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def catalog_scope_index(
    catalog: dict[str, Any] | None,
) -> tuple[dict[tuple[str, str], dict[str, str]], list[dict[str, Any]]]:
    """Map exact division+session to format/league context.

    Conflicting mappings are removed from the usable index and surfaced in a
    conflict list rather than picking whichever row happened to appear last.
    """
    index: dict[tuple[str, str], dict[str, str]] = {}
    conflicted_keys: set[tuple[str, str]] = set()
    conflicts: list[dict[str, Any]] = []

    for row in (catalog or {}).get("divisions") or []:
        row = row or {}
        division_id = str(row.get("division_id") or "").strip()
        session_name = str(
            row.get("catalog_session_name") or row.get("session_name") or ""
        ).strip()
        if not division_id or not session_name:
            continue

        context = {
            "format": _format_name(row.get("format") or row.get("type")) or "",
            "league_id": str(row.get("league_id") or ""),
            "league_slug": str(row.get("league_slug") or ""),
        }
        key = (division_id, session_name)
        if key in conflicted_keys:
            continue
        previous = index.get(key)
        if previous is None:
            index[key] = context
        elif previous != context:
            conflicts.append(
                {
                    "division_id": division_id,
                    "session_name": session_name,
                    "first": previous,
                    "second": context,
                }
            )
            conflicted_keys.add(key)
            index.pop(key, None)

    return index, conflicts


def _identity_status(history: list[PlayerTeamHistory]) -> str:
    for row in history:
        if str(row.team_external_id or "").strip() and str(row.session_name or "").strip():
            return "canonical_team_history"
    return "scoresheet_only_or_unscoped"


def _career_rows(rows: list[PlayerLeagueCareerStats]) -> list[dict[str, Any]]:
    return [
        {
            "league_id": row.league_id,
            "league_slug": row.league_slug or "",
            "alias_external_id": row.alias_external_id,
            "format": row.format,
            "matches_won": row.matches_won,
            "matches_played": row.matches_played,
            "win_rate": _rate(row.matches_won or 0, row.matches_played or 0)
            if row.matches_played is not None
            else None,
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
        for row in sorted(rows, key=lambda x: (x.format or "", x.league_id or ""))
    ]


def build_scout_payload(
    db: Session,
    *,
    catalog: dict[str, Any] | None = None,
    reports: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable all-player scouting graph."""
    scope_index, scope_conflicts = catalog_scope_index(catalog)

    players = db.query(Player).order_by(Player.name, Player.id).all()
    histories = db.query(PlayerTeamHistory).order_by(
        PlayerTeamHistory.player_id,
        PlayerTeamHistory.is_current.desc(),
        PlayerTeamHistory.session_name,
        PlayerTeamHistory.team_name,
    ).all()
    careers = db.query(PlayerLeagueCareerStats).order_by(
        PlayerLeagueCareerStats.player_id,
        PlayerLeagueCareerStats.format,
        PlayerLeagueCareerStats.league_id,
    ).all()
    h2h_joined = (
        db.query(PlayerHeadToHead, Match)
        .join(Match, PlayerHeadToHead.match_id == Match.id)
        .filter(PlayerHeadToHead.result.in_(("W", "L")))
        .order_by(Match.match_date, PlayerHeadToHead.id)
        .all()
    )

    histories_by_player: dict[int, list[PlayerTeamHistory]] = defaultdict(list)
    for row in histories:
        histories_by_player[row.player_id].append(row)

    careers_by_player: dict[int, list[PlayerLeagueCareerStats]] = defaultdict(list)
    for row in careers:
        careers_by_player[row.player_id].append(row)

    player_by_id = {player.id: player for player in players}

    # player -> format -> list[(h2h, match, parsed datetime)]
    games_by_player: dict[int, dict[str, list[tuple[PlayerHeadToHead, Match, datetime | None]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    unrecognized_formats = 0
    unsafe_dates = 0
    for row, match in h2h_joined:
        fmt = _format_name(row.format or match.format)
        if fmt not in _FORMATS:
            unrecognized_formats += 1
            continue
        when = _parse_aware_iso(match.match_date)
        if match.match_date and when is None:
            unsafe_dates += 1
        games_by_player[row.player_id][fmt].append((row, match, when))

    result_players: list[dict[str, Any]] = []
    for player in players:
        player_history = histories_by_player.get(player.id, [])
        identity_status = _identity_status(player_history)

        team_rows: list[dict[str, Any]] = []
        current_levels: dict[str, set[int]] = defaultdict(set)
        for row in player_history:
            scope = scope_index.get(
                (str(row.division_id or ""), str(row.session_name or ""))
            )
            fmt = scope.get("format") if scope else None
            if (
                row.is_current
                and fmt in _FORMATS
                and row.skill_level is not None
            ):
                current_levels[fmt].add(int(row.skill_level))
            team_rows.append(
                {
                    "team_external_id": row.team_external_id,
                    "team_name": row.team_name or "",
                    "division_id": row.division_id or "",
                    "session_name": row.session_name or "",
                    "format": fmt,
                    "league_id": scope.get("league_id") if scope else None,
                    "league_slug": scope.get("league_slug") if scope else None,
                    "is_current": bool(row.is_current),
                    "skill_level": row.skill_level,
                    "matches_won": row.matches_won,
                    "matches_played": row.matches_played,
                    "win_rate": _rate(row.matches_won or 0, row.matches_played or 0)
                    if row.matches_played is not None
                    else None,
                }
            )

        formats: dict[str, Any] = {}
        for fmt in _FORMATS:
            games = games_by_player.get(player.id, {}).get(fmt, [])
            wins = sum(1 for row, _, _ in games if row.result == "W")
            losses = sum(1 for row, _, _ in games if row.result == "L")
            own_levels = [
                int(row.own_skill_level)
                for row, _, _ in games
                if row.own_skill_level is not None
            ]
            opponent_levels = [
                int(row.opponent_skill_level)
                for row, _, _ in games
                if row.opponent_skill_level is not None
            ]

            safe_dated = [
                (when, match.match_date, row)
                for row, match, when in games
                if when is not None
            ]
            safe_dated.sort(key=lambda item: item[0])
            first_date = safe_dated[0][1] if safe_dated else None
            last_date = safe_dated[-1][1] if safe_dated else None

            latest_observed_sl = None
            latest_observed_sl_date = None
            for _, raw_date, row in reversed(safe_dated):
                if row.own_skill_level is not None:
                    latest_observed_sl = int(row.own_skill_level)
                    latest_observed_sl_date = raw_date
                    break

            current_candidates = sorted(current_levels.get(fmt) or [])
            if len(current_candidates) == 1:
                display_sl = current_candidates[0]
                display_sl_status = "current_roster"
            elif len(current_candidates) > 1:
                display_sl = None
                display_sl_status = "ambiguous_current_roster"
            elif latest_observed_sl is not None:
                display_sl = latest_observed_sl
                display_sl_status = "latest_observed"
            else:
                display_sl = None
                display_sl_status = "unavailable"

            by_opponent: dict[int, list[tuple[PlayerHeadToHead, Match, datetime | None]]] = defaultdict(list)
            for row, match, when in games:
                by_opponent[row.opponent_id].append((row, match, when))

            opponents: dict[str, Any] = {}
            for opponent_id, opponent_games in sorted(by_opponent.items()):
                opponent = player_by_id.get(opponent_id)
                if opponent is None:
                    continue
                owins = sum(1 for row, _, _ in opponent_games if row.result == "W")
                olosses = sum(1 for row, _, _ in opponent_games if row.result == "L")
                own_sl = [
                    int(row.own_skill_level)
                    for row, _, _ in opponent_games
                    if row.own_skill_level is not None
                ]
                opp_sl = [
                    int(row.opponent_skill_level)
                    for row, _, _ in opponent_games
                    if row.opponent_skill_level is not None
                ]
                dated = [
                    (when, match.match_date)
                    for _, match, when in opponent_games
                    if when is not None
                ]
                dated.sort(key=lambda item: item[0])
                opponents[str(opponent_id)] = {
                    "opponent_id": opponent_id,
                    "opponent_external_id": opponent.external_id,
                    "opponent_name": opponent.name,
                    "wins": owins,
                    "losses": olosses,
                    "games": owins + olosses,
                    "win_rate": _rate(owins, owins + olosses),
                    "avg_own_skill_level": _average(own_sl),
                    "avg_opponent_skill_level": _average(opp_sl),
                    "first_match_date": dated[0][1] if dated else None,
                    "last_match_date": dated[-1][1] if dated else None,
                }

            formats[fmt] = {
                "wins": wins,
                "losses": losses,
                "games": wins + losses,
                "win_rate": _rate(wins, wins + losses),
                "unique_opponents": len(opponents),
                "avg_own_skill_level": _average(own_levels),
                "avg_opponent_skill_level": _average(opponent_levels),
                "first_match_date": first_date,
                "last_match_date": last_date,
                "display_skill_level": display_sl,
                "display_skill_level_status": display_sl_status,
                "latest_observed_skill_level": latest_observed_sl,
                "latest_observed_skill_date": latest_observed_sl_date,
                "opponents": opponents,
            }

        result_players.append(
            {
                "player_id": player.id,
                "external_id": player.external_id,
                "name": player.name,
                "identity_status": identity_status,
                "selectable_by_default": identity_status == "canonical_team_history",
                "formats": formats,
                "career_stats": _career_rows(careers_by_player.get(player.id, [])),
                "team_history": team_rows,
            }
        )

    return {
        "schema": SCHEMA,
        "odds_status": "LOCKED_NOT_CALIBRATED",
        "players": result_players,
        "counts": {
            "players": len(result_players),
            "canonical_players": sum(
                1 for row in result_players if row["selectable_by_default"]
            ),
            "scoresheet_only_or_unscoped_players": sum(
                1 for row in result_players if not row["selectable_by_default"]
            ),
            "head_to_head_rows_used": sum(
                fmt["games"]
                for player in result_players
                for fmt in player["formats"].values()
            ),
        },
        "quality": {
            "catalog_scope_conflicts": scope_conflicts,
            "unrecognized_head_to_head_formats": unrecognized_formats,
            "head_to_head_rows_with_unsafe_dates": unsafe_dates,
        },
        "catalog": {
            "schema": (catalog or {}).get("schema"),
            "counts": (catalog or {}).get("counts") or {},
            "source_limitations": list((catalog or {}).get("source_limitations") or []),
        },
        "reports": reports or {},
    }
