"""Build the Player Trends table from stored match history.

Reads ``player_matches`` joined to ``matches``, groups by (player, format,
session), evaluates each history with ``analytics.player_trends``, upserts
into ``player_trends``, and prunes aggregates whose underlying matches are
gone.

Uses only data already in the database. No scraping, no network, and no
writes to ``player_matchups`` or ``player_h2h_advantage`` -- the Matchup and
Head-to-Head engines own those.

No population pass is needed: hot/cold uses ABSOLUTE thresholds, so every
player is judged against the spec rather than against other players.

Usage:
    python -m scripts.build_player_trends
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from analytics.player_trends import evaluate, normalize_format
from database.engine import create_db_engine
from database.ingest import ingest_player_trends, prune_player_trends_not_in
from database.models import Match, PlayerMatch
from scheduler.graphql_sync import load_config

logger = logging.getLogger(__name__)


def grouped_history(db: Session) -> dict[tuple[int, str, str], list[PlayerMatch]]:
    """(player_id, format, session_name) -> that player's matches, oldest
    first.

    Format and session come from the joined Match: PlayerMatch carries
    neither, and inferring format from the points scale would be exactly the
    kind of guess this project refuses to make. A match missing either is
    skipped rather than bucketed under a placeholder.

    Ordered by week then match id, because match_date is stored as delivered
    text and does not sort reliably. Order is load-bearing: the regression
    reads skill level against match order.
    """
    rows = (
        db.query(PlayerMatch, Match)
        .join(Match, Match.id == PlayerMatch.match_id)
        .all()
    )

    pairs: dict[tuple[int, str, str], list[tuple[Match, PlayerMatch]]] = defaultdict(list)
    for player_match, match in rows:
        if player_match.player_id is None or not match.format or not match.session_name:
            continue
        key = (player_match.player_id, normalize_format(match.format), match.session_name)
        pairs[key].append((match, player_match))

    ordered: dict[tuple[int, str, str], list[PlayerMatch]] = {}
    for key, group in pairs.items():
        group.sort(key=lambda pair: (
            pair[0].week if pair[0].week is not None else 0, pair[0].id
        ))
        ordered[key] = [player_match for _, player_match in group]
    return ordered


def build_rows(db: Session) -> list[dict[str, Any]]:
    """One evaluated row per (player, format, session).

    A group with no usable skill level at all is skipped: current_skill_level
    and sample_size are NOT NULL in the schema, and a row that cannot supply
    them has nothing to report.

    The full history is handed to `evaluate`, which applies the windowing --
    the two spans differ, so slicing here would silently break one.
    """
    groups = grouped_history(db)
    if not groups:
        logger.warning("No player match history with a format and session -- nothing to build.")
        return []

    built: list[dict[str, Any]] = []
    for (_, format_, session), matches in groups.items():
        player = matches[0].player
        if player is None:
            continue
        result = evaluate(
            skill_levels=[m.skill_level for m in matches],
            player_id=player.external_id,
            format_=format_,
            session_name=session,
        )
        if result.current_skill_level is None or not result.sample_size:
            logger.debug(
                "Skipping %s / %s / %s -- no usable skill level",
                player.external_id, format_, session,
            )
            continue
        built.append(vars(result).copy())

    return built


def run(config_path: str = "apa_config.yaml") -> dict[str, int]:
    """Build, store and prune. Returns {"written": n, "pruned": n}."""
    config = load_config(config_path)
    engine = create_db_engine(config)
    with Session(engine) as db:
        rows = build_rows(db)
        written = ingest_player_trends(db, rows) if rows else 0

        # Prune against DATABASE player ids, which is what the table stores;
        # build_rows reports external ids.
        valid = set(grouped_history(db))
        pruned = prune_player_trends_not_in(db, valid)

        return {"written": written, "pruned": pruned}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    counts = run()
    print(
        f"\nPlayer Trends: {counts['written']} row(s) written, "
        f"{counts['pruned']} stale row(s) pruned\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
