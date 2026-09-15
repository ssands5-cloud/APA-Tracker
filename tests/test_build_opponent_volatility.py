"""Tests for scripts/build_opponent_volatility.py."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Player, PlayerTeamHistory, PlayerTrend, Team
from database.queries import CanonicalRosterError
from scripts.build_opponent_volatility import (
    DuplicateTrendError,
    _roster_players,
    _trend_by_player_id,
    build,
)

OPPONENT_TEAM = "T-OPP"
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


class TestRosterPlayers:
    def test_returns_canonical_current_roster_joined_to_player(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=OPPONENT_TEAM, session_name=SESSION, is_current=True,
        ))
        db.flush()
        players = _roster_players(db, OPPONENT_TEAM, SESSION)
        assert len(players) == 1
        assert players[0]["player_external_id"] == "P1"

    def test_duplicate_current_rows_raise(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=OPPONENT_TEAM, session_name=SESSION, is_current=True,
        ))
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=OPPONENT_TEAM, session_name=SESSION, is_current=True,
        ))
        db.flush()
        with pytest.raises(CanonicalRosterError):
            _roster_players(db, OPPONENT_TEAM, SESSION)


class TestTrendByPlayerId:
    def test_reads_at_most_one_trend_per_player(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTrend(
            player_id=player.id, format="8-ball", session_name=SESSION, sample_size=5,
            current_skill_level=6, volatility=0.2,
        ))
        db.flush()
        by_id = _trend_by_player_id(db, [player.id], SESSION, None)
        assert player.id in by_id
        assert by_id[player.id]["volatility"] == 0.2

    def test_duplicate_trend_rows_raise(self, db):
        # Two distinct persisted (unnormalized) format strings for the same
        # player/session both survive PlayerTrend's real DB unique
        # constraint (player_id, format, session_name) -- but collide once
        # this builder groups by player id alone (no --format filter given).
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTrend(
            player_id=player.id, format="8-Ball Open", session_name=SESSION, sample_size=5, current_skill_level=6,
        ))
        db.add(PlayerTrend(
            player_id=player.id, format="8-ball", session_name=SESSION, sample_size=6, current_skill_level=7,
        ))
        db.flush()
        with pytest.raises(DuplicateTrendError):
            _trend_by_player_id(db, [player.id], SESSION, None)

    def test_format_filter_normalizes(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTrend(
            player_id=player.id, format="8-ball", session_name=SESSION, sample_size=5, current_skill_level=6,
        ))
        db.flush()
        by_id = _trend_by_player_id(db, [player.id], SESSION, "8-Ball Open")
        assert player.id in by_id


class TestBuildEndToEnd:
    def test_writes_real_html_and_excel(self, db, tmp_path):
        db.add(Team(external_id=OPPONENT_TEAM, name="Corner Pockets"))
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=OPPONENT_TEAM, session_name=SESSION, is_current=True,
        ))
        db.add(PlayerTrend(
            player_id=player.id, format="8-ball", session_name=SESSION, sample_size=5,
            current_skill_level=6, volatility=0.2, sl_stability=0.833,
        ))
        db.flush()

        html_path, xlsx_path = build(db, OPPONENT_TEAM, SESSION, tmp_path)

        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "Corner Pockets" in html
        assert "Alice" in html
        assert xlsx_path.exists()

    def test_empty_roster_is_still_an_honest_page(self, db, tmp_path):
        db.add(Team(external_id=OPPONENT_TEAM, name="Corner Pockets"))
        db.flush()

        html_path, xlsx_path = build(db, OPPONENT_TEAM, SESSION, tmp_path)

        html = html_path.read_text(encoding="utf-8")
        assert "No canonical opponent roster player found" in html
        assert xlsx_path.exists()
