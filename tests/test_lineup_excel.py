"""Tests for the workbook's post-built Lineup Optimizer sheet."""

from __future__ import annotations

import json

from openpyxl import load_workbook
from openpyxl import Workbook

from ui.export_excel import (
    LINEUP_COLUMNS,
    LINEUP_SHEET,
    append_lineup_optimizer_sheet,
    lineup_optimizer_rows,
)


def payload():
    return {
        "lineups": [{
            "team_id": "T1",
            "team_name": "Chalk It Up",
            "opponent_team_id": "T2",
            "opponent_team_name": "Corner Pockets",
            "format": "8-ball",
            "session_name": "Summer 2026",
            "assignments": [
                {
                    "player_name": "Alice",
                    "opponent_name": "Bob",
                    "matchup_score_raw": 80,
                    "win_probability": 0.8,
                    "confidence": None,
                    "risk_factor": 0.1,
                    "final_score": 0.72,
                    "lineup_rank": 1,
                    "source_pairing": True,
                    "rationale": "High win probability.",
                },
            ],
        }],
    }


def test_rows_keep_raw_score_and_render_missing_signals_as_no_data():
    rows = lineup_optimizer_rows(payload())
    assert rows[0]["Matchup Score"] == 80
    assert rows[0]["Win Probability"] == 0.8
    assert rows[0]["Confidence"] == "No data"
    assert rows[0]["Source Pairing"] == "Yes"


def test_append_creates_a_frozen_filterable_sheet(tmp_path):
    workbook_path = tmp_path / "workbook.xlsx"
    document_path = tmp_path / "lineups.json"
    workbook = Workbook()
    workbook.active.title = "Existing"
    workbook.save(workbook_path)
    document_path.write_text(json.dumps(payload()), encoding="utf-8")

    assert append_lineup_optimizer_sheet(workbook_path, document_path) == str(workbook_path)
    book = load_workbook(workbook_path)
    sheet = book[LINEUP_SHEET]
    assert [cell.value for cell in sheet[1]] == LINEUP_COLUMNS
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == "A1:N2"
    row = [cell.value for cell in sheet[2]]
    assert row[0:6] == ["Chalk It Up", "Corner Pockets", "8-ball", "Summer 2026", "Alice", "Bob"]
    assert row[6:10] == [80, 0.8, "No data", 0.1]
    assert sheet["H2"].number_format == "0%"


def test_append_is_idempotent_and_replaces_a_prior_sheet(tmp_path):
    workbook_path = tmp_path / "workbook.xlsx"
    document_path = tmp_path / "lineups.json"
    workbook = Workbook()
    workbook.active.title = "Existing"
    workbook.create_sheet(LINEUP_SHEET)
    workbook.save(workbook_path)
    document_path.write_text(json.dumps(payload()), encoding="utf-8")

    append_lineup_optimizer_sheet(workbook_path, document_path)
    append_lineup_optimizer_sheet(workbook_path, document_path)
    assert load_workbook(workbook_path).sheetnames == ["Existing", LINEUP_SHEET]
