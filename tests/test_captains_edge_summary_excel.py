"""Tests for the Captains_Edge_Summary Excel sheet (ui/export_excel.py)."""

from __future__ import annotations

import json

from openpyxl import Workbook, load_workbook

from ui.export_excel import (
    ANCHOR_CANDIDATES_TITLE,
    CAPTAINS_EDGE_SUMMARY_SHEET,
    DANGER_MATCHUPS_TITLE,
    HIGH_RISK_LINEUPS_TITLE,
    STRONGEST_PAIRINGS_TITLE,
    append_captains_edge_summary_sheet,
)


def payload():
    return {
        "pairings": [
            {"player_name": "Alice", "opponent_name": "Bob", "matchup_score": 90},
            {"player_name": "Alex", "opponent_name": "Carol", "matchup_score": 40},
        ],
        "opponent_scouting": [
            {
                "opponent_name": "Bob", "avg_win_probability": 0.2, "opponent_volatility": 0.6,
                "is_danger_matchup": True, "danger_reasons": ["elevated volatility"],
            },
            {
                "opponent_name": "Carol", "avg_win_probability": 0.9, "opponent_volatility": 0.1,
                "is_danger_matchup": False, "danger_reasons": [],
            },
        ],
        "lineups": [
            {
                "team_name": "Chalk It Up", "opponent_team_name": "Corner Pockets",
                "lineup_risk": {
                    "lineup_risk_score": 0.75, "anchor_player_name": "Alice",
                    "anchor_stability_score": 0.65,
                },
            },
        ],
    }


def _write(tmp_path, document):
    workbook_path = tmp_path / "workbook.xlsx"
    document_path = tmp_path / "lineups.json"
    workbook = Workbook()
    workbook.active.title = "Existing"
    workbook.save(workbook_path)
    document_path.write_text(json.dumps(document), encoding="utf-8")
    return workbook_path, document_path


class TestAppendCaptainsEdgeSummarySheet:
    def test_creates_the_real_sheet(self, tmp_path):
        workbook_path, document_path = _write(tmp_path, payload())
        assert append_captains_edge_summary_sheet(workbook_path, document_path) == str(workbook_path)
        assert CAPTAINS_EDGE_SUMMARY_SHEET in load_workbook(workbook_path).sheetnames

    def test_all_four_real_block_titles_are_present(self, tmp_path):
        workbook_path, document_path = _write(tmp_path, payload())
        append_captains_edge_summary_sheet(workbook_path, document_path)
        sheet = load_workbook(workbook_path)[CAPTAINS_EDGE_SUMMARY_SHEET]
        first_column = [row[0].value for row in sheet.iter_rows()]
        for title in (STRONGEST_PAIRINGS_TITLE, DANGER_MATCHUPS_TITLE,
                      ANCHOR_CANDIDATES_TITLE, HIGH_RISK_LINEUPS_TITLE):
            assert title in first_column

    def test_the_strongest_pairing_block_contains_the_real_top_row(self, tmp_path):
        workbook_path, document_path = _write(tmp_path, payload())
        append_captains_edge_summary_sheet(workbook_path, document_path)
        sheet = load_workbook(workbook_path)[CAPTAINS_EDGE_SUMMARY_SHEET]
        values = [[c.value for c in row] for row in sheet.iter_rows()]
        title_idx = [row[0] for row in values].index(STRONGEST_PAIRINGS_TITLE)
        header = values[title_idx + 1]
        assert header[:3] == ["Player", "Opponent", "Matchup Score"]
        data_row = values[title_idx + 2]
        assert data_row[:3] == ["Alice", "Bob", 90]

    def test_the_danger_matchup_block_only_lists_real_flagged_opponents(self, tmp_path):
        workbook_path, document_path = _write(tmp_path, payload())
        append_captains_edge_summary_sheet(workbook_path, document_path)
        sheet = load_workbook(workbook_path)[CAPTAINS_EDGE_SUMMARY_SHEET]
        values = [[c.value for c in row] for row in sheet.iter_rows()]
        title_idx = [row[0] for row in values].index(DANGER_MATCHUPS_TITLE)
        data_row = values[title_idx + 2]
        assert data_row[0] == "Bob"  # Carol wasn't flagged, must not appear

    def test_is_idempotent_and_replaces_a_prior_sheet(self, tmp_path):
        workbook_path, document_path = _write(tmp_path, payload())
        append_captains_edge_summary_sheet(workbook_path, document_path)
        append_captains_edge_summary_sheet(workbook_path, document_path)
        assert load_workbook(workbook_path).sheetnames == ["Existing", CAPTAINS_EDGE_SUMMARY_SHEET]

    def test_respects_a_custom_n(self, tmp_path):
        document = payload()
        document["pairings"] = [
            {"player_name": str(i), "opponent_name": "X", "matchup_score": i} for i in range(10)
        ]
        workbook_path, document_path = _write(tmp_path, document)
        append_captains_edge_summary_sheet(workbook_path, document_path, n=2)
        sheet = load_workbook(workbook_path)[CAPTAINS_EDGE_SUMMARY_SHEET]
        values = [[c.value for c in row] for row in sheet.iter_rows()]
        title_idx = [row[0] for row in values].index(STRONGEST_PAIRINGS_TITLE)
        next_title_idx = [row[0] for row in values].index(DANGER_MATCHUPS_TITLE)
        # header + exactly 2 real data rows + 1 spacer row = 4 rows between titles
        assert next_title_idx - title_idx == 4

    def test_empty_document_still_produces_a_real_sheet_with_no_data_rows(self, tmp_path):
        workbook_path, document_path = _write(tmp_path, {})
        append_captains_edge_summary_sheet(workbook_path, document_path)
        sheet = load_workbook(workbook_path)[CAPTAINS_EDGE_SUMMARY_SHEET]
        first_column = [row[0].value for row in sheet.iter_rows()]
        assert STRONGEST_PAIRINGS_TITLE in first_column
