"""Tests for ui.export_json -- the JSON counterpart to ui.export_excel.

Seeds a small in-memory database through the real ingest functions (not
hand-built ORM rows) so this exercises the same path export_to_json will
see in practice, then checks both the returned file's shape and that it's
valid, re-loadable JSON -- the "lightweight validation" the demo's JSON
export needs, independent of whatever HTML consumes it.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.ingest import (
    ingest_eight_ball_stats,
    ingest_head_to_head,
    ingest_match,
    ingest_match_scores,
    ingest_matchups,
    ingest_player_team_history,
    ingest_standings,
    upsert_player,
    upsert_team,
)
from database.models import Base
from ui.export_json import export_to_json

REQUIRED_TOP_LEVEL_KEYS = {
    "generated_at", "teams", "matches", "standings", "player_stats",
    "match_scores", "career_stats", "team_history", "skill_level_history",
    "skill_level_summary", "matchups",
}

REQUIRED_MATCH_KEYS = {
    "match_id", "week", "home_team_id", "home_team_name", "away_team_id",
    "away_team_name", "home_score", "away_score", "status", "match_date",
    "is_bye", "is_scored", "is_finalized",
}

REQUIRED_PLAYER_STATS_KEYS = {
    "player", "team", "skill_level", "matches", "wins", "losses", "win_pct",
    "ppm", "pa", "avg_points", "source",
}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def seeded_db(db):
    upsert_team(db, "T1", "Chalk It Up")
    upsert_team(db, "T2", "Rack Attack")
    ingest_match(
        db, match_id="M1", home_team_id="T1", away_team_id="T2",
        home_team_name="Chalk It Up", away_team_name="Rack Attack",
        week=9, status="COMPLETED", home_score=18, away_score=12,
        is_scored=True, is_finalized=True,
    )
    ingest_match_scores(
        db, "M1",
        [
            {"player_id": "P1", "player_name": "Alice", "team_id": "T1", "skill_level": 5,
             "result": "W", "points_earned": 6},
            {"player_id": "P2", "player_name": "Bob", "team_id": "T2", "skill_level": 4,
             "result": "L", "points_earned": 3},
        ],
    )
    ingest_standings(
        db,
        [{"team_name": "Chalk It Up", "rank": 1, "wins": None, "losses": None, "points": 142}],
    )
    return db


def _export(db, tmp_path):
    config = {"export": {"json_output_path": str(tmp_path / "demo.json")}}
    path = export_to_json(db, config)
    return json.loads((tmp_path / "demo.json").read_text())


class TestShape:
    def test_top_level_keys_present(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        assert REQUIRED_TOP_LEVEL_KEYS.issubset(document.keys())

    def test_teams_are_present(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        names = {t["team_name"] for t in document["teams"]}
        assert names == {"Chalk It Up", "Rack Attack"}

    def test_match_row_has_every_required_key(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        assert len(document["matches"]) == 1
        assert REQUIRED_MATCH_KEYS.issubset(document["matches"][0].keys())

    def test_match_scores_round_trip(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        match = document["matches"][0]
        assert match["home_score"] == 18
        assert match["away_score"] == 12
        assert match["is_finalized"] is True

    def test_standings_row_shape(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        assert document["standings"] == [
            {"rank": 1, "team_name": "Chalk It Up", "wins": None, "losses": None, "points": 142.0,
             "captured_at": document["standings"][0]["captured_at"]}
        ]

    def test_player_stats_row_has_every_required_key(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        assert len(document["player_stats"]) == 2
        assert REQUIRED_PLAYER_STATS_KEYS.issubset(document["player_stats"][0].keys())

    def test_player_stats_source_is_match_history(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        sources = {row["source"] for row in document["player_stats"]}
        assert sources == {"match history"}

    def test_player_stats_team_is_blank_when_never_rostered(self, seeded_db, tmp_path):
        """seeded_db's Alice/Bob only ever go through ingest_match_scores(),
        which doesn't assign a team -- only upsert_roster() does."""
        document = _export(seeded_db, tmp_path)
        teams = {row["team"] for row in document["player_stats"]}
        assert teams == {""}

    def test_player_stats_team_reflects_the_roster_a_player_is_on(self, db, tmp_path):
        """A player on two of the account's teams during a season shows up
        as two rows here, one per team -- the "team" field is what makes
        that a legible split instead of a mystery duplicate."""
        team = upsert_team(db, "T1", "Mark It Up")
        upsert_player(db, "3349374", "Paul Smith", team)
        document = _export(db, tmp_path)
        assert document["player_stats"][0]["team"] == "Mark It Up"

    def test_match_scores_are_keyed_by_the_matchs_external_id(self, seeded_db, tmp_path):
        document = _export(seeded_db, tmp_path)
        assert set(document["match_scores"].keys()) == {"M1"}
        rows = {r["player"]: r for r in document["match_scores"]["M1"]}
        assert rows["Alice"]["result"] == "W"
        assert rows["Alice"]["points_earned"] == 6.0
        assert rows["Bob"]["result"] == "L"

    def test_a_match_with_no_scoresheet_is_absent_not_an_empty_list(self, db, tmp_path):
        """ingest_viewer_data-only matches never get a scoresheet -- absent
        is more honest than a key that's always there but always empty."""
        upsert_team(db, "T1", "Chalk It Up")
        upsert_team(db, "T2", "Rack Attack")
        ingest_match(
            db, match_id="M2", home_team_id="T1", away_team_id="T2",
            home_team_name="Chalk It Up", away_team_name="Rack Attack",
        )
        document = _export(db, tmp_path)
        assert document["match_scores"] == {}


