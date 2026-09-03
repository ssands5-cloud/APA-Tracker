#!/usr/bin/env python3
"""Build a demo database + Excel export from the sanitized test fixtures.

No network call, no login, no token -- this runs the exact same ingestion
code the live sync uses (scheduler.graphql_sync.ingest_viewer_data,
database.ingest.ingest_standings/ingest_match/ingest_match_scores,
ui.export_excel.export_to_excel), pointed at tests/fixtures/*.json instead
of a real GraphQL response. That's the whole point: what this produces is
what the real pipeline produces, not a hand-typed mockup.

The four fixtures were written independently (one per row-mapper's own
test), so they don't share one consistent set of team/match ids -- treat
this as two honest, separately-sourced illustrations glued into one
workbook, not a single fabricated season. Each section below says which
fixture it came from.

Usage:
    python scripts/build_demo.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from sqlalchemy.orm import Session

from database.engine import create_db_engine
from database.ingest import ingest_match, ingest_match_scores, ingest_standings
from scheduler.graphql_sync import ingest_viewer_data
from scraper.graphql_scraper import division_standings_rows, match_player_scores
from ui.export_excel import export_to_excel
from ui.export_json import export_to_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

FIXTURES = _project_root / "tests" / "fixtures"
DEMO_DB_PATH = "data/demo_apa_tracker.db"
DEMO_EXCEL_PATH = "exports/demo_apa_stats.xlsx"
DEMO_JSON_PATH = "exports/demo_apa_data.json"

DEMO_CONFIG = {
    "database": {"path": DEMO_DB_PATH},
    "export": {"excel_output_path": DEMO_EXCEL_PATH, "json_output_path": DEMO_JSON_PATH},
}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def main() -> None:
    db_file = _project_root / DEMO_DB_PATH
    if db_file.exists():
        db_file.unlink()
        logger.info("Removed previous demo database at %s", db_file)

    dashboard_teams = _load("dashboard_teams_response.json")["data"]["viewer"]
    matches_by_viewer = _load("matches_by_viewer_response.json")["data"]["viewer"]
    division = _load("division_standings_response.json")["data"]["division"]
    match_detail = _load("match_detail_response.json")["data"]["match"]

    engine = create_db_engine(DEMO_CONFIG)
    with Session(engine) as db:
        # 1 & 2. dashboardTeams + matchesByViewer -- every team this (fictional)
        # account plays on, plus every one of those teams' matches, in one pass.
        counts = ingest_viewer_data(db, dashboard_teams, matches_by_viewer)
        logger.info(
            "ingest_viewer_data: %d team(s), %d match(es) (%d new, %d bye, %d unscored)",
            counts["teams"], counts["matches_seen"], counts["matches_new"],
            counts["byes"], counts["unscored"],
        )

        # 3. divisionStandings -- one division's full team table, ranked by points.
        standings_rows = division_standings_rows(division)
        ingest_standings(db, standings_rows)
        logger.info("ingest_standings: %d team(s) in division %s", len(standings_rows), division.get("id"))

        # 4. MatchPage (match detail) -- the one query with real per-player
        # stats: skill level, win/loss, points earned, forfeit/incomplete
        # flags. Needs the Match row to exist first (ingest_match), exactly
        # like a live sync walking a schedule and then fetching detail for
        # each scored match id.
        home, away = match_detail.get("home") or {}, match_detail.get("away") or {}
        home_result = next((r for r in match_detail["results"] if r["homeAway"] == "HOME"), {})
        away_result = next((r for r in match_detail["results"] if r["homeAway"] == "AWAY"), {})
        ingest_match(
            db,
            match_id=str(match_detail["id"]),
            home_team_id=str(home.get("id") or ""),
            away_team_id=str(away.get("id") or ""),
            home_team_name=home.get("name") or "",
            away_team_name=away.get("name") or "",
            match_date=match_detail.get("startTime"),
            status="COMPLETED" if match_detail.get("isFinalized") else "IN PROGRESS",
            home_score=(home_result.get("points") or {}).get("total"),
            away_score=(away_result.get("points") or {}).get("total"),
            week=match_detail.get("week"),
            is_bye=bool(match_detail.get("isBye")),
            is_scored=bool(match_detail.get("isScored")),
            is_finalized=bool(match_detail.get("isFinalized")),
        )
        scores = match_player_scores(match_detail)
        created, updated = ingest_match_scores(db, str(match_detail["id"]), scores)
        logger.info(
            "ingest_match_scores: %d player scoresheet row(s) for match %s (%d new, %d updated)",
            len(scores), match_detail["id"], created, updated,
        )

        excel_path = export_to_excel(db, DEMO_CONFIG)
        json_path = export_to_json(db, DEMO_CONFIG)

    print(f"\nDemo workbook written to {excel_path}")
    print(f"Demo JSON written to {json_path}")
    print(f"Demo database written to {db_file}")


if __name__ == "__main__":
    main()
