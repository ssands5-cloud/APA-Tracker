"""Tests for ui/export_json_coach_advantage.py."""

from __future__ import annotations

from analytics.lineup_lab import LineupLabResult, LineupSlot, UnmatchedOpponent, UnmatchedPlayer
from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix
from analytics.player_matchup_engine import build_player_matchup_report
from analytics.team_matchup_engine import build_team_matchup_report
from ui.export_json_coach_advantage import (
    player_matchup_report_to_dict,
    team_matchup_report_to_dict,
)


def _pairing(**overrides) -> PairingEvidence:
    base = dict(
        player_id=1, player_external_id="P1", player_name="Ann", player_skill_level=5,
        opponent_id=2, opponent_external_id="P2", opponent_name="Bob", opponent_skill_level=4,
        format="8-Ball Open", session_name="Fall 2026",
        evidence_label=EvidenceLabel.DIRECT, observed_win_rate=0.75, direct_evidence_count=4,
        modeled_win_probability=0.7, model_source="analytics.head_to_head",
    )
    base.update(overrides)
    return PairingEvidence(**base)


class TestPlayerMatchupReportToDict:
    def test_round_trips_every_real_field(self):
        report = build_player_matchup_report(_pairing(), "OUR1", "OPP1")
        data = player_matchup_report_to_dict(report)

        assert data["player"]["name"] == "Ann"
        assert data["opponent"]["name"] == "Bob"
        assert data["our_team_id"] == "OUR1"
        assert data["opponent_team_id"] == "OPP1"
        assert data["evidence_label"] == "DIRECT"
        assert data["observed_win_rate"] == 0.75
        assert data["direct_wins"] == 3
        assert data["direct_losses"] == 1
        assert data["summary"] == report.summary

    def test_evidence_label_serializes_as_a_plain_string_not_an_enum(self):
        report = build_player_matchup_report(_pairing(), "OUR1", "OPP1")
        data = player_matchup_report_to_dict(report)
        assert isinstance(data["evidence_label"], str)


class TestTeamMatchupReportToDict:
    def _matrix(self):
        pairing = _pairing()
        return PairingEvidenceMatrix(
            our_team_external_id="OUR1", opponent_team_external_id="OPP1",
            format="8-Ball Open", session_name="Fall 2026",
            expected_pairings=((1, 2),), pairings=(pairing,),
            counts={"DIRECT": 1, "INDIRECT": 0, "UNKNOWN": 0, "total_feasible_pairings": 1},
            our_roster_available=True, opponent_roster_available=True,
        )

    def test_round_trips_roster_and_evidence_counts(self):
        report = build_team_matchup_report(self._matrix(), "Mark It Up", "Corner Pockets")
        data = team_matchup_report_to_dict(report)

        assert data["our_team"]["name"] == "Mark It Up"
        assert data["opponent_roster"][0]["name"] == "Bob"
        assert data["evidence_counts"]["DIRECT"] == 1

    def test_ranked_opponents_carry_the_real_pooled_win_loss_record(self):
        report = build_team_matchup_report(self._matrix(), "Mark It Up", "Corner Pockets")
        data = team_matchup_report_to_dict(report)

        bob = next(o for o in data["ranked_opponents"] if o["name"] == "Bob")
        assert bob["direct_wins"] == 3
        assert bob["direct_losses"] == 1

    def test_lineup_is_none_when_no_result_and_no_error(self):
        report = build_team_matchup_report(self._matrix(), "Mark It Up", "Corner Pockets")
        data = team_matchup_report_to_dict(report)
        assert data["lineup"] is None
        assert data["lineup_error"] is None

    def test_lineup_result_serializes_with_a_1_based_board_number(self):
        lineup_result = LineupLabResult(
            assignments=(
                LineupSlot(
                    player_id=1, player_name="Ann", player_skill_level=5,
                    opponent_id=2, opponent_name="Bob", opponent_skill_level=4,
                    evidence_label=EvidenceLabel.DIRECT, observed_win_rate=0.75,
                    direct_evidence_count=4, modeled_win_probability=0.7,
                    model_source="analytics.head_to_head", lineup_score=0.75,
                    lineup_score_source="direct",
                ),
            ),
            unassigned_players=(UnmatchedPlayer(player_id=9, player_name="Alex"),),
            unassigned_opponents=(UnmatchedOpponent(opponent_id=8, opponent_name="Carol"),),
            total_score=0.75, skill_total=5, is_legal=True, blocked_reason=None,
        )
        report = build_team_matchup_report(
            self._matrix(), "Mark It Up", "Corner Pockets", lineup_result=lineup_result,
        )
        data = team_matchup_report_to_dict(report)

        assert data["lineup"]["assignments"][0]["board"] == 1
        assert data["lineup"]["unassigned_players"] == [{"id": 9, "name": "Alex"}]
        assert data["lineup"]["is_legal"] is True
