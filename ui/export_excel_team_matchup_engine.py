"""Team Matchup Engine (Coach Mode) Excel: multi-sheet workbook over
already-built ``analytics.team_matchup_engine.TeamMatchupReport`` objects,
one workbook per real (opponent, format, session) scope collection. A
REPORTER -- no computation happens here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from analytics.team_matchup_engine import TeamMatchupReport

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F3864")


def _scope_label(report: TeamMatchupReport) -> str:
    label = f"{report.opponent_team_name} {report.format}"
    return label or "Scope"


def _unique_title(desired: str, used_titles: set[str]) -> str:
    """A real Excel sheet title, truncated to the real 31-character limit
    and disambiguated against every title already used in this workbook --
    computed once, up front, so openpyxl never has to silently rename a
    colliding title itself (which pushed a truncated name back OVER 31
    characters by appending its own suffix)."""
    base = (desired or "Scope")[:31]
    if base not in used_titles:
        used_titles.add(base)
        return base
    suffix = 2
    while True:
        candidate = f"{base[:31 - len(str(suffix)) - 1]}~{suffix}"
        if candidate not in used_titles:
            used_titles.add(candidate)
            return candidate
        suffix += 1


def _add_sheet(workbook: Workbook, title: str, columns: list[str], rows: list[list]) -> None:
    sheet = workbook.create_sheet(title)
    sheet.append(columns)
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        sheet.append(row)
    sheet.freeze_panes = "A2"
    last_column = get_column_letter(len(columns))
    sheet.auto_filter.ref = f"A1:{last_column}{max(sheet.max_row, 1)}"
    for index, name in enumerate(columns, start=1):
        width = max(len(str(name)) + 4, 12)
        for row in rows[:200]:
            width = max(width, min(len(str(row[index - 1])) + 2, 60))
        sheet.column_dimensions[get_column_letter(index)].width = width


def write_workbook(reports: Sequence[TeamMatchupReport], path: Path) -> Path:
    """One sheet per real scope: roster comparison, opponent ranking, and
    the approved lineup, side by side for one real matchup."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    used_titles: set[str] = set()
    # Longest real suffix below is " Lineup" (7 chars); reserving that much
    # of the 31-char Excel sheet-title limit for every scope's prefix keeps
    # "Rank"/"Lineup" themselves always intact -- truncating a whole
    # candidate string from the right (the previous approach) could instead
    # chop the suffix itself down to an unrecognizable "Lin".
    prefix_budget = 31 - len(" Lineup")

    for report in reports:
        scope_prefix = _scope_label(report)[:prefix_budget]
        roster_title = _unique_title(scope_prefix, used_titles)
        rank_title = _unique_title(f"{scope_prefix} Rank", used_titles)
        lineup_title = _unique_title(f"{scope_prefix} Lineup", used_titles)

        rows: list[list] = []
        max_roster = max(len(report.our_roster), len(report.opponent_roster))
        for i in range(max_roster):
            our = report.our_roster[i] if i < len(report.our_roster) else None
            opp = report.opponent_roster[i] if i < len(report.opponent_roster) else None
            rows.append([
                our.player_name if our else "", our.skill_level if our else None,
                our.trend.trend if our else "",
                opp.player_name if opp else "", opp.skill_level if opp else None,
                opp.trend.trend if opp else "",
            ])
        _add_sheet(
            workbook, roster_title,
            ["Our Player", "Our SL", "Our Trend", "Opponent", "Opp SL", "Opp Trend"],
            rows,
        )

        ranking_rows = [
            [
                o.opponent_name, o.opponent_skill_level, o.direct_win_rate,
                o.direct_sample_size, o.reliability_weighted_skill_probability,
            ]
            for o in report.ranked_opponents
        ]
        _add_sheet(
            workbook, rank_title,
            ["Opponent", "SL", "Direct Win Rate", "Direct Sample", "Skill-Only Estimate"],
            ranking_rows,
        )

        lineup_rows = []
        if report.lineup_result is not None:
            for index, slot in enumerate(report.lineup_result.assignments):
                lineup_rows.append([
                    index + 1, slot.player_name, slot.opponent_name,
                    slot.evidence_label.value, slot.lineup_score,
                ])
        _add_sheet(
            workbook, lineup_title,
            ["Board", "Our Player", "Opponent", "Evidence", "Lineup Score"],
            lineup_rows,
        )

    if not workbook.worksheets:
        workbook.create_sheet("Team Matchup Engine")

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path
