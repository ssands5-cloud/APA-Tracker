"""Data Coverage Excel export: a standalone workbook, never a patch to the
existing apa_stats.xlsx -- same posture as
ui/export_excel_player_vs_player.py.

One sheet, ``Data_Coverage``: real evidence-coverage counts/percentages,
every missing-skill-level player named individually, and the real sample
size backing each pairing. Fixed column widths and order for deterministic
output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from analytics.data_coverage import DataCoverageReport

SHEET_NAME = "Data_Coverage"

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F3864")

SAMPLE_COLUMNS = (
    "Player", "Opponent", "Evidence", "Direct Matches",
    "Player SL", "Opponent SL", "Model Source",
)
SAMPLE_WIDTHS = {
    "Player": 20, "Opponent": 20, "Evidence": 12, "Direct Matches": 14,
    "Player SL": 10, "Opponent SL": 12, "Model Source": 40,
}


def build_workbook(report: DataCoverageReport) -> Workbook:
    """Always produces a workbook -- unlike Player vs Player's export,
    Data Coverage is meaningful even with zero feasible pairings (it says
    so explicitly), so this is never omitted the way an empty PvP export
    would be."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_NAME

    coverage = report.evidence_coverage
    sheet.append(["Scope", f"{report.our_team_external_id} vs {report.opponent_team_external_id}",
                  report.format, report.session_name])
    sheet.append([])
    sheet.append(["Evidence Label", "Count", "Percentage"])
    for cell in sheet[3]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
    sheet.append(["DIRECT", coverage.direct_count, coverage.direct_pct])
    sheet.append(["INDIRECT", coverage.indirect_count, coverage.indirect_pct])
    sheet.append(["UNKNOWN", coverage.unknown_count, coverage.unknown_pct])
    sheet.append(["Total", coverage.total, 1.0 if coverage.total else None])
    for row in sheet.iter_rows(min_row=4, max_row=7, min_col=3, max_col=3):
        for cell in row:
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0.0%"

    sheet.append([])
    sheet.append(["Refresh dates"])
    sheet.append(["Standings last captured", report.standings_refreshed_at or "No data"])
    for player_id, ts in sorted(report.career_stats_refreshed_at.items()):
        sheet.append([f"Career stats ({player_id})", ts or "No data"])

    sheet.append([])
    sheet.append(["Missing skill levels"])
    sheet.append(["Side", "Player", "External ID"])
    for cell in sheet[sheet.max_row]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    if report.missing_skill_levels:
        for m in report.missing_skill_levels:
            sheet.append([m.side, m.player_name, m.player_external_id])
    else:
        sheet.append(["None -- every player has a real posted skill level."])

    sheet.append([])
    sheet.append(["Unavailable fields"])
    for field in report.unavailable_fields:
        sheet.append([field])

    for column, width in zip("ABCD", (28, 22, 16, 40)):
        sheet.column_dimensions[column].width = width

    samples_sheet = workbook.create_sheet("Sample_Sizes")
    samples_sheet.append(list(SAMPLE_COLUMNS))
    for cell in samples_sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
    for s in report.sample_sizes:
        samples_sheet.append([
            s.player_name, s.opponent_name, s.evidence_label.value,
            s.direct_matches, s.player_skill_level, s.opponent_skill_level,
            s.model_source,
        ])
    samples_sheet.freeze_panes = "A2"
    for index, name in enumerate(SAMPLE_COLUMNS, start=1):
        samples_sheet.column_dimensions[get_column_letter(index)].width = SAMPLE_WIDTHS[name]
    last_column = get_column_letter(len(SAMPLE_COLUMNS))
    samples_sheet.auto_filter.ref = f"A1:{last_column}{max(samples_sheet.max_row, 1)}"

    return workbook


def write_workbook(report: DataCoverageReport, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(report).save(output_path)
    return output_path
