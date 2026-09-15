"""Tests for ui/tabs/opponent_volatility.py."""

from __future__ import annotations

from analytics.opponent_volatility import build_profile
from ui.tabs.opponent_volatility import render


def roster_player(external_id, name="P", player_id=None):
    resolved_id = player_id if player_id is not None else hash(external_id) % 1000
    return {"player_id": resolved_id, "player_external_id": external_id, "player_name": name}


class TestRender:
    def test_measured_player_and_team_median_render(self):
        roster = [roster_player("A", "Alice", player_id=1)]
        trends = {1: {"volatility": 0.2, "sample_size": 5, "sl_stability": 0.833,
                       "regression_slope": 0.1, "format": "8-ball", "session_name": "Fall 2026"}}
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", roster, trends)
        html = render(profile)
        assert "Alice" in html
        assert "Corner Pockets" in html

    def test_missing_trend_renders_no_data_not_zero(self):
        roster = [roster_player("A", "Alice", player_id=1)]
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", roster, {})
        html = render(profile)
        assert "No data" in html
        assert "Insufficient evidence" in html

    def test_empty_roster_is_honest(self):
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", [], {})
        html = render(profile)
        assert "No canonical opponent roster player found" in html

    def test_no_danger_or_riskiest_language(self):
        roster = [roster_player("A", "Alice", player_id=1)]
        trends = {1: {"volatility": 0.2, "sample_size": 5}}
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", roster, trends)
        html = render(profile)
        assert 'class="danger"' not in html
        assert 'class="risk-danger"' not in html
        assert 'default-order="riskiest"' not in html

    def test_hostile_text_is_escaped(self):
        roster = [roster_player("A", "<script>alert(1)</script>", player_id=1)]
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", roster, {})
        html = render(profile)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_no_external_resources(self):
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", [], {})
        html = render(profile)
        assert "http://" not in html
        assert "https://" not in html
