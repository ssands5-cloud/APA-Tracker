"""Tests for scripts/build_season_projection.py."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Match, StandingsSnapshot, Team
from scripts.build_season_projection import _latest_record, _remaining_matches, build

OUR_TEAM = "T-OUR"
OPPONENT_TEAM = "T-OPP"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


class TestLatestRecord:
    def test_returns_the_most_recent_real_capture(self, db):
        db.add(StandingsSnapshot(team_name="Chalk It Up", wins=1, losses=0,
                                  captured_at=datetime.datetime(2026, 9, 1)))
        db.add(StandingsSnapshot(team_name="Chalk It Up", wins=2, losses=0,
                                  captured_at=datetime.datetime(2026, 9, 3)))
        db.flush()

        wins, losses = _latest_record(db, "Chalk It Up")
        assert (wins, losses) == (2, 0)

    def test_no_real_capture_is_none_none(self, db):
        assert _latest_record(db, "Ghost Team") == (None, None)


class TestRemainingMatches:
    def test_finds_real_unscored_non_bye_matches_for_our_team(self, db):
        db.add(Team(external_id=OPPONENT_TEAM, name="Corner Pockets"))
        db.add(Match(external_id="M1", home_team_id=OUR_TEAM, away_team_id=OPPONENT_TEAM,
                     is_scored=False, is_bye=False, week=5, session_name="Fall 2026"))
        db.add(Match(external_id="M2", home_team_id=OUR_TEAM, away_team_id=OPPONENT_TEAM,
                     is_scored=True, is_bye=False, week=4, session_name="Fall 2026"))
        db.flush()

        matches = _remaining_matches(db, OUR_TEAM)

        assert len(matches) == 1
        assert matches[0]["match_id"] == "M1"
        assert matches[0]["opponent_team_name"] == "Corner Pockets"

    def test_a_bye_is_excluded(self, db):
        db.add(Match(external_id="M-BYE", home_team_id=OUR_TEAM, away_team_id=None,
                     is_scored=False, is_bye=True, week=5))
        db.flush()
        assert _remaining_matches(db, OUR_TEAM) == []

    def test_unresolved_opponent_team_name_is_none_not_guessed(self, db):
        db.add(Match(external_id="M1", home_team_id=OUR_TEAM, away_team_id="T-GHOST",
                     is_scored=False, is_bye=False, week=5))
        db.flush()

        matches = _remaining_matches(db, OUR_TEAM)
        assert matches[0]["opponent_team_name"] is None


class TestBuildEndToEnd:
    def test_writes_real_html_and_excel(self, db, tmp_path):
        db.add(Team(external_id=OUR_TEAM, name="Chalk It Up"))
        db.add(Team(external_id=OPPONENT_TEAM, name="Corner Pockets"))
        db.add(StandingsSnapshot(team_name="Chalk It Up", wins=5, losses=2,
                                  captured_at=datetime.datetime(2026, 9, 1)))
        db.add(StandingsSnapshot(team_name="Corner Pockets", wins=3, losses=4,
                                  captured_at=datetime.datetime(2026, 9, 1)))
        db.add(Match(external_id="M1", home_team_id=OUR_TEAM, away_team_id=OPPONENT_TEAM,
                     is_scored=False, is_bye=False, week=6, session_name="Fall 2026"))
        db.flush()

        html_path, xlsx_path = build(db, OUR_TEAM, tmp_path)

        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "Chalk It Up" in html
        assert "5-2" in html
        assert "Corner Pockets" in html

        assert xlsx_path.exists()

    def test_no_standings_and_no_schedule_is_still_an_honest_page(self, db, tmp_path):
        db.add(Team(external_id=OUR_TEAM, name="Chalk It Up"))
        db.flush()

        html_path, xlsx_path = build(db, OUR_TEAM, tmp_path)

        html = html_path.read_text(encoding="utf-8")
        assert "No data" in html
        assert xlsx_path.exists()
