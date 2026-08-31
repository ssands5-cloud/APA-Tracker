"""
Statistical helper functions for APA league analytics.
"""

from __future__ import annotations

from typing import Any


def calculate_win_percentage(wins: int, played: int) -> float:
    """Return win percentage as a float 0-1; returns 0.0 if played is 0."""
    if not played:
        return 0.0
    return round(wins / played, 4)


def calculate_streaks(results: list[str]) -> tuple[int, int]:
    """
    Given an ordered list of result strings ('W' or 'L'), return
    (current_win_streak, current_loss_streak).  Streaks are measured from
    the *end* of the list (most recent game last).
    Returns (0, 0) for an empty list.
    """
    if not results:
        return 0, 0

    win_streak = 0
    loss_streak = 0

    for r in reversed(results):
        r = (r or "").strip().upper()[:1]
        if r == "W":
            if loss_streak == 0:
                win_streak += 1
            else:
                break
        elif r == "L":
            if win_streak == 0:
                loss_streak += 1
            else:
                break
        else:
            break

    return win_streak, loss_streak


def rank_players(player_stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sort players by (skill_level DESC, win_pct DESC) and attach a 'rank' key.
    Modifies the dicts in-place and returns the sorted list.
    """
    sorted_players = sorted(
        player_stats,
        key=lambda p: (-(p.get("skill_level") or 0), -(p.get("win_pct") or 0.0)),
    )
    for i, player in enumerate(sorted_players, start=1):
        player["rank"] = i
    return sorted_players


def identify_trends(historical_win_pcts: list[float]) -> str:
    """
    Given an ordered list of win percentages (oldest first), return a
    trend label: 'Improving', 'Declining', 'Stable', or 'Insufficient Data'.
    Uses a simple comparison of first-half average vs second-half average.
    """
    if len(historical_win_pcts) < 4:
        return "Insufficient Data"
    mid = len(historical_win_pcts) // 2
    first_half = sum(historical_win_pcts[:mid]) / mid
    second_half = sum(historical_win_pcts[mid:]) / (len(historical_win_pcts) - mid)
    delta = second_half - first_half
    if delta > 0.05:
        return "Improving"
    if delta < -0.05:
        return "Declining"
    return "Stable"
