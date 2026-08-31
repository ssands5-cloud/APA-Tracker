"""
Team-level statistics: standings trend and head-to-head records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from database.models import StandingsSnapshot


@dataclass
class StandingsTrend:
    team_name: str
    rank_change: int  # negative = moved up (better), positive = moved down
    points_change: float


def compute_trend(history: list[StandingsSnapshot]) -> Optional[StandingsTrend]:
    """Compare the two most recent snapshots for a team."""
    if len(history) < 2:
        return None
    previous, current = history[-2], history[-1]
    return StandingsTrend(
        team_name=current.team_name,
        rank_change=(current.rank or 0) - (previous.rank or 0),
        points_change=round((current.points or 0.0) - (previous.points or 0.0), 2),
    )


def head_to_head(matches, opponent_name: str) -> dict:
    """Given a flat list of PlayerMatch-like records, tally results against one opponent."""
    relevant = [m for m in matches if m.opponent == opponent_name]
    wins = sum(1 for m in relevant if (m.result or "").strip().upper() == "W")
    losses = sum(1 for m in relevant if (m.result or "").strip().upper() == "L")
    return {"opponent": opponent_name, "played": len(relevant), "wins": wins, "losses": losses}
