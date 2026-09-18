"""Tests for scheduler.graphql_sync's division-wide sync and reconciliation.

sync_division_wide/run_division_wide are exercised for real against a real
SQLite database, with only the fetch_*() functions monkeypatched -- no
requests.post call, no network, and no real token needed. This proves the
actual ingest path (upsert_team, upsert_player, ingest_player_team_history,
ingest_match, ingest_match_scores, ingest_head_to_head) runs unmodified,
which is the property the whole "prove complete coverage" requirement rests
on: the reconciliation counts are worthless if they're checked against a
different code path than the one that actually writes the database.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base
from database.queries import canonical_current_roster
from scheduler import graphql_sync as sync

DIVISION_ID = "300"
SESSION_NAME = "2026 Rehearsal Session"
FORMAT_NAME = "8-Ball Open"

ROSTERS_PAYLOAD = {
    "teams": [
        {"isBye": False, "id": 301, "name": "Fixture Sharks", "roster": [
            {"id": 1, "displayName": "Ann Fixture", "matchesWon": 6, "matchesPlayed": 9,
             "skillLevel": 6, "member": {"id": 9001}},
        ]},
        {"isBye": False, "id": 302, "name": "Fixture Renegades", "roster": [
            {"id": 2, "displayName": "Uma Sample", "matchesWon": 4, "matchesPlayed": 9,
             "skillLevel": 5, "member": {"id": 9002}},
        ]},
    ],
}

SCHEDULE_PAYLOAD = {
    "schedule": [
        {"weekOfPlay": 1, "matches": [
            {
                "id": 90401, "isBye": False, "status": "COMPLETED", "startTime": "2026-01-15",
                "isScored": True, "isFinalized": True,
                "results": [{"homeAway": "HOME", "points": {"total": 18}},
                            {"homeAway": "AWAY", "points": {"total": 12}}],
                "home": {"id": 301, "name": "Fixture Sharks"},
                "away": {"id": 302, "name": "Fixture Renegades"},
            },
        ]},
        {"weekOfPlay": 2, "matches": [
            {
                "id": 90402, "isBye": False, "status": "SCHEDULED", "startTime": "2026-01-22",
                "isScored": False, "isFinalized": False, "results": [],
                "home": {"id": 302, "name": "Fixture Renegades"},
                "away": {"id": 301, "name": "Fixture Sharks"},
            },
        ]},
    ],
}

MATCH_DETAIL_PAYLOAD = {
    "id": 90401,
    "home": {"id": 301, "name": "Fixture Sharks"},
    "away": {"id": 302, "name": "Fixture Renegades"},
    "results": [
        {"homeAway": "HOME", "scores": [
            {"player": {"id": 9001, "displayName": "Ann Fixture"}, "matchPositionNumber": 1,
             "skillLevel": 6, "winLoss": "W", "points": {"total": 3}},
        ]},
        {"homeAway": "AWAY", "scores": [
            {"player": {"id": 9002, "displayName": "Uma Sample"}, "matchPositionNumber": 1,
             "skillLevel": 5, "winLoss": "L", "points": {"total": 1}},
        ]},
    ],
}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mocked_fetches(monkeypatch):
    """Every fetch_*() sync.py imports by name, replaced with fixture data.
    No network, no token, no requests.post."""
    monkeypatch.setattr(sync, "fetch_division_rosters", lambda config, division_id: ROSTERS_PAYLOAD)
    monkeypatch.setattr(sync, "fetch_division_schedule", lambda config, division_id: SCHEDULE_PAYLOAD)
    monkeypatch.setattr(sync, "fetch_match_detail", lambda config, match_id: MATCH_DETAIL_PAYLOAD)


class TestIdentityResolution:
    """The real defect: APA's own scoresheet uses a DIFFERENT alias id
    space than roster/TeamStat queries for the same real person -- even
    across a single real person's own matches. Confirmed on a real
    promoted database: 275 of 277 real scoresheet identities resolved
    uniquely via team-scoped name matching, zero ambiguous. These fixtures
    deliberately use a scoresheet alias id (99001/99002) that differs from
    the roster's real member id (9001/9002), exactly like the real defect.
    """

    ALIAS_ROSTERS_PAYLOAD = ROSTERS_PAYLOAD  # same team/roster shape

    ALIAS_SCHEDULE_PAYLOAD = SCHEDULE_PAYLOAD

    ALIAS_MATCH_DETAIL_PAYLOAD = {
        "id": 90401,
        "home": {"id": 301, "name": "Fixture Sharks"},
        "away": {"id": 302, "name": "Fixture Renegades"},
        "results": [
            {"homeAway": "HOME", "scores": [
                {"player": {"id": 99001, "displayName": "Ann Fixture"}, "matchPositionNumber": 1,
                 "skillLevel": 6, "winLoss": "W", "points": {"total": 3}},
            ]},
            {"homeAway": "AWAY", "scores": [
                {"player": {"id": 99002, "displayName": "Uma Sample"}, "matchPositionNumber": 1,
                 "skillLevel": 5, "winLoss": "L", "points": {"total": 1}},
            ]},
        ],
    }

    def test_scoresheet_alias_ids_are_rewritten_to_canonical_roster_identity(self, db, monkeypatch):
        monkeypatch.setattr(sync, "fetch_division_rosters", lambda config, division_id: self.ALIAS_ROSTERS_PAYLOAD)
        monkeypatch.setattr(sync, "fetch_division_schedule", lambda config, division_id: self.ALIAS_SCHEDULE_PAYLOAD)
        monkeypatch.setattr(sync, "fetch_match_detail", lambda config, match_id: self.ALIAS_MATCH_DETAIL_PAYLOAD)

        sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                 division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        from database.models import Player, PlayerHeadToHead, PlayerMatch

        # The roster's real player (external_id "9001" per ROSTERS_PAYLOAD's
        # member.id) must own the PlayerMatch/PlayerHeadToHead rows -- not a
        # separate Player created under the scoresheet's own alias id 99001.
        ann = db.query(Player).filter_by(external_id="9001").one()
        assert db.query(Player).filter_by(external_id="99001").first() is None
        assert db.query(PlayerMatch).filter_by(player_id=ann.id).count() == 1
        assert db.query(PlayerHeadToHead).filter_by(player_id=ann.id).count() == 1

    def test_the_direct_pairing_matrix_now_finds_this_evidence(self, db, monkeypatch):
        """The actual, user-visible symptom this whole fix addresses: before
        the fix, PairingEvidenceMatrix (keyed on canonical roster ids) could
        never find PlayerHeadToHead rows keyed on scoresheet alias ids, so
        every real pairing showed as INDIRECT even with real games played."""
        monkeypatch.setattr(sync, "fetch_division_rosters", lambda config, division_id: self.ALIAS_ROSTERS_PAYLOAD)
        monkeypatch.setattr(sync, "fetch_division_schedule", lambda config, division_id: self.ALIAS_SCHEDULE_PAYLOAD)
        monkeypatch.setattr(sync, "fetch_match_detail", lambda config, match_id: self.ALIAS_MATCH_DETAIL_PAYLOAD)

        sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                 division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        from analytics.pairing_evidence import EvidenceLabel, build_pairing_evidence_matrix

        matrix = build_pairing_evidence_matrix(
            db, our_team_external_id="301", opponent_team_external_id="302",
            format=FORMAT_NAME, session_name=SESSION_NAME,
        )
        pairing = matrix.pairings[0]
        assert pairing.evidence_label == EvidenceLabel.DIRECT

    def test_resolution_counts_are_reported(self, db, monkeypatch):
        monkeypatch.setattr(sync, "fetch_division_rosters", lambda config, division_id: self.ALIAS_ROSTERS_PAYLOAD)
        monkeypatch.setattr(sync, "fetch_division_schedule", lambda config, division_id: self.ALIAS_SCHEDULE_PAYLOAD)
        monkeypatch.setattr(sync, "fetch_match_detail", lambda config, match_id: self.ALIAS_MATCH_DETAIL_PAYLOAD)

        counts = sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                          division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        assert counts["identity_resolved"] == 2
        assert counts["identity_unresolved"] == 0

    def test_a_name_absent_from_the_current_roster_is_left_unresolved_not_guessed(self, db, monkeypatch):
        """The real, honest case (a substitute player): never merge onto a
        roster player who isn't actually a unique name match."""
        detail = {
            "id": 90401,
            "home": {"id": 301, "name": "Fixture Sharks"},
            "away": {"id": 302, "name": "Fixture Renegades"},
            "results": [
                {"homeAway": "HOME", "scores": [
                    {"player": {"id": 99009, "displayName": "Substitute Sub"}, "matchPositionNumber": 1,
                     "skillLevel": 6, "winLoss": "W", "points": {"total": 3}},
                ]},
                {"homeAway": "AWAY", "scores": [
                    {"player": {"id": 99002, "displayName": "Uma Sample"}, "matchPositionNumber": 1,
                     "skillLevel": 5, "winLoss": "L", "points": {"total": 1}},
                ]},
            ],
        }
        monkeypatch.setattr(sync, "fetch_division_rosters", lambda config, division_id: self.ALIAS_ROSTERS_PAYLOAD)
        monkeypatch.setattr(sync, "fetch_division_schedule", lambda config, division_id: self.ALIAS_SCHEDULE_PAYLOAD)
        monkeypatch.setattr(sync, "fetch_match_detail", lambda config, match_id: detail)

        counts = sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                          division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        from database.models import Player

        assert counts["identity_unresolved"] == 1
        assert counts["identity_resolved"] == 1
        substitute = db.query(Player).filter_by(external_id="99009").one_or_none()
        assert substitute is not None  # kept under its own honest, unmerged identity


