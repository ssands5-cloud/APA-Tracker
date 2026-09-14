"""Tests for scripts/build_captain_first_edge.py (Stage 2).

Seeds a real SQLite database through the actual ORM models, reusing
tests/test_pairing_evidence.py's own fixture helpers so both test files
build rows the same way a schema change would break together.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Match, Team
from scripts.build_captain_first_edge import (
    _team_name,
    build,
    build_match_scopes,
    real_match_scopes,
)
from tests.test_pairing_evidence import (
    FORMAT,
    OPPONENT_TEAM,
    OUR_TEAM,
    SESSION,
    _game,
    _match,
    _player,
    _roster,
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


class TestRealMatchScopes:
    def test_finds_the_real_scope_from_a_scheduled_match(self, db):
        _match(db, "M-1")

        scopes = real_match_scopes(db, OUR_TEAM)

        assert scopes == [(SESSION, OPPONENT_TEAM, FORMAT)]

    def test_our_team_can_be_the_away_side_too(self, db):
        row = Match(
            external_id="M-AWAY", home_team_id=OPPONENT_TEAM, away_team_id=OUR_TEAM,
            format=FORMAT, session_name=SESSION, is_scored=True, is_finalized=True,
        )
        db.add(row)
        db.flush()

        assert real_match_scopes(db, OUR_TEAM) == [(SESSION, OPPONENT_TEAM, FORMAT)]

    def test_a_bye_has_no_real_opponent_and_is_excluded(self, db):
        row = Match(
            external_id="M-BYE", home_team_id=OUR_TEAM, away_team_id=None,
            format=FORMAT, session_name=SESSION, is_bye=True,
        )
        db.add(row)
        db.flush()

        assert real_match_scopes(db, OUR_TEAM) == []

    def test_a_match_not_involving_our_team_is_excluded(self, db):
        row = Match(
            external_id="M-OTHER", home_team_id="TEAM-A", away_team_id="TEAM-B",
            format=FORMAT, session_name=SESSION,
        )
        db.add(row)
        db.flush()

        assert real_match_scopes(db, OUR_TEAM) == []

    def test_duplicate_scopes_across_multiple_matches_collapse(self, db):
        _match(db, "M-1")
        _match(db, "M-2")

        assert real_match_scopes(db, OUR_TEAM) == [(SESSION, OPPONENT_TEAM, FORMAT)]

    def test_two_real_formats_are_two_real_scopes(self, db):
        _match(db, "M-EIGHT", format="EIGHT")
        _match(db, "M-NINE", format="NINE")

        assert real_match_scopes(db, OUR_TEAM) == [
            (SESSION, OPPONENT_TEAM, "EIGHT"),
            (SESSION, OPPONENT_TEAM, "NINE"),
        ]


class TestTeamName:
    def test_a_known_team_resolves_its_real_name(self, db):
        db.add(Team(external_id=OUR_TEAM, name="Chalk It Up"))
        db.flush()

        assert _team_name(db, OUR_TEAM) == "Chalk It Up"

    def test_an_unresolved_team_is_named_honestly_not_guessed(self, db):
        assert _team_name(db, "GHOST-TEAM") == "Unknown opponent (id: GHOST-TEAM)"


class TestBuildMatchScopes:
    def test_a_valid_scope_carries_a_real_matrix(self, db):
        _seed_pair(db)
        _match(db, "M-1")

        [scope] = build_match_scopes(db, OUR_TEAM)

        assert scope.matrix is not None
        assert scope.unavailable_reason is None
        assert scope.matrix.counts["total_feasible_pairings"] == 1

    def test_an_unresolvable_scope_reports_its_real_reason_not_a_crash(self, db):
        player = _player(db, "P-1", "Shared Player")
        _roster(db, player, OUR_TEAM, skill_level=5)
        _roster(db, player, OPPONENT_TEAM, skill_level=5)
        _match(db, "M-1")

        [scope] = build_match_scopes(db, OUR_TEAM)

        assert scope.matrix is None
        assert "both selected teams" in scope.unavailable_reason

    def test_every_real_scope_is_represented_once(self, db):
        _seed_pair(db)
        _match(db, "M-EIGHT", format="EIGHT")
        _match(db, "M-NINE", format="NINE")

        scopes = build_match_scopes(db, OUR_TEAM)

        assert sorted(s.format for s in scopes) == ["EIGHT", "NINE"]
        assert all(s.matrix is not None for s in scopes)


class TestBuildEndToEnd:
    def test_writes_a_real_self_contained_html_file(self, db, tmp_path):
        _seed_pair(db)
        _match(db, "M-1")
        db.add(Team(external_id=OPPONENT_TEAM, name="Corner Pockets"))
        db.flush()

        out_path = build(db, OUR_TEAM, tmp_path)

        assert out_path.name == "captain_first_edge.html"
        html = out_path.read_text(encoding="utf-8")
        assert "Corner Pockets" in html
        assert SESSION in html
        assert "http://" not in html
        assert "https://" not in html

    def test_no_real_scheduled_match_renders_an_honest_empty_state(self, db, tmp_path):
        out_path = build(db, OUR_TEAM, tmp_path)

        html = out_path.read_text(encoding="utf-8")
        assert "No real scheduled match was found" in html
