"""Tests for analytics/opponent_volatility.py."""

from __future__ import annotations

import pytest

from analytics.opponent_volatility import (
    FORMULA_VERSION,
    INSUFFICIENT_EVIDENCE,
    NO_OBSERVED_VARIATION,
    OBSERVED_VARIATION,
    build_profile,
    descriptor,
    volatility_index,
)


def roster_player(external_id, name="P", player_id=None):
    resolved_id = player_id if player_id is not None else hash(external_id) % 1000
    return {"player_id": resolved_id, "player_external_id": external_id, "player_name": name}


def trend(sigma=0.2, sample_size=5, stability=None, slope=0.1, format="8-ball", session="Fall 2026"):
    return {
        "volatility": sigma, "sample_size": sample_size,
        "sl_stability": stability if stability is not None else (1 / (1 + sigma) if sigma is not None else None),
        "regression_slope": slope, "format": format, "session_name": session,
    }


class TestVolatilityIndex:
    def test_matches_the_documented_transform(self):
        assert volatility_index(0.25) == pytest.approx(100 * 0.25 / 1.25)

    def test_null_when_sigma_is_null(self):
        assert volatility_index(None) is None

    def test_zero_sigma_is_a_real_zero_not_null(self):
        assert volatility_index(0.0) == 0.0


class TestDescriptor:
    def test_insufficient_evidence_when_sigma_is_null(self):
        assert descriptor(None) == INSUFFICIENT_EVIDENCE

    def test_no_observed_variation_at_exactly_zero(self):
        assert descriptor(0.0) == NO_OBSERVED_VARIATION

    def test_observed_variation_above_zero(self):
        assert descriptor(0.01) == OBSERVED_VARIATION


class TestBuildProfile:
    def test_measured_players_produce_a_real_median(self):
        roster = [roster_player("A", player_id=1), roster_player("B", player_id=2)]
        trends = {1: trend(sigma=0.2), 2: trend(sigma=0.6)}
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", roster, trends)

        expected_median = round((volatility_index(0.2) + volatility_index(0.6)) / 2, 4)
        assert profile.team_volatility_index == pytest.approx(expected_median, abs=1e-3)
        assert profile.coverage == 1.0
        assert profile.measured_count == 2

    def test_every_roster_player_appears_even_without_a_trend_row(self):
        roster = [roster_player("A", player_id=1), roster_player("B", player_id=2)]
        trends = {1: trend(sigma=0.2)}
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", roster, trends)

        assert len(profile.player_rows) == 2
        assert profile.coverage == 0.5
        missing = [r for r in profile.player_rows if r.player_external_id == "B"][0]
        assert missing.volatility_index is None
        assert missing.descriptor == INSUFFICIENT_EVIDENCE

    def test_zero_measured_players_is_a_null_median_not_zero(self):
        roster = [roster_player("A", player_id=1)]
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", roster, {})
        assert profile.team_volatility_index is None
        assert profile.coverage == 0.0

    def test_empty_roster_is_null_not_zero_coverage(self):
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", [], {})
        assert profile.team_volatility_index is None
        assert profile.coverage is None
        assert profile.roster_count == 0

    def test_median_for_even_count_averages_middle_two(self):
        roster = [roster_player(f"P{i}", player_id=i) for i in range(4)]
        trends = {0: trend(sigma=0.1), 1: trend(sigma=0.3), 2: trend(sigma=0.5), 3: trend(sigma=0.7)}
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", roster, trends)
        indices = sorted(volatility_index(s) for s in (0.1, 0.3, 0.5, 0.7))
        assert profile.team_volatility_index == pytest.approx((indices[1] + indices[2]) / 2)

    def test_formula_version_is_recorded(self):
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", [], {})
        assert profile.formula_version == FORMULA_VERSION

    def test_raw_sigma_and_sample_size_are_carried_through(self):
        roster = [roster_player("A", player_id=1)]
        trends = {1: trend(sigma=0.42, sample_size=8)}
        profile = build_profile("T-OPP", "Corner Pockets", "Fall 2026", roster, trends)
        row = profile.player_rows[0]
        assert row.sigma == 0.42
        assert row.sample_size == 8
