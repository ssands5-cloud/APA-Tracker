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
        direct_wins=3, direct_losses=1,
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

    def test_readings_carry_the_real_chronological_series_for_a_sparkline(self):
        """A real plotted sparkline needs the actual series, not just the
        direction/volatility summary -- readings must be the real ordered
        skill_level values, missing readings skipped, never guessed."""
        matches = [
            PlayerMatch(skill_level=4, match_date="2026-08-01"),
            PlayerMatch(skill_level=None, match_date="2026-08-08"),
            PlayerMatch(skill_level=5, match_date="2026-08-15"),
        ]
        trend = skill_trend_for(matches)
        assert trend.readings == (4, 5)

    def test_reading_dates_are_aligned_with_readings_not_all_matches(self):
        """GPT audit follow-up (2026-09-16): a sparkline needs real date
        context alongside the values, aligned to the same skipped-None
        filtering as readings itself -- a date for a reading that was
        skipped would misalign the two series."""
        matches = [
            PlayerMatch(skill_level=4, match_date="2026-08-01"),
            PlayerMatch(skill_level=None, match_date="2026-08-08"),
            PlayerMatch(skill_level=5, match_date="2026-08-15"),
        ]
        trend = skill_trend_for(matches)
        assert trend.reading_dates == ("2026-08-01", "2026-08-15")

    def test_no_data_sentinel_has_no_readings(self):
        assert NO_SKILL_TREND.readings == ()
        assert NO_SKILL_TREND.reading_dates == ()


class TestBuildPlayerMatchupReport:
    def test_direct_wins_and_losses_pass_through_unreconstructed(self):
        """GPT audit follow-up (2026-09-16): reconstructing wins/losses
        from the rounded observed_win_rate is not exact in general (a real
        501-500 record rounds to 0.500, which reconstructs as the wrong
        500-501). The report must carry PairingEvidence's own exact
        direct_wins/direct_losses straight through, never re-derive them
        from the rate here."""
        pairing = _pairing(
            observed_win_rate=0.5, direct_evidence_count=1001,
            direct_wins=501, direct_losses=500,
        )
        report = _build(pairing)
        assert report.direct_wins == 501
        assert report.direct_losses == 500
        assert "(501-500)" in report.summary

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
            direct_wins=None, direct_losses=None,
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
            direct_wins=None, direct_losses=None,
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

    def test_the_report_carries_the_real_opponent_team_name(self):
        """GPT audit follow-up (2026-09-16): the opponent's real team name
        must be on the report so a coach-facing selector can disambiguate
        a same-named opponent player on two different teams -- the keys
        never collided, but the label alone could look identical."""
        report = _build(opponent_team_name="Corner Pockets")
        assert report.opponent_team_name == "Corner Pockets"

    def test_a_missing_opponent_team_name_is_no_data_not_a_crash(self):
        report = _build()
        assert report.opponent_team_name is None
