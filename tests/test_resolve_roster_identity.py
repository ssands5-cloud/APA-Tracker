"""Tests for database.queries.resolve_roster_identity().

Real APA data key finding this exists to fix: roster/TeamStat queries key a
player on ``member.id``; a match scoresheet keys the same real person under
a separate per-position alias id that can even differ across a real
person's own matches. Confirmed on a real promoted database: 275 of 277
real scoresheet identities resolved uniquely via this exact team+session+
name join, zero ambiguous, and the two non-matches were a real substitute
player on neither team's current roster.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Player, PlayerTeamHistory
from database.queries import resolve_roster_identity

TEAM = "13082948"
OTHER_TEAM = "13082949"
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


def _roster_player(db, external_id, name, team_id=TEAM, session_name=SESSION, is_current=True):
    player = Player(external_id=external_id, name=name)
    db.add(player)
    db.flush()
    db.add(PlayerTeamHistory(
        player_id=player.id, team_external_id=team_id, session_name=session_name,
        is_current=is_current,
    ))
    db.flush()
    return player


class TestUniqueResolution:
    def test_resolves_the_one_real_current_roster_match(self, db):
        expected = _roster_player(db, "3349374", "Paul Smith")
        db.commit()

        resolved = resolve_roster_identity(db, TEAM, SESSION, "Paul Smith")

        assert resolved is not None
        assert resolved.id == expected.id
        assert resolved.external_id == "3349374"

    def test_a_different_teams_same_name_is_not_a_candidate(self, db):
        """Scoping to the exact team is load-bearing, not incidental."""
        _roster_player(db, "3349374", "Paul Smith", team_id=TEAM)
        _roster_player(db, "9999999", "Paul Smith", team_id=OTHER_TEAM)
        db.commit()

        resolved = resolve_roster_identity(db, TEAM, SESSION, "Paul Smith")

        assert resolved is not None
        assert resolved.external_id == "3349374"


class TestNoGuessing:
    def test_zero_candidates_returns_none(self, db):
        _roster_player(db, "1", "Someone Else")
        db.commit()

        assert resolve_roster_identity(db, TEAM, SESSION, "Philip Sigmon") is None

    def test_two_same_named_players_on_the_same_team_returns_none(self, db):
        """The real ambiguous case: never silently pick one."""
        _roster_player(db, "1", "Adam Shapiro")
        _roster_player(db, "2", "Adam Shapiro")
        db.commit()

        assert resolve_roster_identity(db, TEAM, SESSION, "Adam Shapiro") is None

    def test_a_non_current_roster_row_is_not_a_candidate(self, db):
        _roster_player(db, "1", "Paul Smith", is_current=False)
        db.commit()

        assert resolve_roster_identity(db, TEAM, SESSION, "Paul Smith") is None

    def test_a_different_sessions_roster_row_is_not_a_candidate(self, db):
        _roster_player(db, "1", "Paul Smith", session_name="Spring 2027")
        db.commit()

        assert resolve_roster_identity(db, TEAM, SESSION, "Paul Smith") is None

    def test_no_roster_at_all_returns_none(self, db):
        assert resolve_roster_identity(db, TEAM, SESSION, "Nobody") is None
