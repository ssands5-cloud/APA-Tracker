"""Tests for scripts/build_trend_analyzer.py."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Match, Player, PlayerMatch, PlayerTeamHistory, PlayerTrend, Team
from scripts.build_trend_analyzer import _history_rows, _roster_player_ids, _trend_rows, build

OUR_TEAM = "T-OUR"
SESSION = "Fall 2026"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


def _add_player(db, external_id, name):
    player = Player(external_id=external_id, name=name)
    db.add(player)
    db.flush()
    return player


class TestRosterPlayerIds:
    def test_returns_canonical_current_roster_ids(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=OUR_TEAM, session_name=SESSION, is_current=True,
        ))
        db.flush()
        assert _roster_player_ids(db, OUR_TEAM, SESSION) == {player.id}

    def test_no_roster_is_empty_set(self, db):
        assert _roster_player_ids(db, OUR_TEAM, SESSION) == set()


class TestTrendRows:
    def test_reads_persisted_trend_without_recomputing(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTrend(
            player_id=player.id, format="8-ball", session_name=SESSION, sample_size=5,
            current_skill_level=6, regression_slope=0.1, volatility=0.2,
            sl_stability=0.833333, hot_cold_flag="HOT", projected_sl_change_probability=0.3,
        ))
        db.flush()

        rows = _trend_rows(db, {player.id}, SESSION, None)

        assert len(rows) == 1
        assert rows[0]["player_external_id"] == "P1"
        assert rows[0]["regression_slope"] == 0.1

    def test_format_filter_normalizes_before_comparing(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTrend(
            player_id=player.id, format="8-ball", session_name=SESSION, sample_size=5,
            current_skill_level=6,
        ))
        db.flush()

        rows = _trend_rows(db, {player.id}, SESSION, "8-Ball Open")

        assert len(rows) == 1

    def test_no_player_ids_is_empty_list(self, db):
        assert _trend_rows(db, set(), SESSION, None) == []


class TestHistoryRows:
    def test_orders_chronologically_by_week_then_match_id(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(Match(external_id="M2", session_name=SESSION, format="8-Ball Open", week=2))
        db.add(Match(external_id="M1", session_name=SESSION, format="8-Ball Open", week=1))
        db.flush()
        m1 = db.query(Match).filter_by(external_id="M1").one()
        m2 = db.query(Match).filter_by(external_id="M2").one()
        db.add(PlayerMatch(player_id=player.id, match_id=m2.id, skill_level=6))
        db.add(PlayerMatch(player_id=player.id, match_id=m1.id, skill_level=5))
        db.flush()

        history = _history_rows(db, {player.id}, SESSION, None)

        assert [h["match_id"] for h in history] == ["M1", "M2"]
        assert [h["skill_level"] for h in history] == [5, 6]

    def test_match_missing_format_is_excluded(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(Match(external_id="M1", session_name=SESSION, format=None, week=1))
        db.flush()
        match = db.query(Match).filter_by(external_id="M1").one()
        db.add(PlayerMatch(player_id=player.id, match_id=match.id, skill_level=5))
        db.flush()

        assert _history_rows(db, {player.id}, SESSION, None) == []


class TestBuildEndToEnd:
    def test_writes_real_html_and_excel(self, db, tmp_path):
        db.add(Team(external_id=OUR_TEAM, name="Chalk It Up"))
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=OUR_TEAM, session_name=SESSION, is_current=True,
        ))
        db.add(PlayerTrend(
            player_id=player.id, format="8-ball", session_name=SESSION, sample_size=5,
            current_skill_level=6, regression_slope=0.1, volatility=0.2,
            hot_cold_flag="HOT",
        ))
        db.flush()

        html_path, xlsx_path = build(db, OUR_TEAM, SESSION, tmp_path)

        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "Alice" in html
        assert xlsx_path.exists()

    def test_empty_team_is_still_an_honest_page(self, db, tmp_path):
        db.add(Team(external_id=OUR_TEAM, name="Chalk It Up"))
        db.flush()

        html_path, xlsx_path = build(db, OUR_TEAM, SESSION, tmp_path)

        html = html_path.read_text(encoding="utf-8")
        assert "No measured player trends" in html
        assert xlsx_path.exists()
