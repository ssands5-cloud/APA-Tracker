"""
Per-sheet row generators for the APA analytics workbook.

Each class exposes:
  headers  – list of column header strings
  rows     – list of dicts (one per data row)

The SpreadsheetBuilder calls these to populate each worksheet.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Player, PlayerMatch, StandingsSnapshot, Team
from analytics.calculations import (
    calculate_win_percentage,
    calculate_streaks,
    rank_players,
    identify_trends,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_str(value: Any) -> str:
    return str(value) if value is not None else "N/A"


def _safe_float(value: Any, decimals: int = 2) -> float:
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return 0.0


def _result_char(result: str | None) -> str:
    return (result or "?").strip().upper()[:1]


# ---------------------------------------------------------------------------
# 1. PLAYER_MATCH_RESULTS
# ---------------------------------------------------------------------------

class PlayerMatchResultsSheet:
    headers = [
        "Player ID", "Player Name", "Team", "Opponent",
        "Skill Level", "Points Earned", "Result",
        "Win %", "Match Date",
    ]

    def __init__(self, db: Session) -> None:
        self._db = db

    def rows(self) -> list[dict]:
        rows: list[dict] = []
        players = self._db.query(Player).all()
        for player in players:
            team_name = player.team.name if player.team else "N/A"
            results_so_far: list[str] = []
            for pm in sorted(
                player.matches, key=lambda m: m.match_date or ""
            ):
                results_so_far.append(_result_char(pm.result))
                wins = results_so_far.count("W")
                pct = calculate_win_percentage(wins, len(results_so_far))
                rows.append({
                    "Player ID": player.external_id,
                    "Player Name": player.name,
                    "Team": team_name,
                    "Opponent": _safe_str(pm.opponent),
                    "Skill Level": pm.skill_level or player.skill_level or 0,
                    "Points Earned": _safe_float(pm.points_earned),
                    "Result": _result_char(pm.result),
                    "Win %": pct,
                    "Match Date": _safe_str(pm.match_date),
                })
        return rows


# ---------------------------------------------------------------------------
# 2. PLAYER_LIFETIME
# ---------------------------------------------------------------------------

class PlayerLifetimeSheet:
    headers = [
        "Rank", "Player ID", "Player Name", "Primary Team", "Skill Level",
        "Matches Played", "Wins", "Losses",
        "Overall Win %", "Avg Points Earned",
        "Win Streak", "Loss Streak", "Trend",
        "Last Match Date",
    ]

    def __init__(self, db: Session) -> None:
        self._db = db

    def rows(self) -> list[dict]:
        stats: list[dict] = []
        players = self._db.query(Player).all()
        for player in players:
            matches = sorted(player.matches, key=lambda m: m.match_date or "")
            played = len(matches)
            results = [_result_char(m.result) for m in matches]
            wins = results.count("W")
            losses = results.count("L")
            points = [m.points_earned for m in matches if m.points_earned is not None]
            avg_pts = sum(points) / len(points) if points else 0.0
            win_streak, loss_streak = calculate_streaks(results)

            # Build historical win% list for trend detection
            hist: list[float] = []
            for i, r in enumerate(results, start=1):
                w = results[:i].count("W")
                hist.append(calculate_win_percentage(w, i))
            trend = identify_trends(hist)

            last_date = matches[-1].match_date if matches else "N/A"
            team_name = player.team.name if player.team else "N/A"

            stats.append({
                "Player ID": player.external_id,
                "Player Name": player.name,
                "Primary Team": team_name,
                "Skill Level": player.skill_level or 0,
                "Matches Played": played,
                "Wins": wins,
                "Losses": losses,
                "Overall Win %": calculate_win_percentage(wins, played),
                "Avg Points Earned": round(avg_pts, 2),
                "Win Streak": win_streak,
                "Loss Streak": loss_streak,
                "Trend": trend,
                "Last Match Date": _safe_str(last_date),
            })

        ranked = rank_players(stats)
        return ranked


# ---------------------------------------------------------------------------
# 3. TEAM_ROSTER
# ---------------------------------------------------------------------------

class TeamRosterSheet:
    headers = [
        "Team ID", "Team Name", "Player ID", "Player Name",
        "Skill Level", "Matches Played (Season)", "Win % (Season)",
        "Avg Points (Season)",
    ]

    def __init__(self, db: Session) -> None:
        self._db = db

    def rows(self) -> list[dict]:
        rows: list[dict] = []
        teams = self._db.query(Team).order_by(Team.name).all()
        for team in teams:
            for player in sorted(team.players, key=lambda p: p.name):
                matches = player.matches
                played = len(matches)
                results = [_result_char(m.result) for m in matches]
                wins = results.count("W")
                points = [m.points_earned for m in matches if m.points_earned is not None]
                avg_pts = sum(points) / len(points) if points else 0.0
                rows.append({
                    "Team ID": team.external_id,
                    "Team Name": team.name,
                    "Player ID": player.external_id,
                    "Player Name": player.name,
                    "Skill Level": player.skill_level or 0,
                    "Matches Played (Season)": played,
                    "Win % (Season)": calculate_win_percentage(wins, played),
                    "Avg Points (Season)": round(avg_pts, 2),
                })
        return rows


# ---------------------------------------------------------------------------
# 4. HEAD_TO_HEAD
# ---------------------------------------------------------------------------

class HeadToHeadSheet:
    headers = [
        "Player 1", "Player 1 ID",
        "Player 2 (Opponent)", "Times Played",
        "Player 1 Wins", "Player 1 Losses",
        "Win % (vs Opponent)", "Last Played Date",
    ]

    def __init__(self, db: Session) -> None:
        self._db = db

    def rows(self) -> list[dict]:
        rows: list[dict] = []
        players = self._db.query(Player).order_by(Player.name).all()
        for player in players:
            # Group matches by opponent name
            by_opponent: dict[str, list[PlayerMatch]] = defaultdict(list)
            for pm in player.matches:
                if pm.opponent:
                    by_opponent[pm.opponent].append(pm)

            for opponent_name, opp_matches in sorted(by_opponent.items()):
                results = [_result_char(m.result) for m in opp_matches]
                wins = results.count("W")
                losses = results.count("L")
                dates = sorted(m.match_date for m in opp_matches if m.match_date)
                last_date = dates[-1] if dates else "N/A"
                rows.append({
                    "Player 1": player.name,
                    "Player 1 ID": player.external_id,
                    "Player 2 (Opponent)": opponent_name,
                    "Times Played": len(opp_matches),
                    "Player 1 Wins": wins,
                    "Player 1 Losses": losses,
                    "Win % (vs Opponent)": calculate_win_percentage(wins, len(opp_matches)),
                    "Last Played Date": _safe_str(last_date),
                })
        return rows


# ---------------------------------------------------------------------------
# 5. TEAM_STATS
# ---------------------------------------------------------------------------

class TeamStatsSheet:
    headers = [
        "Team ID", "Team Name",
        "Matches Won", "Matches Lost", "Win %",
        "Points", "Rank", "Roster Size",
        "Avg Skill Level",
    ]

    def __init__(self, db: Session) -> None:
        self._db = db

    def rows(self) -> list[dict]:
        rows: list[dict] = []

        # Use the most recent standings snapshot
        latest_ts = self._db.query(
            func.max(StandingsSnapshot.captured_at)
        ).scalar()
        snapshots: dict[str, StandingsSnapshot] = {}
        if latest_ts is not None:
            for snap in self._db.query(StandingsSnapshot).filter(
                StandingsSnapshot.captured_at == latest_ts
            ).all():
                snapshots[snap.team_name] = snap

        teams = self._db.query(Team).order_by(Team.name).all()
        for team in teams:
            snap = snapshots.get(team.name)
            wins = int(snap.wins or 0) if snap else 0
            losses = int(snap.losses or 0) if snap else 0
            points = _safe_float(snap.points if snap else None)
            rank = int(snap.rank or 0) if snap else 0
            played = wins + losses
            roster_size = len(team.players)
            skill_levels = [p.skill_level for p in team.players if p.skill_level]
            avg_skill = sum(skill_levels) / len(skill_levels) if skill_levels else 0.0
            rows.append({
                "Team ID": team.external_id,
                "Team Name": team.name,
                "Matches Won": wins,
                "Matches Lost": losses,
                "Win %": calculate_win_percentage(wins, played),
                "Points": points,
                "Rank": rank,
                "Roster Size": roster_size,
                "Avg Skill Level": round(avg_skill, 2),
            })
        return sorted(rows, key=lambda r: -(r["Win %"]))


# ---------------------------------------------------------------------------
# 6. STANDINGS_HISTORY (replaces MATCHES — uses available StandingsSnapshot)
# ---------------------------------------------------------------------------

class StandingsHistorySheet:
    headers = [
        "Captured At", "Team Name", "Rank", "Wins", "Losses", "Points",
    ]

    def __init__(self, db: Session) -> None:
        self._db = db

    def rows(self) -> list[dict]:
        rows: list[dict] = []
        snapshots = (
            self._db.query(StandingsSnapshot)
            .order_by(StandingsSnapshot.captured_at, StandingsSnapshot.rank)
            .all()
        )
        for snap in snapshots:
            rows.append({
                "Captured At": str(snap.captured_at) if snap.captured_at else "N/A",
                "Team Name": snap.team_name,
                "Rank": snap.rank or 0,
                "Wins": snap.wins or 0,
                "Losses": snap.losses or 0,
                "Points": _safe_float(snap.points),
            })
        return rows


# ---------------------------------------------------------------------------
# 7. SEASON_SUMMARY
# ---------------------------------------------------------------------------

class SeasonSummarySheet:
    headers = ["Metric", "Value"]

    def __init__(self, db: Session) -> None:
        self._db = db

    def rows(self) -> list[dict]:
        total_players = self._db.query(Player).count()
        total_teams = self._db.query(Team).count()
        total_matches = self._db.query(PlayerMatch).count()
        total_snapshots = self._db.query(StandingsSnapshot).count()

        # Top 10 players by win%
        players = self._db.query(Player).all()
        player_stats = []
        for p in players:
            played = len(p.matches)
            wins = sum(1 for m in p.matches if _result_char(m.result) == "W")
            player_stats.append({
                "name": p.name,
                "skill_level": p.skill_level or 0,
                "win_pct": calculate_win_percentage(wins, played),
                "played": played,
            })
        top10_players = sorted(
            player_stats, key=lambda x: (-x["win_pct"], -x["skill_level"])
        )[:10]

        rows: list[dict] = [
            {"Metric": "Generated At", "Value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")},
            {"Metric": "Total Players", "Value": total_players},
            {"Metric": "Total Teams", "Value": total_teams},
            {"Metric": "Total Player-Match Records", "Value": total_matches},
            {"Metric": "Standings Snapshots", "Value": total_snapshots},
            {"Metric": "", "Value": ""},
            {"Metric": "--- TOP 10 PLAYERS BY WIN % ---", "Value": ""},
        ]
        for i, ps in enumerate(top10_players, start=1):
            rows.append({
                "Metric": f"#{i} {ps['name']}",
                "Value": f"{ps['win_pct']*100:.1f}% ({ps['played']} matches, SL {ps['skill_level']})",
            })
        return rows
