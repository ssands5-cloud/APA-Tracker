"""Unit tests for analytics.matchup_builder.build_matchups() -- direct
coverage of the grouping/scoring/pruning logic against a real in-memory
database, seeded through the real ingest functions. The subprocess-level
tests (tests/test_build_matchups.py, tests/test_live_sync_matchup_rebuild.py)
already prove the whole pipeline runs end to end; this is for the specific
behaviors that don't need a full sync to exercise -- especially P1-7's
"rebuild aggregates" (pruning a PlayerMatchup row once its last supporting
head-to-head evidence is reconciled away).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from analytics.matchup_builder import build_matchups
from database.ingest import ingest_head_to_head, ingest_match, upsert_team
from database.models import Base, PlayerMatchup


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_match(db, match_id="M1"):
    upsert_team(db, "T1", "Mark It Up")
    upsert_team(db, "T2", "Rack Attack")
    ingest_match(
        db, match_id=match_id, home_team_id="T1", away_team_id="T2",
        home_team_name="Mark It Up", away_team_name="Rack Attack",
    )


class TestBuildMatchups:
    def test_computes_a_real_matchup_from_seeded_head_to_head_rows(self, db):
        _seed_match(db)
        ingest_head_to_head(db, [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W", "points_earned": 6},
        ])
        rows = build_matchups(db)
        assert len(rows) == 1
        assert rows[0]["player_name"] == "Alice"
        assert rows[0]["opponent_name"] == "Bob"
        assert rows[0]["matches_played"] == 1
        assert db.query(PlayerMatchup).count() == 1

    def test_is_safe_to_call_with_no_head_to_head_data_at_all(self, db):
        assert build_matchups(db) == []
        assert db.query(PlayerMatchup).count() == 0

    def test_rerunning_does_not_duplicate_the_matchup_row(self, db):
        _seed_match(db)
        ingest_head_to_head(db, [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        build_matchups(db)
        build_matchups(db)
        assert db.query(PlayerMatchup).count() == 1


class TestFormatAndSessionDimensions:
    """P1-4: a player's record against an opponent in one format/session
    doesn't predict their record in a different one -- these must group
    (and score) separately, not blend together."""

    def _seed_match_with_context(self, db, match_id, format_, session_name):
        upsert_team(db, "T1", "Mark It Up")
        upsert_team(db, "T2", "Rack Attack")
        ingest_match(
            db, match_id=match_id, home_team_id="T1", away_team_id="T2",
            home_team_name="Mark It Up", away_team_name="Rack Attack",
            format=format_, session_name=session_name,
        )

    def test_head_to_head_rows_inherit_the_matchs_format_and_session(self, db):
        self._seed_match_with_context(db, "M1", "EIGHT_BALL", "2026 Summer")
        ingest_head_to_head(db, [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        from database.models import PlayerHeadToHead

        row = db.query(PlayerHeadToHead).one()
        assert row.format == "EIGHT_BALL"
        assert row.session_name == "2026 Summer"

    def test_two_formats_produce_two_separate_matchup_rows(self, db):
        self._seed_match_with_context(db, "M1", "EIGHT_BALL", "2026 Summer")
        self._seed_match_with_context(db, "M2", "NINE_BALL", "2026 Summer")
        ingest_head_to_head(db, [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        ingest_head_to_head(db, [
            {"match_id": "M2", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "L"},
        ])
        rows = build_matchups(db)

        assert len(rows) == 2
        by_format = {r["format"]: r for r in rows}
        assert by_format["EIGHT_BALL"]["win_rate"] == 1.0
        assert by_format["NINE_BALL"]["win_rate"] == 0.0
        assert db.query(PlayerMatchup).count() == 2

    def test_two_sessions_produce_two_separate_matchup_rows(self, db):
        self._seed_match_with_context(db, "M1", "EIGHT_BALL", "2025 Fall")
        self._seed_match_with_context(db, "M2", "EIGHT_BALL", "2026 Summer")
        ingest_head_to_head(db, [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "L"},
        ])
        ingest_head_to_head(db, [
            {"match_id": "M2", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        rows = build_matchups(db)

        assert len(rows) == 2
        by_session = {r["session_name"]: r for r in rows}
        assert by_session["2025 Fall"]["win_rate"] == 0.0
        assert by_session["2026 Summer"]["win_rate"] == 1.0

    def test_rows_with_no_threaded_context_still_group_under_a_shared_null_bucket(self, db):
        """A match ingested without format/session (an older ingest, or a
        caller with no team context handy) must still aggregate -- not be
        dropped or crash."""
        self._seed_match_with_context(db, "M1", None, None)
        ingest_head_to_head(db, [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        rows = build_matchups(db)
        assert len(rows) == 1
        assert rows[0]["format"] is None
        assert rows[0]["session_name"] is None


class TestPruneStaleMatchups:
    """P1-7: reconciling a match's head-to-head rows away entirely must
    remove the now-unsupported PlayerMatchup aggregate, not leave it
    stale."""

    def test_a_pair_with_zero_remaining_h2h_rows_is_pruned_on_rebuild(self, db):
        _seed_match(db)
        ingest_head_to_head(db, [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        build_matchups(db)
        assert db.query(PlayerMatchup).count() == 1

        # Reconcile the match: the same match_id, but now Alice never
        # appears at all -- e.g. every position in the corrected scoresheet
        # involves different players. Match-level reconciliation
        # (ingest_head_to_head) deletes M1's old rows and inserts these.
        ingest_head_to_head(db, [
            {"match_id": "M1", "player_id": "P3", "player_name": "Carol",
             "opponent_id": "P4", "opponent_name": "Dave", "result": "L"},
        ])
        build_matchups(db)

        remaining = {(r.player.name, r.opponent.name) for r in db.query(PlayerMatchup).all()}
        assert ("Alice", "Bob") not in remaining
        assert ("Carol", "Dave") in remaining
        assert db.query(PlayerMatchup).count() == 1

    def test_a_pair_still_supported_by_a_different_match_is_not_pruned(self, db):
        """Pruning is keyed on the PAIR having zero evidence anywhere, not
        on any one match -- a pair with history from two matches must
        survive one of those matches being reconciled away."""
        _seed_match(db, match_id="M1")
        _seed_match(db, match_id="M2")
        ingest_head_to_head(db, [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        ingest_head_to_head(db, [
            {"match_id": "M2", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "L"},
        ])
        build_matchups(db)
        assert db.query(PlayerMatchup).one().matches_played == 2

        # Reconcile M1 away (Alice/Bob no longer paired there) -- M2 still
        # supports the pair, so it must survive, just with one fewer game.
        ingest_head_to_head(db, [
            {"match_id": "M1", "player_id": "P3", "player_name": "Carol",
             "opponent_id": "P4", "opponent_name": "Dave", "result": "W"},
        ])
        build_matchups(db)

        alice_bob = db.query(PlayerMatchup).join(PlayerMatchup.player).filter_by(external_id="P1").one()
        assert alice_bob.matches_played == 1
