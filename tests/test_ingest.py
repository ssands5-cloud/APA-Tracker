"""Tests for database.ingest and the models it depends on.

These exercise the two ingest paths that share the `PlayerMatch` table
(historical per-player results vs. per-match rosters) plus the roster-stat
columns on `Player`, which were previously being set on model instances
without being mapped columns -- silently discarded on every commit.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import ingest
from database.models import Base, Match, Player, PlayerMatch, Team


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_upsert_roster_persists_stat_columns(db):
    """Roster stats must survive a reload, not just live on the in-memory object."""
    team = ingest.upsert_team(db, "T1", "Team One")
    ingest.upsert_roster(
        db,
        team,
        [
            {
                "player_id": "P1",
                "player_name": "Alice",
                "skill_level": "5",
                "matches_won": "3",
                "matches_played": "4",
                "win_pct": "0.75",
                "ppm": "2.1",
                "pa": "30",
            }
        ],
    )

    db.expire_all()  # force a real reload from the database, not the session cache
    reloaded = db.query(Player).filter_by(external_id="P1").one()
    assert reloaded.matches_won == 3
    assert reloaded.matches_played == 4
    assert reloaded.win_pct == pytest.approx(0.75)
    assert reloaded.ppm == pytest.approx(2.1)
    assert reloaded.pa == pytest.approx(30.0)


def test_ingest_match_creates_match_row(db):
    match_id = ingest.ingest_match(
        db,
        match_id="M1",
        home_team_id="T1",
        away_team_id="T2",
        home_team_name="Team One",
        away_team_name="Team Two",
        location="Corner Pocket Bar",
        match_date="2026-09-01",
        status="final",
    )

    match = db.query(Match).filter_by(external_id="M1").one()
    assert match.id == match_id
    assert match.home_team_name == "Team One"
    assert match.away_team_name == "Team Two"
    assert match.location == "Corner Pocket Bar"
    assert match.status == "final"


def test_ingest_match_is_idempotent(db):
    first = ingest.ingest_match(
        db, "M1", "T1", "T2", "Team One", "Team Two",
    )
    second = ingest.ingest_match(
        db, "M1", "T1", "T2", "Team One", "Team Two",
    )
    assert first is not None
    assert second is None  # already exists, ingest_match returns None
    assert db.query(Match).filter_by(external_id="M1").count() == 1


def test_ingest_match_roster_links_players_to_match(db):
    match_id = ingest.ingest_match(db, "M1", "T1", "T2", "Team One", "Team Two")

    count = ingest.ingest_match_roster(
        db,
        match_id,
        "T1",
        "Team One",
        [
            {
                "player_id": "P1",
                "player_name": "Alice",
                "skill_level": "5",
                "matches_won": "3",
                "matches_played": "4",
                "win_pct": "0.75",
                "ppm": "2.1",
                "pa": "30",
            }
        ],
    )
    assert count == 1

    row = db.query(PlayerMatch).filter_by(match_id=match_id).one()
    assert row.team_name == "Team One"
    assert row.matches_won == 3
    assert row.win_pct == pytest.approx(0.75)

    player = db.query(Player).filter_by(external_id="P1").one()
    assert row.player_id == player.id


def test_ingest_match_roster_is_idempotent_per_player(db):
    match_id = ingest.ingest_match(db, "M1", "T1", "T2", "Team One", "Team Two")
    roster = [{"player_id": "P1", "player_name": "Alice"}]

    first_count = ingest.ingest_match_roster(db, match_id, "T1", "Team One", roster)
    second_count = ingest.ingest_match_roster(db, match_id, "T1", "Team One", roster)

    assert first_count == 1
    assert second_count == 0  # already linked, skipped
    assert db.query(PlayerMatch).filter_by(match_id=match_id).count() == 1


def test_player_match_history_and_match_roster_coexist(db):
    """The two ingest paths share player_matches but must not collide.

    ingest_player_matches() rows have match_id=None; ingest_match_roster()
    rows have match_date=None/opponent=None. Both must be able to insert
    rows for the same player without tripping the (player_id, match_date,
    opponent) unique constraint.
    """
    team = ingest.upsert_team(db, "T1", "Team One")
    player = ingest.upsert_player(db, "P1", "Alice", team)

    ingest.ingest_player_matches(
        db,
        player,
        [{"match_date": "2026-08-01", "opponent": "Bob", "result": "W"}],
    )

    match_id = ingest.ingest_match(db, "M1", "T1", "T2", "Team One", "Team Two")
    ingest.ingest_match_roster(db, match_id, "T1", "Team One", [{"player_id": "P1", "player_name": "Alice"}])

    rows = db.query(PlayerMatch).filter_by(player_id=player.id).all()
    assert len(rows) == 2
