"""Adversarial tests for row-scoped historical Ultimate Coach identity repair."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Match, Player, PlayerHeadToHead, PlayerMatch, PlayerTeamHistory
from scripts.repair_ultimate_coach_historical_identities import repair_historical_identities

SESSION = "Fall 2024"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def roster_player(db, external_id, name, team_id, *, session=SESSION, division="D1"):
    player = Player(external_id=external_id, name=name)
    db.add(player)
    db.flush()
    db.add(
        PlayerTeamHistory(
            player_id=player.id,
            team_external_id=team_id,
            team_name=f"Team {team_id}",
            division_id=division,
            session_name=session,
            is_current=False,
        )
    )
    db.flush()
    return player


def alias_player(db, external_id, name):
    player = Player(external_id=external_id, name=name)
    db.add(player)
    db.flush()
    return player


def match(db, external_id, *, session=SESSION, home="TA", away="TB"):
    row = Match(
        external_id=external_id,
        session_name=session,
        format="EIGHT",
        home_team_id=home,
        away_team_id=away,
        home_team_name=f"Team {home}",
        away_team_name=f"Team {away}",
        match_date="2024-09-01T19:00:00-06:00",
        is_scored=True,
        is_finalized=True,
        is_bye=False,
    )
    db.add(row)
    db.flush()
    return row


def player_match(db, player, match_row, team_id):
    row = PlayerMatch(
        player_id=player.id,
        match_id=match_row.id,
        team_id=team_id,
        team_name=f"Team {team_id}",
        match_date=match_row.match_date,
    )
    db.add(row)
    db.flush()
    return row


def h2h(db, player, opponent, match_row, result="W"):
    row = PlayerHeadToHead(
        player_id=player.id,
        opponent_id=opponent.id,
        match_id=match_row.id,
        result=result,
        format="EIGHT",
        session_name=match_row.session_name,
    )
    db.add(row)
    db.flush()
    return row


def test_dry_run_resolves_historical_noncurrent_roster_without_writing(db):
    real = roster_player(db, "1001", "Historical Ann", "TA")
    alias = alias_player(db, "90001", "Historical Ann")
    m = match(db, "M1")
    pm = player_match(db, alias, m, "TA")
    db.commit()

    report = repair_historical_identities(db, apply=False)

    assert report.scopes_examined == 1
    assert report.scopes_resolved_unique == 1
    assert report.scopes_rewrite_planned == 1
    assert report.scopes_unresolved == 0
    assert db.get(PlayerMatch, pm.id).player_id == alias.id
    assert db.get(PlayerMatch, pm.id).player_id != real.id


def test_apply_rewrites_exact_player_match_and_both_h2h_sides(db):
    real_a = roster_player(db, "1001", "Ann", "TA")
    real_b = roster_player(db, "1002", "Bob", "TB", division="D2")
    alias_a = alias_player(db, "90001", "Ann")
    alias_b = alias_player(db, "90002", "Bob")
    m = match(db, "M1")
    pm_a = player_match(db, alias_a, m, "TA")
    pm_b = player_match(db, alias_b, m, "TB")
    row_ab = h2h(db, alias_a, alias_b, m, "W")
    row_ba = h2h(db, alias_b, alias_a, m, "L")
    db.commit()

    report = repair_historical_identities(db, apply=True)

    assert report.scopes_rewrite_planned == 2
    assert report.player_match_rows_rewritten == 2
    assert report.h2h_id_fields_rewrite_planned == 4
    assert report.h2h_id_fields_rewritten == 4
    assert db.get(PlayerMatch, pm_a.id).player_id == real_a.id
    assert db.get(PlayerMatch, pm_b.id).player_id == real_b.id
    assert (db.get(PlayerHeadToHead, row_ab.id).player_id, db.get(PlayerHeadToHead, row_ab.id).opponent_id) == (
        real_a.id,
        real_b.id,
    )
    assert (db.get(PlayerHeadToHead, row_ba.id).player_id, db.get(PlayerHeadToHead, row_ba.id).opponent_id) == (
        real_b.id,
        real_a.id,
    )


def test_same_alias_player_can_resolve_differently_in_two_match_scopes(db):
    """Proves repair is match-scoped rather than one global alias rewrite."""
    real_a = roster_player(db, "1001", "Alex Same", "TA", division="D1")
    real_b = roster_player(db, "1002", "Alex Same", "TB", division="D2")
    alias = alias_player(db, "99999", "Alex Same")
    m1 = match(db, "M1", home="TA", away="TX")
    m2 = match(db, "M2", home="TB", away="TY")
    pm1 = player_match(db, alias, m1, "TA")
    pm2 = player_match(db, alias, m2, "TB")
    db.commit()

    report = repair_historical_identities(db, apply=True)

    assert report.scopes_examined == 2
    assert report.scopes_rewrite_planned == 2
    assert db.get(PlayerMatch, pm1.id).player_id == real_a.id
    assert db.get(PlayerMatch, pm2.id).player_id == real_b.id


def test_existing_canonical_player_match_blocks_alias_rewrite(db):
    real = roster_player(db, "1001", "Ann", "TA")
    alias = alias_player(db, "90001", "Ann")
    m = match(db, "M1")
    alias_pm = player_match(db, alias, m, "TA")
    canonical_pm = player_match(db, real, m, "TA")
    db.commit()

    report = repair_historical_identities(db, apply=True)

    assert report.scopes_blocked_collision == 1
    assert report.scopes_rewrite_planned == 0
    assert any(row["reason"] == "CANONICAL_PLAYER_MATCH_ALREADY_EXISTS" for row in report.blocked_scopes)
    assert db.get(PlayerMatch, alias_pm.id).player_id == alias.id
    assert db.get(PlayerMatch, canonical_pm.id).player_id == real.id


def test_two_alias_scopes_cannot_collapse_to_same_canonical_match(db):
    real = roster_player(db, "1001", "Ann Same", "TA")
    alias_1 = alias_player(db, "90001", "Ann Same")
    alias_2 = alias_player(db, "90002", "Ann Same")
    m = match(db, "M1")
    pm1 = player_match(db, alias_1, m, "TA")
    pm2 = player_match(db, alias_2, m, "TA")
    db.commit()

    report = repair_historical_identities(db, apply=True)

    assert report.scopes_rewrite_planned == 0
    assert report.scopes_blocked_collision == 2
    assert {
        row["reason"] for row in report.blocked_scopes
    } == {"MULTIPLE_ALIAS_SCOPES_TO_SAME_CANONICAL_MATCH"}
    assert db.get(PlayerMatch, pm1.id).player_id == alias_1.id
    assert db.get(PlayerMatch, pm2.id).player_id == alias_2.id
    assert real.id not in {db.get(PlayerMatch, pm1.id).player_id, db.get(PlayerMatch, pm2.id).player_id}


def test_ambiguous_historical_roster_name_remains_unresolved(db):
    roster_player(db, "1001", "Adam Same", "TA")
    roster_player(db, "1002", "Adam Same", "TA", division="D2")
    alias = alias_player(db, "90001", "Adam Same")
    m = match(db, "M1")
    pm = player_match(db, alias, m, "TA")
    db.commit()

    report = repair_historical_identities(db, apply=True)

    assert report.scopes_unresolved == 1
    assert report.scopes_rewrite_planned == 0
    assert report.unresolved_scopes[0]["reason"] == "NO_UNIQUE_HISTORICAL_ROSTER_IDENTITY"
    assert db.get(PlayerMatch, pm.id).player_id == alias.id


def test_missing_session_scope_is_unresolved_and_untouched(db):
    roster_player(db, "1001", "Ann", "TA")
    alias = alias_player(db, "90001", "Ann")
    m = match(db, "M1", session="")
    pm = player_match(db, alias, m, "TA")
    db.commit()

    report = repair_historical_identities(db, apply=True)

    assert report.scopes_unresolved == 1
    assert report.unresolved_scopes[0]["reason"] == "MISSING_SESSION_SCOPE"
    assert db.get(PlayerMatch, pm.id).player_id == alias.id


def test_h2h_self_pairing_risk_blocks_entire_source_scope(db):
    real = roster_player(db, "1001", "Ann", "TA")
    alias = alias_player(db, "90001", "Ann")
    m = match(db, "M1")
    pm = player_match(db, alias, m, "TA")
    row = h2h(db, alias, real, m, "W")
    db.commit()

    report = repair_historical_identities(db, apply=True)

    assert report.h2h_rows_blocked_self_pairing == 1
    assert report.scopes_rewrite_planned == 0
    assert report.scopes_blocked_collision == 1
    assert any(row_["reason"] == "H2H_SELF_PAIRING_AFTER_RESOLUTION" for row_ in report.blocked_scopes)
    assert db.get(PlayerMatch, pm.id).player_id == alias.id
    assert db.get(PlayerHeadToHead, row.id).player_id == alias.id
    assert db.get(PlayerHeadToHead, row.id).opponent_id == real.id


def test_already_canonical_historical_scope_is_noop(db):
    real = roster_player(db, "1001", "Ann", "TA")
    m = match(db, "M1")
    pm = player_match(db, real, m, "TA")
    db.commit()

    report = repair_historical_identities(db, apply=True)

    assert report.scopes_resolved_unique == 1
    assert report.scopes_already_canonical == 1
    assert report.scopes_rewrite_planned == 0
    assert report.player_match_rows_rewritten == 0
    assert db.get(PlayerMatch, pm.id).player_id == real.id


def test_report_explicitly_stays_offline_and_probability_locked(db):
    report = repair_historical_identities(db, apply=False)
    payload = report.to_dict(applied=False)

    assert payload["network_used"] is False
    assert payload["applied"] is False
    assert payload["identity_scope_rule"] == "EXACT_TEAM_SESSION_MATCH_SCOPE"
    assert payload["probability_publication"] == "FORBIDDEN"
    assert report.resolution_rate is None


def test_duplicate_alias_player_match_scope_is_blocked(db):
    roster_player(db, "1001", "Ann", "TA")
    alias = alias_player(db, "90001", "Ann")
    m = match(db, "M1")
    pm1 = player_match(db, alias, m, "TA")
    pm2 = player_match(db, alias, m, "TA")
    db.commit()

    report = repair_historical_identities(db, apply=True)

    assert report.duplicate_alias_match_scopes == 1
    assert report.scopes_blocked_collision == 1
    assert report.scopes_rewrite_planned == 0
    assert report.blocked_scopes[0]["reason"] == "DUPLICATE_ALIAS_MATCH_SCOPE"
    assert db.get(PlayerMatch, pm1.id).player_id == alias.id
    assert db.get(PlayerMatch, pm2.id).player_id == alias.id


def test_h2h_rewrite_never_crosses_match_scope_for_reused_alias(db):
    real_a = roster_player(db, "1001", "Alex Same", "TA", division="D1")
    real_b = roster_player(db, "1002", "Alex Same", "TB", division="D2")
    opp_a = roster_player(db, "2001", "Opponent A", "TX", division="DX")
    opp_b = roster_player(db, "2002", "Opponent B", "TY", division="DY")
    alias = alias_player(db, "99999", "Alex Same")

    m1 = match(db, "M1", home="TA", away="TX")
    m2 = match(db, "M2", home="TB", away="TY")
    player_match(db, alias, m1, "TA")
    player_match(db, alias, m2, "TB")
    row1 = h2h(db, alias, opp_a, m1, "W")
    row2 = h2h(db, alias, opp_b, m2, "L")
    db.commit()

    report = repair_historical_identities(db, apply=True)

    assert report.scopes_rewrite_planned == 2
    assert report.h2h_id_fields_rewritten == 2
    assert db.get(PlayerHeadToHead, row1.id).player_id == real_a.id
    assert db.get(PlayerHeadToHead, row1.id).opponent_id == opp_a.id
    assert db.get(PlayerHeadToHead, row2.id).player_id == real_b.id
    assert db.get(PlayerHeadToHead, row2.id).opponent_id == opp_b.id
