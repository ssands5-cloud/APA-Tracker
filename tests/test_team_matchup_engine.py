"""Tests for analytics/team_matchup_engine.py.

Purely computational: builds a real PairingEvidenceMatrix (via
build_pairing_matrix, the same helper analytics.pairing_evidence's own
tests use) and real analytics.lineup_lab.LineupLabResult objects directly
-- no database, matching how analytics.opponent_risk_profile and
analytics.lineup_lab are already tested.
"""

from __future__ import annotations

from analytics.lineup_lab import LineupLabResult, LineupSlot, UnmatchedPlayer, UnmatchedOpponent
from analytics.pairing_evidence import (
    EvidenceLabel,
    PairingEvidence,
    PairingEvidenceMatrix,
    build_pairing_matrix,
)
from analytics.head_to_head import skill_only_win_probability
from analytics.player_matchup_engine import SkillTrendInfo
from analytics.team_matchup_engine import build_ranked_opponents, build_team_matchup_report

FORMAT = "8-Ball Open"
SESSION = "Fall 2026"


def _pairing(player_id, opponent_id, player_name, opponent_name, **overrides) -> PairingEvidence:
    base = dict(
        player_id=player_id, player_external_id=f"P{player_id}", player_name=player_name,
        player_skill_level=5,
        opponent_id=opponent_id, opponent_external_id=f"O{opponent_id}", opponent_name=opponent_name,
        opponent_skill_level=4,
        format=FORMAT, session_name=SESSION,
        evidence_label=EvidenceLabel.UNKNOWN,
        observed_win_rate=None, direct_evidence_count=0,
        modeled_win_probability=None, model_source=None,
    )
    base.update(overrides)
    return PairingEvidence(**base)


def _matrix(pairings) -> PairingEvidenceMatrix:
    expected = sorted({(p.player_id, p.opponent_id) for p in pairings})
    counts = build_pairing_matrix(pairings, expected)
    return PairingEvidenceMatrix(
        our_team_external_id="OUR1", opponent_team_external_id="OPP1",
        format=FORMAT, session_name=SESSION,
        expected_pairings=tuple(expected), pairings=tuple(pairings),
        counts=counts, our_roster_available=True, opponent_roster_available=True,
    )


class TestBuildRankedOpponents:
    def test_toughest_opponent_sorts_first(self):
        pairings = [
            _pairing(1, 10, "Ann", "Bob", evidence_label=EvidenceLabel.INDIRECT,
                     player_skill_level=5, opponent_skill_level=7,
                     modeled_win_probability=0.2, model_source="skill_only"),
            _pairing(1, 11, "Ann", "Carol", evidence_label=EvidenceLabel.INDIRECT,
                     player_skill_level=5, opponent_skill_level=3,
                     modeled_win_probability=0.8, model_source="skill_only"),
        ]
        ranked = build_ranked_opponents(_matrix(pairings))

        assert [r.opponent_name for r in ranked] == ["Bob", "Carol"]
        expected_bob = round(skill_only_win_probability(5, 7), 4)
        assert ranked[0].reliability_weighted_skill_probability == expected_bob

    def test_no_signal_sorts_last_never_assumed_average(self):
        pairings = [
            _pairing(1, 10, "Ann", "Bob", evidence_label=EvidenceLabel.INDIRECT,
                     opponent_skill_level=4, modeled_win_probability=0.5, model_source="skill_only"),
            _pairing(1, 11, "Ann", "NoData", evidence_label=EvidenceLabel.UNKNOWN,
                     opponent_skill_level=None),
        ]
        ranked = build_ranked_opponents(_matrix(pairings))

        assert ranked[-1].opponent_name == "NoData"
        assert ranked[-1].reliability_weighted_skill_probability is None

    def test_direct_win_rate_is_the_true_pooled_record_not_an_average_of_rates(self):
        """GPT audit P1, the real example that motivated this fix: a 1-0
        pairing and a 2-2 pairing must pool to the true combined 3-2 (60%)
        record, not the misleading 75% an unweighted average of the two
        pairings' own rates would report."""
        pairings = [
            _pairing(1, 10, "Ann", "Bob", evidence_label=EvidenceLabel.DIRECT,
                     observed_win_rate=1.0, direct_evidence_count=1),
            _pairing(2, 10, "Alex", "Bob", evidence_label=EvidenceLabel.DIRECT,
                     observed_win_rate=0.5, direct_evidence_count=4),
        ]
        ranked = build_ranked_opponents(_matrix(pairings))

        bob = next(r for r in ranked if r.opponent_name == "Bob")
        assert bob.direct_win_rate == 0.6  # true pooled 3-2, not avg(1.0, 0.5) == 0.75
        assert bob.direct_wins == 3
        assert bob.direct_losses == 2
        assert bob.direct_sample_size == 5  # sum of distinct-match counts

    def test_no_direct_history_reports_none_not_zero(self):
        pairings = [
            _pairing(1, 10, "Ann", "Bob", evidence_label=EvidenceLabel.INDIRECT,
                     modeled_win_probability=0.5, model_source="skill_only"),
        ]
        ranked = build_ranked_opponents(_matrix(pairings))

        bob = ranked[0]
        assert bob.direct_win_rate is None
        assert bob.direct_wins is None
        assert bob.direct_losses is None
        assert bob.direct_sample_size == 0


