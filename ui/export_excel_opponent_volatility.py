"""Opponent Volatility Excel export: a standalone workbook, per
docs/opponent_volatility.md's "HTML and Excel layout".

Two values-only sheets: Opponent_Volatility (one team summary row) and
Opponent_Volatility_Players (one row per canonical opponent roster player,
including nulls).
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from analytics.opponent_volatility import OpponentVolatilityProfile

SUMMARY_SHEET = "Opponent_Volatility"
PLAYERS_SHEET = "Opponent_Volatility_Players"

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F3864")

PLAYER_COLUMNS = (
    "Player External ID", "Player Name", "Sample Size", "Raw Volatility", "Stability",
    "Volatility Index", "Consistency Descriptor", "Trend Slope", "Format", "Session",
    "Source Status",
)


def _header(sheet, columns) -> None:
    sheet.append(list(columns))
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
    sheet.freeze_panes = "A2"


def build_workbook(profile: OpponentVolatilityProfile) -> Workbook:
    workbook = Workbook()
    summary = workbook.active
    summary.title = SUMMARY_SHEET
    summary.append(["Field", "Value"])
    for cell in summary[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    for field, value in (
        ("Opponent Team External ID", profile.opponent_team_external_id),
        ("Opponent Team Name", profile.opponent_team_name),
        ("Session", profile.session_name),
        ("Format", profile.format),
        ("Formula Version", profile.formula_version),
        ("Team Volatility Index (median)", profile.team_volatility_index),
        ("Coverage", profile.coverage),
        ("Roster Count", profile.roster_count),
        ("Measured Count", profile.measured_count),
        ("Source Manifest ID", profile.source_manifest_id),
        ("Captured At", profile.captured_at),
    ):
        summary.append([field, value])
    for row in summary.iter_rows(min_row=2, max_row=summary.max_row, min_col=2, max_col=2):
        for cell in row:
            if isinstance(cell.value, float):
                cell.number_format = "0.00%" if 0 <= cell.value <= 1 else "0.00"
    summary.column_dimensions["A"].width = 30
    summary.column_dimensions["B"].width = 26

    players_sheet = workbook.create_sheet(PLAYERS_SHEET)
    _header(players_sheet, PLAYER_COLUMNS)
    for r in profile.player_rows:
        players_sheet.append([
            r.player_external_id, r.player_name, r.sample_size, r.sigma, r.sl_stability,
            r.volatility_index, r.descriptor, r.regression_slope, r.format, r.session_name,
            r.source_status,
        ])
    for index, width in enumerate((18, 22, 12, 14, 12, 16, 22, 14, 12, 14, 16), start=1):
        players_sheet.column_dimensions[get_column_letter(index)].width = width
    last_column = get_column_letter(len(PLAYER_COLUMNS))
    players_sheet.auto_filter.ref = f"A1:{last_column}{max(players_sheet.max_row, 1)}"

    return workbook


def write_workbook(profile: OpponentVolatilityProfile, path: str | Path) -> Path:
    workbook = build_workbook(profile)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path
