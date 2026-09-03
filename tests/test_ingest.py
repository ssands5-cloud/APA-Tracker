"""Regression test for the PlayerMatch uniqueness bug hit running
run_all_teams() against a real account for the first time.

Real failure: two genuinely different matches (different teams, different
divisions, different match_id) landed on the same match_date against two
different opponents that happened to share a name ("Mark It Up"). The same
player appeared in both. ingest_match_scores() correctly deduplicates in
Python on (player_id, match_id) before deciding insert vs. update, but the
table ALSO had a blanket UNIQUE constraint on (player_id, match_date,
opponent) -- meant only for ingest_player_matches's match_id-less rows --
which rejected the second, unrelated match's row as a duplicate of the
first. See database/models.py's PlayerMatch docstring for the fix (a
partial index, WHERE match_id IS NULL).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.ingest import (
    ingest_match,
    ingest_match_scores,
    ingest_player_matches,
    upsert_player,
    upsert_team,
)
from database.models import Base, PlayerMatch


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestTwoMatchLinkedRowsSharingDateAndOpponentName:
    def test_does_not_raise_the_real_live_integrity_error(self, db):
        """The exact shape of the real failure: same player, same
        match_date, same opponent NAME, but two different real matches
        (different match_id, different team_id)."""
        upsert_team(db, "T1", "Brunch Ballers (8-Ball)")
        upsert_team(db, "T2", "Brunch Ballers (9-Ball)")
        ingest_match(
            db, match_id="M1", home_team_id="T1", away_team_id="OPP1",
            home_team_name="Brunch Ballers (8-Ball)", away_team_name="Mark It Up",
            match_date="2026-09-01", week=1,
        )
        ingest_match(
            db, match_id="M2", home_team_id="T2", away_team_id="OPP2",
            home_team_name="Brunch Ballers (9-Ball)", away_team_name="Mark It Up",
            match_date="2026-09-01", week=1,
        )

        # Both should succeed -- no IntegrityError, even though (player_id,
        # match_date, opponent) is identical for both rows.
        created_1, _ = ingest_match_scores(
            db, "M1",
            [{"player_id": "P1", "player_name": "Alice", "team_id": "T1",
              "result": "W", "points_earned": 6}],
        )
        created_2, _ = ingest_match_scores(
            db, "M2",
            [{"player_id": "P1", "player_name": "Alice", "team_id": "T2",
              "result": "L", "points_earned": 3}],
        )

        assert created_1 == 1
        assert created_2 == 1
        rows = db.query(PlayerMatch).filter_by(match_date="2026-09-01").all()
        assert len(rows) == 2
        assert rows[0].match_id != rows[1].match_id
        assert {r.opponent for r in rows} == {"Mark It Up"}


class TestPerPlayerHistoryPathStillDeduplicates:
    """The partial index must still do its original job: ingest_player_matches
    rows (no match_id) are the ones it was built to guard."""

    def test_the_same_history_row_ingested_twice_is_not_duplicated(self, db):
        team = upsert_team(db, "T1", "Brunch Ballers")
        player = upsert_player(db, "P1", "Alice", team)
        row = {"match_date": "2026-09-01", "opponent": "Mark It Up", "result": "W"}

        first = ingest_player_matches(db, player, [row])
        second = ingest_player_matches(db, player, [row])

        assert first == 1
        assert second == 0  # already exists, per ingest_player_matches's own check
        assert db.query(PlayerMatch).filter_by(player_id=player.id).count() == 1

    def test_a_genuinely_different_opponent_same_date_is_a_separate_row(self, db):
        """Sanity check the partial index didn't just become a no-op: this
        path (match_id IS NULL) must still enforce uniqueness for real."""
        team = upsert_team(db, "T1", "Brunch Ballers")
        player = upsert_player(db, "P1", "Alice", team)
        ingest_player_matches(
            db, player, [{"match_date": "2026-09-01", "opponent": "Mark It Up", "result": "W"}]
        )
        # A literal duplicate insert attempt (bypassing ingest_player_matches's
        # own pre-check) must still be rejected by the database itself.
        db.add(PlayerMatch(player_id=player.id, match_date="2026-09-01", opponent="Mark It Up"))
        with pytest.raises(Exception):
            db.commit()
