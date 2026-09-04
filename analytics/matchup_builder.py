"""
Computes the Matchup Advantage Engine's player_matchups table from
already-ingested head-to-head history (PlayerHeadToHead).

Pulled out of scripts/build_matchups.py (a CLI entry point -- argparse,
its own logging setup, a network-adjacent config file) so this reusable
piece of business logic lives in a neutral module instead: importing a
function out of a script meant to be run standalone, the way
scripts/build_demo.py and scheduler/graphql_sync.py both need to, was the
CLI module doing double duty as a library. scripts/build_matchups.py now
just wraps this for the command line.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from analytics.matchups import (
    average_opponent_skill_level,
    average_points_earned,
    confidence_score,
    head_to_head_win_rate,
    matchup_score,
)
from analytics.skill_level_trends import skill_level_trend, skill_level_volatility
from database.ingest import ingest_matchups
from database.queries import all_head_to_head, skill_level_history


def build_matchups(db: Session) -> list[dict]:
    """Group every raw head-to-head row by (player, opponent), score each
    pair, and upsert the result into player_matchups. Returns the rows
    written, for a caller's own summary/logging."""
    by_pair: dict[tuple[int, int], list] = defaultdict(list)
    for row in all_head_to_head(db):
        by_pair[(row.player_id, row.opponent_id)].append(row)

    # Trend/volatility are about the PLAYER, not the pair -- computed once
    # per player from their own skill level history, not once per opponent.
    own_history_by_player: dict[int, list] = defaultdict(list)
    for reading in skill_level_history(db):
        own_history_by_player[reading.player_id].append(reading)

    rows = []
    for (player_id, opponent_id), h2h_rows in by_pair.items():
        player = h2h_rows[0].player
        opponent = h2h_rows[0].opponent
        own_history = own_history_by_player.get(player_id, [])
        trend = skill_level_trend(own_history)
        volatility = skill_level_volatility(own_history)

        rows.append(
            {
                "player_id": player.external_id,
                "player_name": player.name,
                "opponent_id": opponent.external_id,
                "opponent_name": opponent.name,
                "matches_played": len(h2h_rows),
                "win_rate": head_to_head_win_rate(h2h_rows),
                "avg_points_earned": average_points_earned(h2h_rows),
                "avg_opponent_skill_level": average_opponent_skill_level(h2h_rows),
                "trend": trend,
                "volatility": volatility,
                "matchup_score": matchup_score(h2h_rows, trend, volatility),
                "confidence_score": confidence_score(h2h_rows, trend, volatility),
            }
        )

    ingest_matchups(db, rows)
    return rows
