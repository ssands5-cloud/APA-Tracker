"""Tests for scripts/build_player_vs_player_export.py.

Seeds a real database through the ORM the same way
tests/test_build_captain_first_edge.py does, reusing
tests/test_pairing_evidence.py's own fixture helpers.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Match
from scripts.build_player_vs_player_export import _match_dates_for, build
from tests.test_pairing_evidence import (
    FORMAT,
    OPPONENT_TEAM,
    OUR_TEAM,
    SESSION,
    _game,
    _match,
    _seed_pair,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


class TestMatchDates:
    def test_resolves_real_dates_for_the_given_ids(self, db):
        match = Match(external_id="M-1", home_team_id=OUR_TEAM, away_team_id=OPPONENT_TEAM,
                       format=FORMAT, session_name=SESSION, match_date="2026-08-01",
                       is_scored=True, is_finalized=True)
        db.add(match)
        db.flush()

        dates = _match_dates_for(db, {match.id})
        assert dates == {match.id: "2026-08-01"}

    def test_an_unmapped_or_dateless_match_is_simply_absent(self, db):
        match = Match(external_id="M-1", home_team_id=OUR_TEAM, away_team_id=OPPONENT_TEAM,
                       format=FORMAT, session_name=SESSION, match_date=None)
        db.add(match)
        db.flush()

        assert _match_dates_for(db, {match.id}) == {}
        assert _match_dates_for(db, set()) == {}


class TestBuildEndToEnd:
    def test_writes_real_html_and_excel_for_a_direct_pairing(self, db, tmp_path):
        player, opponent = _seed_pair(db)
        match = _match(db, "M-1")
        _game(db, player, opponent, match, "W")

        html_path, xlsx_path = build(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION, tmp_path)

        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "DIRECT" in html
        assert "Our Player vs Opponent Player" in html

        assert xlsx_path is not None
        assert xlsx_path.exists()

    def test_no_feasible_pairings_writes_html_but_omits_the_workbook(self, db, tmp_path):
        html_path, xlsx_path = build(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION, tmp_path)

        assert html_path.exists()
        assert "No feasible pairings" in html_path.read_text(encoding="utf-8")
        assert xlsx_path is None

    def test_real_match_dates_flow_through_to_the_html(self, db, tmp_path):
        player, opponent = _seed_pair(db)
        match = _match(db, "M-1")
        db_match = db.query(Match).filter_by(external_id="M-1").one()
        db_match.match_date = "2026-08-15"
        db.flush()
        _game(db, player, opponent, db_match, "W")

        html_path, _ = build(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION, tmp_path)

        assert "2026-08-15" in html_path.read_text(encoding="utf-8")
