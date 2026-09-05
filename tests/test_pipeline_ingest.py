"""Tests for the fixture-backed ingest pipeline.

Builds a small fixture tree on disk in exactly the layout the scraper writes
(README-scraper.md), then runs the real ingest against it -- so a change to
the fixture contract breaks these rather than silently producing an empty
database.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import (
    Base,
    Match,
    Player,
    PlayerHeadToHead,
    PlayerMatchup,
    Team,
)
from pipeline.fixtures import FixtureStore, unwrap
from pipeline.ingest import run as ingest_run


def write(root, entity, entity_id, operation, data, wrapped=False):
    """Write one fixture in the scraper's layout.

    `wrapped` emulates tools/capture_apa_graphql.py's envelope, the second
    schema that exists on disk.
    """
    folder = root / entity / str(entity_id)
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"data": data}
    if wrapped:
        payload = {"operationName": operation, "entityType": entity,
                   "entityId": str(entity_id), "response": {"data": data}}
    (folder / f"{operation}.json").write_text(json.dumps(payload), encoding="utf-8")


def team_payload(team_id, name, division_id, session="Fall 2026"):
    return {
        "team": {
            "id": team_id, "name": name, "number": "1", "standing": 2,
            "isTied": False,
            "division": {"id": division_id, "name": "8-Ball Open", "format": "EIGHT_BALL",
                         "nightOfPlay": "MONDAY", "isTournament": False},
            "session": {"id": 140, "name": session},
            "league": {"id": 1438, "slug": "arapahoecounty"},
            "location": {"id": 1, "name": "The Hall"},
        }
    }


@pytest.fixture
def fixture_root(tmp_path):
    """Two teams, a shared scored match, and an alias TeamStat payload."""
    root = tmp_path / "sanitized_fixtures"

    write(root, "global", "global", "dashboardTeams", {
        "viewer": {"id": 900, "leagueTeams": [
            {"id": 11, "name": "Chalk It Up", "standing": 2,
             "division": {"id": 500, "type": "EIGHT"},
             "league": {"id": 1438, "slug": "arapahoecounty"},
             "session": {"id": 140, "name": "Fall 2026"}},
        ]}
    })
    write(root, "global", "global", "ViewerQuery", {"viewer": {"id": 900}})

    write(root, "team", 11, "teamPage", team_payload(11, "Chalk It Up", 500))
    write(root, "team", 11, "teamRoster", {
        "team": {"id": 11, "name": "Chalk It Up", "roster": [
            {"id": 71, "displayName": "Alice", "skillLevel": 5,
             "matchesWon": 4, "matchesPlayed": 6, "ppm": 2.1, "pa": 0.6,
             "member": {"id": 71}},
            {"id": 72, "displayName": "Bob", "skillLevel": 4,
             "matchesWon": 2, "matchesPlayed": 6, "ppm": 1.8, "pa": 0.5,
             "member": {"id": 72}},
        ]}
    })
    # teamSchedule intentionally uses the WRAPPED schema, so the loader is
    # exercised against both shapes in one run.
    write(root, "team", 11, "teamSchedule", {
        "team": {"id": 11, "sessionPoints": 40, "sessionBonusPoints": 2,
                 "sessionTotalPoints": 42, "matches": [
                     {"id": 3001, "week": 4, "startTime": "2026-09-01",
                      "status": "COMPLETED", "isScored": True, "isFinalized": True,
                      "isBye": False,
                      "home": {"id": 11, "name": "Chalk It Up"},
                      "away": {"id": 12, "name": "Rack Attack"},
                      "location": {"name": "The Hall"},
                      "results": [{"homeAway": "home", "points": {"total": 12}},
                                  {"homeAway": "away", "points": {"total": 8}}]},
                 ]}
    }, wrapped=True)
    return root


class TestUnwrap:
    def test_it_reads_the_raw_scraper_schema(self):
        assert unwrap({"data": {"team": 1}}) == {"team": 1}

    def test_it_reads_the_capture_envelope_schema(self):
        """A run once reported 0 matches on 56 real ones by reading the
        wrong shape."""
        assert unwrap({"operationName": "x", "response": {"data": {"team": 1}}}) == {"team": 1}

    def test_a_payload_with_no_data_is_empty_not_an_error(self):
        assert unwrap({"errors": [{"message": "nope"}]}) == {}
        assert unwrap({}) == {}
        assert unwrap(None) == {}


class TestFixtureStore:
    def test_it_indexes_every_bucket(self, fixture_root):
        store = FixtureStore(fixture_root).load()
        assert store.count == 5
        assert store.ids("team") == ["11"]

    def test_team_data_recomposes_the_fetcher_shape(self, fixture_root):
        """The three team fixtures must reassemble into exactly what
        scraper.graphql_scraper.fetch_team_data returns, or the existing
        row-mappers cannot be reused."""
        data = FixtureStore(fixture_root).load().team_data(11)
        assert data["team"]["name"] == "Chalk It Up"
        assert len(data["roster"]) == 2
        assert len(data["schedule"]) == 1
        assert data["points"]["sessionTotalPoints"] == 42

    def test_ids_come_from_payloads_not_directory_names(self, tmp_path):
        """The contract's central rule. A fixture filed under the wrong
        directory must still report its real id."""
        root = tmp_path / "fx"
        write(root, "match", "999-wrong-dir", "MatchPage",
              {"match": {"id": 3001, "isScored": True, "scoresheet": {}}})
        (match_id, _), = FixtureStore(root).load().matches()
        assert match_id == "3001"

    def test_a_missing_fixture_tree_says_how_to_make_one(self, tmp_path):
        with pytest.raises(FileNotFoundError) as exc:
            FixtureStore(tmp_path / "absent").load()
        assert "full_auto_scrape" in str(exc.value)

    def test_unreadable_json_is_skipped_not_fatal(self, fixture_root):
        """One corrupt capture must not cost the whole run."""
        (fixture_root / "team" / "11" / "broken.json").write_text("{not json", encoding="utf-8")
        assert FixtureStore(fixture_root).load().count == 5


class TestIngest:
    @pytest.fixture
    def db(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'p.db'}")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            yield session

    def test_it_writes_teams_rosters_and_matches(self, db, fixture_root):
        counts = ingest_run(db, FixtureStore(fixture_root).load())

        assert counts["teams"] == 1
        assert counts["roster"] == 2
        assert counts["matches_seen"] == 1
        assert db.query(Team).count() == 1
        assert {p.name for p in db.query(Player)} == {"Alice", "Bob"}

        match = db.query(Match).one()
        assert match.external_id == "3001"
        assert match.week == 4
        assert (match.home_score, match.away_score) == (12, 8)
        # P1-4: format/session are threaded from the team's own context.
        assert match.session_name == "Fall 2026"

    def test_running_twice_updates_rather_than_duplicates(self, db, fixture_root):
        store = FixtureStore(fixture_root).load()
        ingest_run(db, store)
        second = ingest_run(db, store)

        assert db.query(Team).count() == 1
        assert db.query(Match).count() == 1
        assert second["matches_new"] == 0
        assert second["matches_updated"] == 1

    def test_a_scoresheet_for_an_unknown_match_is_counted_not_fatal(self, db, fixture_root):
        """A MatchPage captured for a match outside our teams' schedules is a
        real condition, not a crash."""
        write(fixture_root, "match", 4002, "MatchPage", {
            "match": {
                "id": 4002, "isScored": True, "week": 9,
                "home": {"id": 11, "name": "Chalk It Up"},
                "away": {"id": 12, "name": "Rack Attack"},
                # Player scores live under results[].scores[], not under
                # "scoresheet" -- getting that wrong yields zero rows.
                "results": [
                    {"homeAway": "home", "points": {"total": 9}, "scores": [
                        {"id": 1, "player": {"id": 71, "displayName": "Alice"},
                         "matchPositionNumber": 1, "skillLevel": 5,
                         "winLoss": "W", "eightBallMatchPointsEarned": 2,
                         "matchForfeited": False, "incompleteMatch": False},
                    ]},
                    {"homeAway": "away", "points": {"total": 3}, "scores": [
                        {"id": 2, "player": {"id": 81, "displayName": "Zed"},
                         "matchPositionNumber": 1, "skillLevel": 4,
                         "winLoss": "L", "eightBallMatchPointsEarned": 0,
                         "matchForfeited": False, "incompleteMatch": False},
                    ]},
                ],
            }
        })
        counts = ingest_run(db, FixtureStore(fixture_root).load())
        assert counts["orphans"] == 1
        assert db.query(PlayerHeadToHead).count() == 0


class TestHeadToHeadAllowsTwoGamesPerMatch:
    """A player can legitimately play more than one game in a single match.
    A unique constraint on (player_id, match_id) rejected that -- confirmed
    against real scoresheet 51007724, where one player lost one game and won
    another in the same match."""

    def test_the_model_permits_two_rows_for_one_player_in_one_match(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'h2h.db'}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            match = Match(external_id="M1", home_team_id="A", away_team_id="B")
            player = Player(external_id="P1", name="Rob")
            first = Player(external_id="P2", name="Paul")
            second = Player(external_id="P3", name="Shiloh")
            db.add_all([match, player, first, second])
            db.flush()

            db.add_all([
                PlayerHeadToHead(player_id=player.id, opponent_id=first.id,
                                 match_id=match.id, result="L", points_earned=0),
                PlayerHeadToHead(player_id=player.id, opponent_id=second.id,
                                 match_id=match.id, result="W", points_earned=2),
            ])
            db.commit()

            rows = db.query(PlayerHeadToHead).filter_by(player_id=player.id).all()
            assert len(rows) == 2
            assert {r.result for r in rows} == {"W", "L"}


class TestMatchupsAreRebuiltNotRecomputed:
    def test_pairings_land_in_the_database(self, tmp_path, fixture_root):
        """Captain's Edge reads player_matchups and never recomputes, so the
        pipeline must actually persist what the engine produced."""
        engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            counts = ingest_run(db, FixtureStore(fixture_root).load())
            assert counts["matchups"] == db.query(PlayerMatchup).count()
