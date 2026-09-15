"""Tests for scripts/build_coherent_demo.py.

These lock in the one property the existing per-unit fixtures do NOT have,
and whose absence is exactly why every cross-referencing analytics module
rendered "No data" against scripts/build_demo.py's output: the players who
carry match/skill history must be the SAME players the canonical current
roster names, for both teams, in one session and format.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from analytics.pairing_evidence import build_pairing_evidence_matrix
from database.models import Match, Player, PlayerHeadToHead, PlayerMatch, PlayerTrend
from database.queries import canonical_current_roster
from scripts.build_coherent_demo import (
    FORMAT_NAME,
    MATCHES,
    OPP_ROSTER,
    OPP_TEAM_ID,
    OUR_ROSTER,
    OUR_TEAM_ID,
    REMAINING_MATCH_ID,
    SESSION_NAME,
    build,
)


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("coherent") / "coherent.db"
    build(str(db_path))
    engine = create_engine(f"sqlite:///{db_path}")
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class TestCanonicalRosters:
    def test_both_teams_have_a_full_canonical_current_roster(self, db):
        ours = canonical_current_roster(db, OUR_TEAM_ID, SESSION_NAME)
        theirs = canonical_current_roster(db, OPP_TEAM_ID, SESSION_NAME)

        assert len(ours) == len(OUR_ROSTER)
        assert len(theirs) == len(OPP_ROSTER)

    def test_every_roster_player_has_a_real_skill_level(self, db):
        for row in canonical_current_roster(db, OUR_TEAM_ID, SESSION_NAME):
            assert row.skill_level is not None

    def test_roster_win_counts_match_the_real_recorded_results(self, db):
        """matches_played must equal the real number of ingested matches --
        a roster aggregate that disagrees with the match rows behind it is
        exactly the incoherence this fixture exists to avoid."""
        for row in canonical_current_roster(db, OUR_TEAM_ID, SESSION_NAME):
            assert row.matches_played == len(MATCHES)
            assert 0 <= row.matches_won <= row.matches_played


class TestIdentityCoherence:
    def test_roster_players_are_the_same_players_who_have_match_history(self, db):
        roster_ids = {r.player_id for r in canonical_current_roster(db, OUR_TEAM_ID, SESSION_NAME)}
        with_history = {pm.player_id for pm in db.query(PlayerMatch).all()}

        assert roster_ids <= with_history

    def test_roster_players_are_the_same_players_who_have_head_to_head_rows(self, db):
        roster_ids = {r.player_id for r in canonical_current_roster(db, OPP_TEAM_ID, SESSION_NAME)}
        with_h2h = {row.player_id for row in db.query(PlayerHeadToHead).all()}

        assert roster_ids <= with_h2h

    def test_every_roster_player_has_a_persisted_trend_row(self, db):
        roster_ids = {r.player_id for r in canonical_current_roster(db, OUR_TEAM_ID, SESSION_NAME)}
        with_trends = {t.player_id for t in db.query(PlayerTrend).all()}

        assert roster_ids <= with_trends


class TestFeasiblePairings:
    def test_the_full_cross_product_is_feasible(self, db):
        ours = canonical_current_roster(db, OUR_TEAM_ID, SESSION_NAME)
        theirs = canonical_current_roster(db, OPP_TEAM_ID, SESSION_NAME)

        matrix = build_pairing_evidence_matrix(
            db,
            our_team_external_id=OUR_TEAM_ID,
            opponent_team_external_id=OPP_TEAM_ID,
            format=FORMAT_NAME,
            session_name=SESSION_NAME,
        )

        assert matrix.counts["total_feasible_pairings"] == len(ours) * len(theirs)

    def test_position_pairings_carry_real_direct_evidence(self, db):
        matrix = build_pairing_evidence_matrix(
            db,
            our_team_external_id=OUR_TEAM_ID,
            opponent_team_external_id=OPP_TEAM_ID,
            format=FORMAT_NAME,
            session_name=SESSION_NAME,
        )

        # Each of the five roster positions met its opposite number in every
        # ingested match, so exactly those five pairs are DIRECT.
        assert matrix.counts["DIRECT"] == len(OUR_ROSTER)
        assert matrix.counts["UNKNOWN"] == 0


class TestSchedule:
    def test_a_real_remaining_unscored_match_exists(self, db):
        remaining = db.query(Match).filter_by(external_id=REMAINING_MATCH_ID).one()

        assert remaining.is_scored is False
        assert remaining.is_bye is False

    def test_every_scored_match_is_finalized_with_both_scores(self, db):
        scored = db.query(Match).filter_by(is_scored=True).all()

        assert len(scored) == len(MATCHES)
        for match in scored:
            assert match.is_finalized is True
            assert match.home_score is not None
            assert match.away_score is not None

    def test_team_score_equals_the_sum_of_its_own_position_points(self, db):
        """The scoresheet and the team score cannot disagree."""
        for match in db.query(Match).filter_by(is_scored=True).all():
            rows = db.query(PlayerMatch).filter_by(match_id=match.id).all()
            home_points = sum(
                r.points_earned or 0 for r in rows if r.team_id == match.home_team_id
            )
            away_points = sum(
                r.points_earned or 0 for r in rows if r.team_id == match.away_team_id
            )
            assert home_points == match.home_score
            assert away_points == match.away_score


class TestFictionalIdentities:
    def test_no_real_person_or_team_name_is_used(self, db):
        """Rehearsal data must be unmistakably fictional."""
        names = {p.name for p in db.query(Player).all()}
        assert names == {name for _, name, _ in OUR_ROSTER} | {name for _, name, _ in OPP_ROSTER}
        assert all(name.endswith(("Fixture", "Sample")) for name in names)
