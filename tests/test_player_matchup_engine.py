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
    reconstruct_win_loss,
    skill_trend_for,
)
from database.models import Match, PlayerMatch

OUR_TEAM = "OUR1"
OPPONENT_TEAM = "OPP1"


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


def _build(pairing=None, **kwargs):
    return build_player_matchup_report(pairing or _pairing(), OUR_TEAM, OPPONENT_TEAM, **kwargs)


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


class TestReconstructWinLoss:
    """GPT audit P1: direct_evidence_count is distinct MATCHES, not games,
    and the exact real (wins, losses) is safely recoverable alongside it --
    not a fabricated precision, since the count is exact, not just the
    rounded rate."""

    def test_exact_record_recovers_correctly(self):
        assert reconstruct_win_loss(0.75, 4) == (3, 1)

    def test_a_rate_that_does_not_round_cleanly_still_recovers_the_real_count(self):
        # 4 of 6 wins -> 0.667 rounded to 3 decimals, as
        # analytics.pairing_evidence._observed_win_rate actually stores it.
        assert reconstruct_win_loss(0.667, 6) == (4, 2)

    def test_the_real_example_that_motivated_this_fix(self):
        # A 1-0 pairing and a 2-2 pairing must each reconstruct exactly,
        # so a caller pooling across pairings gets the true 3-2 combined
        # record, not an average-of-rates distortion.
        assert reconstruct_win_loss(1.0, 1) == (1, 0)
        assert reconstruct_win_loss(0.5, 4) == (2, 2)

    def test_no_rate_is_not_reconstructed(self):
        assert reconstruct_win_loss(None, 0) is None

    def test_zero_count_is_not_reconstructed(self):
        assert reconstruct_win_loss(0.5, 0) is None


class TestBuildPlayerMatchupReport:
    def test_direct_evidence_produces_a_descriptive_not_categorical_summary(self):
        report = _build()

        assert report.evidence_label is EvidenceLabel.DIRECT
        assert "75%" in report.summary
        # GPT audit P1: a distinct match is not a game -- fixed wording.
        assert "recorded match(es)" in report.summary
        assert "game(s)" not in report.summary
        assert "(3-1)" in report.summary  # the real reconstructed record
        # No categorical verdict language -- descriptive only.
        assert "favored" not in report.summary.lower()
        assert "dangerous" not in report.summary.lower()

    def test_indirect_evidence_reports_the_skill_only_estimate(self):
        pairing = _pairing(
            evidence_label=EvidenceLabel.INDIRECT,
            observed_win_rate=None, direct_evidence_count=0,
            modeled_win_probability=0.62, model_source="analytics.head_to_head.skill_only_win_probability",
        )
        report = _build(pairing)

        assert "No direct history" in report.summary
        assert "62%" in report.summary
        assert "SL5 vs SL4" in report.summary
        assert report.direct_wins is None
        assert report.direct_losses is None

    def test_unknown_evidence_says_no_data_not_a_guess(self):
        pairing = _pairing(
            evidence_label=EvidenceLabel.UNKNOWN,
            observed_win_rate=None, direct_evidence_count=0,
            modeled_win_probability=None, model_source=None,
        )
        report = _build(pairing)

        assert report.summary == "No data available for this pairing."
        assert report.modeled_win_probability is None

    def test_missing_trends_default_to_no_data_not_a_crash(self):
        report = _build()
        assert report.player_trend is NO_SKILL_TREND
        assert report.opponent_trend is NO_SKILL_TREND

    def test_trend_context_is_appended_when_available_and_is_labelled_whole_history(self):
        from analytics.player_matchup_engine import SkillTrendInfo

        report = _build(
            player_trend=SkillTrendInfo(trend="up", volatility=1, last_change="SL 4 → SL 5"),
            opponent_trend=SkillTrendInfo(trend="stable", volatility=0, last_change=None),
        )
        assert "Ann: up" in report.summary
        assert "Bob: stable" in report.summary
        # GPT audit P2: skill_level_history is whole captured history, not
        # a recent window -- the summary must say so, not "recent".
        assert "whole captured history" in report.summary
        assert "recent" not in report.summary.lower()

    def test_every_real_field_carries_through_unmodified(self):
        pairing = _pairing()
        report = _build(pairing)
        assert report.player_id == pairing.player_id
        assert report.opponent_external_id == pairing.opponent_external_id
        assert report.format == pairing.format
        assert report.session_name == pairing.session_name
        assert report.direct_evidence_count == pairing.direct_evidence_count

    def test_the_report_carries_the_real_team_scope(self):
        """GPT audit P1: without team ids on the report itself, two real
        scopes with the same two players collide -- see
        ui/export_html_player_matchup_engine.py's scope-safe key."""
        report = _build()
        assert report.our_team_external_id == OUR_TEAM
        assert report.opponent_team_external_id == OPPONENT_TEAM
