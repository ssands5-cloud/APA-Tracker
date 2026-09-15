"""Tests for ui/tabs/season_projection.py."""

from __future__ import annotations

from analytics.season_projection import project_remaining_schedule, team_volatility_curve
from ui.tabs.season_projection import render


def _projection():
    matches = [
        {"match_id": "M1", "opponent_team_id": "T2", "opponent_team_name": "Corner Pockets", "week": 5},
        {"match_id": "M2", "opponent_team_id": "T9", "opponent_team_name": None, "week": 6},
    ]
    return project_remaining_schedule(matches, our_win_rate=0.6, opponent_win_rates={"T2": 0.4})


class TestRender:
    def test_actual_record_and_projected_final_appear(self):
        html = render(_projection(), [], "Chalk It Up", "Fall 2026", 5, 2, "2026-09-15T00:00:00Z")
        assert "5-2" in html
        assert "Chalk It Up" in html

    def test_missing_actual_record_shows_no_data(self):
        html = render(_projection(), [], "Chalk It Up", "Fall 2026", None, None, None)
        assert "No data" in html

    def test_every_remaining_match_appears_with_its_probability_source(self):
        html = render(_projection(), [], "Chalk It Up", "Fall 2026", 5, 2, None)
        assert "BOTH_RATES" in html
        assert "OUR_RATE_ONLY" in html
        assert "Unresolved" in html  # opponent_team_name=None for M2

    def test_standings_points_render_when_present(self):
        history = [
            {"captured_at": "2026-09-01", "wins": 1, "losses": 0},
            {"captured_at": "2026-09-03", "wins": 2, "losses": 0},
        ]
        points = team_volatility_curve(history)
        html = render(_projection(), points, "Chalk It Up", "Fall 2026", 5, 2, None)
        assert "2026-09-01" in html
        assert "2026-09-03" in html

    def test_no_standings_history_is_honest(self):
        html = render(_projection(), [], "Chalk It Up", "Fall 2026", 5, 2, None)
        assert "No real standings history captured yet" in html

    def test_no_categorical_upset_warning_language(self):
        html = render(_projection(), [], "Chalk It Up", "Fall 2026", 5, 2, None)
        assert "high upset risk" not in html.lower()
        assert "recommended" not in html.lower()

    def test_no_external_resources(self):
        html = render(_projection(), [], "Chalk It Up", "Fall 2026", 5, 2, None)
        assert "http://" not in html
        assert "https://" not in html
