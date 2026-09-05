"""Fixtures -> SQLite.

Deliberately thin. Every payload-to-row mapping already exists in
``scraper.graphql_scraper`` and every row-to-database write already exists in
``database.ingest``; re-implementing either here would create a second
definition of "what a roster row is" that could drift from the live sync.

So this module only does the part that genuinely differs: reading the
composed shapes out of fixtures instead of off the network, in the right
order, and reporting what it wrote.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from analytics.matchup_builder import build_matchups
from database.ingest import (
    ingest_head_to_head,
    ingest_match_scores,
    ingest_matchups,
    ingest_player_team_history,
)
from database.models import Player
from scheduler.graphql_sync import ingest_team_data
from scraper.graphql_scraper import (
    head_to_head_rows,
    match_player_scores,
    team_stat_rows,
)

from pipeline.fixtures import FixtureStore

logger = logging.getLogger(__name__)


def ingest_teams(db: Session, store: FixtureStore) -> dict[str, int]:
    """Teams, rosters, standings and schedules, one team at a time.

    Reuses ``scheduler.graphql_sync.ingest_team_data`` verbatim -- it already
    maps a composed team payload onto every relevant ingest function, so the
    fixture path and the live path cannot disagree about what a team is.
    """
    totals = {"teams": 0, "roster": 0, "standings": 0, "matches_seen": 0,
              "matches_new": 0, "matches_updated": 0}

    viewer = store.dashboard_viewer()
    league_teams = viewer.get("leagueTeams") or []
    if not league_teams:
        logger.warning(
            "dashboardTeams listed no teams -- the scrape may have run "
            "unauthenticated. Falling back to whatever team fixtures exist."
        )

    # Ids from the payload where we have it; the directory listing is only a
    # fallback for a tree captured before dashboardTeams was saved.
    team_ids = [str(t.get("id")) for t in league_teams if t.get("id")] or store.ids("team")

    for team_id in team_ids:
        data = store.team_data(team_id)
        if not (data.get("team") or {}).get("id"):
            logger.warning("No teamPage fixture for team %s -- skipped", team_id)
            continue
        counts = ingest_team_data(db, data)
        totals["teams"] += 1
        for key in ("roster", "standings", "matches_seen", "matches_new", "matches_updated"):
            totals[key] += counts.get(key, 0)

    return totals


def ingest_matches(db: Session, store: FixtureStore) -> dict[str, int]:
    """Per-match scoresheets and head-to-head rows.

    Ordered after :func:`ingest_teams` on purpose: ``ingest_match_scores``
    resolves a Match by its external id, which the schedule pass creates.
    A scoresheet for a match no team's schedule mentioned is skipped rather
    than allowed to raise.
    """
    totals = {"matches": 0, "scores": 0, "head_to_head": 0, "orphans": 0}

    for match_id, match in store.matches():
        scores = match_player_scores(match)
        if not scores:
            continue
        try:
            created, updated = ingest_match_scores(db, match_id, scores)
        except ValueError:
            # _resolve_match_pk raises when the Match row does not exist --
            # a real condition (a scoresheet captured for a match outside our
            # teams' schedules), not a bug to crash on.
            totals["orphans"] += 1
            logger.warning("Scoresheet for unknown match %s -- skipped", match_id)
            continue

        totals["matches"] += 1
        totals["scores"] += created + updated
        totals["head_to_head"] += ingest_head_to_head(db, match_id, head_to_head_rows(match))

    return totals


def ingest_team_history(db: Session, store: FixtureStore) -> int:
    """Cross-session team history from the alias-scoped TeamStat payloads.

    ``ingest_player_team_history`` needs the Player the history belongs to.
    The alias id is not a Player.external_id, so the owner is resolved from
    the roster rows already in the database. When it cannot be resolved the
    rows are skipped and said so -- guessing an owner would attach one
    member's season history to somebody else.
    """
    written = 0
    for alias_id, alias in store.aliases():
        rows = team_stat_rows(alias)
        if not rows:
            continue
        player = _resolve_alias_owner(db, store, alias_id, alias)
        if player is None:
            logger.warning(
                "TeamStat alias %s has %d row(s) but no matching player -- skipped",
                alias_id, len(rows),
            )
            continue
        written += ingest_player_team_history(db, player, rows)
    return written


def _resolve_alias_owner(db: Session, store: FixtureStore, alias_id: str,
                         alias: dict[str, Any]) -> Optional[Player]:
    """Find the Player a TeamStat alias belongs to.

    Tries the alias id itself, then the viewer's own member id -- rosters key
    players on ``member.id``, and the only alias we capture is the signed-in
    member's own.
    """
    player = db.query(Player).filter_by(external_id=str(alias_id)).one_or_none()
    if player is not None:
        return player

    viewer = store.get("global", "global", "ViewerQuery").get("viewer") or {}
    viewer_id = viewer.get("id")
    if viewer_id:
        return db.query(Player).filter_by(external_id=str(viewer_id)).one_or_none()
    return None


def rebuild_matchups(db: Session) -> int:
    """Recompute every pairing from what was just ingested.

    The engine is untouched: this calls ``analytics.matchup_builder`` and
    stores what it returns. Captain's Edge reads those rows and never
    recomputes them, so both views always agree.
    """
    rows = build_matchups(db)
    return ingest_matchups(db, rows)


def run(db: Session, store: FixtureStore) -> dict[str, int]:
    """Full fixture -> database pass, in dependency order."""
    counts: dict[str, int] = {}
    counts.update(ingest_teams(db, store))
    counts.update(ingest_matches(db, store))
    counts["team_history"] = ingest_team_history(db, store)
    counts["matchups"] = rebuild_matchups(db)
    return counts
