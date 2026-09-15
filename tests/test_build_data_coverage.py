"""Tests for scripts/build_data_coverage.py."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, PlayerCareerStats, StandingsSnapshot, Team
from scripts.build_data_coverage import (
    _career_stats_refreshed_at,
    _standings_refreshed_at,
    build,
)
from tests.test_pairing_evidence import FORMAT, OPPONENT_TEAM, OUR_TEAM, SESSION, _match, _seed_pair


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


class TestStandingsRefreshedAt:
    def test_real_max_captured_at_for_the_named_team(self, db):
        db.add(StandingsSnapshot(team_name="Chalk It Up", captured_at=None, wins=1, losses=1))
        db.flush()
        row = db.query(StandingsSnapshot).one()
        row.captured_at = __import__("datetime").datetime(2026, 9, 9, 23, 11, 36)
        db.flush()

        assert _standings_refreshed_at(db, "Chalk It Up") == "2026-09-09T23:11:36"

    def test_no_real_row_is_none(self, db):
        assert _standings_refreshed_at(db, "Ghost Team") is None


class TestCareerStatsRefreshedAt:
    def test_real_values_resolved_by_external_id(self, db):
        from database.models import Player
        player = Player(external_id="P-1", name="Paul Smith")
        db.add(player)
        db.flush()
        db.add(PlayerCareerStats(player_id=player.id, format="EIGHT", matches_won=1, matches_played=2))
        db.flush()

        result = _career_stats_refreshed_at(db, {"P-1"})
        assert "P-1" in result

    def test_empty_input_is_an_empty_dict(self, db):
        assert _career_stats_refreshed_at(db, set()) == {}


class TestBuildEndToEnd:
    def test_writes_real_html_and_excel(self, db, tmp_path):
        db.add(Team(external_id=OUR_TEAM, name="Chalk It Up"))
        db.add(Team(external_id=OPPONENT_TEAM, name="Corner Pockets"))
        db.flush()
        _seed_pair(db)
        _match(db, "M-1")

        html_path, xlsx_path = build(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION, tmp_path)

        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "Chalk It Up" in html
        assert "Corner Pockets" in html

        assert xlsx_path.exists()
