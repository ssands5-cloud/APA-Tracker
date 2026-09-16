"""Build the Player Matchup Explorer for every captured player in a scope.

Writes:

    exports/player_matchup_explorer.html

Read-only (mode=ro), same posture as every other builder here.

Scope is the whole captured session, not one team pair: every player with a
canonical current roster row for that session is selectable, so two players
who are both on OTHER teams can be compared. Optionally narrowed to one
division with --division-id.

Meetings come only from real captured PlayerHeadToHead rows, through the
existing database.queries.head_to_head_history -- which was never scoped to
our own team and works for any two player ids. A pair with no captured rows
is reported as having none; nothing is inferred from a shared match, a
shared team, or a shared division.

Usage:
    python scripts/build_player_matchup_explorer.py --session "2026 Rehearsal Session"
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.player_matchup_explorer import build_document
from database.models import Match, Player, PlayerHeadToHead, PlayerTeamHistory
from scripts.build_captains_edge import NoDatabaseError, connect_read_only, resolve_db_path
from ui.export_html_player_matchup_explorer import render

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "exports"
HTML_NAME = "player_matchup_explorer.html"


def selectable_players(
    db: Session, session_name: str, division_id: Optional[str] = None
) -> list[dict]:
    """Every canonical current-roster player in the session.

    Not restricted to one team: this is the whole pool the captured data can
    honestly offer, which is what makes an opponent-vs-opponent comparison
    possible at all.
    """
    query = (
        db.query(PlayerTeamHistory, Player)
        .join(Player, Player.id == PlayerTeamHistory.player_id)
        .filter(
            PlayerTeamHistory.session_name == session_name,
            PlayerTeamHistory.is_current.is_(True),
        )
    )
    if division_id:
        query = query.filter(PlayerTeamHistory.division_id == division_id)

    players: dict[int, dict] = {}
    for history, player in query.all():
        # One canonical current row per player in scope; a duplicate is a
        # real identity problem the roster query already guards, so the
        # first is kept rather than silently merged into a different team.
        players.setdefault(player.id, {
            "player_id": player.id,
            "player_external_id": player.external_id,
            "player_name": player.name,
            "team_external_id": history.team_external_id or "",
            "team_name": history.team_name or "",
            "skill_level": history.skill_level,
        })
    return list(players.values())


def captured_pair_histories(
    db: Session, player_ids: set[int], session_name: str, format_: Optional[str] = None
) -> dict[tuple[int, int], list[dict]]:
    """Real captured games between any two of the selectable players.

    One pass over the scoped rows rather than a query per pair: the pool is
    the whole session, so a per-pair query would be O(n^2) round trips for
    data that is already one table scan.
    """
    if not player_ids:
        return {}

    query = (
        db.query(PlayerHeadToHead, Match)
        .join(Match, Match.id == PlayerHeadToHead.match_id)
        .filter(PlayerHeadToHead.session_name == session_name)
        .filter(PlayerHeadToHead.player_id.in_(player_ids))
        .filter(PlayerHeadToHead.opponent_id.in_(player_ids))
    )
    if format_:
        query = query.filter(PlayerHeadToHead.format == format_)

    histories: dict[tuple[int, int], list[dict]] = defaultdict(list)
    rows = sorted(
        query.all(),
        key=lambda pair: (
            pair[1].week if pair[1].week is not None else 0,
            pair[1].id,
        ),
    )
    for head_to_head, match in rows:
        histories[(head_to_head.player_id, head_to_head.opponent_id)].append({
            "match_id": match.external_id,
            "match_date": match.match_date,
            "week": match.week,
            "own_skill_level": head_to_head.own_skill_level,
            "opponent_skill_level": head_to_head.opponent_skill_level,
            "result": head_to_head.result,
            "points_earned": head_to_head.points_earned,
        })
    return dict(histories)


def build(
    db: Session,
    session_name: str,
    out_dir: Path,
    division_id: Optional[str] = None,
    format_: Optional[str] = None,
) -> Path:
    players = selectable_players(db, session_name, division_id)
    histories = captured_pair_histories(
        db, {p["player_id"] for p in players}, session_name, format_
    )
    document = build_document(
        players, histories,
        session_name=session_name, division_id=division_id, format=format_,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / HTML_NAME
    html_path.write_text(render(document), encoding="utf-8")
    logger.info(
        "%d selectable player(s), %d ordered pair(s), %d with captured meetings",
        len(document.players), len(document.pairs), document.captured_pair_count,
    )
    return html_path


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Path to the SQLite database")
    parser.add_argument("--session", required=True, help='e.g. "2026 Rehearsal Session"')
    parser.add_argument("--division-id", help="narrow to one division")
    parser.add_argument("--format", help='e.g. "8-Ball Open"')
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)

    try:
        db_path = resolve_db_path(args.db)
    except NoDatabaseError as exc:
        logger.error(str(exc))
        return 1

    logger.info("Reading %s", db_path)
    engine = create_engine("sqlite://", creator=lambda: connect_read_only(db_path))
    db = Session(bind=engine)
    try:
        html_path = build(db, args.session, Path(args.out_dir), args.division_id, args.format)
    finally:
        db.close()
        engine.dispose()

    logger.info("Wrote %s", html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
