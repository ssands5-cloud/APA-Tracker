"""Build the Player Trends table from stored match history.

Reads ``player_matches`` joined to ``matches`` for the format, groups by
(player, format), evaluates each history with ``analytics.player_trends``,
and upserts into ``player_trends``.

Uses only data already in the database. No scraping, no network, and no
writes to ``player_matchups`` or ``player_h2h_advantage`` -- the Matchup and
Head-to-Head engines own those.

Unlike the Head-to-Head builder, this one needs no population pass: the
governing spec sets hot/cold by ABSOLUTE thresholds (slope >= +0.05 with
volatility <= 0.40, and the mirror for cold), not by quartiles against other
players. Every player is judged against the spec, not against the league.

Usage:
    python -m scripts.build_player_trends
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from analytics.player_trends import evaluate
from database.engine import create_db_engine
from database.ingest import ingest_player_trends
from database.models import Match, PlayerMatch
from scheduler.graphql_sync import load_config

logger = logging.getLogger(__name__)


def grouped_history(db: Session) -> dict[tuple[int, str], list[PlayerMatch]]:
    """(player_id, format) -> that player's matches, oldest first.

    Format comes from the joined Match: PlayerMatch has no format column of
    its own, and inferring one from the points scale would be exactly the
    kind of guess this project refuses to make.

    Ordered by week then match id, because match_date is stored as delivered
    text and does not sort reliably. Order is load-bearing: the regression
    reads skill level against match order, so an unordered history yields a
    meaningless slope.
    """
    rows = (
        db.query(PlayerMatch, Match)
        .join(Match, Match.id == PlayerMatch.match_id)
        .all()
    )

    pairs: dict[tuple[int, str], list[tuple[Match, PlayerMatch]]] = defaultdict(list)
    for player_match, match in rows:
        if player_match.player_id is None or not match.format:
            continue
        pairs[(player_match.player_id, match.format)].append((match, player_match))

    ordered: dict[tuple[int, str], list[PlayerMatch]] = {}
    for key, group in pairs.items():
        group.sort(key=lambda pair: (
            pair[0].week if pair[0].week is not None else 0, pair[0].id
        ))
        ordered[key] = [player_match for _, player_match in group]
    return ordered


def build_rows(db: Session) -> list[dict[str, Any]]:
    """One evaluated row per (player, format).

    The full history is handed to `evaluate`, which applies the windowing
    itself -- the spec's two spans differ (slope over everything, volatility
    over the last 20), so slicing here would silently break one of them.
    """
    groups = grouped_history(db)
    if not groups:
        logger.warning("No player match history with a format -- nothing to build.")
        return []

    built: list[dict[str, Any]] = []
    for (_, format_), matches in groups.items():
        player = matches[0].player
        if player is None:
            continue
        result = evaluate(
            points=[m.points_earned for m in matches],
            skill_levels=[m.skill_level for m in matches],
            player_id=player.external_id,
            format_=format_,
        )
        built.append(vars(result).copy())

    return built


def run(config_path: str = "apa_config.yaml") -> int:
    """Build and store every trend. Returns the number of rows written."""
    config = load_config(config_path)
    engine = create_db_engine(config)
    with Session(engine) as db:
        rows = build_rows(db)
        if not rows:
            return 0
        return ingest_player_trends(db, rows)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    written = run()
    print(f"\nPlayer Trends: {written} (player, format) row(s) written to player_trends\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
