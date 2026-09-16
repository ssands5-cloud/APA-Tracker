"""Tests for analytics/player_matchup_engine.py.

Purely computational: builds PairingEvidence rows and PlayerMatch fixtures
directly (no database), matching how analytics.lineup_lab and
analytics.opponent_risk_profile are already tested.
"""

from __future__ import annotations

from analytics.pairing_evidence import EvidenceLabel, PairingEvidence
from analytics.player_matchup_engine import (
    NO_SKILL_TREND,
    build_player_matchup_report,
    skill_trend_for,
)
from database.models import Match, PlayerMatch


def _pairing(**overrides) -> PairingEvidence:
    base = dict(
        player_id=1, player_external_id="P1", player_name="Ann",
        player_skill_level=5,
        opponent_id=2, opponent_external_id="P2", opponent_name="Bob",
        opponent_skill_level=4,
        format="8-Ball Open", session_name="Fall 2026",
        evidence_label=EvidenceLabel.DIRECT,
        observed_win_rate=0.75, direct_evidence_count=4,
        modeled_win_probability=0.7, model_source="analytics.head_to_head",
    )
    base.update(overrides)
    return PairingEvidence(**base)


class TestSkillTrendFor:
    def test_no_readings_is_no_data(self):
        trend = skill_trend_for([])
        assert trend.trend == "no data"
        assert trend.volatility == 0
        assert trend.last_change is None

    def test_a_real_change_is_reported(self):
        match = Match(external_id="M1", week=3)
        matches = [
            PlayerMatch(skill_level=4, match_date="2026-08-01"),
            PlayerMatch(skill_level=5, match_date="2026-08-08", match=match),
        ]
        trend = skill_trend_for(matches)
        assert trend.trend == "up"
        assert trend.volatility == 1
        assert trend.last_change == "SL 4 → SL 5 in Week 3"


class TestBuildPlayerMatchupReport:
    def test_direct_evidence_produces_a_descriptive_not_categorical_summary(self):
        pairing = _pairing()
        report = build_player_matchup_report(pairing)

        assert report.evidence_label is EvidenceLabel.DIRECT
        assert "75%" in report.summary
        assert "4 game(s)" in report.summary
        # No categorical verdict language -- descriptive only.
        assert "favored" not in report.summary.lower()
        assert "dangerous" not in report.summary.lower()

    def test_indirect_evidence_reports_the_skill_only_estimate(self):
        pairing = _pairing(
            evidence_label=EvidenceLabel.INDIRECT,
            observed_win_rate=None, direct_evidence_count=0,
            modeled_win_probability=0.62, model_source="analytics.head_to_head.skill_only_win_probability",
        )
        report = build_player_matchup_report(pairing)

        assert "No direct history" in report.summary
        assert "62%" in report.summary
        assert "SL5 vs SL4" in report.summary

    def test_unknown_evidence_says_no_data_not_a_guess(self):
        pairing = _pairing(
            evidence_label=EvidenceLabel.UNKNOWN,
            observed_win_rate=None, direct_evidence_count=0,
            modeled_win_probability=None, model_source=None,
        )
        report = build_player_matchup_report(pairing)

        assert report.summary == "No data available for this pairing."
        assert report.modeled_win_probability is None

    def test_missing_trends_default_to_no_data_not_a_crash(self):
        report = build_player_matchup_report(_pairing())
        assert report.player_trend is NO_SKILL_TREND
        assert report.opponent_trend is NO_SKILL_TREND

    def test_trend_context_is_appended_when_available(self):
        from analytics.player_matchup_engine import SkillTrendInfo

        report = build_player_matchup_report(
            _pairing(),
            player_trend=SkillTrendInfo(trend="up", volatility=1, last_change="SL 4 → SL 5"),
            opponent_trend=SkillTrendInfo(trend="stable", volatility=0, last_change=None),
        )
        assert "Ann: up" in report.summary
        assert "Bob: stable" in report.summary

    def test_every_real_field_carries_through_unmodified(self):
        pairing = _pairing()
        report = build_player_matchup_report(pairing)
        assert report.player_id == pairing.player_id
        assert report.opponent_external_id == pairing.opponent_external_id
        assert report.format == pairing.format
        assert report.session_name == pairing.session_name
        assert report.direct_evidence_count == pairing.direct_evidence_count
