"""Tests for ui/export_excel_ultimate_coach.py.

Two layers, deliberately:

1. Structural tests via openpyxl.load_workbook -- run everywhere, always.
2. An end-to-end real-Excel test via COM automation (win32com) -- skipped
   wherever pywin32/Excel isn't available (not a declared project
   dependency, and CI has no reason to have real Excel installed), but
   runs for real in a Windows dev environment that does.

Layer 2 exists because layer 1 alone is not sufficient here: openpyxl's own
reader is lenient about OOXML it wrote itself, and happily round-tripped a
workbook that real Excel refused to open at all (Workbooks.Open failed
outright, not even a repair prompt) -- found by actually opening a build of
this module in Excel via COM during development. The bug was a duplicate
worksheet-level autoFilter alongside a Table's own internal autoFilter, and
separately a cross-sheet structured-table-reference used directly as a data
validation list source (Excel requires a workbook-scoped defined Name to do
that reliably). Neither would have been caught by openpyxl-only assertions.
"""

from __future__ import annotations

import sys

import pytest
from openpyxl import load_workbook

from ui.export_excel_ultimate_coach import build_workbook, write_workbook


def _payload():
    return {
        "schema": "ultimate-coach-verified-cockpit-v1",
        "probability_publication": "FORBIDDEN",
        "matchup_probability": None,
        "predictive_confidence": None,
        "requires_live_apa_login": False,
        "database_mutated": False,
        "name_matching_used": False,
        "trust": {
            "verified_identity_count": 3, "identity_exclusion_count": 0,
            "identity_verified_game_count": 2, "quarantined_game_count": 0,
            "suspect_participant_count": 0, "indeterminate_participant_count": 0,
            "source_coverage_issue_count": 0, "total_all_games_rows": 2,
        },
        "counts": {"players": 3, "head_to_head_rows": 4, "all_games": 2},
        "players": [
            {
                "id": 1, "external_id": "1001", "name": "Ann Archer",
                "current_skill_level": 4, "current_matches_won": 10, "current_matches_played": 15,
                "team_history": [
                    {"team_name": "Sharks", "division_id": "d1", "session_name": "Spring 2026", "is_current": True, "skill_level": 4, "matches_won": 10, "matches_played": 15},
                ],
            },
            {
                "id": 2, "external_id": "1002", "name": "Bea Baker",
                "current_skill_level": None, "current_matches_won": None, "current_matches_played": None,
                "team_history": [
                    # Same team, two divisions -- must dedupe on the Team Rosters sheet.
                    {"team_name": "Sharks", "division_id": "da", "session_name": "Spring 2026", "is_current": True, "skill_level": 5, "matches_won": 2, "matches_played": 6},
                    {"team_name": "Sharks", "division_id": "db", "session_name": "Spring 2026", "is_current": True, "skill_level": 5, "matches_won": 3, "matches_played": 6},
                ],
            },
            {
                "id": 3, "external_id": "1003", "name": "Cam Cole",
                "current_skill_level": 3, "current_matches_won": 3, "current_matches_played": 5,
                "team_history": [
                    {"team_name": "Falcons", "division_id": "d2", "session_name": "Spring 2026", "is_current": True, "skill_level": 3, "matches_won": 3, "matches_played": 5},
                ],
            },
            {
                # Duplicate display name on purpose -- 184 of these exist in
                # the real verified dataset. A dropdown keyed on name alone
                # would silently resolve to whichever duplicate MATCH finds
                # first: exactly the "fuzzy name matching as identity" /
                # "silent identity merge" the project's safety locks forbid.
                "id": 4, "external_id": "1004", "name": "Ann Archer",
                "current_skill_level": 6, "current_matches_won": 1, "current_matches_played": 3,
                "team_history": [],
            },
        ],
        "evidence": [
            {"player_id": 1, "opponent_id": 3, "format": "EIGHT", "result": "W"},
            {"player_id": 3, "opponent_id": 1, "format": "EIGHT", "result": "L"},
            {"player_id": 1, "opponent_id": 3, "format": "EIGHT", "result": "L"},
            {"player_id": 3, "opponent_id": 1, "format": "EIGHT", "result": "W"},
        ],
    }


def test_workbook_has_expected_sheets_and_no_fabricated_probability(tmp_path):
    path = write_workbook(_payload(), tmp_path / "uc.xlsx", built_at="test", source_db="test.db")
    wb = load_workbook(path)

    assert set(wb.sheetnames) == {
        "Build Info", "Data Trust", "Players", "Team Rosters", "Teams",
        "Player vs Player", "Coach Dashboard", "Match Night",
    }

    build_info = {row[0].value: row[1].value for row in wb["Build Info"].iter_rows(min_row=2, max_col=2) if row[0].value}
    assert build_info["Probability publication"] == "FORBIDDEN"
    assert build_info["Matchup probability"] is None
    assert build_info["Predictive confidence"] is None


