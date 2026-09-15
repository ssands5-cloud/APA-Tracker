"""Build the Player vs Player export for one real scope: every feasible
pairing between the configured team and one real opponent, combined with
each pairing's own real per-pair game history.

Writes:

    exports/player_vs_player.html    self-contained, opens with no server
    exports/player_vs_player.xlsx    standalone workbook (omitted entirely
                                      when there are no feasible pairings)

This is a REPORTER, the same posture as scripts/build_captain_first_edge.py:
it queries the database read-only (mode=ro; never calls
database.engine.create_db_engine(), which would write) and combines two
already-real sources -- analytics.pairing_evidence's evidence matrix and
analytics.player_vs_player's per-pair summaries -- via
analytics.player_vs_player_matrix.build_matrix_export. Nothing here
recomputes a label, a rate, or a probability.

Usage:
    python scripts/build_player_vs_player_export.py --opponent-team-id 13082949 --format "8-Ball Open" --session "Fall 2026"
    python scripts/build_player_vs_player_export.py --db path/to/apa.db --our-team-id 13082948 ...
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.pairing_evidence import build_pairing_evidence_matrix
from analytics.player_vs_player_matrix import build_matrix_export
from database.models import Match
from database.queries import head_to_head_history
from scripts.build_captain_first_edge import _configured_our_team_id, _team_name
from scripts.build_captains_edge import connect_read_only, resolve_db_path
from ui.export_excel_player_vs_player import write_workbook as write_excel_workbook
from ui.export_html_player_vs_player import render_export

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "exports"
HTML_NAME = "player_vs_player.html"
XLSX_NAME = "player_vs_player.xlsx"


def _match_dates_for(db: Session, match_ids: set[int]) -> dict[int, str]:
    """Real Match.match_date text for a real set of match ids.
    PlayerHeadToHead has no ORM relationship to Match (see
    analytics/player_vs_player.py's own docstring), so this small,
    explicit query is the query layer's job."""
    if not match_ids:
        return {}
    rows = db.query(Match.id, Match.match_date).filter(Match.id.in_(match_ids)).all()
    return {match_id: date for match_id, date in rows if date}


def build(
    db: Session,
    our_team_external_id: str,
    opponent_team_external_id: str,
    format: str,
    session_name: str,
    out_dir: Path,
) -> tuple[Path, Optional[Path]]:
    matrix = build_pairing_evidence_matrix(
        db,
        our_team_external_id=our_team_external_id,
        opponent_team_external_id=opponent_team_external_id,
        format=format,
        session_name=session_name,
    )

    histories = {
        (pairing.player_id, pairing.opponent_id): head_to_head_history(
            db, pairing.player_id, pairing.opponent_id
        )
        for pairing in matrix.pairings
    }
    match_ids = {row.match_id for rows in histories.values() for row in rows}
    match_dates = _match_dates_for(db, match_ids)

    rows = build_matrix_export(matrix, histories, match_dates=match_dates)

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / HTML_NAME
    html_path.write_text(render_export(rows), encoding="utf-8")

    xlsx_path = write_excel_workbook(rows, out_dir / XLSX_NAME)

    return html_path, xlsx_path


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Path to the SQLite database (default: configured/fallback path)")
    parser.add_argument("--our-team-id", help="Override apa_config.yaml's team.team_id")
    parser.add_argument("--opponent-team-id", required=True, help="The real opponent team's external id")
    parser.add_argument("--format", required=True, help='e.g. "8-Ball Open"')
    parser.add_argument("--session", required=True, help='e.g. "Fall 2026"')
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Directory to write into")
    args = parser.parse_args(argv)

    from scripts.build_captains_edge import NoDatabaseError

    try:
        db_path = resolve_db_path(args.db)
    except NoDatabaseError as exc:
        logger.error(str(exc))
        return 1

    our_team_external_id = args.our_team_id or _configured_our_team_id()
    if not our_team_external_id:
        logger.error("No team id given. Set apa_config.yaml's team.team_id, or pass --our-team-id.")
        return 1

    logger.info("Reading %s", db_path)
    engine = create_engine("sqlite://", creator=lambda: connect_read_only(db_path))
    db = Session(bind=engine)
    try:
        html_path, xlsx_path = build(
            db, our_team_external_id, args.opponent_team_id, args.format, args.session,
            Path(args.out_dir),
        )
    finally:
        db.close()
        engine.dispose()

    logger.info("Wrote %s", html_path)
    logger.info("Wrote %s", xlsx_path if xlsx_path else "(no workbook -- no feasible pairings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
