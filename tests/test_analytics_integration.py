"""Analytics against GraphQL-sourced data specifically -- not the older
HTML-scraper path. analytics/player_stats.py and analytics/team_stats.py
predate the GraphQL ingestion added this round, and read columns
(opponent, match_date, result, points_earned) that ingest_match_scores()
only started populating correctly after the fixes in this same commit.
This is the test that would have caught the FK bug from the analytics side:
summarize_player() would have silently returned all-zero stats, because
player_match_history() (database/queries.py) looks up rows by the real
Match primary key, and an orphaned match_id meant the join found nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from analytics.player_stats import recent_form, summarize_player
from analytics.team_stats import head_to_head
from database.ingest import ingest_match, ingest_match_scores
from database.models import Base
from database.queries import player_match_history
from scraper.graphql_scraper import match_player_scores

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "match_detail_response.json").read_text()
)
MATCH = FIXTURE["data"]["match"]


def _db_with_one_match_ingested(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analytics.db'}")
    Base.metadata.create_all(engine)
    db = Session(engine)
    ingest_match(
        db, match_id="555001", home_team_id="90001", away_team_id="90002",
        home_team_name="Chalk It Up", away_team_name="Rack Attack",
        match_date="2026-08-27",
    )
    ingest_match_scores(db, "555001", match_player_scores(MATCH))
    return db


class TestSummarizePlayerAgainstGraphQLData:
    def test_a_winning_players_stats_are_correct(self, tmp_path):
        db = _db_with_one_match_ingested(tmp_path)
        matches = player_match_history(db, "501")  # Player One, won their match
        assert len(matches) == 1, "the exact symptom of the FK bug: this was 0"

        stat = summarize_player("Player One", matches)
        assert (stat.matches_played, stat.wins, stat.losses) == (1, 1, 0)
        assert stat.win_pct == 1.0
        assert stat.avg_points == 6.0

    def test_a_losing_players_stats_are_correct(self, tmp_path):
        db = _db_with_one_match_ingested(tmp_path)
        matches = player_match_history(db, "502")  # Player Two, lost
        stat = summarize_player("Player Two", matches)
        assert (stat.matches_played, stat.wins, stat.losses) == (1, 0, 1)

    def test_on_break_and_break_and_run_totals_are_summed_from_real_data(self, tmp_path):
        db = _db_with_one_match_ingested(tmp_path)
        one = summarize_player("Player One", player_match_history(db, "501"))
        two = summarize_player("Player Two", player_match_history(db, "502"))
        assert one.total_eight_break_and_runs == 1
        assert one.total_eight_on_breaks == 0
        assert two.total_eight_on_breaks == 1
        assert two.total_nine_on_snaps == 0  # 8-ball match -- nothing to sum

    def test_recent_form_reads_the_correct_result(self, tmp_path):
        db = _db_with_one_match_ingested(tmp_path)
        matches = player_match_history(db, "501")
        assert recent_form(matches) == "W"


class TestHeadToHeadAgainstGraphQLData:
    def test_finds_matches_by_opponent_name(self, tmp_path):
        """Before this round's fix, ingest_match_scores never set `opponent`,
        so this always returned zero matches regardless of what was ingested."""
        db = _db_with_one_match_ingested(tmp_path)
        matches = player_match_history(db, "501")  # plays for Chalk It Up

        result = head_to_head(matches, "Rack Attack")
        assert result == {"opponent": "Rack Attack", "played": 1, "wins": 1, "losses": 0}

    def test_a_different_opponent_name_finds_nothing(self, tmp_path):
        db = _db_with_one_match_ingested(tmp_path)
        matches = player_match_history(db, "501")
        result = head_to_head(matches, "Some Other Team")
        assert result == {"opponent": "Some Other Team", "played": 0, "wins": 0, "losses": 0}

    def test_the_away_players_opponent_is_the_home_team(self, tmp_path):
        db = _db_with_one_match_ingested(tmp_path)
        matches = player_match_history(db, "601")  # plays for Rack Attack
        result = head_to_head(matches, "Chalk It Up")
        assert result["played"] == 1
