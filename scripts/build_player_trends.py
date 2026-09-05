"""Build the Player Trends table from stored match history.

Reads ``player_matches`` joined to ``matches`` for the format, groups by
(player, format), evaluates each window with ``analytics.player_trends``,
and upserts into ``player_trends``.

Uses only data already in the database. No scraping, no network, and no
writes to ``player_matchups`` or ``player_h2h_advantage`` -- the Matchup and
Head-to-Head engines own those.

Usage:
    python -m scripts.build_player_trends
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from analytics.player_trends import evaluate, quartile_thresholds, trend_slope, rolling_window
from database.engine import create_db_engine
from database.ingest import ingest_player_trends
from database.models import Match, PlayerMatch
from scheduler.graphql_sync import load_config

logger = logging.getLogger(__name__)


def _grouped_history(db: Session) -> dict[tuple[int, str], list[PlayerMatch]]:
    """(player_id, format) -> that player's matches, oldest first.

    Format comes from the joined Match: PlayerMatch has no format column of
    its own, and guessing one from the points scale would be exactly the kind
    of inference this project refuses to make.

    Ordered by week then match id, because match_date is stored as delivered
    text and does not sort reliably. Order matters: the slope reads against
    match order, so an unordered window yields a meaningless trend.
    """
    rows = (
        db.query(PlayerMatch, Match)
        .join(Match, Match.id == PlayerMatch.match_id)
        .all()
    )
    groups: dict[tuple[int, str], list[PlayerMatch]] = defaultdict(list)
    for player_match, match in rows:
        if player_match.player_id is None or not match.format:
            continue
        groups[(player_match.player_id, match.format)].append((match, player_match))

    ordered: dict[tuple[int, str], list[PlayerMatch]] = {}
    for key, pairs in groups.items():
        pairs.sort(key=lambda pair: (
            pair[0].week if pair[0].week is not None else 0, pair[0].id
        ))
        ordered[key] = [player_match for _, player_match in pairs]
    return ordered


def build_rows(db: Session) -> list[dict[str, Any]]:
    """One evaluated window per (player, format).

    Two passes on purpose: hot/cold is a quartile against everyone else in
    the SAME format, so every slope has to exist before any player can be
    labelled. Thresholds computed from a mixed-format population would call
    an 8-ball player hot for a slope that is ordinary in 9-ball scoring.
    """
    groups = _grouped_history(db)
    if not groups:
        logger.warning("No player match history with a format -- nothing to build.")
        return []

    # Pass 1: slopes per format, for the quartile thresholds.
    slopes_by_format: dict[str, list[float]] = defaultdict(list)
    for (_, format_), matches in groups.items():
        slope = trend_slope([m.points_earned for m in rolling_window(matches)])
        if slope is not None:
            slopes_by_format[format_].append(slope)

    thresholds = {
        format_: quartile_thresholds(slopes)
        for format_, slopes in slopes_by_format.items()
    }

    # Pass 2: evaluate each window against its own format's thresholds.
    built: list[dict[str, Any]] = []
    for (player_id, format_), matches in groups.items():
        player = matches[0].player
        if player is None:
            continue
        hot, cold = thresholds.get(format_, (None, None))
        result = evaluate(
            points=[m.points_earned for m in matches],
            levels=[m.skill_level for m in matches],
            player_id=player.external_id,
            format_=format_,
            hot_threshold=hot,
            cold_threshold=cold,
        )
        built.append(vars(result).copy())

    return built


def run(config_path: str = "apa_config.yaml") -> int:
    """Build and store every window. Returns the number of rows written."""
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
    print(f"\nPlayer Trends: {written} (player, format) window(s) written to player_trends\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
