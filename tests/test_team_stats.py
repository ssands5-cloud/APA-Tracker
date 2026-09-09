"""Tests for the Team_Stats aggregates in analytics/team_stats.py.

Real, currently-computable fields only: a team's match record (from Match
rows), average roster skill level (from Player.skill_level), and opponent
strength index (from PlayerHeadToHead). No clutch rating, no numeric trend
score, no break/run rate, no defensive-shot rate -- see the module's own
docstring for why those are deliberately absent, not merely unfinished.
"""

from __future__ import annotations

from analytics.team_stats import (
    TeamMatchRecord,
    average_skill_level,
    opponent_strength_index,
    team_match_record,
)
from database.models import Match, Player, PlayerHeadToHead


def match(home_id="T1", away_id="T2", home_score=None, away_score=None, is_bye=False):
    return Match(
        external_id="M1", home_team_id=home_id, away_team_id=away_id,
        home_score=home_score, away_score=away_score, is_bye=is_bye,
    )


class TestTeamMatchRecord:
    def test_a_home_win_counts_as_a_win_and_a_home_win(self):
        record = team_match_record([match(home_score=18, away_score=12)], "T1")
        assert record.wins == 1 and record.losses == 0
        assert record.home_wins == 1 and record.home_losses == 0
        assert record.away_wins == 0

    def test_an_away_win_counts_as_a_win_and_an_away_win(self):
        record = team_match_record([match(home_score=12, away_score=18)], "T2")
        assert record.wins == 1
        assert record.away_wins == 1 and record.home_wins == 0

    def test_a_loss_counts_correctly_for_the_losing_side(self):
        record = team_match_record([match(home_score=18, away_score=12)], "T2")
        assert record.losses == 1 and record.wins == 0
        assert record.away_losses == 1

    def test_a_bye_is_not_a_decided_match(self):
        record = team_match_record([match(home_score=None, away_score=None, is_bye=True)], "T1")
        assert record.matches_played == 0

    def test_an_unscored_match_is_not_decided(self):
        record = team_match_record([match(home_score=None, away_score=None)], "T1")
        assert record.matches_played == 0

    def test_a_tie_is_not_a_decided_result_either_way(self):
        """A real tie score is not a fabricated coin-flip win or loss."""
        record = team_match_record([match(home_score=10, away_score=10)], "T1")
        assert record.matches_played == 0

    def test_a_match_neither_side_of_is_ignored(self):
        record = team_match_record([match(home_id="T1", away_id="T2", home_score=18, away_score=12)], "T3")
        assert record.matches_played == 0

    def test_win_percentage_is_none_not_zero_with_nothing_decided(self):
        record = TeamMatchRecord(0, 0, 0, 0, 0, 0, 0)
        assert record.win_percentage is None

    def test_win_percentage_is_computed_from_real_results(self):
        record = team_match_record(
            [match(home_score=18, away_score=12), match(home_score=10, away_score=15)],
            "T1",
        )
        assert record.matches_played == 2
        assert record.win_percentage == 0.5

    def test_home_and_away_record_strings(self):
        record = team_match_record(
            [
                match(home_id="T1", away_id="T2", home_score=18, away_score=12),  # home win
                match(home_id="T2", away_id="T1", home_score=18, away_score=12),  # away loss
            ],
            "T1",
        )
        assert record.home_record == "1-0"
        assert record.away_record == "0-1"


class TestAverageSkillLevel:
    def test_means_the_real_skill_levels(self):
        players = [Player(skill_level=5), Player(skill_level=4), Player(skill_level=6)]
        assert average_skill_level(players) == 5.0

    def test_ignores_players_with_no_recorded_skill_level(self):
        players = [Player(skill_level=5), Player(skill_level=None)]
        assert average_skill_level(players) == 5.0

    def test_no_roster_at_all_is_none_not_zero(self):
        assert average_skill_level([]) is None

    def test_a_roster_with_no_skill_levels_recorded_is_none(self):
        assert average_skill_level([Player(skill_level=None)]) is None


class TestOpponentStrengthIndex:
    def test_means_the_real_opponent_skill_levels_actually_faced(self):
        rows = [
            PlayerHeadToHead(opponent_skill_level=6),
            PlayerHeadToHead(opponent_skill_level=4),
        ]
        assert opponent_strength_index(rows) == 5.0

    def test_no_history_at_all_is_none_not_zero(self):
        assert opponent_strength_index([]) is None

    def test_ignores_rows_missing_an_opponent_skill_level(self):
        rows = [PlayerHeadToHead(opponent_skill_level=6), PlayerHeadToHead(opponent_skill_level=None)]
        assert opponent_strength_index(rows) == 6.0
