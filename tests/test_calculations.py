"""
Unit tests for analytics/calculations.py
"""

import pytest

from analytics.calculations import (
    calculate_win_percentage,
    calculate_streaks,
    identify_trends,
    rank_players,
)


class TestCalculateWinPercentage:
    def test_normal(self):
        assert calculate_win_percentage(3, 5) == 0.6

    def test_zero_played(self):
        assert calculate_win_percentage(0, 0) == 0.0

    def test_all_wins(self):
        assert calculate_win_percentage(10, 10) == 1.0

    def test_no_wins(self):
        assert calculate_win_percentage(0, 10) == 0.0

    def test_rounding(self):
        # 1/3 = 0.3333
        assert calculate_win_percentage(1, 3) == 0.3333


class TestCalculateStreaks:
    def test_empty(self):
        assert calculate_streaks([]) == (0, 0)

    def test_win_streak(self):
        assert calculate_streaks(["L", "W", "W", "W"]) == (3, 0)

    def test_loss_streak(self):
        assert calculate_streaks(["W", "L", "L"]) == (0, 2)

    def test_mixed_ends_with_single_win(self):
        assert calculate_streaks(["L", "L", "W"]) == (1, 0)

    def test_all_wins(self):
        assert calculate_streaks(["W", "W", "W"]) == (3, 0)

    def test_all_losses(self):
        assert calculate_streaks(["L", "L"]) == (0, 2)


class TestRankPlayers:
    def test_rank_assigned(self):
        players = [
            {"player_id": "A", "skill_level": 3, "win_pct": 0.5},
            {"player_id": "B", "skill_level": 5, "win_pct": 0.8},
            {"player_id": "C", "skill_level": 5, "win_pct": 0.6},
        ]
        ranked = rank_players(players)
        assert ranked[0]["player_id"] == "B"
        assert ranked[1]["player_id"] == "C"
        assert ranked[2]["player_id"] == "A"
        assert ranked[0]["rank"] == 1
        assert ranked[2]["rank"] == 3

    def test_empty_list(self):
        assert rank_players([]) == []


class TestIdentifyTrends:
    def test_improving(self):
        trend = identify_trends([0.2, 0.3, 0.7, 0.8])
        assert trend == "Improving"

    def test_declining(self):
        trend = identify_trends([0.8, 0.7, 0.3, 0.2])
        assert trend == "Declining"

    def test_stable(self):
        trend = identify_trends([0.5, 0.5, 0.5, 0.5])
        assert trend == "Stable"

    def test_insufficient_data(self):
        assert identify_trends([0.5, 0.6]) == "Insufficient Data"
        assert identify_trends([]) == "Insufficient Data"