def test_players_sheet_disambiguates_duplicate_names(tmp_path):
    path = write_workbook(_payload(), tmp_path / "uc.xlsx", built_at="test", source_db="test.db")
    wb = load_workbook(path)

    labels = [row[0].value for row in wb["Players"].iter_rows(min_row=2, max_col=1)]
    assert "Ann Archer (Member #1001)" in labels
    assert "Ann Archer (Member #1004)" in labels
    assert len(labels) == len(set(labels))


def test_team_rosters_sheet_dedupes_multi_division_membership(tmp_path):
    path = write_workbook(_payload(), tmp_path / "uc.xlsx", built_at="test", source_db="test.db")
    wb = load_workbook(path)

    rows = list(wb["Team Rosters"].iter_rows(min_row=2, values_only=True))
    sharks_rows = [r for r in rows if r[0] == "Sharks"]
    assert len(sharks_rows) == 2  # Ann + Bea once each, never Bea twice

    teams_rows = {r[0]: r for r in wb["Teams"].iter_rows(min_row=2, values_only=True)}
    assert teams_rows["Sharks"][3] == 2  # Roster Count
    assert teams_rows["Sharks"][5] == 9  # Skill Total: Ann 4 + Bea 5, once each


def test_player_vs_player_sheet_has_pair_key_for_lookup(tmp_path):
    path = write_workbook(_payload(), tmp_path / "uc.xlsx", built_at="test", source_db="test.db")
    wb = load_workbook(path)

    rows = list(wb["Player vs Player"].iter_rows(min_row=2, values_only=True))
    keys = {r[7] for r in rows}
    assert "1|EIGHT|3" in keys
    assert "3|EIGHT|1" in keys


def test_returns_none_workbook_gracefully_handles_no_players(tmp_path):
    payload = _payload()
    payload["players"] = []
    payload["evidence"] = []
    path = write_workbook(payload, tmp_path / "uc_empty.xlsx", built_at="test", source_db="test.db")
    wb = load_workbook(path)
    # Still a valid workbook with all sheets -- no crash, no fabricated rows.
    assert "Coach Dashboard" in wb.sheetnames
    assert wb["Players"].max_row == 1  # header only


@pytest.mark.skipif(sys.platform != "win32", reason="Excel COM automation requires Windows")
def test_coach_dashboard_and_match_night_compute_correctly_in_real_excel(tmp_path):
    win32com_client = pytest.importorskip("win32com.client", reason="pywin32/Excel not available")

    path = write_workbook(_payload(), tmp_path / "uc_com.xlsx", built_at="test", source_db="test.db")

    try:
        excel = win32com_client.Dispatch("Excel.Application")
    except Exception:
        pytest.skip("Excel is not installed/registered on this machine")

    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(str(path))
    except Exception as exc:
        excel.Quit()
        pytest.fail(f"Real Excel refused to open the generated workbook: {exc}")

    try:
        dash = wb.Worksheets("Coach Dashboard")

        dash.Range("B4").Value = "Ann Archer (Member #1001)"
        dash.Range("B5").Value = "Cam Cole (Member #1003)"
        dash.Range("B6").Value = "8-Ball"
        excel.CalculateFullRebuild()
        assert dash.Range("B21").Value == 1  # Wins
        assert dash.Range("B22").Value == 1  # Losses
        assert dash.Range("B23").Value == 2  # Recorded meetings
        assert "50.0%" in str(dash.Range("B24").Value)

        dash.Range("B5").Value = "Bea Baker (Member #1002)"
        excel.CalculateFullRebuild()
        assert dash.Range("B21").Value == "0"
        assert "No recorded direct meeting" in str(dash.Range("B25").Value)
        # The disclosure explicitly explains it is NOT a real 0-0 record --
        # an absence of evidence, never fabricated evidence of a tie.
        assert "not evidence of a tie" in str(dash.Range("B25").Value)
        # Bea's current_skill_level is None -- must read as "not captured"
        # ("—"), never as a real skill level 0 (not a valid APA skill
        # level, but easy to misread if a blank INDEX result silently
        # reads back as numeric 0 instead of triggering the fallback).
        assert dash.Range("B18").Value == "—"

        night = wb.Worksheets("Match Night")
        night.Range("B5").Value = "Sharks"
        night.Range("C5").Value = "Falcons"
        excel.CalculateFullRebuild()
        assert night.Range("B7").Value == 2  # Sharks roster count (deduped)
        assert night.Range("C7").Value == 1  # Falcons roster count
        assert night.Range("B9").Value == 9  # Sharks skill total: 4 + 5
        assert night.Range("C9").Value == 3  # Falcons skill total
    finally:
        wb.Close(False)
        excel.Quit()
