"""Build the Team Strength view for one real team/session
(docs/team_strength.md).

Writes:

    exports/team_strength.html
    exports/team_strength.xlsx

Read-only (mode=ro), same posture as every other builder in this project.
Assembles real, already-guarded rows -- canonical current roster via
database.queries.canonical_current_roster (exact team_external_id + session,
raises CanonicalRosterError on a duplicate-identity roster rather than
silently choosing one row), and eligible (finalized, scored, non-bye) Match
rows for that team -- then hands them to the pure analytics.team_strength
module, which does no querying of its own.

Standings are resolved by team display name (StandingsSnapshot has no team
id column, the same disclosed limitation scripts/build_season_projection.py
already documents): an unresolved or absent capture leaves standings as
None, never guessed.

Usage:
    python scripts/build_team_strength.py --session "Fall 2026"
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

from analytics.team_strength import build_report
from database.models import Match, Player, Team
from database.queries import CanonicalRosterError, canonical_current_roster
from scripts.build_captain_first_edge import _configured_our_team_id, _team_name
from scripts.build_captains_edge import NoDatabaseError, connect_read_only, resolve_db_path
from ui.export_excel_team_strength import write_workbook as write_excel_workbook
from ui.tabs.team_strength import render

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "exports"
HTML_NAME = "team_strength.html"
XLSX_NAME = "team_strength.xlsx"


def _roster_players(db: Session, team_external_id: str, session_name: str) -> list[dict]:
    """Canonical current roster rows joined to Player for external_id/name,
    in the dict shape analytics.team_strength.build_report expects."""
    rows = canonical_current_roster(db, team_external_id, session_name)
    players = []
    for row in rows:
        player = db.query(Player).filter_by(id=row.player_id).one_or_none()
        if player is None:
            continue
        players.append({
            "player_id": player.id,
            "player_external_id": player.external_id,
            "player_name": player.name,
            "skill_level": row.skill_level,
            "matches_won": row.matches_won or 0,
            "matches_played": row.matches_played or 0,
        })
    return players


def _opponent_team_name(db: Session, opponent_team_external_id: Optional[str]) -> Optional[str]:
    if not opponent_team_external_id:
        return None
    team = db.query(Team).filter_by(external_id=opponent_team_external_id).one_or_none()
    return team.name if team is not None else None


def _eligible_matches(db: Session, team_external_id: str, session_name: str) -> list[dict]:
    """Real, finalized, scored, non-bye matches for this team/session with
    both scores present -- the doc's required guard for the defense proxy
    and match sample."""
    rows = (
        db.query(Match)
        .filter(
            Match.session_name == session_name,
            Match.is_bye.is_(False),
            Match.is_scored.is_(True),
            Match.is_finalized.is_(True),
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
        )
        .filter(
            (Match.home_team_id == team_external_id) | (Match.away_team_id == team_external_id)
        )
        .order_by(Match.week)
        .all()
    )
    matches = []
    for match in rows:
        is_home = match.home_team_id == team_external_id
        opponent_id = match.away_team_id if is_home else match.home_team_id
        matches.append({
            "match_id": match.external_id,
            "match_date": match.match_date,
            "week": match.week,
            "format": match.format,
            "session_name": match.session_name,
            "opponent_team_id": opponent_id,
            "opponent_team_name": _opponent_team_name(db, opponent_id),
            "is_home": is_home,
            "points_for": match.home_score if is_home else match.away_score,
            "points_against": match.away_score if is_home else match.home_score,
        })
    return matches


def _standings(db: Session, team_name: str) -> tuple[Optional[int], Optional[str]]:
    from database.queries import standings_history

    history = standings_history(db, team_name)
    if not history:
        return None, None
    latest = history[-1]
    record = (
        f"{latest.wins}-{latest.losses}"
        if latest.wins is not None and latest.losses is not None
        else None
    )
    return latest.rank, record


def build(
    db: Session, our_team_external_id: str, session_name: str, out_dir: Path
) -> tuple[Path, Path]:
    team_name = _team_name(db, our_team_external_id)
    players = _roster_players(db, our_team_external_id, session_name)
    matches = _eligible_matches(db, our_team_external_id, session_name)
    current_rank, standings_record = _standings(db, team_name)

    # Match carries no division_id column; only format is available, and
    # only when at least one eligible match established it.
    format_name = matches[0]["format"] if matches else None

    report = build_report(
        our_team_external_id, team_name, session_name, players, matches,
        division_id=None, format=format_name, source_manifest_id=None, captured_at=None,
        current_rank=current_rank, standings_record=standings_record,
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
        html_path, xlsx_path = build(db, our_team_external_id, args.session, Path(args.out_dir))
    except CanonicalRosterError as exc:
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
