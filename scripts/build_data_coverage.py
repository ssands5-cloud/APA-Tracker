"""Build the Data Coverage view for one real scope (docs/captain_first_edge_experience.md §11).

Writes:

    exports/data_coverage.html
    exports/data_coverage.xlsx

Read-only (mode=ro), same posture as scripts/build_captain_first_edge.py
and scripts/build_player_vs_player_export.py -- never calls
database.engine.create_db_engine(), which would write.

Usage:
    python scripts/build_data_coverage.py --opponent-team-id 13082949 --format "8-Ball Open" --session "Fall 2026"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.data_coverage import build_report
from analytics.pairing_evidence import build_pairing_evidence_matrix
from database.models import PlayerCareerStats, StandingsSnapshot, Team
from scripts.build_captain_first_edge import _configured_our_team_id, _team_name
from scripts.build_captains_edge import NoDatabaseError, connect_read_only, resolve_db_path
from ui.export_excel_data_coverage import write_workbook as write_excel_workbook
from ui.tabs.data_coverage import render

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "exports"
HTML_NAME = "data_coverage.html"
XLSX_NAME = "data_coverage.xlsx"


def _standings_refreshed_at(db: Session, team_name: str) -> Optional[str]:
    """Real max(StandingsSnapshot.captured_at) for this team's real display
    name -- the only identifier that table carries (no team id column)."""
    value = (
        db.query(func.max(StandingsSnapshot.captured_at))
        .filter(StandingsSnapshot.team_name == team_name)
        .scalar()
    )
    return value.isoformat() if value else None


def _career_stats_refreshed_at(db: Session, player_external_ids: set[str]) -> dict[str, Optional[str]]:
    """Real max(PlayerCareerStats.updated_at) per player, across whichever
    real format row(s) that player has -- a deliberately coarser grain
    than per-format, since Data Coverage asks "when was this player's
    career data last refreshed at all", not "for which specific format".
    """
    from database.models import Player

    result: dict[str, Optional[str]] = {}
    if not player_external_ids:
        return result
    rows = (
        db.query(Player.external_id, func.max(PlayerCareerStats.updated_at))
        .join(PlayerCareerStats, PlayerCareerStats.player_id == Player.id)
        .filter(Player.external_id.in_(player_external_ids))
        .group_by(Player.external_id)
        .all()
    )
    for external_id, updated_at in rows:
        result[external_id] = updated_at.isoformat() if updated_at else None
    return result


def build(
    db: Session,
    our_team_external_id: str,
    opponent_team_external_id: str,
    format: str,
    session_name: str,
    out_dir: Path,
) -> tuple[Path, Path]:
    matrix = build_pairing_evidence_matrix(
        db,
        our_team_external_id=our_team_external_id,
        opponent_team_external_id=opponent_team_external_id,
        format=format,
        session_name=session_name,
    )

    our_team_name = _team_name(db, our_team_external_id)
    opponent_team_name = _team_name(db, opponent_team_external_id)

    player_ids = {p.player_external_id for p in matrix.pairings} | {
        p.opponent_external_id for p in matrix.pairings
    }
    report = build_report(
        matrix,
        standings_refreshed_at=_standings_refreshed_at(db, our_team_name),
        career_stats_refreshed_at=_career_stats_refreshed_at(db, player_ids),
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / HTML_NAME
    html_path.write_text(render(report, our_team_name, opponent_team_name), encoding="utf-8")
    xlsx_path = write_excel_workbook(report, out_dir / XLSX_NAME)

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
    logger.info("Wrote %s", xlsx_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
