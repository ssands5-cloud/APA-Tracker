"""Tests for analytics/trend_analyzer.py."""

from __future__ import annotations

from analytics.player_trends import trend_score as reference_trend_score
from analytics.trend_analyzer import FORMULA_VERSION, build_report, build_rows


def trend_row(player_id=1, external_id="P1", name="Alice", format="8-ball",
              session="Fall 2026", sample_size=5, slope=0.1, sigma=0.2,
              hot_cold="HOT", current_sl=6, projected=0.3):
    return {
        "player_id": player_id, "player_external_id": external_id, "player_name": name,
        "format": format, "session_name": session, "sample_size": sample_size,
        "current_skill_level": current_sl, "regression_slope": slope, "volatility": sigma,
        "sl_stability": None if sigma is None else round(1 / (1 + sigma), 6),
        "hot_cold_flag": hot_cold, "projected_sl_change_probability": projected,
    }


class TestBuildRows:
    def test_trend_score_matches_the_public_formula(self):
        rows = build_rows([trend_row(slope=0.1, sigma=0.2, sample_size=5)])
        expected = reference_trend_score(0.1, 0.2, 5)
        assert rows[0].trend_score == expected
        assert expected is not None

    def test_trend_score_is_null_when_evidence_gate_is_closed(self):
        rows = build_rows([trend_row(sample_size=2, hot_cold=None)])
        assert rows[0].trend_score is None

    def test_never_recomputes_slope_or_volatility_from_raw_data(self):
        # Only the persisted values are consumed -- no skill_levels input exists.
        row = trend_row(slope=0.42, sigma=0.13)
        result = build_rows([row])[0]
        assert result.regression_slope == 0.42
        assert result.volatility == 0.13

    def test_canonical_initial_order_is_format_session_name_id_not_slope(self):
        rows = build_rows([
            trend_row(external_id="P2", name="Zed", format="9-ball", slope=0.9),
            trend_row(external_id="P1", name="Alice", format="8-ball", slope=0.1),
        ])
        assert [r.player_external_id for r in rows] == ["P1", "P2"]


class TestBuildReport:
    def test_counts_are_disjoint_and_sum_to_total(self):
        rows = [
            trend_row(external_id="P1", hot_cold="HOT"),
            trend_row(external_id="P2", hot_cold="COLD"),
            trend_row(external_id="P3", hot_cold="NEUTRAL"),
            trend_row(external_id="P4", hot_cold=None, sample_size=2),
        ]
        report = build_report("T1", "Chalk It Up", "Fall 2026", rows, [])
        assert report.hot_count == 1
        assert report.cold_count == 1
        assert report.neutral_count == 1
        assert report.no_data_count == 1
        assert report.measured_count == 3

    def test_formula_version_is_recorded(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [])
        assert report.formula_version == FORMULA_VERSION

    def test_history_rows_are_carried_through(self):
        history = [{
            "player_id": 1, "player_external_id": "P1", "match_id": "M1",
            "match_order": 1, "match_date": "2026-09-01", "format": "8-ball",
            "session_name": "Fall 2026", "skill_level": 5,
        }]
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], history)
        assert len(report.history) == 1
        assert report.history[0].skill_level == 5

    def test_empty_input_is_an_honest_empty_report(self):
        report = build_report("T1", "Chalk It Up", "Fall 2026", [], [])
        assert report.rows == ()
        assert report.measured_count == 0
