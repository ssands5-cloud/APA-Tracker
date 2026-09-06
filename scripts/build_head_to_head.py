"""Build the Head-to-Head Advantage table from stored match history.

Reads ``player_head_to_head`` -- the per-game rows the ingest pipeline
already writes -- groups them into (player, opponent, format, session)
pairings, evaluates each with ``analytics.head_to_head``, and upserts the
result into ``player_h2h_advantage``.

Uses only data already in the database. No scraping, no network, and no
writes to ``player_matchups``: the Matchup Advantage Engine owns that table
and is left exactly as it was.

Usage:
    python scripts/build_head_to_head.py
    python -m scripts.build_head_to_head
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Optional

from sqlalchemy.orm import Session

from analytics.head_to_head import EIGHT_BALL, NINE_BALL, evaluate
from database.engine import create_db_engine
from database.ingest import ingest_h2h_advantage, prune_h2h_advantage_not_in
from database.models import PlayerHeadToHead
from scheduler.graphql_sync import load_config

logger = logging.getLogger(__name__)


def ordered_rows(db: Session) -> list[PlayerHeadToHead]:
    """Every head-to-head game, oldest first.

    Order matters: the trend reads the player's first skill level against
    their last, so an unordered list yields a meaningless trend. Sorted by
    the match's week then its id, since match_date is stored as delivered
    text and does not sort reliably.

    Public (not module-private) so other callers needing the exact same
    chronological order -- scripts/validate_predictions.py's walk-forward
    backtest, in particular -- reuse this instead of re-deriving it. Two
    orderings of the same rows would be a silent source of drift.
    """
    rows = db.query(PlayerHeadToHead).all()
    return sorted(
        rows,
        key=lambda r: (
            (r.match.week if r.match and r.match.week is not None else 0),
            r.match_id or 0,
            r.id,
        ),
    )


def group_by_pairing(
    rows: list[PlayerHeadToHead],
) -> dict[tuple[int, int, Optional[str], Optional[str]], list[PlayerHeadToHead]]:
    """Bucket already-ordered rows into (player_id, opponent_id, format,
    session_name) groups, preserving each group's internal order.

    Rows with no resolved player or opponent id are dropped -- the same
    guard build_rows() applied inline before this was extracted.
    """
    groups: dict[tuple, list[PlayerHeadToHead]] = defaultdict(list)
    for row in rows:
        if row.player_id is None or row.opponent_id is None:
            continue
        groups[(row.player_id, row.opponent_id, row.format, row.session_name)].append(row)
    return groups


def _baselines(rows: list[PlayerHeadToHead]) -> dict[tuple[int, str], float]:
    """A player's average output across ALL opponents, per format.

    This is the anchor a thin pairing is shrunk toward: with one game
    against someone, the player's own normal output is better evidence than
    that single night. Keyed (player_id, format-marker).
    """
    buckets: dict[tuple[int, str], list[float]] = defaultdict(list)
    for row in rows:
        fmt = row.format or ""
        if EIGHT_BALL.lower() in fmt.lower() and row.points_earned is not None:
            buckets[(row.player_id, EIGHT_BALL)].append(row.points_earned)
        elif NINE_BALL.lower() in fmt.lower() and row.nine_ball_points is not None:
            buckets[(row.player_id, NINE_BALL)].append(row.nine_ball_points)
    return {key: sum(vals) / len(vals) for key, vals in buckets.items() if vals}


def build_rows(db: Session) -> list[dict[str, Any]]:
    """One evaluated pairing per (player, opponent, format, session)."""
    rows = ordered_rows(db)
    if not rows:
        logger.warning("No head-to-head rows in the database -- nothing to build.")
        return []

    baselines = _baselines(rows)
    groups = group_by_pairing(rows)

    built: list[dict[str, Any]] = []
    for (player_id, opponent_id, fmt, session), pair_rows in groups.items():
        player = pair_rows[0].player
        opponent = pair_rows[0].opponent
        if player is None or opponent is None:
            continue

        advantage = evaluate(
            pair_rows,
            player_id=player.external_id,
            opponent_id=opponent.external_id,
            points_baseline=baselines.get((player_id, EIGHT_BALL)),
            balls_baseline=baselines.get((player_id, NINE_BALL)),
        )
        record = vars(advantage).copy()
        # evaluate() reads format/session off the rows; keep the group's own
        # values authoritative so the upsert key always matches the grouping.
        record["format"] = fmt
        record["session_name"] = session
        built.append(record)

    return built


def run(config_path: str = "apa_config.yaml") -> int:
    """Build, store, and prune every pairing. Returns rows written."""
    config = load_config(config_path)
    engine = create_db_engine(config)
    with Session(engine) as db:
        valid_keys = set(group_by_pairing(ordered_rows(db)))
        rows = build_rows(db)
        written = ingest_h2h_advantage(db, rows) if rows else 0
        prune_h2h_advantage_not_in(db, valid_keys)
        return written


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    written = run()
    print(f"\nHead-to-Head Advantage: {written} pairing(s) written to player_h2h_advantage\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
