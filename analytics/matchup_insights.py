"""
Lightweight matchup analysis: compares two players' historical performance
to surface simple, explainable insights (not a prediction model).
"""

from __future__ import annotations

from dataclasses import dataclass

from analytics.player_stats import summarize_player
from database.models import PlayerMatch


@dataclass
class MatchupInsight:
    player_a: str
    player_b: str
    player_a_win_pct: float
    player_b_win_pct: float
    edge: str  # name of the player with the higher recent win pct, or "even"


def compare_players(
    player_a_name: str,
    player_a_matches: list[PlayerMatch],
    player_b_name: str,
    player_b_matches: list[PlayerMatch],
) -> MatchupInsight:
    stat_a = summarize_player(player_a_name, player_a_matches)
    stat_b = summarize_player(player_b_name, player_b_matches)

    if stat_a.win_pct > stat_b.win_pct:
        edge = player_a_name
    elif stat_b.win_pct > stat_a.win_pct:
        edge = player_b_name
    else:
        edge = "even"

    return MatchupInsight(
        player_a=player_a_name,
        player_b=player_b_name,
        player_a_win_pct=stat_a.win_pct,
        player_b_win_pct=stat_b.win_pct,
        edge=edge,
    )
