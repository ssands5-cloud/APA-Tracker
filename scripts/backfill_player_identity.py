"""One-time repair: rewrite scoresheet-alias player identities in an
ALREADY-INGESTED database to their real canonical-roster identity.

Why this exists: scheduler.graphql_sync now resolves this identity BEFORE
ingesting (see database.queries.resolve_roster_identity and
scheduler.graphql_sync.resolve_scoresheet_identities), so every sync from
here on is unaffected. A database populated by a sync from BEFORE that fix
still has PlayerMatch/PlayerHeadToHead rows keyed on the scoresheet's own
per-position alias id -- a different id space than the canonical roster's
member.id, confirmed to differ even across one real person's own matches.
This repairs that already-stored data without a fresh scrape: every input
this needs (team, session, real display name) is already in the database.

Nothing here queries the network or requires a token. It resolves through
the exact same database.queries.resolve_roster_identity used at ingest
time -- the exact same team-scoped, uniquely-validated name join, never an
unscoped guess -- so a database repaired by this script and a database
synced fresh under the new code agree by construction.

Usage:
    python scripts/backfill_player_identity.py --db data/apa_tracker.db
    python scripts/backfill_player_identity.py --db data/apa_tracker.db --apply
    python scripts/backfill_player_identity.py --db data/apa_tracker.db --apply --rebuild-matchups
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Match, Player, PlayerHeadToHead, PlayerMatch
from database.queries import resolve_roster_identity

logger = logging.getLogger(__name__)


@dataclass
class BackfillReport:
    identities_examined: int = 0
    resolved: int = 0
    unresolved: int = 0
    player_match_rows_rewritten: int = 0
    head_to_head_rows_rewritten: int = 0
    unresolved_names: list[str] = field(default_factory=list)

    @property
    def resolution_rate(self) -> Optional[float]:
        total = self.resolved + self.unresolved
        return round(self.resolved / total, 4) if total else None


def _distinct_alias_identities(db: Session) -> list[tuple[int, str, str, str]]:
    """One entry per (alias Player.id, team_id, session_name, display_name)
    actually referenced by a real PlayerMatch row.

    session_name comes from the joined Match, since PlayerMatch itself has
    no session column of its own. A row whose match or team_id cannot be
    resolved is skipped -- there is no scope to resolve identity against.
    """
    rows = (
        db.query(PlayerMatch, Match, Player)
        .join(Match, Match.id == PlayerMatch.match_id)
        .join(Player, Player.id == PlayerMatch.player_id)
        .filter(PlayerMatch.team_id.isnot(None), PlayerMatch.team_id != "")
        .all()
    )
    seen: set[tuple[int, str, str]] = set()
    identities: list[tuple[int, str, str, str]] = []
    for player_match, match, player in rows:
        key = (player.id, player_match.team_id, match.session_name or "")
        if key in seen:
            continue
        seen.add(key)
        identities.append((player.id, player_match.team_id, match.session_name or "", player.name))
    return identities


def backfill(db: Session, *, apply: bool = False) -> BackfillReport:
    """Resolve every distinct alias identity and, when ``apply`` is true,
    rewrite the real PlayerMatch/PlayerHeadToHead rows to point at the
    resolved canonical-roster Player instead.

    Dry-run (``apply=False``, the default) reports exactly what WOULD change
    without writing anything -- always run this first against a real
    database and inspect it before applying.
    """
    report = BackfillReport()
    identities = _distinct_alias_identities(db)
    report.identities_examined = len(identities)

    rewrites: dict[int, int] = {}  # alias Player.id -> resolved Player.id
    for alias_player_id, team_id, session_name, display_name in identities:
        resolved_player = resolve_roster_identity(db, team_id, session_name, display_name)
        if resolved_player is None:
            report.unresolved += 1
            report.unresolved_names.append(f"{display_name} (team {team_id}, session {session_name!r})")
            continue
        report.resolved += 1
        if resolved_player.id != alias_player_id:
            rewrites[alias_player_id] = resolved_player.id

    if not apply or not rewrites:
        return report

    for alias_id, real_id in rewrites.items():
        updated = (
            db.query(PlayerMatch)
            .filter(PlayerMatch.player_id == alias_id)
            .update({PlayerMatch.player_id: real_id}, synchronize_session=False)
        )
        report.player_match_rows_rewritten += updated

        updated_player = (
            db.query(PlayerHeadToHead)
            .filter(PlayerHeadToHead.player_id == alias_id)
            .update({PlayerHeadToHead.player_id: real_id}, synchronize_session=False)
        )
        updated_opponent = (
            db.query(PlayerHeadToHead)
            .filter(PlayerHeadToHead.opponent_id == alias_id)
            .update({PlayerHeadToHead.opponent_id: real_id}, synchronize_session=False)
        )
        report.head_to_head_rows_rewritten += updated_player + updated_opponent

    db.commit()
    return report


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to the SQLite database to repair")
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually rewrite rows. Without this, only a dry-run report is printed.",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        logger.error("No database at %s", db_path)
        return 1

    engine = create_engine(f"sqlite:///{db_path}")
    db = Session(bind=engine)
    try:
        report = backfill(db, apply=args.apply)
    finally:
        db.close()
        engine.dispose()

    logger.info(
        "%s: %d identit(y/ies) examined, %d resolved (%s), %d unresolved",
        "APPLIED" if args.apply else "DRY RUN",
        report.identities_examined, report.resolved,
        "n/a" if report.resolution_rate is None else f"{report.resolution_rate * 100:.1f}%",
        report.unresolved,
    )
    if args.apply:
        logger.info(
            "Rewrote %d PlayerMatch row(s), %d PlayerHeadToHead row(s)",
            report.player_match_rows_rewritten, report.head_to_head_rows_rewritten,
        )
    if report.unresolved_names:
        logger.info("Unresolved (kept under their own identity, never guessed):")
        for name in report.unresolved_names:
            logger.info("  %s", name)
    if not args.apply:
        logger.info("Dry run only -- re-run with --apply to actually rewrite rows.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
