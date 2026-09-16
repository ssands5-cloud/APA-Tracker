"""Tests for ui/export_excel_player_matchup_engine.py."""

from __future__ import annotations

from openpyxl import load_workbook

from analytics.pairing_evidence import EvidenceLabel, PairingEvidence
from analytics.player_matchup_engine import build_player_matchup_report
from ui.export_excel_player_matchup_engine import write_workbook


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


class TestWriteWorkbook:
    def test_a_real_row_per_report(self, tmp_path):
        path = write_workbook(
            [build_player_matchup_report(_pairing())], tmp_path / "player_matchup_engine.xlsx",
        )
        workbook = load_workbook(path)
        sheet = workbook["Player Matchup Engine"]
        assert sheet.max_row == 2  # header + one report
        assert sheet.cell(row=2, column=1).value == "Ann"
        assert sheet.cell(row=2, column=5).value == "Bob"

    def test_headers_are_frozen_and_filterable(self, tmp_path):
        path = write_workbook(
            [build_player_matchup_report(_pairing())], tmp_path / "out.xlsx",
        )
        sheet = load_workbook(path)["Player Matchup Engine"]
        assert sheet.freeze_panes == "A2"
        assert sheet.auto_filter.ref is not None

    def test_an_empty_report_list_still_produces_an_openable_workbook(self, tmp_path):
        path = write_workbook([], tmp_path / "empty.xlsx")
        workbook = load_workbook(path)
        assert workbook["Player Matchup Engine"].max_row == 1  # header only