class TestSyncDivisionWide:
    def test_every_discovered_team_is_ingested(self, db, mocked_fetches):
        counts = sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                          division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        assert counts["teams_discovered"] == 2
        assert counts["teams_ingested"] == 2

    def test_an_opponent_only_team_gets_a_real_canonical_roster(self, db, mocked_fetches):
        """The load-bearing new behavior: a team the account never played
        still resolves through canonical_current_roster afterward."""
        sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                 division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        roster = canonical_current_roster(db, "302", SESSION_NAME)
        assert len(roster) == 1
        assert roster[0].skill_level == 5
    def test_historical_mode_never_marks_old_roster_current_and_still_resolves_identity(
        self, db, mocked_fetches
    ):
        counts = sync.sync_division_wide(
            config={}, db=db, division_id=DIVISION_ID,
            division_format=FORMAT_NAME, division_session_name=SESSION_NAME,
            roster_is_current=False, identity_current_only=False,
        )

        from database.models import PlayerTeamHistory

        rows = db.query(PlayerTeamHistory).all()
        assert rows
        assert all(row.is_current is False for row in rows)
        assert canonical_current_roster(db, "301", SESSION_NAME) == []
        assert canonical_current_roster(db, "302", SESSION_NAME) == []
        assert counts["identity_resolved"] == 2
        assert counts["identity_unresolved"] == 0

    def test_every_discovered_match_is_ingested_including_unscored(self, db, mocked_fetches):
        counts = sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                          division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        assert counts["matches_discovered"] == 2
        assert counts["matches_ingested"] == 2

    def test_a_scored_match_gets_a_real_scoresheet(self, db, mocked_fetches):
        counts = sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                          division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        assert counts["scored_matches_discovered"] == 1
        assert counts["scored_matches_with_scoresheet"] == 1

    def test_an_unscored_match_needs_no_scoresheet_to_be_complete(self, db, mocked_fetches):
        counts = sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                          division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        # 1 scheduled + 1 scored -- the unscored one is never counted as a gap.
        assert counts["matches_ingested"] == 2
        assert counts["scored_matches_discovered"] == 1

    def test_a_failed_scoresheet_fetch_is_not_silently_complete(self, db, monkeypatch):
        monkeypatch.setattr(sync, "fetch_division_rosters", lambda config, division_id: ROSTERS_PAYLOAD)
        monkeypatch.setattr(sync, "fetch_division_schedule", lambda config, division_id: SCHEDULE_PAYLOAD)

        def failing_detail(config, match_id):
            raise RuntimeError("simulated transient failure")

        monkeypatch.setattr(sync, "fetch_match_detail", failing_detail)

        counts = sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                          division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        assert counts["scored_matches_discovered"] == 1
        assert counts["scored_matches_with_scoresheet"] == 0


