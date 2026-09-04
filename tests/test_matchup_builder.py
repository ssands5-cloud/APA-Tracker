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
from database.ingest import ingest_head_to_head, ingest_match, ingest_match_scores, upsert_team
from database.models import Base, PlayerHeadToHead, PlayerMatchup


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_match(db, match_id="M1", format_=None, session_name=None):
    upsert_team(db, "T1", "Mark It Up")
    upsert_team(db, "T2", "Rack Attack")
    ingest_match(
        db, match_id=match_id, home_team_id="T1", away_team_id="T2",
        home_team_name="Mark It Up", away_team_name="Rack Attack",
        format=format_, session_name=session_name,
    )


class TestBuildMatchups:
    def test_computes_a_real_matchup_from_seeded_head_to_head_rows(self, db):
        _seed_match(db)
        ingest_head_to_head(db, "M1", [
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
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        build_matchups(db)
        build_matchups(db)
        assert db.query(PlayerMatchup).count() == 1


class TestMatchesPlayedCountsRecognizedResultsOnly:
    """P1-6: an unrecognized result (None, "UNKNOWN", blank) must not
    inflate matches_played past what win_rate/matchup_score actually used
    as evidence."""

    def test_a_win_plus_an_unrecognized_row_counts_as_one_played(self, db):
        _seed_match(db, "M1")
        _seed_match(db, "M2")
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        ingest_head_to_head(db, "M2", [
            {"match_id": "M2", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "UNKNOWN"},
        ])
        rows = build_matchups(db)
        assert len(rows) == 1
        assert rows[0]["matches_played"] == 1
        assert rows[0]["win_rate"] == 1.0

    def test_all_unrecognized_rows_counts_as_zero_played_not_a_crash(self, db):
        _seed_match(db, "M1")
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": None},
        ])
        rows = build_matchups(db)
        assert rows[0]["matches_played"] == 0


class TestFormatAndSessionDimensions:
    """P1-4: a player's record against an opponent in one format/session
    doesn't predict their record in a different one -- these must group
    (and score) separately, not blend together."""

    def test_head_to_head_rows_inherit_the_matchs_format_and_session(self, db):
        _seed_match(db, "M1", "EIGHT_BALL", "2026 Summer")
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        row = db.query(PlayerHeadToHead).one()
        assert row.format == "EIGHT_BALL"
        assert row.session_name == "2026 Summer"

    def test_two_formats_produce_two_separate_matchup_rows(self, db):
        _seed_match(db, "M1", "EIGHT_BALL", "2026 Summer")
        _seed_match(db, "M2", "NINE_BALL", "2026 Summer")
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        ingest_head_to_head(db, "M2", [
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
        _seed_match(db, "M1", "EIGHT_BALL", "2025 Fall")
        _seed_match(db, "M2", "EIGHT_BALL", "2026 Summer")
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "L"},
        ])
        ingest_head_to_head(db, "M2", [
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
        _seed_match(db, "M1", None, None)
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        rows = build_matchups(db)
        assert len(rows) == 1
        assert rows[0]["format"] is None
        assert rows[0]["session_name"] is None

    def test_eight_ball_and_nine_ball_skill_level_trend_do_not_bleed(self, db):
        """The regression this closes: trend/volatility used to be grouped
        by player_id alone, so an 8-ball skill-level change could shift the
        trend/confidence on a completely separate 9-ball matchup. Alice's
        skill level is stable in 8-ball but jumps around in 9-ball -- the
        8-ball matchup's confidence must not be dragged down by that.
        """
        _seed_match(db, "M1", "EIGHT_BALL", "2026 Summer")
        _seed_match(db, "M2", "NINE_BALL", "2026 Summer")
        _seed_match(db, "M3", "NINE_BALL", "2026 Summer")
        _seed_match(db, "M4", "NINE_BALL", "2026 Summer")

        # 8-ball: one steady scoresheet appearance (skill level 5).
        ingest_match_scores(db, "M1", [
            {"player_id": "P1", "player_name": "Alice", "team_id": "T1",
             "skill_level": 5, "result": "W"},
        ])
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])

        # 9-ball: skill level bounces 5 -> 6 -> 5 across three appearances --
        # real volatility, but only in the 9-ball history.
        for match_id, level in [("M2", 5), ("M3", 6), ("M4", 5)]:
            ingest_match_scores(db, match_id, [
                {"player_id": "P1", "player_name": "Alice", "team_id": "T1",
                 "skill_level": level, "result": "W"},
            ])
        ingest_head_to_head(db, "M2", [
            {"match_id": "M2", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P3", "opponent_name": "Carol", "result": "W"},
        ])

        rows = build_matchups(db)
        by_format = {r["format"]: r for r in rows}

        assert by_format["EIGHT_BALL"]["volatility"] == 0
        assert by_format["EIGHT_BALL"]["trend"] == "stable"
        assert by_format["NINE_BALL"]["volatility"] == 2  # 5->6, 6->5
        assert by_format["EIGHT_BALL"]["confidence_score"] > by_format["NINE_BALL"]["confidence_score"]


class TestPruneStaleMatchups:
    """P1-7: reconciling a match's head-to-head rows away entirely must
    remove the now-unsupported PlayerMatchup aggregate, not leave it
    stale."""

    def test_a_pair_with_zero_remaining_h2h_rows_is_pruned_on_rebuild(self, db):
        _seed_match(db)
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        build_matchups(db)
        assert db.query(PlayerMatchup).count() == 1

        # Reconcile the match: the same match_id, but now Alice never
        # appears at all -- e.g. every position in the corrected scoresheet
        # involves different players. Match-level reconciliation
        # (ingest_head_to_head) deletes M1's old rows and inserts these.
        ingest_head_to_head(db, "M1", [
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
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        ingest_head_to_head(db, "M2", [
            {"match_id": "M2", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "L"},
        ])
        build_matchups(db)
        assert db.query(PlayerMatchup).one().matches_played == 2

        # Reconcile M1 away (Alice/Bob no longer paired there) -- M2 still
        # supports the pair, so it must survive, just with one fewer game.
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P3", "player_name": "Carol",
             "opponent_id": "P4", "opponent_name": "Dave", "result": "W"},
        ])
        build_matchups(db)

        alice_bob = db.query(PlayerMatchup).join(PlayerMatchup.player).filter_by(external_id="P1").one()
        assert alice_bob.matches_played == 1

    def test_an_authoritative_empty_reconciliation_prunes_the_matchup_on_rebuild(self, db):
        """P1-7: ingest M1 -> rebuild -> resync M1 with [] (the match's
        current scoresheet has zero valid pairings) -> rebuild -> the
        stale player_matchups row for that pair must be gone."""
        _seed_match(db)
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        build_matchups(db)
        assert db.query(PlayerMatchup).count() == 1

        ingest_head_to_head(db, "M1", [])
        build_matchups(db)

        assert db.query(PlayerHeadToHead).count() == 0
        assert db.query(PlayerMatchup).count() == 0
