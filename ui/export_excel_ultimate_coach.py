"""Ultimate Coach Excel companion: a standalone workbook built from the same
verified cockpit payload (analytics.ultimate_coach_cockpit_identity_bridge)
as the standalone HTML, so the two cannot silently disagree about who is a
verified player, which games count as evidence, or what the schedule says.

Sheets (user-facing first):
    Match Day          Date -> who you are (APA record ID) -> your team ->
                       optional format -> every real fixture that day ->
                       a printable side-by-side roster matchup, plus your
                       team's season schedule. Formula-driven, but every
                       formula is a plain INDEX/MATCH/COUNTIF against a
                       pre-built key column (see "Excel constraints").
    Print Matchup      The focused one-page printable matchup for the fixture
                       chosen on Match Day: clearly labeled OUR TEAM and
                       OPPONENT rosters (name + APA record ID), with every
                       missing-data disclosure.
    Match Night        Any two teams side by side (roster lists + totals).
    Coach Dashboard    Two player dropdowns + a format dropdown; pulls the
                       real direct-evidence record for that exact pair, or
                       discloses "no recorded direct meeting" -- never a
                       fabricated 0-0.
    Schedule           One row per (current team scope, fixture) -- every
                       value pre-rendered for display ("No data", "Bye -- no
                       opponent", scores as text), AutoFilter-ready.
    Schedule Keys      Static lookup keys driving Match Day's fixture list.
    Team Rosters       One row per (team scope, player) current membership.
    Teams              One row per current team scope.
    Player Teams       Each verified player's current team scopes, keyed for
                       Match Day's "your teams" list.
    Players            One row per verified player.
    Player vs Player   One row per (player, opponent, format) with at least
                       one recorded meeting.
    Lists              Dropdown sources.
    Data Trust / Build Info   Static provenance.

Identity: player names collide in the real data (184 duplicate names among
15,180 verified players). Every player label is "Name (APA record ID n)",
unique per verified identity. The APA record ID is APA's member record
number (GraphQL member.id) -- NOT the league card number printed on a member
card, which is per-league and not in this data. A configured card number is
shown only as display provenance, never used as identity.

Excel constraints (confirmed earlier against the actual target install):
no dynamic-array functions (FILTER fails as #NAME?), no array/CSE formulas,
no macros, no volatile functions (NOW/TODAY/RAND/OFFSET/INDIRECT). A blank
cell reached through INDEX evaluates to 0 in Excel, so every column Match
Day reads through INDEX is written fully populated with display text --
never left blank -- while genuine numeric scores (including real zeros) stay
numeric in their own Schedule columns.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from analytics.ultimate_coach_excel_payload import (
    build_player_vs_player_pairs,
    build_team_rosters,
    build_teams_summary,
)
from analytics.ultimate_coach_match_day import (
    DEFAULT_MATCH_DAY_TIMEZONE,
    EIGHT_NINE_CATEGORIES,
    FORMAT_FILTER_ALL_LABEL,
    FORMAT_FILTER_EIGHT_NINE_LABEL,
    build_match_day_section,
    excel_date_serial,
    viewer_player,
)

# ---- Pool-room palette, shared with the HTML cockpit ----
FELT = "14532D"
FELT_DEEP = "0C3A1F"
FELT_SOFT = "E7F1EA"
BRASS = "B8862B"
BRASS_SOFT = "F6ECD6"
INPUT_YELLOW = "FFF4CC"
MUTED = "5B6A61"
WARN_SOFT = "FFF6DF"

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor=FELT)
TITLE_FONT = Font(bold=True, size=18, color=FELT_DEEP)
SUBTITLE_FONT = Font(italic=True, size=11, color=MUTED)
SECTION_FONT = Font(bold=True, size=12, color="FFFFFF")
SECTION_FILL = PatternFill("solid", fgColor=FELT)
SUBHEAD_FILL = PatternFill("solid", fgColor=FELT_SOFT)
SUBHEAD_FONT = Font(bold=True, color=FELT_DEEP)
LABEL_FONT = Font(bold=True)
MUTED_FONT = Font(italic=True, color="666666")
HELPER_FONT = Font(color="8A8A8A", size=9)
LINK_FONT = Font(color="1F5C99", underline="single", bold=True)
INPUT_FILL = PatternFill("solid", fgColor=INPUT_YELLOW)
NOTE_FILL = PatternFill("solid", fgColor=WARN_SOFT)
_BRASS_SIDE = Side(style="medium", color=BRASS)
INPUT_BORDER = Border(left=_BRASS_SIDE, right=_BRASS_SIDE, top=_BRASS_SIDE, bottom=_BRASS_SIDE)
_THIN = Side(style="thin", color="D9D2C3")
CELL_BORDER = Border(bottom=_THIN)
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
TABLE_STYLE = "TableStyleMedium7"  # green, matches the felt palette

NAV_SHEETS = ["Match Day", "Print Matchup", "Match Night", "Coach Dashboard", "Schedule", "Team Rosters", "Players",
              "Data Trust", "Build Info"]
SHEET_ORDER = ["Match Day", "Print Matchup", "Match Night", "Coach Dashboard", "Schedule", "Team Rosters", "Teams",
               "Players", "Player vs Player", "Player Teams", "Schedule Keys", "Lists", "Data Trust", "Build Info"]
RAIL = "5A3A1F"
OPPONENT_FILL = PatternFill("solid", fgColor=RAIL)

NO_DATA = "No data"
BYE_TEXT = "Bye — no opponent"
NONE_TOKEN = "—"


def _player_label(name: str, external_id: Any) -> str:
    return f"{name} (APA record ID {external_id})"


# EIGHT/NINE are always offered even with zero matching evidence -- they are
# the two primary APA team formats. Any other raw format recorded in the
# source data (e.g. "MASTERS", "MASTERS ALT" -- both are real APA formats,
# see scraper.graphql_scraper._VALID_FORMATS) is appended rather than
# dropped, so a real recorded meeting can never be unreachable from the
# dashboard's Format dropdown just because it happened outside 8-Ball/9-Ball.
BASE_FORMAT_ORDER = ["EIGHT", "NINE"]
FORMAT_LABELS = {"EIGHT": "8-Ball", "NINE": "9-Ball", "MASTERS": "Masters", "MASTERS ALT": "Masters Alt"}


def _format_label(fmt: str) -> str:
    return FORMAT_LABELS.get(fmt, fmt)


def _dashboard_format_options(pairs: list[dict[str, Any]]) -> list[str]:
    present = {row["format"] for row in pairs if row.get("format")}
    extra = sorted(present - set(BASE_FORMAT_ORDER))
    return BASE_FORMAT_ORDER + extra


def _format_code_formula(options: list[str], cell: str) -> str:
    expr = '"EIGHT"'
    for fmt in reversed(options):
        if fmt == "EIGHT":
            continue
        expr = f'IF({cell}="{_format_label(fmt)}","{fmt}",{expr})'
    return "=" + expr


# ---- styling helpers ----

def _style_header(sheet: Worksheet, columns: list[str], *, freeze: str = "A2") -> None:
    sheet.append(columns)
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 30
    sheet.freeze_panes = freeze


def _apply_widths(sheet: Worksheet, columns: list[str], widths: dict[str, int]) -> None:
    for index, name in enumerate(columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = widths.get(name, 14)


def _autotable(sheet: Worksheet, name: str, columns: list[str], row_count: int) -> None:
    last_column = get_column_letter(len(columns))
    last_row = max(row_count + 1, 1)
    full_range = f"A1:{last_column}{last_row}"
    if row_count:
        # An Excel Table owns its own <autoFilter> internally -- a
        # worksheet-level auto_filter.ref on top of that produces two
        # conflicting autoFilter declarations for the same range, which real
        # Excel refuses to open at all (confirmed against the actual target
        # Excel install earlier in this PR). Only set the plain autoFilter
        # when there is no table to own it.
        table = Table(displayName=name, ref=full_range)
        table.tableStyleInfo = TableStyleInfo(name=TABLE_STYLE, showRowStripes=True)
        sheet.add_table(table)
    else:
        sheet.auto_filter.ref = full_range


def _title(sheet: Worksheet, title: str, subtitle: str, *, last_col: str) -> None:
    sheet.sheet_view.showGridLines = False
    sheet["A1"] = title
    sheet["A1"].font = TITLE_FONT
    sheet.row_dimensions[1].height = 30
    sheet["A2"] = subtitle
    sheet["A2"].font = SUBTITLE_FONT
    sheet["A2"].alignment = WRAP_TOP
    sheet.merge_cells(f"A2:{last_col}2")
    sheet.row_dimensions[2].height = 32
    _nav_row(sheet, 3, current=sheet.title)


def _nav_row(sheet: Worksheet, row: int, *, current: str) -> None:
    col = 1
    sheet.cell(row=row, column=col, value="Go to:").font = MUTED_FONT
    for name in NAV_SHEETS:
        if name == current:
            continue
        col += 1
        cell = sheet.cell(row=row, column=col, value=name)
        cell.hyperlink = Hyperlink(ref=cell.coordinate, location=f"'{name}'!A1", display=name)
        cell.font = LINK_FONT


def _section(sheet: Worksheet, row: int, text: str, *, last_col: int) -> None:
    for col in range(1, last_col + 1):
        sheet.cell(row=row, column=col).fill = SECTION_FILL
    cell = sheet.cell(row=row, column=1, value=text)
    cell.font = SECTION_FONT
    cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[row].height = 22


def _subheader(sheet: Worksheet, row: int, labels: list[tuple[int, str]]) -> None:
    for col, text in labels:
        cell = sheet.cell(row=row, column=col, value=text)
        cell.font = SUBHEAD_FONT
        cell.fill = SUBHEAD_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _input(cell, value: Any = "") -> None:
    cell.value = value
    cell.fill = INPUT_FILL
    cell.border = INPUT_BORDER
    cell.font = Font(bold=True, size=12)
    cell.alignment = Alignment(vertical="center")


def _note(sheet: Worksheet, cell_ref: str, text: str, *, merge_to: str | None = None, height: float | None = None,
          font: Font = MUTED_FONT) -> None:
    sheet[cell_ref] = text
    sheet[cell_ref].font = font
    sheet[cell_ref].alignment = WRAP_TOP
    if merge_to:
        sheet.merge_cells(f"{cell_ref}:{merge_to}")
    if height:
        sheet.row_dimensions[sheet[cell_ref].row].height = height


def _add_dropdown(sheet: Worksheet, cell: str, source_ref: str, *, title: str, message: str,
                  allow_blank: bool = True) -> None:
    validation = DataValidation(type="list", formula1=source_ref, allow_blank=allow_blank)
    validation.errorTitle = title
    validation.error = message
    validation.promptTitle = title
    validation.prompt = message
    sheet.add_data_validation(validation)
    validation.add(cell)


# ---- static reference sheets ----

def _build_info_sheet(wb: Workbook, payload: dict[str, Any], *, built_at: str, source_db: str,
                      match_day: dict[str, Any]) -> None:
    sheet = wb.active
    sheet.title = "Build Info"
    sheet.column_dimensions["A"].width = 40
    sheet.column_dimensions["B"].width = 80

    trust = payload.get("trust") or {}
    counts = payload.get("counts") or {}
    coverage = match_day.get("coverage") or {}
    rows = [
        ("Built", built_at or "unknown"),
        ("Source database", source_db),
        ("Schema", payload.get("schema", "")),
        ("Probability publication", payload.get("probability_publication")),
        ("Matchup probability", payload.get("matchup_probability")),
        ("Predictive confidence", payload.get("predictive_confidence")),
        ("Requires live APA login", payload.get("requires_live_apa_login")),
        ("Database mutated during build", payload.get("database_mutated")),
        ("Name matching used for identity", payload.get("name_matching_used")),
        ("Verified players", counts.get("players")),
        ("Head-to-head evidence rows", counts.get("head_to_head_rows")),
        ("Total recorded games (all_games)", counts.get("all_games")),
        ("Identity-verified games usable as evidence", trust.get("identity_verified_game_count")),
        ("Games quarantined (not used as evidence)", trust.get("quarantined_game_count")),
        ("Match Day display timezone", match_day.get("display_timezone")),
        ("Stored fixtures", coverage.get("stored_fixture_count")),
        ("Fixtures included for Match Day", coverage.get("embedded_fixture_count")),
        ("Fixtures excluded (no current roster on either side)", coverage.get("excluded_fixture_count")),
    ]
    sheet.append(["Field", "Value"])
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    for label, value in rows:
        sheet.append([label, value])
    for row in sheet.iter_rows(min_row=2, max_col=1):
        row[0].font = LABEL_FONT
    sheet.freeze_panes = "A2"
    sheet.append([])
    sheet.append(
        [
            "This workbook and the standalone HTML both derive from the same "
            "build_verified_cockpit_payload() output, so they cannot silently "
            "disagree about who is a verified player or which games count as "
            "evidence. No matchup probability is shown anywhere in this "
            "workbook until a separately back-tested calibration gate passes."
        ]
    )
    sheet.cell(row=sheet.max_row, column=1).font = MUTED_FONT
    sheet.cell(row=sheet.max_row, column=1).alignment = WRAP_TOP
    sheet.merge_cells(start_row=sheet.max_row, start_column=1, end_row=sheet.max_row, end_column=2)
    sheet.row_dimensions[sheet.max_row].height = 48
    _nav_row(sheet, sheet.max_row + 2, current="Build Info")


def _data_trust_sheet(wb: Workbook, payload: dict[str, Any]) -> None:
    sheet = wb.create_sheet("Data Trust")
    sheet.column_dimensions["A"].width = 46
    sheet.column_dimensions["B"].width = 16
    sheet.column_dimensions["C"].width = 60
    trust = payload.get("trust") or {}
    sheet.append(["Metric", "Count"])
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    sheet.freeze_panes = "A2"
    labels = [
        ("verified_identity_count", "Verified selectable identities"),
        ("identity_exclusion_count", "Identities excluded (unresolved/ambiguous)"),
        ("identity_verified_game_count", "Identity-verified games usable as evidence"),
        ("quarantined_game_count", "Games quarantined (not used as evidence)"),
        ("suspect_participant_count", "Suspect participant rows"),
        ("indeterminate_participant_count", "Indeterminate participant rows"),
        ("source_coverage_issue_count", "Source coverage issues (contract-level)"),
        ("total_all_games_rows", "Total recorded games (all_games)"),
    ]
    for key, label in labels:
        sheet.append([label, trust.get(key)])
    sheet.append([])
    sheet.append(
        [
            "Only players with roster-backed, uniquely-verified identity provenance "
            "are listed on the Players sheet. Only games that are both mirror-verified "
            "and identity-verified feed the Player vs Player sheet. Quarantined or "
            "unresolved evidence is counted above, never silently dropped or blended in."
        ]
    )
    row = sheet.max_row
    sheet.cell(row=row, column=1).font = MUTED_FONT
    sheet.cell(row=row, column=1).alignment = WRAP_TOP
    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    sheet.row_dimensions[row].height = 48
    _nav_row(sheet, row + 2, current="Data Trust")


PLAYERS_COLUMNS = [
    "Player Label", "Player ID", "External ID", "Player Name",
    "Current SL", "Current Matches Won", "Current Matches Played",
]
PLAYERS_WIDTHS = {
    "Player Label": 40, "Player ID": 10, "External ID": 14, "Player Name": 24,
    "Current SL": 11, "Current Matches Won": 16, "Current Matches Played": 18,
}


def _players_sheet(wb: Workbook, payload: dict[str, Any]) -> None:
    sheet = wb.create_sheet("Players")
    _style_header(sheet, PLAYERS_COLUMNS)
    players = sorted(payload.get("players") or [], key=lambda p: (p["name"], str(p["external_id"])))
    for p in players:
        sheet.append(
            [
                _player_label(p["name"], p["external_id"]),
                # External ID is APA's record ID -- written as text so a typed
                # ID on Match Day matches it exactly (never as a float).
                p["id"], str(p["external_id"]), p["name"],
                p.get("current_skill_level"), p.get("current_matches_won"), p.get("current_matches_played"),
            ]
        )
    _apply_widths(sheet, PLAYERS_COLUMNS, PLAYERS_WIDTHS)
    _autotable(sheet, "Players_Table", PLAYERS_COLUMNS, len(players))


def _sl_display(row: dict[str, Any]) -> str:
    if row.get("skill_level") is None:
        return NO_DATA
    return f"{row['skill_level']}" + ("" if row.get("skill_level_is_live") else "*")


def _record_display(won: Any, played: Any) -> str:
    if won is None or played is None:
        return NO_DATA
    return f"{won}-{max(0, played - won)}"


TEAM_ROSTERS_COLUMNS = [
    "Team", "Division ID", "Session", "Player Label", "Player Name",
    "Skill Level", "Skill Level Is Live", "Matches Won", "Matches Played",
    # Appended (never inserted earlier) so positional column indices stay
    # stable. Display columns are always populated (never blank) because
    # Match Day/Match Night read them through INDEX.
    "APA Record ID", "Team Scope Key", "Roster Slot Key", "SL Display", "W-L Display",
]
TEAM_ROSTERS_WIDTHS = {
    "Team": 34, "Division ID": 12, "Session": 14, "Player Label": 40, "Player Name": 24,
    "Skill Level": 11, "Skill Level Is Live": 14, "Matches Won": 12, "Matches Played": 14,
    "APA Record ID": 14, "Team Scope Key": 30, "Roster Slot Key": 32, "SL Display": 11, "W-L Display": 12,
}


def _ordered_roster(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (r["skill_level"] is None, -(r["skill_level"] or 0), r["player_name"]))


def _team_rosters_sheet(wb: Workbook, payload: dict[str, Any], rosters: list[dict[str, Any]]) -> int:
    players_by_id = {p["id"]: p for p in payload.get("players") or []}
    by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rosters:
        by_scope[row["team_scope_key"]].append(row)
    slot_by_identity: dict[tuple[str, Any], int] = {}
    for scope, rows in by_scope.items():
        for k, row in enumerate(_ordered_roster(rows), start=1):
            slot_by_identity[(scope, row["player_id"])] = k
    sheet = wb.create_sheet("Team Rosters")
    _style_header(sheet, TEAM_ROSTERS_COLUMNS)
    for row in rosters:
        external_id = players_by_id.get(row["player_id"], {}).get("external_id")
        scope = row["team_scope_key"]
        sheet.append(
            [
                row["team_label"], row["division_id"], row["session_name"],
                _player_label(row["player_name"], external_id), row["player_name"],
                row["skill_level"], row["skill_level_is_live"],
                row["matches_won"], row["matches_played"],
                str(external_id or NO_DATA), scope, f"{scope}|{slot_by_identity[(scope, row['player_id'])]}",
                _sl_display(row), _record_display(row["matches_won"], row["matches_played"]),
            ]
        )
    _apply_widths(sheet, TEAM_ROSTERS_COLUMNS, TEAM_ROSTERS_WIDTHS)
    _autotable(sheet, "TeamRosters_Table", TEAM_ROSTERS_COLUMNS, len(rosters))
    return max((len(rows) for rows in by_scope.values()), default=0)


TEAMS_COLUMNS = [
    "Team", "Division ID", "Session", "Roster Count", "Known-Skill Players", "Skill Total (known only)",
    # Appended at the end (never inserted earlier) so existing positional
    # column indices elsewhere stay correct.
    "Team External ID", "Combo Key", "Scope Key", "Summary",
]
TEAMS_WIDTHS = {
    "Team": 34, "Division ID": 12, "Session": 14, "Roster Count": 12, "Known-Skill Players": 15,
    "Skill Total (known only)": 18, "Team External ID": 16, "Combo Key": 24, "Scope Key": 30, "Summary": 44,
}


def _team_summary_text(t: dict[str, Any]) -> str:
    if t["known_skill_count"] == t["roster_count"]:
        return f"{t['roster_count']} rostered · full-roster SL total {t['skill_total']}"
    return (f"{t['roster_count']} rostered · SL total {t['skill_total']} from {t['known_skill_count']} "
            f"players with a captured SL (missing excluded, not counted as 0)")


def _teams_sheet(wb: Workbook, rosters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    teams = build_teams_summary(rosters)
    labels = [t["team_label"] for t in teams]
    if len(labels) != len(set(labels)):
        # build_team_rosters() disambiguates same-named scopes by division;
        # a label that still collides would let a dropdown silently resolve
        # to the wrong roster scope. Refuse rather than guess.
        raise ValueError("Ultimate Coach team labels are not unique per roster scope")
    sheet = wb.create_sheet("Teams")
    _style_header(sheet, TEAMS_COLUMNS)
    for t in teams:
        sheet.append(
            [
                t["team_label"], t["division_id"], t["session_name"],
                t["roster_count"], t["known_skill_count"], t["skill_total"],
                t["team_external_id"], f"{t['team_external_id']}|{t['session_name']}",
                t["team_scope_key"], _team_summary_text(t),
            ]
        )
    _apply_widths(sheet, TEAMS_COLUMNS, TEAMS_WIDTHS)
    _autotable(sheet, "Teams_Table", TEAMS_COLUMNS, len(teams))
    sheet.append([])
    note_row = sheet.max_row + 1
    sheet.cell(row=note_row, column=1, value=(
        "Skill totals are informational only, not a 5-player lineup total: this data "
        "source does not capture your division's actual modified skill cap. The "
        "commonly used APA default is 23 for a 5-player team -- verify against your "
        "own division rules. Players with no captured skill level are excluded from "
        "the total, never counted as 0."
    )).font = MUTED_FONT
    return teams


PVP_COLUMNS = ["Player Label", "Format", "Opponent Label", "Wins", "Losses", "Games", "Win Rate", "Pair Key"]
PVP_WIDTHS = {"Player Label": 40, "Format": 10, "Opponent Label": 40, "Wins": 8, "Losses": 8, "Games": 8, "Win Rate": 10, "Pair Key": 20}


def _player_vs_player_sheet(wb: Workbook, payload: dict[str, Any]) -> list[dict[str, Any]]:
    pairs = build_player_vs_player_pairs(payload)
    players_by_id = {p["id"]: p for p in payload.get("players") or []}
    sheet = wb.create_sheet("Player vs Player")
    _style_header(sheet, PVP_COLUMNS)
    for row in pairs:
        player = players_by_id.get(row["player_id"], {})
        opponent = players_by_id.get(row["opponent_id"], {})
        sheet.append(
            [
                _player_label(row["player_name"], player.get("external_id")),
                _format_label(row["format"]),
                _player_label(row["opponent_name"], opponent.get("external_id")),
                row["wins"], row["losses"], row["games"], row["win_rate"],
                row["pair_key"],
            ]
        )
    _apply_widths(sheet, PVP_COLUMNS, PVP_WIDTHS)
    _autotable(sheet, "PlayerVsPlayer_Table", PVP_COLUMNS, len(pairs))
    return pairs


# ---- Match Day data sheets ----

PLAYER_TEAMS_COLUMNS = ["Viewer Slot Key", "APA Record ID", "Player Name", "Slot", "Team", "Team Scope Key", "Session", "Division ID"]
PLAYER_TEAMS_WIDTHS = {"Viewer Slot Key": 16, "APA Record ID": 14, "Player Name": 24, "Slot": 6, "Team": 36,
                       "Team Scope Key": 30, "Session": 14, "Division ID": 12}


def _player_teams_sheet(wb: Workbook, payload: dict[str, Any], teams: list[dict[str, Any]]) -> int:
    """Each verified player's CURRENT team scopes, numbered 1..n, so Match
    Day can list "your teams" for whatever APA record ID is typed in --
    identity-backed (record ID), never matched by name."""
    label_by_scope = {t["team_scope_key"]: t["team_label"] for t in teams}
    team_by_scope = {t["team_scope_key"]: t for t in teams}
    rows = []
    max_slots = 0
    for player in sorted(payload.get("players") or [], key=lambda p: str(p["external_id"])):
        scopes = []
        seen = set()
        for hist in player.get("team_history") or []:
            if not hist.get("is_current") or not hist.get("team_name"):
                continue
            key = "|".join([
                str(hist.get("team_external_id") or hist.get("team_name") or ""),
                str(hist.get("division_id") or ""), str(hist.get("session_name") or ""),
            ])
            if key in seen or key not in label_by_scope:
                continue
            seen.add(key)
            scopes.append(key)
        scopes.sort(key=lambda k: label_by_scope[k])
        max_slots = max(max_slots, len(scopes))
        for slot, key in enumerate(scopes, start=1):
            team = team_by_scope[key]
            rows.append([
                f"{player['external_id']}|{slot}", str(player["external_id"]), player["name"], slot,
                label_by_scope[key], key, team["session_name"] or NO_DATA, team["division_id"] or NO_DATA,
            ])
    sheet = wb.create_sheet("Player Teams")
    _style_header(sheet, PLAYER_TEAMS_COLUMNS)
    for row in rows:
        sheet.append(row)
    _apply_widths(sheet, PLAYER_TEAMS_COLUMNS, PLAYER_TEAMS_WIDTHS)
    _autotable(sheet, "PlayerTeams_Table", PLAYER_TEAMS_COLUMNS, len(rows))
    return max_slots


SCHEDULE_COLUMNS = [
    "Team", "Team Scope Key", "Local Date", "Date Display", "Kickoff", "Time Zone", "Home/Away",
    "Opponent", "Format", "Format Category", "Session", "Venue", "Status", "Score (home–away)",
    "Home Score", "Away Score", "Opponent Roster", "Opponent Team", "Opponent Scope Key",
    "Source Timestamp", "Match ID", "Date Status",
]
SCHEDULE_WIDTHS = {
    "Team": 34, "Team Scope Key": 26, "Local Date": 12, "Date Display": 17, "Kickoff": 14, "Time Zone": 26,
    "Home/Away": 10, "Opponent": 28, "Format": 20, "Format Category": 11, "Session": 13, "Venue": 16,
    "Status": 13, "Score (home–away)": 13, "Home Score": 10, "Away Score": 10, "Opponent Roster": 34,
    "Opponent Team": 34, "Opponent Scope Key": 26, "Source Timestamp": 26, "Match ID": 11, "Date Status": 12,
}
SCHEDULE_KEYS_COLUMNS = ["Slot Key", "Group Key", "Schedule Row"]


def _opponent_roster_text(opponent: dict[str, Any]) -> str:
    status = opponent.get("status")
    if status == "resolved":
        return "Current roster captured"
    if status == "bye":
        return "Not applicable (bye)"
    if status == "ambiguous":
        return f"Ambiguous: {len(opponent.get('candidate_scope_keys') or [])} roster scopes match — compare manually"
    if status == "missing":
        return "No opponent recorded"
    return "No current roster captured"


def _score_text(fixture: dict[str, Any]) -> str:
    home, away = fixture.get("home_score"), fixture.get("away_score")
    if fixture.get("is_scored") and home is not None and away is not None:
        return f"{home} – {away}"
    return "Not recorded"


def _filter_codes(fixture: dict[str, Any]) -> list[str]:
    codes = []
    if fixture.get("format") in EIGHT_NINE_CATEGORIES:
        codes.append("89")
    codes.append("ALL")
    raw = str(fixture.get("format_raw") or "")
    if raw:
        codes.append(f"F:{raw}")
    return codes


def _schedule_sheets(wb: Workbook, match_day: dict[str, Any], teams: list[dict[str, Any]]) -> dict[str, int]:
    """Schedule (display rows) + Schedule Keys (static lookup keys).

    Group keys: "<scope>|<excel date serial>|<filter code>" for one date and
    "<scope>|ALL|<filter code>" for the season list; slot keys append
    "|1".."|n" in kickoff order. Filter codes: "89" (every 8-Ball/9-Ball
    variant), "ALL", and "F:<raw recorded format>"."""
    label_by_scope = {t["team_scope_key"]: t["team_label"] for t in teams}
    fixtures = match_day.get("fixtures") or []
    tz_name = match_day.get("display_timezone") or DEFAULT_MATCH_DAY_TIMEZONE
    schedule_rows: list[list[Any]] = []
    key_rows: list[list[Any]] = []
    group_counts: dict[str, int] = defaultdict(int)
    max_per_date = 0
    max_per_season = 0
    for scope_key in sorted(match_day.get("schedule") or {}, key=lambda k: label_by_scope.get(k, k)):
        if scope_key not in label_by_scope:
            continue
        for side in match_day["schedule"][scope_key]:
            f = fixtures[side["fixture_index"]]
            opponent = side["opponent"]
            ok = f.get("date_status") == "ok"
            schedule_rows.append([
                label_by_scope[scope_key], scope_key,
                date.fromisoformat(f["local_date"]) if ok else NO_DATA,
                f"{f['local_display'].split(' · ')[0]}" if ok else (
                    "Unparseable: " + str(f.get("match_date")) if f.get("date_status") == "unparseable" else NO_DATA),
                f"{f['local_time']} {f['local_tz_abbrev']}" if ok else NO_DATA,
                f"{tz_name} (UTC{f['local_utc_offset']})" if ok else tz_name,
                "Home" if side["side"] == "home" else "Away",
                BYE_TEXT if opponent["status"] == "bye" else (opponent.get("team_name") or NO_DATA),
                f.get("format_display") or f.get("format_raw") or _format_label(f.get("format") or "") or NO_DATA,
                f.get("format") or NO_DATA,
                f.get("session_name") or NO_DATA,
                (str(f.get("location")).strip() or NO_DATA) if f.get("location") else NO_DATA,
                f.get("status") or NO_DATA,
                _score_text(f),
                f.get("home_score"), f.get("away_score"),
                _opponent_roster_text(opponent),
                label_by_scope.get(opponent.get("scope_key") or "", NONE_TOKEN),
                opponent.get("scope_key") if opponent.get("scope_key") in label_by_scope else NONE_TOKEN,
                f.get("match_date") or NO_DATA,
                str(f.get("match_external_id") or NO_DATA),
                f.get("date_status"),
            ])
            row_number = len(schedule_rows)
            serial = excel_date_serial(f.get("local_date")) if ok else None
            for code in _filter_codes(f):
                groups = [f"{scope_key}|ALL|{code}"]
                if serial is not None:
                    groups.append(f"{scope_key}|{serial}|{code}")
                for group in groups:
                    group_counts[group] += 1
                    key_rows.append([f"{group}|{group_counts[group]}", group, row_number])
                    if "|ALL|" in group:
                        max_per_season = max(max_per_season, group_counts[group])
                    else:
                        max_per_date = max(max_per_date, group_counts[group])

    sheet = wb.create_sheet("Schedule")
    _style_header(sheet, SCHEDULE_COLUMNS, freeze="B2")
    for row in schedule_rows:
        sheet.append(row)
    for r in range(2, len(schedule_rows) + 2):
        sheet.cell(row=r, column=3).number_format = "yyyy-mm-dd"
    _apply_widths(sheet, SCHEDULE_COLUMNS, SCHEDULE_WIDTHS)
    _autotable(sheet, "Schedule_Table", SCHEDULE_COLUMNS, len(schedule_rows))

    keys = wb.create_sheet("Schedule Keys")
    _style_header(keys, SCHEDULE_KEYS_COLUMNS)
    for row in key_rows:
        keys.append(row)
    _apply_widths(keys, SCHEDULE_KEYS_COLUMNS, {"Slot Key": 52, "Group Key": 48, "Schedule Row": 13})
    _autotable(keys, "ScheduleKeys_Table", SCHEDULE_KEYS_COLUMNS, len(key_rows))
    return {"max_per_date": max_per_date, "max_per_season": max_per_season, "rows": len(schedule_rows)}


def _lists_sheet(wb: Workbook, format_filter_options: list[str], compare_slots: int) -> None:
    sheet = wb.create_sheet("Lists")
    sheet["A1"] = "Match Day format filter"
    sheet["B1"] = "Fixture #"
    for cell in (sheet["A1"], sheet["B1"]):
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    for i, option in enumerate(format_filter_options, start=2):
        sheet.cell(row=i, column=1, value=option)
    for i in range(1, compare_slots + 1):
        sheet.cell(row=i + 1, column=2, value=i)
    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 10
    wb.defined_names["FormatFilterList"] = DefinedName(
        "FormatFilterList", attr_text=f"Lists!$A$2:$A${len(format_filter_options) + 1}"
    )
    wb.defined_names["FixtureNumberList"] = DefinedName(
        "FixtureNumberList", attr_text=f"Lists!$B$2:$B${compare_slots + 1}"
    )


# ---- user-facing sheets ----

def _coach_dashboard_sheet(wb: Workbook, player_count: int, format_options: list[str]) -> None:
    sheet = wb.create_sheet("Coach Dashboard", 0)
    sheet.column_dimensions["A"].width = 34
    sheet.column_dimensions["B"].width = 44
    sheet.column_dimensions["C"].width = 18
    sheet.column_dimensions["D"].width = 18
    sheet.column_dimensions["E"].width = 16
    sheet.column_dimensions["F"].width = 16
    sheet.column_dimensions["G"].width = 16
    sheet.column_dimensions["H"].width = 16
    sheet.column_dimensions["I"].width = 16
    _title(sheet, "Ultimate Coach — Coach Dashboard",
           "Player vs Player, evidence-backed. Pick two players and a format in the yellow cells.", last_col="D")

    sheet["A4"] = "Player A"
    sheet["A5"] = "Player B"
    sheet["A6"] = "Format"
    for ref in ("A4", "A5", "A6"):
        sheet[ref].font = LABEL_FONT
    _input(sheet["B4"])
    _input(sheet["B5"])
    _input(sheet["B6"], _format_label(format_options[0]))

    if player_count:
        _add_dropdown(
            sheet, "B4", "PlayerLabelList",
            title="Unknown player", message="Choose a player already listed on the Players sheet.",
        )
        _add_dropdown(
            sheet, "B5", "PlayerLabelList",
            title="Unknown player", message="Choose a player already listed on the Players sheet.",
        )
    format_labels = [_format_label(fmt) for fmt in format_options]
    _add_dropdown(
        sheet, "B6", '"' + ",".join(format_labels) + '"',
        title="Format", message="Choose " + " / ".join(format_labels) + ".",
    )

    # Helper block: resolve dropdown labels to canonical IDs and build the
    # same pair key the Player vs Player sheet was written with. Kept on the
    # visible sheet (not hidden) so the lookup chain is inspectable.
    sheet["A9"] = "Lookup detail"
    sheet["A9"].font = LABEL_FONT
    sheet["A10"] = "Player A ID"
    sheet["B10"] = '=IFERROR(INDEX(Players_Table[Player ID],MATCH(B4,Players_Table[Player Label],0)),"")'
    sheet["A11"] = "Player B ID"
    sheet["B11"] = '=IFERROR(INDEX(Players_Table[Player ID],MATCH(B5,Players_Table[Player Label],0)),"")'
    sheet["A12"] = "Format code"
    sheet["B12"] = _format_code_formula(format_options, "B6")
    sheet["A13"] = "Pair key"
    sheet["B13"] = '=B10&"|"&B12&"|"&B11'
    sheet["A14"] = "Pair row in Player vs Player"
    sheet["B14"] = '=IFERROR(MATCH(B13,PlayerVsPlayer_Table[Pair Key],0),"")'
    for row in range(10, 15):
        sheet.cell(row=row, column=1).font = HELPER_FONT
        sheet.cell(row=row, column=2).font = HELPER_FONT

    _section(sheet, 16, "Current skill levels", last_col=4)
    sheet["A17"] = "Player A current SL"
    # A blank Current SL cell reached through INDEX evaluates to 0 -- not a
    # valid APA skill level, but easy to misread as a verified SL 0. Test
    # the indexed value against "" first.
    sheet["B17"] = (
        '=IFERROR(IF(INDEX(Players_Table[Current SL],MATCH(B4,Players_Table[Player Label],0))="",'
        '"—",INDEX(Players_Table[Current SL],MATCH(B4,Players_Table[Player Label],0))),"—")'
    )
    sheet["A18"] = "Player B current SL"
    sheet["B18"] = (
        '=IFERROR(IF(INDEX(Players_Table[Current SL],MATCH(B5,Players_Table[Player Label],0))="",'
        '"—",INDEX(Players_Table[Current SL],MATCH(B5,Players_Table[Player Label],0))),"—")'
    )

    _section(sheet, 20, "Direct record (Player A perspective)", last_col=4)
    sheet["A21"] = "Wins"
    sheet["B21"] = '=IF(B14="","0",INDEX(PlayerVsPlayer_Table[Wins],B14))'
    sheet["A22"] = "Losses"
    sheet["B22"] = '=IF(B14="","0",INDEX(PlayerVsPlayer_Table[Losses],B14))'
    sheet["A23"] = "Recorded meetings"
    sheet["B23"] = '=IF(B14="","0",INDEX(PlayerVsPlayer_Table[Games],B14))'
    sheet["A24"] = "Observed win rate"
    sheet["B24"] = '=IF(B14="","No recorded evidence",TEXT(INDEX(PlayerVsPlayer_Table[Win Rate],B14),"0.0%"))'
    sheet["A25"] = "Evidence disclosure"
    sheet["B25"] = (
        '=IF(OR(B4="",B5=""),"Choose Player A and Player B above.",'
        'IF(B14="","No recorded direct meeting between these two players in this format. '
        'Not shown as a 0-0 record -- this is an absence of evidence, not evidence of a tie. '
        'Check the Team Rosters / Player vs Player sheets for shared-opponent context.",'
        '"Direct evidence found -- see Wins/Losses/Recorded meetings above."))'
    )
    sheet["B25"].alignment = WRAP_TOP
    sheet.merge_cells("B25:D25")
    sheet.row_dimensions[25].height = 48
    for row in (17, 18, 21, 22, 23, 24, 25):
        sheet.cell(row=row, column=1).font = LABEL_FONT

    sheet["A28"] = "Probability status"
    sheet["A28"].font = LABEL_FONT
    sheet["B28"] = (
        "NOT CALIBRATED. This dashboard shows real recorded evidence only. No matchup "
        "probability is shown until a separately back-tested calibration gate passes."
    )
    sheet["B28"].font = MUTED_FONT
    sheet["B28"].alignment = WRAP_TOP
    sheet["B28"].fill = NOTE_FILL
    sheet.merge_cells("B28:D28")
    sheet.row_dimensions[28].height = 36
    sheet.freeze_panes = "A4"

    if not player_count:
        sheet["A31"] = "No verified players were available when this workbook was built."
        sheet["A31"].font = MUTED_FONT


def _roster_block(sheet: Worksheet, *, top: int, left: int, scope_ref: str, slots: int, title_formula: str,
                  helper_col: int) -> None:
    """A roster list for the team scope whose key is in `scope_ref`, read
    slot-by-slot through Team Rosters' static Roster Slot Key (plain MATCH,
    no array formula). All values read are pre-rendered text columns."""
    col = get_column_letter
    sheet.cell(row=top, column=left, value=title_formula).font = SUBHEAD_FONT
    sheet.merge_cells(start_row=top, start_column=left, end_row=top, end_column=left + 3)
    _subheader(sheet, top + 1, [(left, "Player"), (left + 1, "APA record ID"), (left + 2, "SL"), (left + 3, "Current W-L")])
    for k in range(1, slots + 1):
        r = top + 1 + k
        key = f'{scope_ref}&"|{k}"'
        row_ref = f"${col(helper_col)}{r}"
        sheet.cell(row=r, column=helper_col,
                   value=f'=IF({scope_ref}="","",IFERROR(MATCH({key},TeamRosters_Table[Roster Slot Key],0),""))').font = HELPER_FONT
        for offset, column_name in enumerate(("Player Name", "APA Record ID", "SL Display", "W-L Display")):
            cell = sheet.cell(row=r, column=left + offset,
                              value=f'=IF({row_ref}="","",INDEX(TeamRosters_Table[{column_name}],{row_ref}))')
            cell.border = CELL_BORDER


def _match_night_sheet(wb: Workbook, team_count: int, roster_slots: int) -> None:
    sheet = wb.create_sheet("Match Night", 1)
    for letter, width in zip("ABCDEFGHIJ", (26, 34, 34, 14, 6, 6, 30, 16, 10, 14)):
        sheet.column_dimensions[letter].width = width
    _title(sheet, "Ultimate Coach — Match Night",
           "Pick our team and the opponent team in the yellow cells for a side-by-side roster comparison.",
           last_col="D")

    sheet["B4"] = "Our Team"
    sheet["C4"] = "Opponent Team"
    for cell in ("B4", "C4"):
        sheet[cell].font = LABEL_FONT
    _input(sheet["B5"])
    _input(sheet["C5"])
    if team_count:
        for cell in ("B5", "C5"):
            _add_dropdown(
                sheet, cell, "TeamNameList",
                title="Unknown team", message="Choose a team already listed on the Teams sheet.",
            )

    sheet["A7"] = "Roster size"
    sheet["B7"] = '=IF(B5="","",COUNTIF(TeamRosters_Table[Team],B5))'
    sheet["C7"] = '=IF(C5="","",COUNTIF(TeamRosters_Table[Team],C5))'
    sheet["A8"] = "Players with known skill level"
    sheet["B8"] = '=IF(B5="","",COUNTIFS(TeamRosters_Table[Team],B5,TeamRosters_Table[Skill Level],"<>"))'
    sheet["C8"] = '=IF(C5="","",COUNTIFS(TeamRosters_Table[Team],C5,TeamRosters_Table[Skill Level],"<>"))'
    sheet["A9"] = "Full-roster skill total (known only)"
    sheet["B9"] = '=IF(B5="","",SUMIF(TeamRosters_Table[Team],B5,TeamRosters_Table[Skill Level]))'
    sheet["C9"] = '=IF(C5="","",SUMIF(TeamRosters_Table[Team],C5,TeamRosters_Table[Skill Level]))'
    for row in (7, 8, 9):
        sheet.cell(row=row, column=1).font = LABEL_FONT

    sheet["A12"] = "Skill totals are informational only, not a 5-player lineup total -- this data source does not capture your division's actual modified skill cap. The commonly used APA default is 23 for a 5-player team; verify against your own division rules."
    sheet["A12"].font = MUTED_FONT
    sheet["A12"].alignment = WRAP_TOP
    sheet.merge_cells("A12:C12")
    sheet.row_dimensions[12].height = 48

    sheet["A15"] = "How to scout this matchup"
    sheet["A15"].font = LABEL_FONT
    sheet["A16"] = (
        "1. Both current rosters are listed below. Rosters are each team's CURRENT captured roster, "
        "not who played on any particular past date.\n"
        "2. For any specific pairing, open Coach Dashboard and pick that Player A / Player B to see their "
        "real direct-evidence record.\n"
        "3. No lineup recommendation here is a solved optimal assignment or a win-probability claim -- "
        "matchup_probability stays unpublished throughout this workbook."
    )
    sheet["A16"].alignment = WRAP_TOP
    sheet.merge_cells("A16:C16")
    sheet.row_dimensions[16].height = 80

    sheet["H5"] = "Our scope key"
    sheet["I5"] = '=IF(B5="","",IFERROR(INDEX(Teams_Table[Scope Key],MATCH(B5,Teams_Table[Team],0)),""))'
    sheet["H6"] = "Opponent scope key"
    sheet["I6"] = '=IF(C5="","",IFERROR(INDEX(Teams_Table[Scope Key],MATCH(C5,Teams_Table[Team],0)),""))'
    for ref in ("H5", "I5", "H6", "I6"):
        sheet[ref].font = HELPER_FONT

    _section(sheet, 19, "Current rosters (highest skill level first)", last_col=4)
    # Two stacked blocks keep each roster readable within columns A-D.
    _roster_block(sheet, top=20, left=1, scope_ref="$I$5", slots=roster_slots, helper_col=8,
                  title_formula='=IF(B5="","Our team: choose a team above","Our team: "&B5)')
    _roster_block(sheet, top=22 + roster_slots + 1, left=1, scope_ref="$I$6", slots=roster_slots, helper_col=8,
                  title_formula='=IF(C5="","Opponent: choose a team above","Opponent: "&C5)')
    sheet.freeze_panes = "A4"

    if not team_count:
        sheet["A18"] = "No current team rosters were available when this workbook was built."
        sheet["A18"].font = MUTED_FONT


def _match_day_sheet(
    wb: Workbook,
    *,
    match_day: dict[str, Any],
    format_filter_options: list[str],
    team_slots: int,
    fixture_slots: int,
    season_slots: int,
    roster_slots: int,
    viewer_member_external_id: str | None,
    viewer_card_number: str | None,
    viewer_resolved: bool,
    viewer_label: str | None = None,
    has_players: bool = True,
) -> dict[str, Any]:
    """Date -> APA record ID -> my team -> format -> every real fixture ->
    printable roster matchup -> season schedule. Every lookup is a plain
    INDEX/MATCH/COUNTIF against a static key column; no dynamic arrays, no
    array formulas, no macros. Returns key row numbers (used by tests)."""
    sheet = wb.create_sheet("Match Day", 0)
    widths = {"A": 24, "B": 30, "C": 16, "D": 18, "E": 30, "F": 13, "G": 14, "H": 13, "I": 15, "J": 32, "K": 26,
              "L": 3, "M": 3, "N": 30, "O": 40, "P": 10, "Q": 10}
    for letter, width in widths.items():
        sheet.column_dimensions[letter].width = width
    tz_name = match_day.get("display_timezone") or DEFAULT_MATCH_DAY_TIMEZONE
    _title(sheet, "Ultimate Coach — Match Day",
           f"1 Date → 2 Who you are → 3 Your team → 4 Format (optional) → every real fixture that day → "
           f"compare rosters. All dates and kickoff times are in {tz_name}.", last_col="K")

    # Helper (lookup detail) column, visible but quiet -- never a black box.
    sheet["N5"] = "Lookup detail (formulas)"
    sheet["N5"].font = LABEL_FONT

    def helper(row: int, label: str, formula: str) -> str:
        sheet.cell(row=row, column=14, value=label).font = HELPER_FONT
        sheet.cell(row=row, column=15, value=formula).font = HELPER_FONT
        return f"$O${row}"

    _section(sheet, 5, "Your selection (yellow cells)", last_col=11)
    inputs = [
        (6, "1 · Date", "Type a date such as 10/11/2026, or pick one from your season schedule further down this sheet."),
        (7, "2 · I am", "Pick your own name from the list — every entry shows that player's APA record ID, so "
                        "same-name players stay distinct — or type just your APA record ID. (The record ID is not the "
                        "league card number printed on your member card.)"),
        (8, "3 · My team", "Choose one of your current teams (the list fills in once your record ID is recognized)."),
        (9, "4 · Format", f"“{FORMAT_FILTER_EIGHT_NINE_LABEL}” (default) includes every 8-Ball and 9-Ball variant; "
                          "other recorded formats are listed too."),
        (10, "5 · Compare fixture #", "Which listed fixture the printable matchup below compares (default 1)."),
    ]
    for row, label, help_text in inputs:
        sheet.cell(row=row, column=1, value=label).font = LABEL_FONT
        _note(sheet, f"C{row}", help_text, merge_to=f"K{row}", height=30)
    _input(sheet["B6"])
    sheet["B6"].number_format = "ddd, mmm d, yyyy"
    date_validation = DataValidation(type="date", operator="greaterThan", formula1="1")
    date_validation.errorTitle = "Date"
    date_validation.error = "Type a calendar date, e.g. 10/11/2026."
    date_validation.promptTitle = "Date"
    date_validation.prompt = "Type a calendar date, e.g. 10/11/2026."
    sheet.add_data_validation(date_validation)
    date_validation.add("B6")
    # Pre-filled with the configured, verified viewer as "Name (APA record ID n)" -- the name is shown next
    # to the ID, but the lookup below still resolves to the record ID (never to the name).
    _input(sheet["B7"], (viewer_label or "") if viewer_resolved else "")
    sheet["B7"].number_format = "@"
    if has_players:
        _add_dropdown(sheet, "B7", "PlayerLabelList", title="I am",
                      message="Pick your name (APA record ID shown), or type just your APA record ID.")
    _input(sheet["B8"])
    _input(sheet["B9"], FORMAT_FILTER_EIGHT_NINE_LABEL)
    _input(sheet["B10"], 1)
    _add_dropdown(sheet, "B9", "FormatFilterList", title="Format",
                  message=f"Choose {FORMAT_FILTER_EIGHT_NINE_LABEL}, {FORMAT_FILTER_ALL_LABEL}, or one recorded format.")
    _add_dropdown(sheet, "B10", "FixtureNumberList", title="Fixture #",
                  message="Choose which listed fixture to compare.")

    serial = helper(6, "Date serial", '=IF(B6="","",IF(ISNUMBER(B6),INT(B6),IFERROR(INT(DATEVALUE(B6)),"bad")))')
    # A picked "Name (APA record ID n)" label resolves to its record ID through the unique Player Label
    # column; anything else typed is treated as a record ID. A bare name never matches a record ID.
    vkey = helper(7, "Record ID key", '=IF(B7="","",IF(ISNUMBER(B7),TEXT(B7,"0"),'
                                      'IFERROR(INDEX(Players_Table[External ID],MATCH(TRIM(B7),Players_Table[Player Label],0)),TRIM(B7))))')
    name_row = helper(8, "Verified player name",
                      f'=IF({vkey}="","",IFERROR(INDEX(Players_Table[Player Name],MATCH({vkey},Players_Table[External ID],0)),""))')
    team_list_top = 18
    team_list_bottom = team_list_top + team_slots - 1
    scope = helper(9, "My team scope key",
                   f'=IF(OR(B8="",COUNTIF($B${team_list_top}:$B${team_list_bottom},B8)=0),"",'
                   f'IFERROR(INDEX(Teams_Table[Scope Key],MATCH(B8,Teams_Table[Team],0)),""))')
    code = helper(10, "Format filter code",
                  f'=IF(OR(B9="",B9="{FORMAT_FILTER_EIGHT_NINE_LABEL}"),"89",IF(B9="{FORMAT_FILTER_ALL_LABEL}","ALL","F:"&B9))')
    group = helper(11, "Date group key",
                   f'=IF(OR({scope}="",{serial}="",{serial}="bad"),"",{scope}&"|"&{serial}&"|"&{code})')
    count = helper(12, "Fixtures found", f'=IF({group}="",0,COUNTIF(ScheduleKeys_Table[Group Key],{group}))')
    compare_n = helper(13, "Compare fixture #", '=IF(ISNUMBER(B10),INT(B10),1)')
    season_group = helper(14, "Season group key", f'=IF({scope}="","",{scope}&"|ALL|"&{code})')
    season_count = helper(15, "Season fixtures", f'=IF({season_group}="",0,COUNTIF(ScheduleKeys_Table[Group Key],{season_group}))')
    team_count = helper(16, "Current team scopes", f'=IF({vkey}="",0,COUNTIF(PlayerTeams_Table[APA Record ID],{vkey}))')

    # ---- who you are ----
    _section(sheet, 12, "Who you are & your current teams", last_col=11)
    sheet["A13"] = "Verified player"
    sheet["B13"] = (
        f'=IF({vkey}="","Enter your APA record ID in step 2.",'
        f'IF({name_row}="","No verified player has APA record ID "&{vkey}&" in this build.",'
        f'{name_row}&" (APA record ID "&{vkey}&")"))'
    )
    sheet["A14"] = "Name check"
    sheet["B14"] = (
        f'=IF({name_row}="","",IF(COUNTIF(Players_Table[Player Name],{name_row})>1,'
        f'COUNTIF(Players_Table[Player Name],{name_row})&" verified players share this name — the record ID decides which one is you.",'
        f'"Unique name among verified players."))'
    )
    sheet["A15"] = "League card number"
    if viewer_resolved and viewer_card_number:
        sheet["B15"] = (
            f'=IF({vkey}="{viewer_member_external_id}","Card #{viewer_card_number} was verified to this record when the build '
            f'was configured (display only; card numbers are per league and never used as identity).","—")'
        )
    else:
        sheet["B15"] = "—"
    sheet["A16"] = "Current team scopes"
    sheet["B16"] = (
        f'=IF({name_row}="","",IF({team_count}=0,"No current team captured for this player.",'
        f'{team_count}&" current team scope"&IF({team_count}=1,"","s")&" (each division listed separately)."))'
    )
    for row in range(13, 17):
        sheet.cell(row=row, column=1).font = LABEL_FONT
        sheet.merge_cells(f"B{row}:K{row}")
        sheet.cell(row=row, column=2).alignment = WRAP_TOP
    _subheader(sheet, 17, [(1, "Slot"), (2, "Your team"), (3, "On chosen date")])
    sheet.merge_cells("C17:E17")
    for k in range(1, team_slots + 1):
        r = team_list_top + k - 1
        sheet.cell(row=r, column=1, value=f'=IF(B{r}="","","Team {k}")')
        sheet.cell(row=r, column=2, value=(
            f'=IF({vkey}="","",IFERROR(INDEX(PlayerTeams_Table[Team],MATCH({vkey}&"|{k}",PlayerTeams_Table[Viewer Slot Key],0)),""))'
        ))
        sheet.cell(row=r, column=14, value=f"Team {k} scope").font = HELPER_FONT
        sheet.cell(row=r, column=15, value=(
            f'=IF({vkey}="","",IFERROR(INDEX(PlayerTeams_Table[Team Scope Key],MATCH({vkey}&"|{k}",PlayerTeams_Table[Viewer Slot Key],0)),""))'
        )).font = HELPER_FONT
        sheet.cell(row=r, column=3, value=(
            f'=IF(OR(B{r}="",{serial}="",{serial}="bad"),"",'
            f'COUNTIF(ScheduleKeys_Table[Group Key],$O{r}&"|"&{serial}&"|"&{code})&" fixture(s) on this date")'
        ))
        sheet.merge_cells(f"C{r}:E{r}")
        for c in (1, 2, 3):
            sheet.cell(row=r, column=c).border = CELL_BORDER
    wb.defined_names["MyTeamSlotList"] = DefinedName(
        "MyTeamSlotList", attr_text=f"'Match Day'!$B${team_list_top}:$B${team_list_bottom}"
    )
    _add_dropdown(sheet, "B8", "MyTeamSlotList", title="My team",
                  message="Choose one of your current teams (listed under “Who you are”).")

    # ---- fixtures on the chosen date ----
    fx_section = team_list_bottom + 2
    _section(sheet, fx_section, "Fixtures on the chosen date", last_col=11)
    status_row = fx_section + 1
    sheet.cell(row=status_row, column=1, value=(
        f'=IF(B6="","Step 1: enter a date.",IF({serial}="bad","That date was not recognized — type it like 10/11/2026.",'
        f'IF({vkey}="","Step 2: enter your APA record ID.",IF({name_row}="","That APA record ID is not a verified player in this build.",'
        f'IF({scope}="","Step 3: choose one of your teams.",IF({count}=0,"No scheduled match found for "&B8&" on "&TEXT({serial},"dddd, mmm d, yyyy")&" ("&B9&").",'
        f'{count}&" fixture"&IF({count}=1,"","s")&" found for "&B8&" on "&TEXT({serial},"dddd, mmm d, yyyy")&" ("&B9&"). "&'
        f'IF({count}>{fixture_slots},"Showing the first {fixture_slots} — filter the Schedule sheet by Team and Local Date for the rest.",'
        f'IF({count}=1,"","All are listed below; none is picked automatically."))))))))'
    ))
    sheet.cell(row=status_row, column=1).font = Font(bold=True, size=12, color=FELT_DEEP)
    sheet.cell(row=status_row, column=1).alignment = WRAP_TOP
    sheet.merge_cells(f"A{status_row}:K{status_row}")
    sheet.row_dimensions[status_row].height = 34
    header_row = status_row + 1
    fixture_fields = [
        (2, "Kickoff"), (3, "Home/Away"), (4, "Format"), (5, "Opponent"), (6, "Session"), (7, "Venue"),
        (8, "Status"), (9, "Score (home–away)"), (10, "Opponent Roster"), (11, "Source Timestamp"),
    ]
    _subheader(sheet, header_row, [(1, "# · Date")] + [(c, name) for c, name in fixture_fields])
    first_slot_row = header_row + 1
    for k in range(1, fixture_slots + 1):
        r = first_slot_row + k - 1
        row_ref = f"$O{r}"
        sheet.cell(row=r, column=14, value=f"Fixture {k} schedule row").font = HELPER_FONT
        sheet.cell(row=r, column=15, value=(
            f'=IF(OR({group}="",{k}>{count}),"",IFERROR(INDEX(ScheduleKeys_Table[Schedule Row],'
            f'MATCH({group}&"|{k}",ScheduleKeys_Table[Slot Key],0)),""))'
        )).font = HELPER_FONT
        sheet.cell(row=r, column=1, value=f'=IF({row_ref}="","","{k} · "&INDEX(Schedule_Table[Date Display],{row_ref}))')
        for col, name in fixture_fields:
            sheet.cell(row=r, column=col, value=f'=IF({row_ref}="","",INDEX(Schedule_Table[{name}],{row_ref}))')
        for c in range(1, 12):
            sheet.cell(row=r, column=c).border = CELL_BORDER
            sheet.cell(row=r, column=c).alignment = WRAP_TOP
    last_slot_row = first_slot_row + fixture_slots - 1

    # ---- printable matchup ----
    mu = last_slot_row + 2
    _section(sheet, mu, "Matchup preview", last_col=11)
    print_link = sheet.cell(row=mu, column=7, value="Print-ready page: Print Matchup sheet →")
    print_link.hyperlink = Hyperlink(ref=f"G{mu}", location="'Print Matchup'!A1", display="Print-ready page: Print Matchup sheet →")
    print_link.font = Font(bold=True, color="FFFFFF", underline="single")
    cmp_row = f"$O${mu}"
    sheet.cell(row=mu, column=14, value="Compared schedule row").font = HELPER_FONT
    sheet.cell(row=mu, column=15, value=(
        f'=IF(OR({compare_n}<1,{compare_n}>{count},{compare_n}>{fixture_slots}),"",INDEX($O${first_slot_row}:$O${last_slot_row},{compare_n}))'
    )).font = HELPER_FONT
    opp_scope = helper(mu + 1, "Opponent scope key",
                       f'=IF({cmp_row}="","",IF(INDEX(Schedule_Table[Opponent Scope Key],{cmp_row})="{NONE_TOKEN}","",'
                       f'INDEX(Schedule_Table[Opponent Scope Key],{cmp_row})))')
    sheet.cell(row=mu + 1, column=1, value=(
        f'=IF({count}=0,"Choose a date and team with a scheduled fixture to compare rosters.",'
        f'IF({cmp_row}="","Fixture #"&{compare_n}&" is not in the list above — choose 1 to "&MIN({count},{fixture_slots})&" in step 5.",'
        f'"Fixture #"&{compare_n}&": "&B8&" ("&INDEX(Schedule_Table[Home/Away],{cmp_row})&") vs "&INDEX(Schedule_Table[Opponent],{cmp_row})'
        f'&" · "&INDEX(Schedule_Table[Date Display],{cmp_row})&" · "&INDEX(Schedule_Table[Kickoff],{cmp_row})))'
    ))
    sheet.cell(row=mu + 1, column=1).font = Font(bold=True, size=12)
    sheet.merge_cells(f"A{mu + 1}:K{mu + 1}")
    sheet.cell(row=mu + 2, column=1, value=(
        f'=IF({cmp_row}="","",IF({opp_scope}="","Opponent roster: "&INDEX(Schedule_Table[Opponent Roster],{cmp_row})&"."'
        f',"Opponent roster scope: "&INDEX(Schedule_Table[Opponent Team],{cmp_row})))'
    ))
    sheet.cell(row=mu + 2, column=1).font = MUTED_FONT
    sheet.merge_cells(f"A{mu + 2}:K{mu + 2}")
    roster_top = mu + 3
    _roster_block(sheet, top=roster_top, left=1, scope_ref=scope, slots=roster_slots, helper_col=16,
                  title_formula=(f'=IF({scope}="","OUR TEAM — choose your team (step 3)","OUR TEAM — "&B8&'
                                 f'IF({cmp_row}="",""," ("&INDEX(Schedule_Table[Home/Away],{cmp_row})&")"))'))
    _roster_block(sheet, top=roster_top, left=7, scope_ref=opp_scope, slots=roster_slots, helper_col=17,
                  title_formula=(f'=IF({cmp_row}="","OPPONENT — choose a fixture above",IF({opp_scope}="",'
                                 f'"OPPONENT — "&INDEX(Schedule_Table[Opponent],{cmp_row})&" · "&INDEX(Schedule_Table[Opponent Roster],{cmp_row}),'
                                 f'"OPPONENT — "&INDEX(Schedule_Table[Opponent Team],{cmp_row})&" ("&'
                                 f'IF(INDEX(Schedule_Table[Home/Away],{cmp_row})="Home","Away","Home")&")"))'))
    totals_row = roster_top + roster_slots + 2
    sheet.cell(row=totals_row, column=1, value=(
        f'=IF({scope}="","",IFERROR(INDEX(Teams_Table[Summary],MATCH({scope},Teams_Table[Scope Key],0)),""))'
    )).font = MUTED_FONT
    sheet.merge_cells(f"A{totals_row}:E{totals_row}")
    sheet.cell(row=totals_row, column=7, value=(
        f'=IF({opp_scope}="","",IFERROR(INDEX(Teams_Table[Summary],MATCH({opp_scope},Teams_Table[Scope Key],0)),""))'
    )).font = MUTED_FONT
    sheet.merge_cells(f"G{totals_row}:K{totals_row}")
    _note(sheet, f"A{totals_row + 1}",
          "Rosters are each team's CURRENT captured roster, not a reconstruction of who actually played on the chosen "
          "date — this data source doesn't capture historical lineups. * = division-scoped skill level (no live rating "
          "captured). Skill totals are informational, not a lineup cap check. No win probability is shown: NOT CALIBRATED.",
          merge_to=f"K{totals_row + 1}", height=44)
    print_bottom = totals_row + 1

    # ---- season schedule ----
    ss = print_bottom + 2
    _section(sheet, ss, "Your team's season schedule (pick a date from here)", last_col=11)
    season_fields = [(1, "Date Display"), (2, "Kickoff"), (3, "Home/Away"), (4, "Format"), (5, "Opponent"),
                     (6, "Session"), (7, "Venue"), (8, "Status"), (9, "Score (home–away)"), (10, "Opponent Roster")]
    _subheader(sheet, ss + 1, [(c, "Date" if name == "Date Display" else name) for c, name in season_fields])
    sheet.cell(row=ss + 2, column=1, value=(
        f'=IF({season_group}="","Choose your team above to list its season.",IF({season_count}=0,"No fixtures for this team in this format.",'
        f'{season_count}&" fixture"&IF({season_count}=1,"","s")&IF({season_count}>{season_slots}," — showing the first {season_slots}; see the Schedule sheet for all.","")))'
    )).font = MUTED_FONT
    sheet.merge_cells(f"A{ss + 2}:K{ss + 2}")
    for k in range(1, season_slots + 1):
        r = ss + 2 + k
        row_ref = f"$O{r}"
        sheet.cell(row=r, column=14, value=f"Season {k} schedule row").font = HELPER_FONT
        sheet.cell(row=r, column=15, value=(
            f'=IF(OR({season_group}="",{k}>{season_count}),"",IFERROR(INDEX(ScheduleKeys_Table[Schedule Row],'
            f'MATCH({season_group}&"|{k}",ScheduleKeys_Table[Slot Key],0)),""))'
        )).font = HELPER_FONT
        for col, name in season_fields:
            sheet.cell(row=r, column=col, value=f'=IF({row_ref}="","",INDEX(Schedule_Table[{name}],{row_ref}))')
            sheet.cell(row=r, column=col).border = CELL_BORDER
    season_bottom = ss + 2 + season_slots

    # ---- disclosures ----
    coverage = match_day.get("coverage") or {}
    disc = season_bottom + 2
    _section(sheet, disc, "About this data", last_col=11)
    disclosures = [
        f"Timezone: every date, weekday and kickoff time is converted to {tz_name} (MST/MDT as applicable). The original "
        "source timestamp is kept in the Source Timestamp column. A source time like 2026-08-30T01:00:00Z is Saturday "
        "Aug 29 at 7:00 PM in Denver, so it is listed on Aug 29.",
        f"Schedule coverage: {int(coverage.get('embedded_fixture_count') or 0):,} of {int(coverage.get('stored_fixture_count') or 0):,} "
        f"stored fixtures are included — every fixture involving a team with a current captured roster "
        f"({', '.join(coverage.get('current_sessions') or []) or 'no current session'}). The other "
        f"{int(coverage.get('excluded_fixture_count') or 0):,} belong to past-session teams with no current roster, so "
        "My team can't reach them; their individual game results still feed Player vs Player.",
        f"Venue is blank in the source for {int(coverage.get('location_missing_count') or 0):,} included fixtures and shows "
        "as “No data”. Byes say “Bye — no opponent”; their placeholder team names are never treated as an opponent.",
        "APA record ID is APA's internal member record number; it is not the league card number printed on a member card.",
    ]
    for i, text in enumerate(disclosures, start=1):
        _note(sheet, f"A{disc + i}", text, merge_to=f"K{disc + i}", height=44)

    sheet.freeze_panes = "A4"
    sheet.print_area = f"A1:K{print_bottom}"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_options.horizontalCentered = True
    sheet.page_margins.left = sheet.page_margins.right = 0.4
    return {
        "status_row": status_row, "first_slot_row": first_slot_row, "matchup_row": mu,
        "roster_top": roster_top, "season_row": ss, "team_list_top": team_list_top,
        "scope": scope, "compare_n": compare_n, "count": count, "cmp": cmp_row, "opp_scope": opp_scope,
    }


def _print_matchup_sheet(wb: Workbook, *, refs: dict[str, Any], roster_slots: int, tz_name: str, built_at: str) -> dict[str, int]:
    """A focused, one-page printable matchup for the fixture chosen on Match
    Day: a fixture header, then clearly labeled OUR TEAM / OPPONENT panels,
    each with team, side and roster (name + APA record ID + SL + current
    W-L), the stated reason when no opponent roster exists (bye, no current
    roster, ambiguous), and the missing-data legend. It reads Match Day's own
    identity-backed selection (roster scope keys and the compared schedule
    row) and never looks anything up by name."""
    sheet = wb.create_sheet("Print Matchup", 1)
    sheet.sheet_view.showGridLines = False
    for letter, width in {"A": 5, "B": 28, "C": 16, "D": 8, "E": 13, "F": 3, "G": 5, "H": 28, "I": 16, "J": 8,
                          "K": 13, "L": 3, "M": 28, "N": 34, "O": 9, "P": 9}.items():
        sheet.column_dimensions[letter].width = width
    md = "'Match Day'!"

    def mirror(row: int, label: str, ref: str) -> str:
        # Guarded so a blank Match Day input never reads back here as 0.
        sheet.cell(row=row, column=13, value=label).font = HELPER_FONT
        sheet.cell(row=row, column=14, value=f'=IF({md}{ref}="","",{md}{ref})').font = HELPER_FONT
        return f"$N${row}"

    sheet["M1"] = "Lookup detail (from Match Day)"
    sheet["M1"].font = LABEL_FONT
    cmp = mirror(2, "Compared schedule row", refs["cmp"])
    opp = mirror(3, "Opponent scope key", refs["opp_scope"])
    ours = mirror(4, "Our team scope key", refs["scope"])
    team = mirror(5, "Our team label", "$B$8")
    number = mirror(6, "Fixture #", refs["compare_n"])
    count = mirror(7, "Fixtures found", refs["count"])
    back = sheet.cell(row=9, column=13, value="← Back to Match Day")
    back.hyperlink = Hyperlink(ref="M9", location="'Match Day'!A1", display="← Back to Match Day")
    back.font = LINK_FONT

    sheet["A1"] = "Ultimate Coach — Matchup"
    sheet["A1"].font = TITLE_FONT
    sheet.merge_cells("A1:K1")
    sheet.row_dimensions[1].height = 30
    sheet["A2"] = (
        f'=IF({cmp}="",IF({ours}="","Choose a date, your team and a fixture on the Match Day sheet — this page then shows that matchup, ready to print.",'
        f'"No fixture selected for "&{team}&" — choose a date with a scheduled fixture on Match Day (step 1) and the fixture # (step 5)."),'
        f'INDEX(Schedule_Table[Date Display],{cmp})&" · "&INDEX(Schedule_Table[Kickoff],{cmp})&" ({tz_name})")'
    )
    sheet["A2"].font = Font(bold=True, size=14, color=FELT_DEEP)
    sheet["A2"].alignment = WRAP_TOP
    sheet.merge_cells("A2:K2")
    sheet.row_dimensions[2].height = 24
    sheet["A3"] = (
        f'=IF({cmp}="","",INDEX(Schedule_Table[Format],{cmp})&" · "&INDEX(Schedule_Table[Session],{cmp})&'
        f'" · Venue: "&INDEX(Schedule_Table[Venue],{cmp})&" · Status: "&INDEX(Schedule_Table[Status],{cmp})&'
        f'" · Score (home–away): "&INDEX(Schedule_Table[Score (home–away)],{cmp}))'
    )
    sheet["A3"].alignment = WRAP_TOP
    sheet.merge_cells("A3:K3")
    sheet["A4"] = (
        f'=IF({cmp}="","","Source timestamp: "&INDEX(Schedule_Table[Source Timestamp],{cmp})&" · fixture #"&{number}&'
        f'" of "&{count}&" on Match Day · built {built_at or "unknown"}")'
    )
    sheet["A4"].font = MUTED_FONT
    sheet.merge_cells("A4:K4")

    for left, fill, label in ((1, SECTION_FILL, "OUR TEAM"), (7, OPPONENT_FILL, "OPPONENT")):
        for col in range(left, left + 5):
            sheet.cell(row=6, column=col).fill = fill
        cell = sheet.cell(row=6, column=left, value=label)
        cell.font = SECTION_FONT
        sheet.merge_cells(start_row=6, start_column=left, end_row=6, end_column=left + 4)
    sheet.row_dimensions[6].height = 22
    sheet["A7"] = (
        f'=IF({ours}="","Not chosen — pick your team on Match Day (step 3).",{team}&'
        f'IF({cmp}="",""," — "&INDEX(Schedule_Table[Home/Away],{cmp})))'
    )
    sheet["G7"] = (
        f'=IF({cmp}="","Not chosen — pick a fixture on Match Day.",IF({opp}="",INDEX(Schedule_Table[Opponent],{cmp}),'
        f'INDEX(Schedule_Table[Opponent Team],{cmp})&" — "&IF(INDEX(Schedule_Table[Home/Away],{cmp})="Home","Away","Home")))'
    )
    sheet["A8"] = f'=IF({ours}="","",IFERROR(INDEX(Teams_Table[Summary],MATCH({ours},Teams_Table[Scope Key],0)),""))'
    sheet["G8"] = (
        f'=IF({cmp}="","",IF({opp}="","Opponent roster: "&INDEX(Schedule_Table[Opponent Roster],{cmp})&".",'
        f'IFERROR(INDEX(Teams_Table[Summary],MATCH({opp},Teams_Table[Scope Key],0)),"")))'
    )
    for ref in ("A7", "G7"):
        sheet[ref].font = Font(bold=True, size=13)
        sheet[ref].alignment = WRAP_TOP
    for ref in ("A8", "G8"):
        sheet[ref].font = MUTED_FONT
        sheet[ref].alignment = WRAP_TOP
    for row in (7, 8):
        sheet.merge_cells(f"A{row}:E{row}")
        sheet.merge_cells(f"G{row}:K{row}")
    sheet.row_dimensions[7].height = 34
    sheet.row_dimensions[8].height = 30

    header_row = 9
    for left in (1, 7):
        _subheader(sheet, header_row, [(left, "#"), (left + 1, "Player"), (left + 2, "APA record ID"),
                                        (left + 3, "SL"), (left + 4, "Current W-L")])
    first = header_row + 1
    for k in range(1, roster_slots + 1):
        r = first + k - 1
        for left, helper_col, scope in ((1, 15, ours), (7, 16, opp)):
            row_ref = f"${get_column_letter(helper_col)}{r}"
            sheet.cell(row=r, column=helper_col, value=(
                f'=IF({scope}="","",IFERROR(MATCH({scope}&"|{k}",TeamRosters_Table[Roster Slot Key],0),""))'
            )).font = HELPER_FONT
            sheet.cell(row=r, column=left, value=f'=IF({row_ref}="","",{k})')
            for offset, column_name in enumerate(("Player Name", "APA Record ID", "SL Display", "W-L Display"), start=1):
                sheet.cell(row=r, column=left + offset,
                           value=f'=IF({row_ref}="","",INDEX(TeamRosters_Table[{column_name}],{row_ref}))')
            for col in range(left, left + 5):
                sheet.cell(row=r, column=col).border = CELL_BORDER
        if k == 1:
            # The opponent panel says so explicitly when there is nothing to list.
            sheet.cell(row=r, column=8, value=(
                f'=IF($P{r}="",IF(AND({opp}="",{cmp}<>""),"No opponent roster to list — see above.",""),'
                f'INDEX(TeamRosters_Table[Player Name],$P{r}))'
            ))
    legend_top = first + roster_slots + 1
    legend = [
        "Legend — “No data”: not captured in the source. SL with *: division-scoped skill level (no live current "
        "rating captured). Players without a captured SL are left out of skill totals, never counted as 0.",
        "Rosters are each team's CURRENT captured roster, not a reconstruction of who actually played on this date. "
        "Skill totals are informational, not a 5-player lineup cap check (the commonly used APA default is 23; "
        "verify your division's rules).",
        f"No win probability is shown: NOT CALIBRATED. Dates and times are in {tz_name}. Players are identified by "
        "APA record ID (not the league card number printed on a member card).",
    ]
    for i, text in enumerate(legend):
        _note(sheet, f"A{legend_top + i}", text, merge_to=f"K{legend_top + i}", height=30)
    last = legend_top + len(legend) - 1
    sheet.print_area = f"A1:K{last}"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_options.horizontalCentered = True
    sheet.page_margins.left = sheet.page_margins.right = 0.4
    sheet.page_margins.top = sheet.page_margins.bottom = 0.5
    _nav_row(sheet, last + 2, current="Print Matchup")
    return {"header_row": header_row, "first_roster_row": first, "legend_row": legend_top}


def build_workbook(
    payload: dict[str, Any],
    *,
    built_at: str = "",
    source_db: str = "",
    viewer_member_external_id: str | None = None,
    viewer_card_number: str | None = None,
) -> Workbook:
    players = payload.get("players") or []
    match_day = payload.get("match_day") or build_match_day_section([], players)
    wb = Workbook()
    _build_info_sheet(wb, payload, built_at=built_at, source_db=source_db, match_day=match_day)
    _data_trust_sheet(wb, payload)
    _players_sheet(wb, payload)
    rosters = build_team_rosters(payload)
    max_roster = _team_rosters_sheet(wb, payload, rosters)
    teams = _teams_sheet(wb, rosters)
    pairs = _player_vs_player_sheet(wb, payload)
    max_teams = _player_teams_sheet(wb, payload, teams)
    schedule_stats = _schedule_sheets(wb, match_day, teams)

    raw_formats = sorted({str(f.get("format_raw") or "") for f in match_day.get("fixtures") or []} - {""})
    format_filter_options = [FORMAT_FILTER_EIGHT_NINE_LABEL, FORMAT_FILTER_ALL_LABEL] + raw_formats
    fixture_slots = max(4, schedule_stats["max_per_date"])
    _lists_sheet(wb, format_filter_options, fixture_slots)

    player_count = len(players)
    team_count = len({r["team_scope_key"] for r in rosters})

    # Excel's data-validation list source cannot reliably reference a Table
    # on a different sheet than the dropdown cell itself (confirmed against
    # the actual target Excel install earlier in this PR); a workbook-scoped
    # defined Name wrapping the same structured reference works from any sheet.
    if player_count:
        wb.defined_names["PlayerLabelList"] = DefinedName(
            "PlayerLabelList", attr_text="Players!Players_Table[Player Label]"
        )
    if rosters:
        wb.defined_names["TeamNameList"] = DefinedName(
            "TeamNameList", attr_text="Teams!Teams_Table[Team]"
        )

    roster_slots = max(8, min(max_roster, 16))
    _match_night_sheet(wb, team_count, roster_slots)
    _coach_dashboard_sheet(wb, player_count, _dashboard_format_options(pairs))
    viewer = viewer_player(players, viewer_member_external_id)
    resolved = viewer is not None
    refs = _match_day_sheet(
        wb,
        match_day=match_day,
        format_filter_options=format_filter_options,
        team_slots=max(4, max_teams),
        fixture_slots=fixture_slots,
        season_slots=max(10, min(schedule_stats["max_per_season"], 40)),
        roster_slots=roster_slots,
        viewer_member_external_id=viewer_member_external_id,
        viewer_card_number=viewer_card_number,
        viewer_resolved=resolved,
        viewer_label=_player_label(viewer["name"], viewer["external_id"]) if viewer else None,
        has_players=bool(player_count),
    )
    _print_matchup_sheet(
        wb, refs=refs, roster_slots=roster_slots,
        tz_name=match_day.get("display_timezone") or DEFAULT_MATCH_DAY_TIMEZONE, built_at=built_at,
    )

    for target, name in enumerate(SHEET_ORDER):
        wb.move_sheet(wb[name], offset=target - wb.sheetnames.index(name))
    wb.active = wb["Match Day"]
    return wb


def write_workbook(
    payload: dict[str, Any],
    path: str | Path,
    *,
    built_at: str = "",
    source_db: str = "",
    viewer_member_external_id: str | None = None,
    viewer_card_number: str | None = None,
) -> Path:
    workbook = build_workbook(
        payload, built_at=built_at, source_db=source_db,
        viewer_member_external_id=viewer_member_external_id, viewer_card_number=viewer_card_number,
    )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path