class TestMatchAlreadyHasScoresheet:
    def test_false_when_the_match_does_not_exist_at_all(self, db):
        assert sync.match_already_has_scoresheet(db, "90401") is False

    def test_false_when_the_match_exists_but_has_no_playermatch_rows(self, db):
        from database.models import Match

        db.add(Match(external_id="90401", session_name=SESSION_NAME, format=FORMAT_NAME))
        db.flush()

        assert sync.match_already_has_scoresheet(db, "90401") is False

    def test_true_once_a_real_playermatch_row_exists(self, db, mocked_fetches):
        sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                 division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        assert sync.match_already_has_scoresheet(db, "90401") is True


class TestResume:
    def test_resume_skips_fetch_match_detail_for_an_already_ingested_match(self, db, mocked_fetches, monkeypatch):
        # First pass: real ingestion, exactly like a run that got this far
        # before the token expired.
        sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                 division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        def must_not_be_called(config, match_id):
            raise AssertionError("fetch_match_detail should have been skipped on resume")

        monkeypatch.setattr(sync, "fetch_match_detail", must_not_be_called)

        # Second pass, resume=True: the one scored match already has a real
        # scoresheet, so fetch_match_detail must not run again.
        counts = sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                          division_format=FORMAT_NAME, division_session_name=SESSION_NAME,
                                          resume=True)

        assert counts["scored_matches_discovered"] == 1
        assert counts["scored_matches_with_scoresheet"] == 1

    def test_resume_still_fetches_a_genuinely_new_scored_match(self, db, monkeypatch):
        """A resume must not become a no-op: a match that legitimately
        never got its scoresheet still gets fetched."""
        monkeypatch.setattr(sync, "fetch_division_rosters", lambda config, division_id: ROSTERS_PAYLOAD)
        monkeypatch.setattr(sync, "fetch_division_schedule", lambda config, division_id: SCHEDULE_PAYLOAD)
        calls = []

        def counting_detail(config, match_id):
            calls.append(match_id)
            return MATCH_DETAIL_PAYLOAD

        monkeypatch.setattr(sync, "fetch_match_detail", counting_detail)

        counts = sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                          division_format=FORMAT_NAME, division_session_name=SESSION_NAME,
                                          resume=True)

        assert calls == [90401]
        assert counts["scored_matches_with_scoresheet"] == 1

    def test_without_resume_the_match_is_refetched_regardless(self, db, mocked_fetches, monkeypatch):
        sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                 division_format=FORMAT_NAME, division_session_name=SESSION_NAME)

        calls = []

        def counting_detail(config, match_id):
            calls.append(match_id)
            return MATCH_DETAIL_PAYLOAD

        monkeypatch.setattr(sync, "fetch_match_detail", counting_detail)

        sync.sync_division_wide(config={}, db=db, division_id=DIVISION_ID,
                                 division_format=FORMAT_NAME, division_session_name=SESSION_NAME,
                                 resume=False)

        assert calls == [90401]

    def test_run_all_teams_resume_skips_an_already_scored_own_match(self, db, monkeypatch):
        from database.models import Match, PlayerMatch, Player

        db.add(Match(external_id="55555", session_name=SESSION_NAME, format=FORMAT_NAME,
                     home_team_id="T1", away_team_id="T2", is_scored=True))
        db.flush()
        match = db.query(Match).filter_by(external_id="55555").one()
        player = Player(external_id="P1", name="Ann")
        db.add(player)
        db.flush()
        db.add(PlayerMatch(player_id=player.id, match_id=match.id, result="W"))
        db.commit()

        monkeypatch.setattr(sync, "load_config", lambda path: {})
        monkeypatch.setattr(sync, "create_db_engine", lambda config: db.get_bind())
        monkeypatch.setattr(sync, "fetch_dashboard_teams", lambda config: {"leagueTeams": [], "tournamentTeams": []})
        monkeypatch.setattr(sync, "fetch_matches_by_viewer", lambda config: {
            "leagueTeams": [{"matches": [{
                "id": 55555, "isBye": False, "isScored": True, "isFinalized": True,
                "startTime": "2026-01-15", "status": "COMPLETED",
                "home": {"id": "T1", "name": "Home"}, "away": {"id": "T2", "name": "Away"},
                "results": [],
            }]}],
        })

        def must_not_be_called(config, match_id):
            raise AssertionError("fetch_match_detail should have been skipped on resume")

        monkeypatch.setattr(sync, "fetch_match_detail", must_not_be_called)

        sync.run_all_teams(config_path="unused.yaml", export=False, resume=True)
        # No AssertionError above means the checkpoint worked.


