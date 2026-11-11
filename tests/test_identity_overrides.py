import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Match, Player, PlayerHeadToHead, PlayerMatch, PlayerTeamHistory
from pipeline.identity_overrides import IdentityOverrideError, IdentityOverrides, SCHEMA, SCOPE_FIELDS
from pipeline.ultimate_coach_refresh import RefreshFailed, fixture_identity_resolver
from scripts.refresh_ultimate_coach_current_session import reconcile_match


APPROVAL = {
    "match_id": "90401", "score_row_id": "1234", "scoresheet_player_id": "500",
    "team_id": "301", "division_id": "300", "league_id": "7", "session_id": "26", "format": "EIGHT",
    "canonical_member_id": "101", "reviewed_by": "Owner", "reviewed_at": "2026-11-11T09:00:00-07:00",
    "evidence_reference": "Synthetic owner-reviewed source",
}
DIVISION = {"division_id": "300", "format": "EIGHT", "session_name": "Fall"}
CATALOG = {"divisions": [{**DIVISION, "league_id": "7", "session_id": "26"}]}
SOURCE_ROW = {"match_id": "90401", "score_row_id": "1234", "player_id": "500",
              "team_id": "301", "player_name": "Scoresheet Display", "result": "W"}


def write_overrides(path, *approvals):
    path.write_text(json.dumps({"schema": SCHEMA, "overrides": approvals}), encoding="utf-8")
    return IdentityOverrides(path)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Player(external_id="101", name="Canonical Name"),
                         Player(external_id="102", name="Other Player"),
                         Player(external_id="500", name="Scoresheet Display")])
        session.commit()
        yield session
    engine.dispose()


@pytest.mark.parametrize("field", SCOPE_FIELDS)
def test_override_does_not_follow_an_id_outside_exact_scope(db, tmp_path, field):
    value = "NINE" if field == "format" else "9999"
    approvals = write_overrides(tmp_path / "review.json", {**APPROVAL, field: value})
    store = SimpleNamespace(exact_player_members=lambda: {})
    resolver = fixture_identity_resolver(store, CATALOG, DIVISION, approvals)

    assert resolver(db, "Fall", [SOURCE_ROW.copy()]) == ({}, 0, 1)
    assert not approvals.applied


@pytest.mark.parametrize("failure", ["captured_conflict", "roster_conflict", "missing_member",
                                     "duplicate_alias", "duplicate_member"])
def test_override_rejects_conflicts_without_recording_application(db, tmp_path, failure):
    approvals = write_overrides(tmp_path / "review.json", APPROVAL)
    links = {("7", "26", "EIGHT", "500"): {"102"}} if failure == "captured_conflict" else {}
    rows = [SOURCE_ROW.copy()]
    if failure == "roster_conflict":
        other = db.query(Player).filter_by(external_id="102").one()
        other.name = SOURCE_ROW["player_name"]
        db.add(PlayerTeamHistory(player_id=other.id, team_external_id="301",
                                division_id="300", session_name="Fall", is_current=True))
        db.commit()
    if failure == "missing_member":
        approvals = write_overrides(tmp_path / "review.json", {**APPROVAL, "canonical_member_id": "999"})
    if failure == "duplicate_alias":
        rows.append({**SOURCE_ROW, "score_row_id": "1235"})
    if failure == "duplicate_member":
        rows.append({**SOURCE_ROW, "score_row_id": "1235", "player_id": "101"})
    resolver = fixture_identity_resolver(SimpleNamespace(exact_player_members=lambda: links),
                                         CATALOG, DIVISION, approvals)
    with pytest.raises(RefreshFailed, match="reviewed"):
        resolver(db, "Fall", rows)
    assert not approvals.applied


def test_reviewed_binding_reconciles_results_and_h2h_without_changing_roster(db, tmp_path):
    approvals = write_overrides(tmp_path / "review.json", APPROVAL)
    match = Match(external_id="90401", session_name="Fall", format="EIGHT",
                  home_team_id="301", away_team_id="302", match_date="2026-11-01")
    old = db.query(Player).filter_by(external_id="500").one()
    opponent = db.query(Player).filter_by(external_id="102").one()
    db.add(match)
    db.add(PlayerTeamHistory(player_id=opponent.id, team_external_id="302",
                             division_id="300", session_name="Fall", is_current=True))
    db.flush()
    db.add(PlayerMatch(player_id=old.id, match_id=match.id, team_id="301"))
    db.commit()

    def scoresheet(_config, _match_id):
        other = {"player_id": "102", "player_name": "Other Player", "team_id": "302", "result": "L"}
        pairs = [{"player_id": "500", "player_name": "Scoresheet Display", "opponent_id": "102",
                  "opponent_name": "Other Player", "result": "W"},
                 {"player_id": "102", "player_name": "Other Player", "opponent_id": "500",
                  "opponent_name": "Scoresheet Display", "result": "L"}]
        return [SOURCE_ROW.copy(), other], pairs

    resolver = fixture_identity_resolver(SimpleNamespace(exact_player_members=lambda: {}),
                                         CATALOG, DIVISION, approvals)
    first = reconcile_match({}, db, "90401", "Fall", scoresheet=scoresheet, resolve=resolver)
    second = reconcile_match({}, db, "90401", "Fall", scoresheet=scoresheet, resolve=resolver)
    assert first["removed"] == ["500"]
    assert second["status"] == "unchanged"
    canonical = db.query(Player).filter_by(external_id="101").one()
    assert canonical.name == "Canonical Name" and canonical.team_id is None
    assert db.query(PlayerTeamHistory).filter_by(player_id=canonical.id).count() == 0
    assert db.query(PlayerMatch).filter_by(match_id=match.id).count() == 2
    assert {(r.player_id, r.opponent_id) for r in db.query(PlayerHeadToHead).all()} == {
        (canonical.id, opponent.id), (opponent.id, canonical.id),
    }
    assert approvals.audit()["reviewed"] == [APPROVAL]
    assert len(approvals.audit()["applied_scope_sha256"]) == 1


@pytest.mark.parametrize("rows", [
    ({**APPROVAL, "reviewed_at": "2026-11-11T09:00:00"},),
    ({**APPROVAL, "evidence_reference": ""},),
    (APPROVAL, APPROVAL),
])
def test_review_metadata_is_required_and_duplicate_scope_is_rejected(tmp_path, rows):
    with pytest.raises(IdentityOverrideError):
        write_overrides(tmp_path / "review.json", *rows)
