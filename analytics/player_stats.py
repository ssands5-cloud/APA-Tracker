"""
Per-player statistics derived from match history.
"""

from __future__ import annotations

from dataclasses import dataclass

from database.models import PlayerMatch


@dataclass
class PlayerStatLine:
    player_name: str
    matches_played: int
    wins: int
    losses: int
    win_pct: float
    avg_points: float
    # Real, per-match counts (database.models.PlayerMatch.eight_on_break etc.)
    # summed across every match on record -- only ingest_match_scores
    # populates these on any given row, so a player with no scoresheet-
    # sourced matches (history-page-only, or roster-totals-only) gets 0
    # here, same as wins/losses do for that case.
    total_eight_on_breaks: int
    total_eight_break_and_runs: int
    total_nine_on_snaps: int
    total_nine_break_and_runs: int


def summarize_player(player_name: str, matches: list[PlayerMatch]) -> PlayerStatLine:
    played = len(matches)
    wins = sum(1 for m in matches if (m.result or "").strip().upper() == "W")
    losses = sum(1 for m in matches if (m.result or "").strip().upper() == "L")
    points = [m.points_earned for m in matches if m.points_earned is not None]
    avg_points = sum(points) / len(points) if points else 0.0
    win_pct = wins / played if played else 0.0

    return PlayerStatLine(
        player_name=player_name,
        matches_played=played,
        wins=wins,
        losses=losses,
        win_pct=round(win_pct, 3),
        avg_points=round(avg_points, 2),
        total_eight_on_breaks=sum(m.eight_on_break or 0 for m in matches),
        total_eight_break_and_runs=sum(m.eight_break_and_run or 0 for m in matches),
        total_nine_on_snaps=sum(m.nine_on_snap or 0 for m in matches),
        total_nine_break_and_runs=sum(m.nine_break_and_run or 0 for m in matches),
    )


def recent_form(matches: list[PlayerMatch], last_n: int = 5) -> str:
    """Return a W/L string for the player's last N matches, most recent last."""
    recent = matches[-last_n:]
    return "".join((m.result or "?")[:1].upper() for m in recent)
