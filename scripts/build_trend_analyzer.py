"""Build the dedicated Trend Analyzer view for one real team/session
(docs/trend_analyzer.md).

Writes:

    exports/trend_analyzer.html
    exports/trend_analyzer.xlsx

Read-only (mode=ro), same posture as every other builder in this project.
Database population is a separate, explicit phase: this script does NOT
call scripts/build_player_trends.py, mutate PlayerTrend aggregates, or
silently substitute a different session/format. It reads the already-
persisted PlayerTrend rows for the team's canonical current roster and the
underlying PlayerMatch/Match chronology for the Trend History sheet, then
hands both to the pure analytics.trend_analyzer module, which introduces no
second trend formula.

Usage:
    python scripts/build_trend_analyzer.py --session "Fall 2026"
    python scripts/build_trend_analyzer.py --session "Fall 2026" --format "8-ball"
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

from analytics.player_trends import normalize_format
from analytics.trend_analyzer import build_report
from database.models import Match, Player, PlayerMatch, PlayerTrend
from database.queries import canonical_current_roster
from scripts.build_captain_first_edge import _configured_our_team_id, _team_name
from scripts.build_captains_edge import NoDatabaseError, connect_read_only, resolve_db_path
from ui.export_excel_trend_analyzer import write_workbook as write_excel_workbook
from ui.tabs.trend_analyzer import render

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "exports"
HTML_NAME = "trend_analyzer.html"
XLSX_NAME = "trend_analyzer.xlsx"


def _roster_player_ids(db: Session, team_external_id: str, session_name: str) -> set[int]:
    return {row.player_id for row in canonical_current_roster(db, team_external_id, session_name)}


def _trend_rows(
    db: Session, player_ids: set[int], session_name: str, format_: Optional[str]
) -> list[dict]:
    """Already-persisted PlayerTrend rows for this roster/session, joined to
    Player for external_id/name -- no formula is recomputed here."""
    if not player_ids:
        return []
    query = (
        db.query(PlayerTrend, Player)
        .join(Player, Player.id == PlayerTrend.player_id)
        .filter(PlayerTrend.player_id.in_(player_ids))
        .filter(PlayerTrend.session_name == session_name)
    )
    normalized_format = normalize_format(format_) if format_ else None
    rows = []
    for trend, player in query.all():
        if normalized_format and trend.format != normalized_format:
            continue
        rows.append({
            "player_id": trend.player_id,
            "player_external_id": player.external_id,
            "player_name": player.name,
            "format": trend.format,
            "session_name": trend.session_name,
            "sample_size": trend.sample_size,
            "current_skill_level": trend.current_skill_level,
            "regression_slope": trend.regression_slope,
            "volatility": trend.volatility,
            "sl_stability": trend.sl_stability,
            "hot_cold_flag": trend.hot_cold_flag,
            "projected_sl_change_probability": trend.projected_sl_change_probability,
        })
    return rows


def _history_rows(
    db: Session, player_ids: set[int], session_name: str, format_: Optional[str]
) -> list[dict]:
    """Real chronological skill-level observations for this roster/session,
    ordered the same way scripts/build_player_trends.py orders them (week
    then match id) -- read-only, no aggregate is written."""
    if not player_ids:
        return []
    normalized_format = normalize_format(format_) if format_ else None
    rows = (
        db.query(PlayerMatch, Match, Player)
        .join(Match, Match.id == PlayerMatch.match_id)
        .join(Player, Player.id == PlayerMatch.player_id)
        .filter(PlayerMatch.player_id.in_(player_ids))
        .filter(Match.session_name == session_name)
        .all()
    )

    grouped: dict[int, list[tuple[Match, PlayerMatch, Player]]] = defaultdict(list)
    for player_match, match, player in rows:
        if not match.format:
            continue
        if normalized_format and normalize_format(match.format) != normalized_format:
            continue
        grouped[player_match.player_id].append((match, player_match, player))

    history: list[dict] = []
    for player_id, group in grouped.items():
        group.sort(key=lambda triple: (triple[0].week if triple[0].week is not None else 0, triple[0].id))
        for order, (match, player_match, player) in enumerate(group, start=1):
            history.append({
                "player_id": player_id,
                "player_external_id": player.external_id,
                "match_id": match.external_id,
                "match_order": order,
                "match_date": match.match_date,
                "format": normalize_format(match.format),
                "session_name": match.session_name,
                "skill_level": player_match.skill_level,
            })
    return history


def build(
    db: Session, our_team_external_id: str, session_name: str, out_dir: Path,
    format_: Optional[str] = None,
) -> tuple[Path, Path]:
    team_name = _team_name(db, our_team_external_id)
    player_ids = _roster_player_ids(db, our_team_external_id, session_name)
    trend_rows = _trend_rows(db, player_ids, session_name, format_)
    history_rows = _history_rows(db, player_ids, session_name, format_)

    report = build_report(
        our_team_external_id, team_name, session_name, trend_rows, history_rows,
        format=normalize_format(format_) if format_ else None,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / HTML_NAME
    html_path.write_text(render(report), encoding="utf-8")
    xlsx_path = write_excel_workbook(report, out_dir / XLSX_NAME)

    return html_path, xlsx_path


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Path to the SQLite database (default: configured/fallback path)")
    parser.add_argument("--our-team-id", help="Override apa_config.yaml's team.team_id")
    parser.add_argument("--session", required=True, help='e.g. "Fall 2026"')
    parser.add_argument("--format", help='e.g. "8-ball" or "8-Ball Open"')
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
        html_path, xlsx_path = build(db, our_team_external_id, args.session, Path(args.out_dir), args.format)
    finally:
        db.close()
        engine.dispose()

    logger.info("Wrote %s", html_path)
    logger.info("Wrote %s", xlsx_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
