"""Tests for scripts/backfill_player_identity.py.

Repairs an already-ingested database where PlayerMatch/PlayerHeadToHead
rows are keyed on a scoresheet's own alias id instead of the canonical
roster's real id -- the exact defect scheduler.graphql_sync now prevents
at ingest time (see tests/test_division_wide_sync.py's TestIdentityResolution),
but which an already-populated database from before that fix still has.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Match, Player, PlayerHeadToHead, PlayerMatch, PlayerTeamHistory
from scripts.backfill_player_identity import backfill

TEAM = "301"
OPPONENT_TEAM = "302"
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


def _roster_player(db, external_id, name, team_id):
    player = Player(external_id=external_id, name=name)
    db.add(player)
    db.flush()
    db.add(PlayerTeamHistory(
        player_id=player.id, team_external_id=team_id, session_name=SESSION, is_current=True,
    ))
    db.flush()
    return player


def _alias_scoresheet_player(db, alias_external_id, name):
    """A player row created the OLD way -- keyed on the scoresheet's own
    alias id, with no PlayerTeamHistory row at all."""
    player = Player(external_id=alias_external_id, name=name)
    db.add(player)
    db.flush()
    return player


class TestDryRun:
    def test_a_resolvable_identity_is_reported_but_nothing_is_written(self, db):
        roster_ann = _roster_player(db, "9001", "Ann Fixture", TEAM)
        alias_ann = _alias_scoresheet_player(db, "99001", "Ann Fixture")
        match = Match(external_id="M1", session_name=SESSION, format="8-Ball Open",
                       home_team_id=TEAM, away_team_id=OPPONENT_TEAM)
        db.add(match)
        db.flush()
        db.add(PlayerMatch(player_id=alias_ann.id, match_id=match.id, team_id=TEAM))
        db.commit()

        report = backfill(db, apply=False)

        assert report.resolved == 1
        assert report.unresolved == 0
        # Nothing rewritten yet -- the PlayerMatch row still points at the alias.
        row = db.query(PlayerMatch).one()
        assert row.player_id == alias_ann.id
        assert row.player_id != roster_ann.id


class TestApply:
    def test_playermatch_rows_are_rewritten_to_the_real_roster_identity(self, db):
        roster_ann = _roster_player(db, "9001", "Ann Fixture", TEAM)
        alias_ann = _alias_scoresheet_player(db, "99001", "Ann Fixture")
        match = Match(external_id="M1", session_name=SESSION, format="8-Ball Open",
                       home_team_id=TEAM, away_team_id=OPPONENT_TEAM)
        db.add(match)
        db.flush()
        db.add(PlayerMatch(player_id=alias_ann.id, match_id=match.id, team_id=TEAM))
        db.commit()

        report = backfill(db, apply=True)

        assert report.player_match_rows_rewritten == 1
        row = db.query(PlayerMatch).one()
        assert row.player_id == roster_ann.id

    def test_head_to_head_rows_are_rewritten_on_both_sides(self, db):
        roster_ann = _roster_player(db, "9001", "Ann Fixture", TEAM)
        roster_uma = _roster_player(db, "9002", "Uma Sample", OPPONENT_TEAM)
        alias_ann = _alias_scoresheet_player(db, "99001", "Ann Fixture")
        alias_uma = _alias_scoresheet_player(db, "99002", "Uma Sample")
        match = Match(external_id="M1", session_name=SESSION, format="8-Ball Open",
                       home_team_id=TEAM, away_team_id=OPPONENT_TEAM,
                       is_scored=True, is_finalized=True, is_bye=False)
        db.add(match)
        db.flush()
        db.add(PlayerMatch(player_id=alias_ann.id, match_id=match.id, team_id=TEAM))
        db.add(PlayerMatch(player_id=alias_uma.id, match_id=match.id, team_id=OPPONENT_TEAM))
        db.add(PlayerHeadToHead(
            player_id=alias_ann.id, opponent_id=alias_uma.id, match_id=match.id,
            result="W", format="8-Ball Open", session_name=SESSION,
        ))
        db.add(PlayerHeadToHead(
            player_id=alias_uma.id, opponent_id=alias_ann.id, match_id=match.id,
            result="L", format="8-Ball Open", session_name=SESSION,
        ))
        db.commit()

        report = backfill(db, apply=True)

        assert report.head_to_head_rows_rewritten == 4  # 2 rows x 2 id columns each
        rows = db.query(PlayerHeadToHead).all()
        ids = {(r.player_id, r.opponent_id) for r in rows}
        assert ids == {(roster_ann.id, roster_uma.id), (roster_uma.id, roster_ann.id)}

    def test_the_direct_pairing_matrix_resolves_after_repair(self, db):
        """The real end-to-end proof: after backfill, the exact same
        canonical-roster query PairingEvidenceMatrix uses finds the
        evidence that was previously invisible to it."""
        roster_ann = _roster_player(db, "9001", "Ann Fixture", TEAM)
        roster_uma = _roster_player(db, "9002", "Uma Sample", OPPONENT_TEAM)
        alias_ann = _alias_scoresheet_player(db, "99001", "Ann Fixture")
        alias_uma = _alias_scoresheet_player(db, "99002", "Uma Sample")
        match = Match(external_id="M1", session_name=SESSION, format="8-Ball Open",
                       home_team_id=TEAM, away_team_id=OPPONENT_TEAM,
                       is_scored=True, is_finalized=True, is_bye=False)
        db.add(match)
        db.flush()
        db.add(PlayerMatch(player_id=alias_ann.id, match_id=match.id, team_id=TEAM))
        db.add(PlayerMatch(player_id=alias_uma.id, match_id=match.id, team_id=OPPONENT_TEAM))
        db.add(PlayerHeadToHead(
            player_id=alias_ann.id, opponent_id=alias_uma.id, match_id=match.id,
            result="W", format="8-Ball Open", session_name=SESSION,
        ))
        db.commit()

        backfill(db, apply=True)

        from analytics.pairing_evidence import EvidenceLabel, build_pairing_evidence_matrix

        matrix = build_pairing_evidence_matrix(
            db, our_team_external_id=TEAM, opponent_team_external_id=OPPONENT_TEAM,
            format="8-Ball Open", session_name=SESSION,
        )
        pairing = next(
            p for p in matrix.pairings if p.player_id == roster_ann.id and p.opponent_id == roster_uma.id
        )
        assert pairing.evidence_label == EvidenceLabel.DIRECT


class TestNoGuessing:
    def test_an_unresolvable_alias_is_left_completely_untouched(self, db):
        alias_sub = _alias_scoresheet_player(db, "99009", "Substitute Sub")
        match = Match(external_id="M1", session_name=SESSION, format="8-Ball Open",
                       home_team_id=TEAM, away_team_id=OPPONENT_TEAM)
        db.add(match)
        db.flush()
        db.add(PlayerMatch(player_id=alias_sub.id, match_id=match.id, team_id=TEAM))
        db.commit()

        report = backfill(db, apply=True)

        assert report.unresolved == 1
        assert "Substitute Sub" in report.unresolved_names[0]
        row = db.query(PlayerMatch).one()
        assert row.player_id == alias_sub.id  # untouched

    def test_an_ambiguous_name_on_the_current_roster_is_not_merged(self, db):
        _roster_player(db, "9001", "Adam Shapiro", TEAM)
        _roster_player(db, "9002", "Adam Shapiro", TEAM)
        alias = _alias_scoresheet_player(db, "99001", "Adam Shapiro")
        match = Match(external_id="M1", session_name=SESSION, format="8-Ball Open",
                       home_team_id=TEAM, away_team_id=OPPONENT_TEAM)
        db.add(match)
        db.flush()
        db.add(PlayerMatch(player_id=alias.id, match_id=match.id, team_id=TEAM))
        db.commit()

        report = backfill(db, apply=True)

        assert report.unresolved == 1
        row = db.query(PlayerMatch).one()
        assert row.player_id == alias.id  # untouched -- never guessed

    def test_a_row_already_on_its_real_roster_identity_is_a_no_op(self, db):
        roster_ann = _roster_player(db, "9001", "Ann Fixture", TEAM)
        match = Match(external_id="M1", session_name=SESSION, format="8-Ball Open",
                       home_team_id=TEAM, away_team_id=OPPONENT_TEAM)
        db.add(match)
        db.flush()
        db.add(PlayerMatch(player_id=roster_ann.id, match_id=match.id, team_id=TEAM))
        db.commit()

        report = backfill(db, apply=True)

        assert report.resolved == 1
        assert report.player_match_rows_rewritten == 0  # already correct, nothing to rewrite


class TestReportShape:
    def test_resolution_rate_is_none_with_nothing_examined(self, db):
        report = backfill(db, apply=False)
        assert report.identities_examined == 0
        assert report.resolution_rate is None

    def test_resolution_rate_reflects_real_counts(self, db):
        _roster_player(db, "9001", "Ann Fixture", TEAM)
        alias_ann = _alias_scoresheet_player(db, "99001", "Ann Fixture")
        alias_sub = _alias_scoresheet_player(db, "99009", "Substitute Sub")
        match = Match(external_id="M1", session_name=SESSION, format="8-Ball Open",
                       home_team_id=TEAM, away_team_id=OPPONENT_TEAM)
        db.add(match)
        db.flush()
        db.add(PlayerMatch(player_id=alias_ann.id, match_id=match.id, team_id=TEAM))
        db.add(PlayerMatch(player_id=alias_sub.id, match_id=match.id, team_id=TEAM))
        db.commit()

        report = backfill(db, apply=False)

        assert report.resolution_rate == 0.5
