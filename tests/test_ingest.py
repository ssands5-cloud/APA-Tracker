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
    ingest_eight_ball_stats,
    ingest_match,
    ingest_match_roster,
    ingest_match_scores,
    ingest_player_matches,
    ingest_player_career_stats,
    ingest_player_team_history,
    ingest_standings,
    upsert_player,
    upsert_team,
)
from database.models import Base, Player, PlayerCareerStats, PlayerMatch, PlayerTeamHistory
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


class TestVacantScoresheetSlotsAreSkippedNotMerged:
    """Real bug found reading an actual export: a player with no name at
    all, a 0-0 record, spanning two unrelated matches. A forfeited/vacant
    roster slot has no real player_id, and every such slot -- across every
    match -- shared the same blank external_id, so they all collapsed into
    one fake "player" that accumulated match history belonging to nobody.
    """

    def test_ingest_match_scores_skips_an_entry_with_no_player_id(self, db):
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Home", away_team_name="Away")
        created, updated = ingest_match_scores(
            db, "M1",
            [
                {"player_id": "P1", "player_name": "Alice", "result": "W", "points_earned": 6},
                {"player_id": "", "player_name": "", "result": None, "points_earned": None},
            ],
        )
        assert created == 1  # only Alice
        assert db.query(Player).filter_by(external_id="").count() == 0

    def test_ingest_match_roster_skips_an_entry_with_no_player_id(self, db):
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Home", away_team_name="Away")
        count = ingest_match_roster(
            db, "M1", "T1", "Home",
            [
                {"player_id": "P1", "player_name": "Alice"},
                {"player_id": "", "player_name": ""},
            ],
        )
        assert count == 1
        assert db.query(Player).filter_by(external_id="").count() == 0

    def test_two_vacant_slots_across_two_matches_do_not_merge_into_one_player(self, db):
        """The exact real shape: forfeited slots in TWO DIFFERENT matches
        must not both land on one shared blank-id Player row."""
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Home", away_team_name="Away")
        ingest_match(db, match_id="M2", home_team_id="T1", away_team_id="T3",
                     home_team_name="Home", away_team_name="Someone Else")
        ingest_match_scores(db, "M1", [{"player_id": "", "player_name": ""}])
        ingest_match_scores(db, "M2", [{"player_id": "", "player_name": ""}])

        assert db.query(Player).count() == 0
        assert db.query(PlayerMatch).count() == 0


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


class TestIngestEightBallStats:
    """HANDOFF.md item 2, now confirmed and wired: career stats from
    getEightBallStats, split into one PlayerCareerStats row per format."""

    STATS_ROW = {
        "alias_id": 700001,
        "display_name": "Paul Smith",
        "eight_ball_matches_won": 64,
        "eight_ball_matches_played": 129,
        "eight_ball_cla": 1,
        "eight_ball_defensive_shot_avg": 1.26,
        "eight_ball_match_count_for_last_two_yrs": 123,
        "eight_ball_last_played": "2026-08-31",
        "nine_ball_matches_won": None,
        "nine_ball_matches_played": None,
        "nine_ball_cla": None,
        "nine_ball_defensive_shot_avg": None,
        "nine_ball_match_count_for_last_two_yrs": None,
        "nine_ball_last_played": None,
    }

    def test_writes_one_row_for_the_format_with_data(self, db):
        team = upsert_team(db, "T1", "Mark It Up")
        player = upsert_player(db, "3349374", "Paul Smith", team)
        written = ingest_eight_ball_stats(db, player, self.STATS_ROW)
        assert written == 1
        row = db.query(PlayerCareerStats).filter_by(player_id=player.id, format="EIGHT").one()
        assert row.matches_won == 64
        assert row.matches_played == 129
        assert row.match_count_last_two_yrs == 123

    def test_skips_the_format_with_no_data(self, db):
        team = upsert_team(db, "T1", "Mark It Up")
        player = upsert_player(db, "3349374", "Paul Smith", team)
        ingest_eight_ball_stats(db, player, self.STATS_ROW)
        assert db.query(PlayerCareerStats).filter_by(player_id=player.id, format="NINE").count() == 0

    def test_rerunning_updates_in_place_not_a_second_row(self, db):
        team = upsert_team(db, "T1", "Mark It Up")
        player = upsert_player(db, "3349374", "Paul Smith", team)
        ingest_eight_ball_stats(db, player, self.STATS_ROW)
        updated = dict(self.STATS_ROW, eight_ball_matches_won=65, eight_ball_matches_played=130)
        ingest_eight_ball_stats(db, player, updated)

        rows = db.query(PlayerCareerStats).filter_by(player_id=player.id, format="EIGHT").all()
        assert len(rows) == 1
        assert rows[0].matches_won == 65


class TestIngestPlayerTeamHistory:
    """HANDOFF.md item 2, now confirmed and wired: cross-season history
    from TeamStat."""

    ROWS = [
        {
            "is_current": False, "team_id": "13082718", "team_name": "Rack Attack",
            "division_id": "436647", "is_tournament": False, "session_name": "2025 Fall",
            "nick_name": "J-Rock", "skill_level": 6, "rank": 2,
            "matches_won": 19, "matches_played": 27,
        },
        {
            "is_current": True, "team_id": "13082948", "team_name": "Chalk It Up",
            "division_id": "436670", "is_tournament": False, "session_name": "2026 Summer",
            "nick_name": "J-Rock", "skill_level": 6, "rank": None,
            "matches_won": 6, "matches_played": 9,
        },
    ]

    def test_one_row_per_team(self, db):
        team = upsert_team(db, "T1", "Mark It Up")
        player = upsert_player(db, "3349374", "Paul Smith", team)
        count = ingest_player_team_history(db, player, self.ROWS)
        assert count == 2
        assert db.query(PlayerTeamHistory).filter_by(player_id=player.id).count() == 2

    def test_current_vs_past_is_preserved(self, db):
        team = upsert_team(db, "T1", "Mark It Up")
        player = upsert_player(db, "3349374", "Paul Smith", team)
        ingest_player_team_history(db, player, self.ROWS)
        rows = {r.team_name: r for r in db.query(PlayerTeamHistory).filter_by(player_id=player.id)}
        assert rows["Rack Attack"].is_current is False
        assert rows["Chalk It Up"].is_current is True

    def test_rerunning_updates_in_place_not_duplicated(self, db):
        team = upsert_team(db, "T1", "Mark It Up")
        player = upsert_player(db, "3349374", "Paul Smith", team)
        ingest_player_team_history(db, player, self.ROWS)
        updated = [dict(self.ROWS[0], matches_won=20), self.ROWS[1]]
        ingest_player_team_history(db, player, updated)

        rows = db.query(PlayerTeamHistory).filter_by(player_id=player.id).all()
        assert len(rows) == 2
        rack_attack = next(r for r in rows if r.team_name == "Rack Attack")
        assert rack_attack.matches_won == 20
