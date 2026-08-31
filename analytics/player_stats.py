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
    )


def recent_form(matches: list[PlayerMatch], last_n: int = 5) -> str:
    """Return a W/L string for the player's last N matches, most recent last."""
    recent = matches[-last_n:]
    return "".join((m.result or "?")[:1].upper() for m in recent)