class TestEmptyDatabase:
    """Nothing ingested yet must produce a valid, empty-list document, not
    an error -- a fresh checkout runs the demo before anything is ingested."""

    def test_empty_database_yields_empty_lists_not_an_error(self, db, tmp_path):
        document = _export(db, tmp_path)
        assert document["teams"] == []
        assert document["matches"] == []
        assert document["standings"] == []
        assert document["player_stats"] == []
        assert document["career_stats"] == []
        assert document["team_history"] == []
        assert document["skill_level_history"] == []
        assert document["skill_level_summary"] == []
        assert document["matchups"] == []

    def test_generated_at_is_always_present(self, db, tmp_path):
        document = _export(db, tmp_path)
        assert document["generated_at"]


class TestCareerStatsAndTeamHistory:
    """HANDOFF.md item 2, now confirmed and wired end to end."""

    def test_career_stats_row_shape(self, db, tmp_path):
        team = upsert_team(db, "T1", "Mark It Up")
        player = upsert_player(db, "3349374", "Paul Smith", team)
        ingest_eight_ball_stats(db, player, {
            "eight_ball_matches_won": 64, "eight_ball_matches_played": 129,
            "eight_ball_cla": 1, "eight_ball_defensive_shot_avg": 1.26,
            "eight_ball_match_count_for_last_two_yrs": 123, "eight_ball_last_played": "2026-08-31",
        })
        document = _export(db, tmp_path)
        assert document["career_stats"] == [{
            "player": "Paul Smith", "format": "EIGHT", "matches_won": 64,
            "matches_played": 129, "cla": 1, "defensive_shot_avg": 1.26,
            "match_count_last_two_yrs": 123, "last_played": "2026-08-31",
        }]

    def test_team_history_row_shape(self, db, tmp_path):
        team = upsert_team(db, "T1", "Mark It Up")
        player = upsert_player(db, "3349374", "Paul Smith", team)
        ingest_player_team_history(db, player, [{
            "is_current": True, "team_name": "Mark It Up", "division_id": "436670",
            "is_tournament": False, "session_name": "2026 Summer", "nick_name": "Paulie",
            "skill_level": 4, "rank": None, "matches_won": 2, "matches_played": 2,
        }])
        document = _export(db, tmp_path)
        assert document["team_history"] == [{
            "player": "Paul Smith", "is_current": True, "team_name": "Mark It Up",
            "division_id": "436670", "is_tournament": False, "session_name": "2026 Summer",
            "nick_name": "Paulie", "skill_level": 4, "rank": None,
            "matches_won": 2, "matches_played": 2,
        }]


