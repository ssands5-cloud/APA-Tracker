"""Tests for scripts/build_captain_first_edge.py (Stage 2).

Seeds a real SQLite database through the actual ORM models, reusing
tests/test_pairing_evidence.py's own fixture helpers so both test files
build rows the same way a schema change would break together.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import scripts.build_captain_first_edge as builder_module
from analytics.lineup_lab import LineupLabError
from database.models import Base, Match, Team
from scripts.build_captain_first_edge import (
    _database_error,
    _team_name,
    build,
    build_match_scopes,
    real_match_scopes,
    real_matches_for_scope,
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


class TestRealMatchesForScope:
    """Directive follow-up: Match Night needs each real calendar match's
    own identity (external_id/date), not just the (session, opponent,
    format) scope it belongs to -- a scope can legitimately span more than
    one real match, and saved planner state must key on the specific real
    match, not the scope alone."""

    def test_finds_the_one_real_match_behind_a_scope(self, db):
        row = _match(db, "M-1")
        row.match_date = "2026-09-10"
        row.status = "Scheduled"
        db.flush()

        matches = real_matches_for_scope(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION)

        assert len(matches) == 1
        assert matches[0].external_id == "M-1"
        assert matches[0].match_date == "2026-09-10"
        assert matches[0].is_scored is True
        assert matches[0].is_finalized is True
        assert matches[0].status == "Scheduled"

    def test_a_scope_spanning_two_real_matches_returns_both(self, db):
        """The real gap this exists to close: two real calendar matches
        against the same opponent, same format/session -- a genuine,
        common real occurrence -- must both be identifiable, not
        collapsed into one."""
        _match(db, "M-1")
        _match(db, "M-2")

        matches = real_matches_for_scope(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION)

        assert sorted(m.external_id for m in matches) == ["M-1", "M-2"]

    def test_our_team_can_be_the_away_side_too(self, db):
        _match(db, "M-1", home_team_id=OPPONENT_TEAM, away_team_id=OUR_TEAM)

        matches = real_matches_for_scope(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION)

        assert [m.external_id for m in matches] == ["M-1"]

    def test_a_match_against_a_different_opponent_is_excluded(self, db):
        _match(db, "M-1", away_team_id="TEAM-OTHER")

        matches = real_matches_for_scope(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION)

        assert matches == []

    def test_a_bye_is_excluded(self, db):
        _match(db, "M-1", is_bye=True)

        matches = real_matches_for_scope(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION)

        assert matches == []

    def test_no_real_match_returns_an_empty_list_not_a_guess(self, db):
        assert real_matches_for_scope(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION) == []

    def test_an_unscored_not_yet_played_match_is_still_returned(self, db):
        """An upcoming, not-yet-played match is exactly who Match Night is
        for -- excluding it would defeat the whole purpose."""
        _match(db, "M-1", is_scored=False, is_finalized=False)

        matches = real_matches_for_scope(db, OUR_TEAM, OPPONENT_TEAM, FORMAT, SESSION)

        assert len(matches) == 1
        assert matches[0].is_scored is False
        assert matches[0].is_finalized is False


class TestTeamName:
    def test_a_known_team_resolves_its_real_name(self, db):
        db.add(Team(external_id=OUR_TEAM, name="Chalk It Up"))
        db.flush()

        assert _team_name(db, OUR_TEAM) == "Chalk It Up"

    def test_an_unresolved_team_is_named_honestly_not_guessed(self, db):
        assert _team_name(db, "GHOST-TEAM") == "Unresolved team (id: GHOST-TEAM)"


class TestDatabaseErrors:
    @staticmethod
    def _stale_schema_error():
        return OperationalError(
            "SELECT private_column FROM player_team_history",
            {},
            sqlite3.OperationalError(
                "no such column: player_team_history.team_external_id"
            ),
        )

    def test_reason_names_root_error_without_leaking_sql(self):
        reason = _database_error(self._stale_schema_error())

        assert reason == (
            "OperationalError: no such column: "
            "player_team_history.team_external_id"
        )
        assert "SELECT" not in reason


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

    def test_stale_schema_marks_scope_unavailable_instead_of_crashing(
        self, db, monkeypatch
    ):
        _match(db, "M-1")

        def raise_stale_schema(*args, **kwargs):
            raise TestDatabaseErrors._stale_schema_error()

        monkeypatch.setattr(
            builder_module,
            "build_pairing_evidence_matrix",
            raise_stale_schema,
        )

        [scope] = build_match_scopes(db, OUR_TEAM)

        assert scope.matrix is None
        assert scope.unavailable_reason == (
            "OperationalError: no such column: "
            "player_team_history.team_external_id"
        )

    def test_blank_format_or_session_is_not_offered(self, db):
        _match(db, "M-BLANK-FORMAT", format="   ")
        row = Match(
            external_id="M-BLANK-SESSION",
            home_team_id=OUR_TEAM,
            away_team_id=OPPONENT_TEAM,
            format=FORMAT,
            session_name="   ",
        )
        db.add(row)
        db.flush()

        assert real_match_scopes(db, OUR_TEAM) == []


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

    def test_scope_query_failure_writes_an_honest_database_error_page(
        self, db, tmp_path, monkeypatch
    ):
        def raise_stale_schema(*args, **kwargs):
            raise TestDatabaseErrors._stale_schema_error()

        monkeypatch.setattr(builder_module, "real_match_scopes", raise_stale_schema)

        out_path = build(db, OUR_TEAM, tmp_path)

        html = out_path.read_text(encoding="utf-8")
        assert "could not read the configured database" in html
        assert "no such column: player_team_history.team_external_id" in html
        assert "SELECT private_column" not in html

    def test_a_real_scope_carries_a_wired_lineup_result(self, db, tmp_path):
        _seed_pair(db)
        _match(db, "M-1")
        db.add(Team(external_id=OPPONENT_TEAM, name="Corner Pockets"))
        db.flush()

        out_path = build(db, OUR_TEAM, tmp_path)

        html = out_path.read_text(encoding="utf-8")
        assert "Approved Best Lineup" in html


class TestLineupLabWiring:
    def test_a_valid_scope_carries_a_real_lineup_result(self, db):
        _seed_pair(db)
        _match(db, "M-1")

        [scope] = build_match_scopes(db, OUR_TEAM)

        assert scope.lineup_error is None
        assert scope.lineup_result is not None
        # Only one real player on each side -- an honest partial result,
        # never padded to a fabricated five-player lineup.
        assert scope.lineup_result.blocked_reason is not None
        assert "Only 1 of 5" in scope.lineup_result.blocked_reason

    def test_a_lineup_lab_error_is_captured_not_raised(self, db, monkeypatch):
        _seed_pair(db)
        _match(db, "M-1")

        def raise_lineup_error(*args, **kwargs):
            raise LineupLabError("narrow tonight's availability first")

        monkeypatch.setattr(builder_module, "solve_lineup_lab", raise_lineup_error)

        [scope] = build_match_scopes(db, OUR_TEAM)

        assert scope.matrix is not None
        assert scope.lineup_result is None
        assert scope.lineup_error == "narrow tonight's availability first"