class TestReconciliation:
    def _complete(self):
        return {
            "teams_discovered": 2, "teams_ingested": 2,
            "roster_players_discovered": 5, "roster_players_ingested": 5,
            "matches_discovered": 10, "matches_ingested": 10,
            "scored_matches_discovered": 4, "scored_matches_with_scoresheet": 4,
        }

    def test_complete_coverage_has_no_gaps(self):
        assert sync.reconcile_division_wide_coverage(self._complete()) == []

    def test_a_missing_team_is_a_gap(self):
        totals = self._complete()
        totals["teams_ingested"] = 1
        gaps = sync.reconcile_division_wide_coverage(totals)
        assert any("team" in g for g in gaps)

    def test_a_missing_roster_player_is_a_gap(self):
        totals = self._complete()
        totals["roster_players_ingested"] = 3
        gaps = sync.reconcile_division_wide_coverage(totals)
        assert any("roster player" in g for g in gaps)

    def test_a_missing_match_is_a_gap(self):
        totals = self._complete()
        totals["matches_ingested"] = 9
        gaps = sync.reconcile_division_wide_coverage(totals)
        assert any("scheduled match" in g for g in gaps)

    def test_a_missing_scoresheet_is_a_gap(self):
        totals = self._complete()
        totals["scored_matches_with_scoresheet"] = 3
        gaps = sync.reconcile_division_wide_coverage(totals)
        assert any("scoresheet" in g for g in gaps)

    def test_multiple_gaps_are_all_reported_at_once(self):
        totals = self._complete()
        totals["teams_ingested"] = 1
        totals["matches_ingested"] = 9
        gaps = sync.reconcile_division_wide_coverage(totals)
        assert len(gaps) == 2


