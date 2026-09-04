"""P1-5: SQLite ignores foreign keys unless a connection explicitly turns
them on -- database.engine.create_db_engine() now does that for every
connection it opens (see _enable_foreign_keys's docstring for the real bug
this would have caught sooner: an orphaned PlayerMatch.match_id that
silently pointed at nothing).

Tests here use create_db_engine() itself, not a bare create_engine() --
the point is to prove the actual production entry point enforces this,
not just that SQLite's pragma works in the abstract.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.engine import create_db_engine
from database.ingest import upsert_player, upsert_team
from database.models import PlayerHeadToHead, PlayerMatch


@pytest.fixture
def db(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "fk_test.db")}})
    with Session(engine) as session:
        yield session


class TestForeignKeysAreOn:
    def test_the_pragma_is_actually_set_on_this_connection(self, db):
        value = db.execute(text("PRAGMA foreign_keys")).scalar()
        assert value == 1


class TestOrphanInsertsAreRejected:
    def test_a_player_match_row_with_no_real_player_fails_to_commit(self, db):
        """The exact shape of the real bug this closes: a PlayerMatch (or
        PlayerHeadToHead) row pointing at a player_id that doesn't exist
        must not silently succeed."""
        db.add(PlayerMatch(player_id=999999, match_date="2026-01-01"))
        with pytest.raises((IntegrityError, sqlite3.IntegrityError)):
            db.commit()

    def test_a_head_to_head_row_with_no_real_opponent_fails_to_commit(self, db):
        team = upsert_team(db, "T1", "Mark It Up")
        player = upsert_player(db, "501", "Player One", team)
        db.add(PlayerHeadToHead(player_id=player.id, opponent_id=999999, match_id=1))
        with pytest.raises((IntegrityError, sqlite3.IntegrityError)):
            db.commit()

    def test_a_real_row_with_real_foreign_keys_still_commits_fine(self, db):
        """Enforcement must not be so strict it rejects legitimate rows --
        only ones with no matching parent."""
        from database.ingest import ingest_match

        team = upsert_team(db, "T1", "Mark It Up")
        upsert_team(db, "T2", "Rack Attack")
        player = upsert_player(db, "501", "Player One", team)
        match_pk, _ = ingest_match(
            db, match_id="M1", home_team_id="T1", away_team_id="T2",
            home_team_name="Mark It Up", away_team_name="Rack Attack",
        )
        db.add(PlayerMatch(player_id=player.id, match_id=match_pk, match_date="2026-01-01"))
        db.commit()  # must not raise
        assert db.query(PlayerMatch).count() == 1
