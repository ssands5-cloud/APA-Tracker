"""Tests for scripts/build_team_strength.py."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Match, Player, PlayerTeamHistory, StandingsSnapshot, Team
from database.queries import CanonicalRosterError
from scripts.build_team_strength import _eligible_matches, _roster_players, _standings, build

OUR_TEAM = "T-OUR"
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


def _add_player(db, external_id, name, skill=5):
    player = Player(external_id=external_id, name=name, skill_level=skill)
    db.add(player)
    db.flush()
    return player


class TestRosterPlayers:
    def test_returns_canonical_current_roster_joined_to_player(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=OUR_TEAM, session_name=SESSION,
            is_current=True, matches_won=5, matches_played=10, skill_level=6,
        ))
        db.flush()

        players = _roster_players(db, OUR_TEAM, SESSION)

        assert len(players) == 1
        assert players[0]["player_external_id"] == "P1"
        assert players[0]["player_name"] == "Alice"
        assert players[0]["matches_won"] == 5

    def test_duplicate_current_rows_raise_not_silently_pick_one(self, db):
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=OUR_TEAM, session_name=SESSION, is_current=True,
        ))
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=OUR_TEAM, session_name=SESSION, is_current=True,
        ))
        db.flush()

        with pytest.raises(CanonicalRosterError):
            _roster_players(db, OUR_TEAM, SESSION)

    def test_no_canonical_roster_is_an_empty_list(self, db):
        assert _roster_players(db, OUR_TEAM, SESSION) == []


class TestEligibleMatches:
    def test_finds_finalized_scored_non_bye_matches(self, db):
        db.add(Team(external_id=OPPONENT_TEAM, name="Corner Pockets"))
        db.add(Match(
            external_id="M1", home_team_id=OUR_TEAM, away_team_id=OPPONENT_TEAM,
            session_name=SESSION, is_bye=False, is_scored=True, is_finalized=True,
            home_score=8, away_score=2, week=3, format="8-Ball Open",
        ))
        db.flush()

        matches = _eligible_matches(db, OUR_TEAM, SESSION)

        assert len(matches) == 1
        assert matches[0]["points_for"] == 8
        assert matches[0]["points_against"] == 2
        assert matches[0]["opponent_team_name"] == "Corner Pockets"
        assert matches[0]["is_home"] is True

    def test_unfinalized_match_is_excluded(self, db):
        db.add(Match(
            external_id="M1", home_team_id=OUR_TEAM, away_team_id=OPPONENT_TEAM,
            session_name=SESSION, is_bye=False, is_scored=True, is_finalized=False,
            home_score=8, away_score=2,
        ))
        db.flush()
        assert _eligible_matches(db, OUR_TEAM, SESSION) == []

    def test_bye_is_excluded(self, db):
        db.add(Match(
            external_id="M1", home_team_id=OUR_TEAM, away_team_id=None,
            session_name=SESSION, is_bye=True, is_scored=True, is_finalized=True,
            home_score=8, away_score=0,
        ))
        db.flush()
        assert _eligible_matches(db, OUR_TEAM, SESSION) == []

    def test_away_side_swaps_points_for_and_against(self, db):
        db.add(Team(external_id=OPPONENT_TEAM, name="Corner Pockets"))
        db.add(Match(
            external_id="M1", home_team_id=OPPONENT_TEAM, away_team_id=OUR_TEAM,
            session_name=SESSION, is_bye=False, is_scored=True, is_finalized=True,
            home_score=6, away_score=4,
        ))
        db.flush()

        matches = _eligible_matches(db, OUR_TEAM, SESSION)

        assert matches[0]["points_for"] == 4
        assert matches[0]["points_against"] == 6
        assert matches[0]["is_home"] is False


class TestStandings:
    def test_resolves_by_team_name(self, db):
        db.add(StandingsSnapshot(team_name="Chalk It Up", wins=5, losses=2, rank=1))
        db.flush()
        rank, record = _standings(db, "Chalk It Up")
        assert rank == 1
        assert record == "5-2"

    def test_no_capture_is_none_none(self, db):
        assert _standings(db, "Ghost Team") == (None, None)


class TestBuildEndToEnd:
    def test_writes_real_html_and_excel(self, db, tmp_path):
        db.add(Team(external_id=OUR_TEAM, name="Chalk It Up"))
        db.add(Team(external_id=OPPONENT_TEAM, name="Corner Pockets"))
        player = _add_player(db, "P1", "Alice")
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=OUR_TEAM, session_name=SESSION,
            is_current=True, matches_won=5, matches_played=10,
        ))
        db.add(Match(
            external_id="M1", home_team_id=OUR_TEAM, away_team_id=OPPONENT_TEAM,
            session_name=SESSION, is_bye=False, is_scored=True, is_finalized=True,
            home_score=8, away_score=2, format="8-Ball Open",
        ))
        db.add(StandingsSnapshot(team_name="Chalk It Up", wins=5, losses=2, rank=1))
        db.flush()

        html_path, xlsx_path = build(db, OUR_TEAM, SESSION, tmp_path)

        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "Chalk It Up" in html
        assert "Alice" in html

        assert xlsx_path.exists()

    def test_empty_team_is_still_an_honest_page(self, db, tmp_path):
        db.add(Team(external_id=OUR_TEAM, name="Chalk It Up"))
        db.flush()

        html_path, xlsx_path = build(db, OUR_TEAM, SESSION, tmp_path)

        html = html_path.read_text(encoding="utf-8")
        assert "No data" in html
        assert xlsx_path.exists()