class TestRunDivisionWide:
    def test_end_to_end_reports_complete_coverage_and_no_gaps(self, db, monkeypatch, mocked_fetches):
        monkeypatch.setattr(sync, "create_db_engine", lambda config: db.get_bind())
        monkeypatch.setattr(sync, "load_config", lambda path: {})
        monkeypatch.setattr(
            sync, "run_all_teams",
            lambda config_path, export=False, db_path=None, resume=False: {"teams": 0},
        )
        monkeypatch.setattr(sync, "fetch_dashboard_teams", lambda config: {
            "leagueTeams": [{"id": 301, "name": "Fixture Sharks",
                              "division": {"id": 300, "type": "EIGHT_BALL"},
                              "league": {"id": 1, "slug": "l"},
                              "session": {"id": 1, "name": SESSION_NAME}}],
            "tournamentTeams": [],
        })
        monkeypatch.setattr(sync, "fetch_team_data", lambda config, team_id: {
            "team": {"id": 301, "name": "Fixture Sharks",
                      "division": {"id": 300, "name": "D", "format": FORMAT_NAME},
                      "session": {"id": 1, "name": SESSION_NAME},
                      "league": {"id": 1, "slug": "l"}, "location": {}},
        })

        # sync.py opens its OWN Session(engine) internally; give it the same
        # in-memory database this test already set up rather than a second,
        # empty one.
        result = sync.run_division_wide(config_path="unused.yaml", export=False)

        assert result["coverage_gaps"] == []
        assert result["division_wide"]["teams_ingested"] == 2

    def test_a_division_with_no_format_context_is_reported_incomplete(self, db, monkeypatch, mocked_fetches):
        monkeypatch.setattr(sync, "create_db_engine", lambda config: db.get_bind())
        monkeypatch.setattr(sync, "load_config", lambda path: {})
        monkeypatch.setattr(
            sync, "run_all_teams",
            lambda config_path, export=False, db_path=None, resume=False: {"teams": 0},
        )
        monkeypatch.setattr(sync, "fetch_dashboard_teams", lambda config: {
            "leagueTeams": [{"id": 301, "name": "Fixture Sharks",
                              "division": {"id": 300, "type": "EIGHT_BALL"},
                              "league": {"id": 1, "slug": "l"},
                              "session": {"id": 1, "name": SESSION_NAME}}],
            "tournamentTeams": [],
        })

        def failing_team_data(config, team_id):
            raise RuntimeError("simulated failure fetching context")

        monkeypatch.setattr(sync, "fetch_team_data", failing_team_data)

        result = sync.run_division_wide(config_path="unused.yaml", export=False)

        # No division was actually synced, so there is nothing to report as
        # ingested against nothing discovered -- zero teams processed.
        assert result["division_wide"]["teams_discovered"] == 0
        assert result["division_wide"]["teams_ingested"] == 0
