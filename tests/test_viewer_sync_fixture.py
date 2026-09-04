"""ingest_viewer_data() -- the multi-team ingestion path -- end to end:
sanitized fixtures -> normalization -> SQLite.

Uses the same two fixtures as test_dashboard_teams_fixture.py and
test_matches_by_viewer_fixture.py, shaped to match the real captures that
proved a single hardcoded team_id cannot express an account playing on
multiple teams. No live call anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Match, Team
from scheduler.graphql_sync import ingest_viewer_data

TEAMS = json.loads(
    (Path(__file__).parent / "fixtures" / "dashboard_teams_response.json").read_text()
)["data"]["viewer"]
MATCHES = json.loads(
    (Path(__file__).parent / "fixtures" / "matches_by_viewer_response.json").read_text()
)["data"]["viewer"]


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestIngestViewerData:
    def test_all_four_teams_land_in_the_database(self, db):
        counts = ingest_viewer_data(db, TEAMS, MATCHES)
        assert counts["teams"] == 4
        assert {t.name for t in db.query(Team).all()} == {
            "Chalk It Up", "Rack Attack", "Side Pocket Squad", "Weekend Warriors",
        }

    def test_matches_from_both_teams_are_ingested(self, db):
        counts = ingest_viewer_data(db, TEAMS, MATCHES)
        assert counts["matches_seen"] == 2
        assert counts["matches_new"] == 2
        assert db.query(Match).count() == 2

    def test_the_bye_is_recorded_with_a_bye_marker_team_name(self, db):
        ingest_viewer_data(db, TEAMS, MATCHES)
        bye = db.query(Match).filter_by(external_id="51419677").one()
        assert bye.is_bye is True
        assert bye.away_team_name == "BYE"

    def test_rerunning_updates_rather_than_duplicates(self, db):
        ingest_viewer_data(db, TEAMS, MATCHES)
        second = ingest_viewer_data(db, TEAMS, MATCHES)
        assert second["matches_new"] == 0
        assert second["matches_updated"] == 2
        assert db.query(Match).count() == 2

    def test_counts_reflect_byes_and_unscored(self, db):
        counts = ingest_viewer_data(db, TEAMS, MATCHES)
        assert counts["byes"] == 1
        assert counts["unscored"] == 1  # the bye itself is unscored too

    def test_empty_viewer_data_ingests_nothing_and_does_not_crash(self, db):
        counts = ingest_viewer_data(db, {}, {})
        assert counts == {
            "teams": 0, "matches_seen": 0, "matches_new": 0, "matches_updated": 0,
            "byes": 0, "unscored": 0,
        }
