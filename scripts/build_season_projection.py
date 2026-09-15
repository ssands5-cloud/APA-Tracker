"""Build the Season Projection view for the configured team
(docs/season_projection.md).

Writes:

    exports/season_projection.html
    exports/season_projection.xlsx

Read-only (mode=ro), same posture as every other builder in this project.
Closes the two real integration gaps docs/season_projection.md names,
disclosed rather than silently worked around:

- `StandingsSnapshot` has no team id column, only `team_name` -- resolving
  a real opponent's standings requires a name-based join. This builder
  does that join but leaves a rate unavailable (never guesses one) when
  the opponent's team name cannot be resolved to exactly one real Team
  row, or that team has no real StandingsSnapshot capture yet.
- Which team's remaining schedule to project is threaded through from
  `apa_config.yaml`'s `team.team_id`, the same real field every other
  per-team view in this project already uses.

Usage:
    python scripts/build_season_projection.py --session "Fall 2026"
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

from analytics.season_projection import (
    project_remaining_schedule,
    team_volatility_curve,
    win_rate,
)
from database.models import Match, Team
from database.queries import standings_history
from scripts.build_captain_first_edge import _configured_our_team_id, _team_name
from scripts.build_captains_edge import NoDatabaseError, connect_read_only, resolve_db_path
from ui.export_excel_season_projection import write_workbook as write_excel_workbook
from ui.tabs.season_projection import render

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "exports"
HTML_NAME = "season_projection.html"
XLSX_NAME = "season_projection.xlsx"


def _latest_record(db: Session, team_name: str) -> tuple[Optional[int], Optional[int]]:
    """The most recent real (wins, losses) for a team's real display name,
    or (None, None) when no real StandingsSnapshot exists for it."""
    history = standings_history(db, team_name)
    if not history:
        return None, None
    latest = history[-1]
    return latest.wins, latest.losses


def _opponent_team_name(db: Session, opponent_team_external_id: Optional[str]) -> Optional[str]:
    if not opponent_team_external_id:
        return None
    team = db.query(Team).filter_by(external_id=opponent_team_external_id).one_or_none()
    return team.name if team is not None else None


def _remaining_matches(db: Session, our_team_external_id: str) -> list[dict]:
    rows = (
        db.query(Match)
        .filter(
            Match.is_scored.is_(False),
            Match.is_bye.is_(False),
        )
        .filter(
            (Match.home_team_id == our_team_external_id)
            | (Match.away_team_id == our_team_external_id)
        )
        .order_by(Match.week)
        .all()
    )
    matches = []
    for match in rows:
        opponent_id = (
            match.away_team_id if match.home_team_id == our_team_external_id else match.home_team_id
        )
        matches.append({
            "match_id": match.external_id,
            "opponent_team_id": opponent_id,
            "opponent_team_name": _opponent_team_name(db, opponent_id),
            "week": match.week,
            "session_name": match.session_name,
        })
    return matches


def build(db: Session, our_team_external_id: str, out_dir: Path) -> tuple[Path, Path]:
    our_team_name = _team_name(db, our_team_external_id)
    actual_wins, actual_losses = _latest_record(db, our_team_name)
    our_win_rate = win_rate(actual_wins, actual_losses)

    remaining = _remaining_matches(db, our_team_external_id)
    opponent_rates: dict[str, float] = {}
    for match in remaining:
        opponent_id = match["opponent_team_id"]
        opponent_name = match["opponent_team_name"]
        if not opponent_id or not opponent_name:
            continue
        wins, losses = _latest_record(db, opponent_name)
        rate = win_rate(wins, losses)
        if rate is not None:
            opponent_rates[opponent_id] = rate

    projection = project_remaining_schedule(remaining, our_win_rate, opponent_rates)

    history_rows = [
        {"captured_at": row.captured_at.isoformat() if row.captured_at else "", "wins": row.wins, "losses": row.losses}
        for row in standings_history(db, our_team_name)
    ]
    standings_points = team_volatility_curve(history_rows)
    capture_time = standings_points[-1].captured_at if standings_points else None

    session_name = remaining[0].get("session_name") if remaining else None
    session_name = session_name or "Unknown session"

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / HTML_NAME
    html_path.write_text(
        render(projection, standings_points, our_team_name, session_name,
               actual_wins, actual_losses, capture_time),
        encoding="utf-8",
    )
    xlsx_path = write_excel_workbook(
        projection, standings_points, our_team_external_id, our_team_name, session_name,
        actual_wins, actual_losses, capture_time, out_dir / XLSX_NAME,
    )

    return html_path, xlsx_path


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Path to the SQLite database (default: configured/fallback path)")
    parser.add_argument("--our-team-id", help="Override apa_config.yaml's team.team_id")
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
        html_path, xlsx_path = build(db, our_team_external_id, Path(args.out_dir))
    finally:
        db.close()
        engine.dispose()

    logger.info("Wrote %s", html_path)
    logger.info("Wrote %s", xlsx_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