class TestSkillLevelHistory:
    """Not a new extraction step -- ingest_match_scores/ingest_match_roster
    already write PlayerMatch.skill_level per match; this reads it back out
    match-by-match instead of only the current Player.skill_level snapshot."""

    def test_skill_level_history_row_shape(self, db, tmp_path):
        upsert_team(db, "T1", "Mark It Up")
        upsert_team(db, "T2", "Rack Attack")
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack",
                     week=1, match_date="2026-06-01", status="COMPLETED",
                     home_score=6, away_score=3)
        ingest_match_scores(db, "M1", [
            {"player_id": "3349374", "player_name": "Paul Smith", "team_id": "T1",
             "skill_level": 5, "result": "W", "points_earned": 6},
        ])
        document = _export(db, tmp_path)
        assert document["skill_level_history"] == [{
            "player": "Paul Smith", "player_id": "3349374", "week": 1,
            "skill_level": 5, "match_date": "2026-06-01", "source": "scoresheet",
        }]

    def test_trend_volatility_and_last_change_across_two_matches(self, db, tmp_path):
        upsert_team(db, "T1", "Mark It Up")
        upsert_team(db, "T2", "Rack Attack")
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack",
                     week=1, match_date="2026-06-01", status="COMPLETED",
                     home_score=6, away_score=3)
        ingest_match_scores(db, "M1", [
            {"player_id": "3349374", "player_name": "Paul Smith", "team_id": "T1",
             "skill_level": 5, "result": "W", "points_earned": 6},
        ])
        ingest_match(db, match_id="M2", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack",
                     week=7, match_date="2026-07-20", status="COMPLETED",
                     home_score=6, away_score=3)
        ingest_match_scores(db, "M2", [
            {"player_id": "3349374", "player_name": "Paul Smith", "team_id": "T1",
             "skill_level": 6, "result": "W", "points_earned": 6},
        ])
        document = _export(db, tmp_path)

        assert [row["week"] for row in document["skill_level_history"]] == [1, 7]
        assert document["skill_level_summary"] == [{
            "player": "Paul Smith", "player_id": "3349374", "current_skill_level": 6,
            "trend": "up", "volatility": 1, "last_change": "SL 5 → SL 6 in Week 7",
        }]

    def test_a_player_never_scored_has_no_skill_level_history(self, db, tmp_path):
        """A player known only from a roster/name, never a scored match, has
        no skill_level reading to show -- absent, not a fabricated zero."""
        upsert_team(db, "T1", "Mark It Up")
        upsert_player(db, "P9", "Bench Player")
        document = _export(db, tmp_path)
        assert document["skill_level_history"] == []
        assert document["skill_level_summary"] == []


class TestMatchups:
    """The Matchup Advantage Engine's aggregate (PlayerMatchup) -- this only
    checks the export shape, not the scoring math itself. See
    tests/test_matchups.py for the analytics functions and
    tests/test_ingest.py for ingest_matchups()."""

    def test_matchup_row_shape(self, db, tmp_path):
        upsert_player(db, "501", "Player One")
        upsert_player(db, "601", "Player Four")
        ingest_matchups(db, [{
            "player_id": "501", "opponent_id": "601", "matches_played": 3,
            "win_rate": 0.667, "avg_points_earned": 5.0,
            "avg_opponent_skill_level": 5.0, "trend": "up", "volatility": 1,
            "matchup_score": 72, "confidence_score": 63,
        }])
        document = _export(db, tmp_path)
        assert document["matchups"] == [{
            "player": "Player One", "player_id": "501", "opponent": "Player Four",
            "opponent_id": "601", "matches_played": 3, "win_rate": 0.667,
            "avg_points_earned": 5.0, "avg_opponent_skill_level": 5.0,
            "trend": "up", "volatility": 1, "matchup_score": 72, "confidence_score": 63,
            "format": None, "session_name": None, "has_history": True,
        }]