class TestBuildTeamMatchupReport:
    def _lineup_result(self):
        return LineupLabResult(
            assignments=(
                LineupSlot(
                    player_id=1, player_name="Ann", player_skill_level=5,
                    opponent_id=10, opponent_name="Bob", opponent_skill_level=4,
                    evidence_label=EvidenceLabel.INDIRECT, observed_win_rate=None,
                    direct_evidence_count=0, modeled_win_probability=0.6,
                    model_source="skill_only", lineup_score=0.6, lineup_score_source="skill_only",
                ),
            ),
            unassigned_players=(UnmatchedPlayer(player_id=2, player_name="Alex"),),
            unassigned_opponents=(),
            total_score=0.6, skill_total=5, is_legal=None, blocked_reason=None,
        )

    def test_rosters_are_derived_from_the_matrix_never_requeried(self):
        pairings = [
            _pairing(1, 10, "Ann", "Bob", evidence_label=EvidenceLabel.INDIRECT,
                     modeled_win_probability=0.6, model_source="skill_only"),
        ]
        report = build_team_matchup_report(_matrix(pairings), "Mark It Up", "Corner Pockets")

        assert [p.player_name for p in report.our_roster] == ["Ann"]
        assert [p.player_name for p in report.opponent_roster] == ["Bob"]

    def test_trends_are_attached_by_player_id(self):
        pairings = [
            _pairing(1, 10, "Ann", "Bob", evidence_label=EvidenceLabel.INDIRECT,
                     modeled_win_probability=0.6, model_source="skill_only"),
        ]
        trend = SkillTrendInfo(trend="up", volatility=1, last_change="SL 4 → SL 5")
        report = build_team_matchup_report(
            _matrix(pairings), "Mark It Up", "Corner Pockets",
            our_trends={1: trend},
        )
        assert report.our_roster[0].trend is trend

    def test_evidence_counts_match_the_matrix_exactly(self):
        pairings = [
            _pairing(1, 10, "Ann", "Bob", evidence_label=EvidenceLabel.DIRECT,
                     observed_win_rate=1.0, direct_evidence_count=2),
            _pairing(1, 11, "Ann", "Carol", evidence_label=EvidenceLabel.UNKNOWN),
        ]
        matrix = _matrix(pairings)
        report = build_team_matchup_report(matrix, "Mark It Up", "Corner Pockets")

        assert report.evidence_counts == matrix.counts

    def test_lineup_result_carries_through_and_summary_reports_board_count(self):
        pairings = [
            _pairing(1, 10, "Ann", "Bob", evidence_label=EvidenceLabel.INDIRECT,
                     modeled_win_probability=0.6, model_source="skill_only"),
        ]
        report = build_team_matchup_report(
            _matrix(pairings), "Mark It Up", "Corner Pockets",
            lineup_result=self._lineup_result(),
        )
        assert report.lineup_result is not None
        assert len(report.lineup_result.assignments) == 1
        assert "1 board(s)" in report.summary

    def test_a_lineup_error_carries_through_and_is_named_in_the_summary(self):
        pairings = [
            _pairing(1, 10, "Ann", "Bob", evidence_label=EvidenceLabel.INDIRECT,
                     modeled_win_probability=0.6, model_source="skill_only"),
        ]
        report = build_team_matchup_report(
            _matrix(pairings), "Mark It Up", "Corner Pockets",
            lineup_error="Lineup of 10 players vs 10 opponents needs too many assignments",
        )
        assert report.lineup_result is None
        assert "No approved lineup" in report.summary

    def test_the_summary_never_narrates_a_toughest_or_favorable_verdict(self):
        """GPT audit P1: an earlier version's summary said "Toughest real
        matchup: X" / "Most favorable real matchup: Y", which reads as a
        tactical verdict from a ranking signal
        (reliability_weighted_skill_probability) that has not been
        independently validated. The ranked table itself still carries the
        real signal -- the auto-generated prose summary must not narrate
        it as a verdict."""
        pairings = [
            _pairing(1, 10, "Ann", "Bob", evidence_label=EvidenceLabel.INDIRECT,
                     player_skill_level=5, opponent_skill_level=7,
                     modeled_win_probability=0.2, model_source="skill_only"),
            _pairing(1, 11, "Ann", "Carol", evidence_label=EvidenceLabel.INDIRECT,
                     player_skill_level=5, opponent_skill_level=3,
                     modeled_win_probability=0.8, model_source="skill_only"),
        ]
        report = build_team_matchup_report(_matrix(pairings), "Mark It Up", "Corner Pockets")

        assert "toughest" not in report.summary.lower()
        assert "favorable" not in report.summary.lower()
        assert "favored" not in report.summary.lower()
        # The real ranking signal is still there -- just not narrated.
        assert len(report.ranked_opponents) == 2
