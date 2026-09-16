"""Tests for scripts/build_full_production_demo.py's _live_scope().

Live scope must be chosen from what was actually ingested -- never a
fixture constant, and never a guess. These build a small real SQLite
database directly (no network, no builder run) and exercise the real
function against it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Match, PlayerTeamHistory
from scripts.build_full_production_demo import BuildError, _live_scope

OUR_TEAM = "13082948"  # apa_config.yaml's real configured team.team_id
OPPONENT = "20000000"
SESSION = "2026 Fall"
FORMAT_NAME = "8-Ball Open"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


def _roster(db, team_id, session_name, n=5):
    for i in range(n):
        from database.models import Player
        player = Player(external_id=f"{team_id}-P{i}", name=f"Player {i}")
        db.add(player)
        db.flush()
        db.add(PlayerTeamHistory(
            player_id=player.id, team_external_id=team_id, session_name=session_name,
            is_current=True, skill_level=5,
        ))
    db.flush()


class TestLiveScopeSelection:
    def test_picks_the_only_real_scope_with_rosters_on_both_sides(self, db):
        db.add(Match(
            external_id="M1", home_team_id=OUR_TEAM, away_team_id=OPPONENT,
            is_bye=False, session_name=SESSION, format=FORMAT_NAME, week=1,
        ))
        _roster(db, OUR_TEAM, SESSION)
        _roster(db, OPPONENT, SESSION)
        db.flush()

        scope = _live_scope(db)

        assert scope == {
            "our_team_id": OUR_TEAM, "opponent_team_id": OPPONENT,
            "session_name": SESSION, "format": FORMAT_NAME,
        }

    def test_earliest_week_wins_when_several_are_usable(self, db):
        db.add(Match(external_id="M2", home_team_id=OUR_TEAM, away_team_id="30000000",
                      is_bye=False, session_name=SESSION, format=FORMAT_NAME, week=2))
        db.add(Match(external_id="M1", home_team_id=OUR_TEAM, away_team_id=OPPONENT,
                      is_bye=False, session_name=SESSION, format=FORMAT_NAME, week=1))
        _roster(db, OUR_TEAM, SESSION)
        _roster(db, OPPONENT, SESSION)
        _roster(db, "30000000", SESSION)
        db.flush()

        scope = _live_scope(db)

        assert scope["opponent_team_id"] == OPPONENT  # week 1, not week 2

    def test_a_bye_is_never_a_candidate(self, db):
        db.add(Match(external_id="MBYE", home_team_id=OUR_TEAM, away_team_id=None,
                      is_bye=True, session_name=SESSION, format=FORMAT_NAME, week=1))
        _roster(db, OUR_TEAM, SESSION)
        db.flush()

        with pytest.raises(BuildError, match="no real matches found"):
            _live_scope(db)

    def test_a_match_missing_an_opponent_roster_is_skipped_for_the_next_one(self, db):
        db.add(Match(external_id="M1", home_team_id=OUR_TEAM, away_team_id="NOROSTER",
                      is_bye=False, session_name=SESSION, format=FORMAT_NAME, week=1))
        db.add(Match(external_id="M2", home_team_id=OUR_TEAM, away_team_id=OPPONENT,
                      is_bye=False, session_name=SESSION, format=FORMAT_NAME, week=2))
        _roster(db, OUR_TEAM, SESSION)
        _roster(db, OPPONENT, SESSION)
        # "NOROSTER" deliberately gets no PlayerTeamHistory rows at all.
        db.flush()

        scope = _live_scope(db)

        assert scope["opponent_team_id"] == OPPONENT

    def test_no_usable_scope_raises_a_clear_message_naming_the_attempt_count(self, db):
        db.add(Match(external_id="M1", home_team_id=OUR_TEAM, away_team_id=OPPONENT,
                      is_bye=False, session_name=SESSION, format=FORMAT_NAME, week=1))
        _roster(db, OUR_TEAM, SESSION)
        # No opponent roster at all -- this candidate is tried and rejected.
        db.flush()

        with pytest.raises(BuildError, match=r"tried 1 candidate"):
            _live_scope(db)

    def test_our_side_missing_a_roster_also_disqualifies_the_candidate(self, db):
        db.add(Match(external_id="M1", home_team_id=OUR_TEAM, away_team_id=OPPONENT,
                      is_bye=False, session_name=SESSION, format=FORMAT_NAME, week=1))
        _roster(db, OPPONENT, SESSION)
        # We have no PlayerTeamHistory of our own in this session.
        db.flush()

        with pytest.raises(BuildError):
            _live_scope(db)

    def test_no_matches_at_all_is_a_distinct_honest_message(self, db):
        with pytest.raises(BuildError, match="no real matches found"):
            _live_scope(db)
