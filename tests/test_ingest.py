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

from datetime import datetime, timedelta

from database.ingest import (
    ingest_match,
    ingest_match_scores,
    ingest_player_matches,
    ingest_standings,
    upsert_player,
    upsert_team,
)
from database.models import Base, PlayerMatch
from database.queries import latest_standings


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


class TestIngestStandingsSharedTimestamp:
    """Real bug from the first real 4-division sync: run_all_teams() calls
    ingest_standings() once per division, and without an explicit shared
    captured_at, each call's default datetime.utcnow() lands microseconds
    apart. latest_standings() (what the Excel/JSON exports read) filters to
    the single MAX captured_at -- so only the last division ever showed up.
    Confirmed against a real account: 40 real standings rows across 4
    divisions, only 10 (the last division processed) reached the export.
    """

    def test_default_timestamps_reproduce_the_bug(self, db):
        """Without captured_at, two separate ingest_standings() calls a
        moment apart really do get different timestamps, and
        latest_standings() really does drop the earlier one -- this is
        what run_all_teams() did before the fix."""
        ingest_standings(db, [{"team_name": "Division A Team", "rank": 1, "points": 100}])
        ingest_standings(db, [{"team_name": "Division B Team", "rank": 1, "points": 90}])

        rows = latest_standings(db)
        names = {r.team_name for r in rows}
        assert names == {"Division B Team"}, (
            "if this starts failing because both rows show up, the bug this "
            "test documents may have been fixed some OTHER way -- that's "
            "fine, but update/remove this test rather than leaving it "
            "asserting the old broken behavior"
        )

    def test_a_shared_captured_at_keeps_every_division(self, db):
        """The actual fix: pass the SAME captured_at to every division's
        ingest_standings() call within one sync run."""
        synced_at = datetime.utcnow()
        ingest_standings(
            db, [{"team_name": "Division A Team", "rank": 1, "points": 100}],
            captured_at=synced_at,
        )
        ingest_standings(
            db, [{"team_name": "Division B Team", "rank": 1, "points": 90}],
            captured_at=synced_at,
        )

        rows = latest_standings(db)
        names = {r.team_name for r in rows}
        assert names == {"Division A Team", "Division B Team"}

    def test_a_later_sync_run_supersedes_an_earlier_one(self, db):
        """Two full sync runs, each internally consistent -- the later run's
        rows are what latest_standings() should return, not a mix of both."""
        earlier = datetime.utcnow() - timedelta(hours=1)
        later = datetime.utcnow()
        ingest_standings(db, [{"team_name": "Stale Team", "rank": 1, "points": 50}], captured_at=earlier)
        ingest_standings(db, [{"team_name": "Fresh Team", "rank": 1, "points": 60}], captured_at=later)

        rows = latest_standings(db)
        assert {r.team_name for r in rows} == {"Fresh Team"}


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
