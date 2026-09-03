"""Tests for ui.export_json -- the JSON counterpart to ui.export_excel.

Seeds a small in-memory database through the real ingest functions (not
hand-built ORM rows) so this exercises the same path export_to_json will
see in practice, then checks both the returned file's shape and that it's
valid, re-loadable JSON -- the "lightweight validation" the demo's JSON
export needs, independent of whatever HTML consumes it.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.ingest import ingest_match, ingest_match_scores, ingest_standings, upsert_team
from database.models import Base
from ui.export_json import export_to_json

REQUIRED_TOP_LEVEL_KEYS = {"generated_at", "teams", "matches", "standings", "player_stats", "match_scores"}

REQUIRED_MATCH_KEYS = {
    "match_id", "week", "home_team_id", "home_team_name", "away_team_id",
    "away_team_name", "home_score", "away_score", "status", "match_date",
    "is_bye", "is_scored", "is_finalized",
}

REQUIRED_PLAYER_STATS_KEYS = {
    "player", "skill_level", "matches", "wins", "losses", "win_pct",
    "ppm", "pa", "avg_points", "source",
}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def seeded_db(db):
    upsert_team(db, "T1", "Chalk It Up")
    upsert_team(db, "T2", "Rack Attack")
    ingest_match(
        db, match_id="M1", home_team_id="T1", away_team_id="T2",
        home_team_name="Chalk It Up", away_team_name="Rack Attack",
        week=9, status="COMPLETED", home_score=18, away_score=12,
        is_scored=True, is_finalized=True,
    )
    ingest_match_scores(
        db, "M1",
        [
            {"player_id": "P1", "player_name": "Alice", "team_id": "T1", "skill_level": 5,
             "result": "W", "points_earned": 6},
            {"player_id": "P2", "player_name": "Bob", "team_id": "T2", "skill_level": 4,
             "result": "L", "points_earned": 3},
        ],
    )
    ingest_standings(
        db,
        [{"team_name": "Chalk It Up", "rank": 1, "wins": None, "losses": None, "points": 142}],
    )
    return db


def _export(db, tmp_path):
    config = {"export": {"json_output_path": str(tmp_path / "demo.json")}}
    path = export_to_json(db, config)
    return json.loads((tmp_path / "demo.json").read_text())


class TestShape:
    def test_top_level_keys_present(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        assert REQUIRED_TOP_LEVEL_KEYS.issubset(document.keys())

    def test_teams_are_present(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        names = {t["team_name"] for t in document["teams"]}
        assert names == {"Chalk It Up", "Rack Attack"}

    def test_match_row_has_every_required_key(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        assert len(document["matches"]) == 1
        assert REQUIRED_MATCH_KEYS.issubset(document["matches"][0].keys())

    def test_match_scores_round_trip(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        match = document["matches"][0]
        assert match["home_score"] == 18
        assert match["away_score"] == 12
        assert match["is_finalized"] is True

    def test_standings_row_shape(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        assert document["standings"] == [
            {"rank": 1, "team_name": "Chalk It Up", "wins": None, "losses": None, "points": 142.0,
             "captured_at": document["standings"][0]["captured_at"]}
        ]

    def test_player_stats_row_has_every_required_key(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        assert len(document["player_stats"]) == 2
        assert REQUIRED_PLAYER_STATS_KEYS.issubset(document["player_stats"][0].keys())

    def test_player_stats_source_is_match_history(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        sources = {row["source"] for row in document["player_stats"]}
        assert sources == {"match history"}

    def test_match_scores_are_keyed_by_the_matchs_external_id(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        assert set(document["match_scores"].keys()) == {"M1"}
        rows = {r["player"]: r for r in document["match_scores"]["M1"]}
        assert rows["Alice"]["result"] == "W"
        assert rows["Alice"]["points_earned"] == 6.0
        assert rows["Bob"]["result"] == "L"

    def test_a_match_with_no_scoresheet_is_absent_not_an_empty_list(self, db, tmp_path):
        """ingest_viewer_data-only matches never get a scoresheet -- absent
        is more honest than a key that's always there but always empty."""
        upsert_team(db, "T1", "Chalk It Up")
        upsert_team(db, "T2", "Rack Attack")
        ingest_match(
            db, match_id="M2", home_team_id="T1", away_team_id="T2",
            home_team_name="Chalk It Up", away_team_name="Rack Attack",
        )
        document = _export(db, tmp_path)
        assert document["match_scores"] == {}


class TestEmptyDatabase:
    """Nothing ingested yet must produce a valid, empty-list document, not
    an error -- a fresh checkout runs the demo before anything is ingested."""

    def test_empty_database_yields_empty_lists_not_an_error(self, db, tmp_path):
        document = _export(db, tmp_path)
        assert document["teams"] == []
        assert document["matches"] == []
        assert document["standings"] == []
        assert document["player_stats"] == []

    def test_generated_at_is_always_present(self, db, tmp_path):
        document = _export(db, tmp_path)
        assert document["generated_at"]


class TestFileIsValidJson:
    def test_written_file_parses_and_matches_return_value(self, seeded_db, tmp_path):
        config = {"export": {"json_output_path": str(tmp_path / "out.json")}}
        path = export_to_json(seeded_db, config)
        on_disk = json.loads((tmp_path / "out.json").read_text())
        assert str(tmp_path / "out.json") == path
        assert REQUIRED_TOP_LEVEL_KEYS.issubset(on_disk.keys())

    def test_creates_parent_directory(self, seeded_db, tmp_path):
        nested = tmp_path / "nested" / "dir"
        config = {"export": {"json_output_path": str(nested / "out.json")}}
        export_to_json(seeded_db, config)
        assert (nested / "out.json").exists()
