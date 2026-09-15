"""Tests for ui/tabs/trend_analyzer.py."""

from __future__ import annotations

from analytics.trend_analyzer import build_report
from ui.tabs.trend_analyzer import render


def trend_row(external_id="P1", name="Alice", format="8-ball", session="Fall 2026",
              sample_size=5, slope=0.1, sigma=0.2, hot_cold="HOT"):
    return {
        "player_id": 1, "player_external_id": external_id, "player_name": name,
        "format": format, "session_name": session, "sample_size": sample_size,
        "current_skill_level": 6, "regression_slope": slope, "volatility": sigma,
        "sl_stability": None if sigma is None else round(1 / (1 + sigma), 6),
        "hot_cold_flag": hot_cold, "projected_sl_change_probability": 0.3,
    }


class TestRender:
    def test_player_and_scope_render(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [trend_row()], [])
        html = render(report)
        assert "Alice" in html
        assert "Chalk It Up" in html
        assert "HOT" in html

    def test_empty_report_is_honest(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [])
        html = render(report)
        assert "No measured player trends" in html

    def test_missing_values_render_no_data_not_zero(self):
        report = build_report(
            "T1", "Chalk It Up", "Fall 2026",
            [trend_row(sample_size=2, sigma=None, slope=None, hot_cold=None)], [],
        )
        html = render(report)
        assert "No data" in html

    def test_no_categorical_recommendation_class(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [trend_row()], [])
        html = render(report)
        assert 'class="recommended"' not in html
        assert 'class="danger"' not in html
        assert 'class="avoid"' not in html

    def test_hostile_text_is_escaped(self):
        report = build_report(
            "T1", "Chalk It Up", "Fall 2026",
            [trend_row(name="<script>alert(1)</script>")], [],
        )
        html = render(report)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_no_external_resources(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [trend_row()], [])
        html = render(report)
        assert "http://" not in html
        assert "https://" not in html
