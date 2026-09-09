"""Tests for the per-LINEUP rationale builder (analytics/rationale.py).

Per-pairing rationale already exists and is deliberately not duplicated
here -- see analytics.captains_edge.build_rationale and
analytics.lineup_optimizer.build_rationale, both already tested in their
own test files. This module (and this test file) covers only what's
genuinely new: a real, factual sentence about a solved LINEUP's risk
profile.
"""

from __future__ import annotations

from analytics.lineup_risk import DEFAULT_LINEUP_RISK_WEIGHTS, LineupRiskMetrics
from analytics.rationale import (
    ANCHOR_SHAKY_AT,
    ANCHOR_STABLE_AT,
    DEFAULT_RATIONALE_TOGGLES,
    LINEUP_VOLATILITY_LOAD_HIGH,
    LINEUP_VOLATILITY_LOAD_LOW,
    RationaleToggles,
    lineup_risk_rationale,
)


def metrics(**overrides) -> LineupRiskMetrics:
    defaults = dict(
        upset_risk_index=0.2,
        anchor_stability_score=0.6,
        anchor_player_name="Alice",
        lineup_volatility_load=1.0,
        danger_matchup_count=0,
        lineup_risk_score=0.35,
    )
    defaults.update(overrides)
    return LineupRiskMetrics(**defaults)


class TestLineupRiskRationale:
    def test_an_empty_lineup_states_plainly_there_is_nothing_to_describe(self):
        empty = LineupRiskMetrics(
            upset_risk_index=0.0, anchor_stability_score=None, anchor_player_name=None,
            lineup_volatility_load=0.0, danger_matchup_count=0, lineup_risk_score=0.0,
        )
        text = lineup_risk_rationale(empty, DEFAULT_LINEUP_RISK_WEIGHTS)
        assert "no real assignments" in text.lower()
        assert "Alice" not in text  # never a guessed anchor

    def test_names_the_real_anchor(self):
        text = lineup_risk_rationale(metrics(anchor_player_name="Bob"), DEFAULT_LINEUP_RISK_WEIGHTS)
        assert "Bob" in text

    def test_a_stable_anchor_is_described_as_stable(self):
        text = lineup_risk_rationale(
            metrics(anchor_stability_score=ANCHOR_STABLE_AT), DEFAULT_LINEUP_RISK_WEIGHTS
        )
        assert "stable" in text.lower()

    def test_a_shaky_anchor_is_described_as_shaky(self):
        text = lineup_risk_rationale(
            metrics(anchor_stability_score=ANCHOR_SHAKY_AT), DEFAULT_LINEUP_RISK_WEIGHTS
        )
        assert "shaky" in text.lower()

    def test_zero_danger_matchups_is_stated_explicitly(self):
        text = lineup_risk_rationale(metrics(danger_matchup_count=0), DEFAULT_LINEUP_RISK_WEIGHTS)
        assert "no danger matchups" in text.lower()

    def test_a_real_danger_count_is_named_with_the_real_threshold(self):
        text = lineup_risk_rationale(
            metrics(danger_matchup_count=2), DEFAULT_LINEUP_RISK_WEIGHTS
        )
        assert "2 danger matchup" in text
        assert f"{DEFAULT_LINEUP_RISK_WEIGHTS.danger_threshold:.0%}" in text

    def test_singular_danger_matchup_is_not_pluralized(self):
        text = lineup_risk_rationale(
            metrics(danger_matchup_count=1), DEFAULT_LINEUP_RISK_WEIGHTS
        )
        assert "1 danger matchup " in text or text.count("matchups") == 0

    def test_high_volatility_load_is_named(self):
        text = lineup_risk_rationale(
            metrics(lineup_volatility_load=LINEUP_VOLATILITY_LOAD_HIGH),
            DEFAULT_LINEUP_RISK_WEIGHTS,
        )
        assert "high overall volatility" in text.lower()

    def test_low_volatility_load_is_named(self):
        text = lineup_risk_rationale(
            metrics(lineup_volatility_load=LINEUP_VOLATILITY_LOAD_LOW),
            DEFAULT_LINEUP_RISK_WEIGHTS,
        )
        assert "low overall volatility" in text.lower()

    def test_a_middling_volatility_load_names_neither_extreme(self):
        mid = (LINEUP_VOLATILITY_LOAD_HIGH + LINEUP_VOLATILITY_LOAD_LOW) / 2
        text = lineup_risk_rationale(
            metrics(lineup_volatility_load=mid), DEFAULT_LINEUP_RISK_WEIGHTS
        )
        assert "volatility" not in text.lower()

    def test_states_the_real_lineup_risk_score(self):
        text = lineup_risk_rationale(metrics(lineup_risk_score=0.777), DEFAULT_LINEUP_RISK_WEIGHTS)
        assert "0.78" in text


class TestRationaleToggles:
    def test_default_includes_lineup_rationale(self):
        assert DEFAULT_RATIONALE_TOGGLES.include_lineup_rationale is True

    def test_can_be_turned_off(self):
        assert RationaleToggles(include_lineup_rationale=False).include_lineup_rationale is False