class TestMatchupNeutralFill:
    """P1-8: a known player with no head-to-head history against a
    specific other known player must still show up, as a neutral 50, not
    be silently absent."""

    def _seed(self, db):
        upsert_team(db, "T1", "Mark It Up")
        upsert_team(db, "T2", "Rack Attack")
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack")
        ingest_match(db, match_id="M2", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack")

    def test_a_pair_with_no_history_gets_a_neutral_fifty_row(self, db, tmp_path):
        self._seed(db)
        # Alice has played both Bob and Carol -- Bob and Carol have never
        # played each other.
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        ingest_head_to_head(db, "M2", [
            {"match_id": "M2", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P3", "opponent_name": "Carol", "result": "L"},
        ])
        ingest_matchups(db, [
            {"player_id": "P1", "opponent_id": "P2", "matches_played": 1, "win_rate": 1.0, "matchup_score": 60},
            {"player_id": "P2", "opponent_id": "P1", "matches_played": 1, "win_rate": 0.0, "matchup_score": 40},
            {"player_id": "P1", "opponent_id": "P3", "matches_played": 1, "win_rate": 0.0, "matchup_score": 40},
            {"player_id": "P3", "opponent_id": "P1", "matches_played": 1, "win_rate": 1.0, "matchup_score": 60},
        ])

        document = _export(db, tmp_path)
        pairs = {(row["player"], row["opponent"]): row for row in document["matchups"]}

        assert ("Bob", "Carol") in pairs and ("Carol", "Bob") in pairs
        assert pairs[("Bob", "Carol")]["matchup_score"] == 50
        assert pairs[("Bob", "Carol")]["has_history"] is False
        assert pairs[("Bob", "Carol")]["matches_played"] == 0
        assert pairs[("Bob", "Carol")]["win_rate"] is None

        # A real, computed pair must not be overridden by the fill.
        assert pairs[("Alice", "Bob")]["has_history"] is True
        assert pairs[("Alice", "Bob")]["matchup_score"] == 60

    def test_a_roster_player_with_zero_games_gets_a_neutral_row_against_a_known_opponent(self, db, tmp_path):
        """P1-8: subjects = roster players UNION head-to-head players. A
        brand-new player who's on a team (a real roster slot) but hasn't
        played a single scored game yet is still a real subject a captain
        wants a placeholder row for against players who ARE known --
        rather than being left off the sheet just because they have no
        history of their own."""
        self._seed(db)
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        team = upsert_team(db, "T1", "Mark It Up")
        upsert_player(db, "P9", "Rookie Player", team)  # rostered, never played

        document = _export(db, tmp_path)
        pairs = {(row["player"], row["opponent"]): row for row in document["matchups"]}

        assert ("Rookie Player", "Alice") in pairs
        assert pairs[("Rookie Player", "Alice")]["matchup_score"] == 50
        assert pairs[("Rookie Player", "Alice")]["has_history"] is False
        # A roster player is a subject, not an opponent -- Bob (known only
        # from head-to-head, no roster slot) has no reason to get a row
        # AGAINST the rookie unless the rookie is also a known opponent.
        assert ("Bob", "Rookie Player") not in pairs

    def test_a_matchup_row_for_an_unknown_player_is_skipped_not_crashed(self, db, tmp_path):
        """ingest_matchups() requires both Player rows to already exist --
        this documents that an unresolvable id is dropped, not a crash."""
        written = ingest_matchups(db, [{"player_id": "999", "opponent_id": "998", "matchup_score": 50}])
        assert written == 0
        document = _export(db, tmp_path)
        assert document["matchups"] == []


class TestFileIsValidJson:
    def test_written_file_parses_and_matches_return_value(self, seeded_db, tmp_path):
        config = {"export": {"json_output_path": str(tmp_path / "out.json")}}
        path = export_to_json(seeded_db, config)
        on_disk = json.loads((tmp_path / "out.json").read_text())
        assert str(tmp_path / "out.json") == path
        assert REQUIRED_TOP_LEVEL_KEYS.issubset(on_disk.keys())

    def test_creates_parent_directory(self, seeded_db, tmp_path):
        nested = tmp_path / "nested" / "dir"
        config = {"export": {"json_output_path": str(nested / "out.json")}}
        export_to_json(seeded_db, config)
        assert (nested / "out.json").exists()
