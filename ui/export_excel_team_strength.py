"""Team Strength Excel export: a standalone workbook, per
docs/team_strength.md's "Excel layout" -- never a patch to the existing
apa_stats.xlsx.

Three values-only sheets: Team_Strength (one scope-level summary row),
Team_Strength_Players (one row per canonical roster player), and
Team_Strength_Matches (one row per eligible finalized match).
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from analytics.team_strength import TeamStrengthReport

SUMMARY_SHEET = "Team_Strength"
PLAYERS_SHEET = "Team_Strength_Players"
MATCHES_SHEET = "Team_Strength_Matches"

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F3864")

PLAYER_COLUMNS = (
    "Player ID", "Player External ID", "Player Name", "Skill Level", "Matches Won",
    "Matches Played", "Observed Rate", "Contributes To Offense", "Scoreable For Depth",
    "Depth Order", "Is Fifth Depth Row",
)
MATCH_COLUMNS = (
    "Match ID", "Match Date", "Week", "Format", "Session", "Opponent Team ID",
    "Opponent Team Name", "Home/Away", "Points For", "Points Against",
)


def _header(sheet, columns) -> None:
    sheet.append(list(columns))
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
    sheet.freeze_panes = "A2"


def build_workbook(report: TeamStrengthReport) -> Workbook:
    workbook = Workbook()
    summary = workbook.active
    summary.title = SUMMARY_SHEET
    summary.append(["Field", "Value"])
    for cell in summary[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    for field, value in (
        ("Team External ID", report.team_external_id),
        ("Team Name", report.team_name),
        ("Session", report.session_name),
        ("Division ID", report.division_id),
        ("Format", report.format),
        ("Source Manifest ID", report.source_manifest_id),
        ("Captured At", report.captured_at),
        ("Formula Version", report.formula_version),
        ("Team Strength Index", report.team_strength_index),
        ("Offense Index", report.offense_index),
        ("Offense Wins", report.offense_wins),
        ("Offense Played", report.offense_played),
        ("Offense Player Count", report.offense_player_count),
        ("Defense Index", report.defense_index),
        ("Points For", report.points_for),
        ("Points Against", report.points_against),
        ("Defense Match Count", report.defense_match_count),
        ("Depth Index", report.depth_index),
        ("Roster Count", report.roster_count),
        ("Scoreable Player Count", report.scoreable_player_count),
        ("Depth Player ID", report.depth_player_id),
        ("Current Rank", report.current_rank),
        ("Standings Record", report.standings_record),
        ("Unavailable Reasons", "; ".join(report.unavailable_reasons) or None),
    ):
        summary.append([field, value])
    for row in summary.iter_rows(min_row=2, max_row=summary.max_row, min_col=2, max_col=2):
        for cell in row:
            if isinstance(cell.value, float):
                cell.number_format = "0.00"
    summary.column_dimensions["A"].width = 28
    summary.column_dimensions["B"].width = 30

    players_sheet = workbook.create_sheet(PLAYERS_SHEET)
    _header(players_sheet, PLAYER_COLUMNS)
    sorted_players = sorted(
        report.player_rows,
        key=lambda p: (p.observed_rate is None, -(p.observed_rate or 0), p.player_external_id),
    )
    for p in sorted_players:
        players_sheet.append([
            p.player_id, p.player_external_id, p.player_name, p.skill_level, p.matches_won,
            p.matches_played, p.observed_rate, p.contributes_to_offense, p.scoreable_for_depth,
            p.depth_order, p.player_external_id == report.depth_player_id,
        ])
    for index, width in enumerate((10, 18, 22, 10, 12, 14, 14, 20, 18, 12, 16), start=1):
        players_sheet.column_dimensions[get_column_letter(index)].width = width
    last_column = get_column_letter(len(PLAYER_COLUMNS))
    players_sheet.auto_filter.ref = f"A1:{last_column}{max(players_sheet.max_row, 1)}"

    matches_sheet = workbook.create_sheet(MATCHES_SHEET)
    _header(matches_sheet, MATCH_COLUMNS)
    for m in report.match_rows:
        matches_sheet.append([
            m.match_id, m.match_date, m.week, m.format, m.session_name, m.opponent_team_id,
            m.opponent_team_name, "Home" if m.is_home else "Away", m.points_for, m.points_against,
        ])
    for index, width in enumerate((14, 16, 8, 16, 16, 18, 22, 12, 12, 16), start=1):
        matches_sheet.column_dimensions[get_column_letter(index)].width = width
    last_column = get_column_letter(len(MATCH_COLUMNS))
    matches_sheet.auto_filter.ref = f"A1:{last_column}{max(matches_sheet.max_row, 1)}"

    return workbook


def write_workbook(report: TeamStrengthReport, path: str | Path) -> Path:
    workbook = build_workbook(report)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path
