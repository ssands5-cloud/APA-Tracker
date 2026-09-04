#!/usr/bin/env python3
"""CLI wrapper around analytics.matchup_builder.build_matchups() --
computes the Matchup Advantage Engine's player_matchups table from
already-ingested head-to-head history (PlayerHeadToHead).

Standalone by design: run it any time after a sync (scheduler.graphql_sync)
or the offline demo build (scripts/build_demo.py) has written head-to-head
rows, to (re)compute player_matchups without touching the network. Safe to
re-run -- database.ingest.ingest_matchups() upserts on (player, opponent).
The live sync (scheduler.graphql_sync.run_all_teams) and the demo build
both call analytics.matchup_builder.build_matchups() directly as part of
their own pipeline, so this script is for recomputing on demand against an
existing database, not the only way the table gets populated.

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
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from sqlalchemy.orm import Session

from analytics.matchup_builder import build_matchups
from database.engine import create_db_engine
from scheduler.graphql_sync import load_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


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
            f"(confidence {r['confidence_score']}, win rate {r['win_rate']:.0%}, "
            f"{r['matches_played']} game(s))"
        )

    print("\nWeakest matchups:")
    for r in ranked[-5:]:
        print(
            f"  {r['player_name']} vs {r['opponent_name']}: {r['matchup_score']} "
            f"(confidence {r['confidence_score']}, win rate {r['win_rate']:.0%}, "
            f"{r['matches_played']} game(s))"
        )


if __name__ == "__main__":
    main()
