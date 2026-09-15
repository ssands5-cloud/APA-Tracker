"""Build the Opponent Volatility Profile for one real opponent
team/session/format (docs/opponent_volatility.md).

Writes:

    exports/opponent_volatility.html
    exports/opponent_volatility.xlsx

Read-only (mode=ro), same posture as every other builder in this project.
The query boundary starts from the opponent's canonical current roster
(database.queries.canonical_current_roster -- exact opponent team external
ID and session, raising CanonicalRosterError on a duplicate-identity roster
rather than silently choosing one row), joins Player identity, then reads at
most one matching PlayerTrend per player/normalized-format/session. Every
roster player remains in the output even when no trend row matches;
duplicate trend rows for the same player/format/session block the profile.

Never triggers trend population, falls back across formats/sessions, or
accepts a display name as identity, and does not modify
analytics/player_vs_player.py or analytics/opponent_scouting.py.

Usage:
    python scripts/build_opponent_volatility.py --opponent-team-id 13082949 --session "Fall 2026" --format "8-ball"
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

from analytics.opponent_volatility import build_profile
from analytics.player_trends import normalize_format
from database.models import Player, PlayerTrend, Team
from database.queries import CanonicalRosterError, canonical_current_roster
from scripts.build_captains_edge import NoDatabaseError, connect_read_only, resolve_db_path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "exports"
HTML_NAME = "opponent_volatility.html"
XLSX_NAME = "opponent_volatility.xlsx"


class DuplicateTrendError(RuntimeError):
    """More than one PlayerTrend row matches the same
    player/normalized-format/session -- blocking rather than silently
    picking one."""


def _opponent_team_name(db: Session, opponent_team_external_id: str) -> str:
    team = db.query(Team).filter_by(external_id=opponent_team_external_id).one_or_none()
    return team.name if team is not None else opponent_team_external_id


def _roster_players(db: Session, opponent_team_external_id: str, session_name: str) -> list[dict]:
    rows = canonical_current_roster(db, opponent_team_external_id, session_name)
    players = []
    for row in rows:
        player = db.query(Player).filter_by(id=row.player_id).one_or_none()
        if player is None:
            continue
        players.append({
            "player_id": player.id,
            "player_external_id": player.external_id,
            "player_name": player.name,
        })
    return players


def _trend_by_player_id(
    db: Session, player_ids: list[int], session_name: str, format_: Optional[str]
) -> dict[int, dict]:
    if not player_ids:
        return {}
    normalized_format = normalize_format(format_) if format_ else None
    query = (
        db.query(PlayerTrend)
        .filter(PlayerTrend.player_id.in_(player_ids))
        .filter(PlayerTrend.session_name == session_name)
    )
    by_player: dict[int, dict] = {}
    for trend in query.all():
        if normalized_format and trend.format != normalized_format:
            continue
        if trend.player_id in by_player:
            raise DuplicateTrendError(
                f"Multiple PlayerTrend rows for player {trend.player_id!r}, "
                f"format {trend.format!r}, session {session_name!r}"
            )
        by_player[trend.player_id] = {
            "format": trend.format,
            "session_name": trend.session_name,
            "sample_size": trend.sample_size,
            "volatility": trend.volatility,
            "sl_stability": trend.sl_stability,
            "regression_slope": trend.regression_slope,
        }
    return by_player


def build(
    db: Session, opponent_team_external_id: str, session_name: str, out_dir: Path,
    format_: Optional[str] = None,
) -> tuple[Path, Path]:
    from ui.export_excel_opponent_volatility import write_workbook as write_excel_workbook
    from ui.tabs.opponent_volatility import render

    team_name = _opponent_team_name(db, opponent_team_external_id)
    roster = _roster_players(db, opponent_team_external_id, session_name)
    player_ids = [p["player_id"] for p in roster]
    trend_by_id = _trend_by_player_id(db, player_ids, session_name, format_)

    profile = build_profile(
        opponent_team_external_id, team_name, session_name, roster, trend_by_id,
        format=normalize_format(format_) if format_ else None,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / HTML_NAME
    html_path.write_text(render(profile), encoding="utf-8")
    xlsx_path = write_excel_workbook(profile, out_dir / XLSX_NAME)

    return html_path, xlsx_path


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Path to the SQLite database (default: configured/fallback path)")
    parser.add_argument("--opponent-team-id", required=True, help="The opponent's real APA team external ID")
    parser.add_argument("--session", required=True, help='e.g. "Fall 2026"')
    parser.add_argument("--format", help='e.g. "8-ball" or "8-Ball Open"')
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Directory to write into")
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
        html_path, xlsx_path = build(
            db, args.opponent_team_id, args.session, Path(args.out_dir), args.format,
        )
    except (CanonicalRosterError, DuplicateTrendError) as exc:
        logger.error(str(exc))
        return 1
    finally:
        db.close()
        engine.dispose()

    logger.info("Wrote %s", html_path)
    logger.info("Wrote %s", xlsx_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
