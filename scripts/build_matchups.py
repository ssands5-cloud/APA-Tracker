#!/usr/bin/env python3
"""Compute the Matchup Advantage Engine's player_matchups table from
already-ingested head-to-head history (PlayerHeadToHead).

Standalone by design: run it any time after a sync (scheduler.graphql_sync)
or the offline demo build (scripts/build_demo.py) has written head-to-head
rows, to (re)compute player_matchups without touching the network. Safe to
re-run -- database.ingest.ingest_matchups() upserts on (player, opponent).

See docs/matchups.md for how the score is computed and what it doesn't
cover yet (most notably: opponent identity inherits the same fragmentation
risk flagged for career stats -- a real opponent split across two Player
rows shows up here as two separate, incomplete matchups rather than one
merged one).

Usage:
    python scripts/build_matchups.py                  # apa_config.yaml's database
    python scripts/build_matchups.py --config other.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from sqlalchemy.orm import Session

from analytics.matchups import (
    average_opponent_skill_level,
    average_points_earned,
    head_to_head_win_rate,
    matchup_score,
)
from analytics.skill_level_trends import skill_level_trend, skill_level_volatility
from database.engine import create_db_engine
from database.ingest import ingest_matchups
from database.queries import all_head_to_head, skill_level_history
from scheduler.graphql_sync import load_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def build_matchups(db: Session) -> list[dict]:
    """Group every raw head-to-head row by (player, opponent), score each
    pair, and upsert the result into player_matchups. Returns the rows
    written, for the CLI summary below."""
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
            }
        )

    written = ingest_matchups(db, rows)
    logger.info("Computed and wrote %d matchup(s)", written)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="apa_config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    engine = create_db_engine(config)
    with Session(engine) as db:
        rows = build_matchups(db)

    if not rows:
        print(
            "\nNo head-to-head history ingested yet -- run a sync "
            "(python -m scheduler.graphql_sync) or scripts/build_demo.py first."
        )
        return

    ranked = sorted(rows, key=lambda r: r["matchup_score"], reverse=True)
    print(f"\nComputed {len(ranked)} matchup(s).")

    print("\nStrongest matchups:")
    for r in ranked[:5]:
        print(
            f"  {r['player_name']} vs {r['opponent_name']}: {r['matchup_score']} "
            f"(win rate {r['win_rate']:.0%}, {r['matches_played']} game(s))"
        )

    print("\nWeakest matchups:")
    for r in ranked[-5:]:
        print(
            f"  {r['player_name']} vs {r['opponent_name']}: {r['matchup_score']} "
            f"(win rate {r['win_rate']:.0%}, {r['matches_played']} game(s))"
        )


if __name__ == "__main__":
    main()
