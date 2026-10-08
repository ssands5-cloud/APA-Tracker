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
    Match Night        Any two teams side by side: roster lists + totals, a team
                       comparison, and an evidence ranking of our players
                       against each opponent player (precomputed for every
                       pairing with a scheduled fixture).
    Coach Dashboard    Two player dropdowns + a format dropdown; pulls the
                       real direct-evidence record for that exact pair, or
                       discloses "no recorded direct meeting" -- never a
                       fabricated 0-0.
    Schedule           One row per (current team scope, fixture) -- every
                       value pre-rendered for display ("No data", "Bye -- no
                       opponent", scores as text), AutoFilter-ready.
    Schedule Keys      Static lookup keys driving Match Day's fixture list.
    Team Comparison / Matchup Evidence
                       Precomputed comparison + ranking blocks per directed
                       team pairing (analytics.ultimate_coach_matchup_evidence).
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
from openpyxl.worksheet.pagebreak import Break
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from analytics.ultimate_coach_excel_payload import (
    build_player_vs_player_pairs,
    build_team_rosters,
    build_teams_summary,
)
from analytics.ultimate_coach_matchup_evidence import (
    member_order_key,
    build_pair_index,
    fixture_scope_pairs,
    matchup_evidence,
    members_by_scope,
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

NAV_SHEETS = ["Match Day", "War Room", "Lineup Lab", "Captain Packet", "Coach Dashboard", "Schedule",
              "Team Rosters", "Players", "Data Trust", "Build Info"]
SHEET_ORDER = ["START HERE", "Command Center", "Match Day", "War Room", "Lineup Lab", "Scouting Cards", "Captain Packet", "Coach Dashboard",
               "Coach Notes", "Schedule", "Team Rosters", "Teams", "Players", "Player vs Player", "Player Teams", "Schedule Keys",
               "Date Keys", "Suggested Dates", "Stale Scopes", "Team Comparison", "Matchup Evidence", "Threats", "Concerning",
               "Meetings", "Scouting", "Lists", "Engine", "Engine MD", "Data Trust", "Build Info"]
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


NO_ROWS = "(no rows)"


def _autotable(sheet: Worksheet, name: str, columns: list[str], row_count: int) -> None:
    if not row_count:
        # Formulas on the coach-facing sheets refer to every table by name; a
        # table that doesn't exist would break them when Excel opens the file.
        # An empty table therefore keeps one clearly marked sentinel row that
        # no lookup key can ever match.
        sheet.append([NO_ROWS] + ["—"] * (len(columns) - 1))
        row_count = 1
    last_column = get_column_letter(len(columns))
    full_range = f"A1:{last_column}{row_count + 1}"
    # An Excel Table owns its own <autoFilter> internally -- never add a
    # worksheet-level auto_filter.ref on top of it: two conflicting
    # autoFilter declarations make real Excel refuse to open the file
    # (confirmed against the actual target Excel install earlier in this PR).
    table = Table(displayName=name, ref=full_range)
    table.tableStyleInfo = TableStyleInfo(name=TABLE_STYLE, showRowStripes=True)
    sheet.add_table(table)


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
    return f"{row['skill_level']}"


def _record_display(won: Any, played: Any) -> str:
    if won is None or played is None:
        return NO_DATA
    return f"{won}-{max(0, played - won)}"


TEAM_ROSTERS_COLUMNS = [
    "Team", "Division ID", "Session", "Player Label", "Player Name",
    "Skill Level", "SL Scope", "Matches Won", "Matches Played",
    # Appended (never inserted earlier) so positional column indices stay
    # stable. Display columns are always populated (never blank) because
    # Match Day/Match Night read them through INDEX.
    "APA Record ID", "Team Scope Key", "Roster Slot Key", "SL Display", "W-L Display", "Player ID",
]
TEAM_ROSTERS_WIDTHS = {
    "Team": 34, "Division ID": 12, "Session": 14, "Player Label": 40, "Player Name": 24,
    "Skill Level": 11, "SL Scope": 22, "Matches Won": 12, "Matches Played": 14,
    "APA Record ID": 14, "Team Scope Key": 30, "Roster Slot Key": 32, "SL Display": 11, "W-L Display": 12,
}


def _ordered_roster(rows: list[dict[str, Any]], external_ids: dict[Any, Any]) -> list[dict[str, Any]]:
    # Same order as analytics.ultimate_coach_matchup_evidence.member_order_key, so roster slot k here is
    # the same player as row k of the War Room's matrix.
    return sorted(rows, key=lambda r: member_order_key({"name": r["player_name"], "skill_level": r["skill_level"],
                                                        "external_id": external_ids.get(r["player_id"])}))


def _team_rosters_sheet(wb: Workbook, payload: dict[str, Any], rosters: list[dict[str, Any]]) -> int:
    players_by_id = {p["id"]: p for p in payload.get("players") or []}
    by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rosters:
        by_scope[row["team_scope_key"]].append(row)
    slot_by_identity: dict[tuple[str, Any], int] = {}
    for scope, rows in by_scope.items():
        for k, row in enumerate(_ordered_roster(rows, {pid: p.get("external_id") for pid, p in players_by_id.items()}), start=1):
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
                row["skill_level"], f"This team ({_format_label(row.get('format') or '') or 'format not recorded'})",
                row["matches_won"], row["matches_played"],
                str(external_id or NO_DATA), scope, f"{scope}|{slot_by_identity[(scope, row['player_id'])]}",
                _sl_display(row), _record_display(row["matches_won"], row["matches_played"]), row["player_id"],
            ]
        )
    _apply_widths(sheet, TEAM_ROSTERS_COLUMNS, TEAM_ROSTERS_WIDTHS)
    _autotable(sheet, "TeamRosters_Table", TEAM_ROSTERS_COLUMNS, len(rosters))
    return max((len(rows) for rows in by_scope.values()), default=0)


TEAMS_COLUMNS = [
    "Team", "Division ID", "Session", "Roster Count", "Known-Skill Players", "Skill Total (known only)",
    # Appended at the end (never inserted earlier) so existing positional
    # column indices elsewhere stay correct.
    "Team External ID", "Combo Key", "Scope Key", "Summary", "Format Category",
]
TEAMS_WIDTHS = {
    "Team": 34, "Division ID": 12, "Session": 14, "Roster Count": 12, "Known-Skill Players": 15,
    "Skill Total (known only)": 18, "Team External ID": 16, "Combo Key": 24, "Scope Key": 30, "Summary": 44,
    "Format Category": 14,
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
                t["team_scope_key"], _team_summary_text(t), t.get("format") or "No data",
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

























from analytics.ultimate_coach_war_room import build_version, worked_example  # noqa: E402  (after base helpers)


def build_workbook(
    payload: dict[str, Any],
    *,
    built_at: str = "",
    source_db: str = "",
    viewer_member_external_id: str | None = None,
    viewer_card_number: str | None = None,
) -> Workbook:
    from ui import excel_war_room as war  # imported here: that module builds on this one's helpers

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
    stats = war.write_lookup_tables(wb, payload=payload, match_day=match_day, rosters=rosters, teams=teams,
                                    pairs=pairs, built_at=built_at)

    raw_formats = sorted({str(f.get("format_raw") or "") for f in match_day.get("fixtures") or []} - {""})
    format_filter_options = [FORMAT_FILTER_EIGHT_NINE_LABEL, FORMAT_FILTER_ALL_LABEL] + raw_formats
    fixture_slots = max(4, schedule_stats["max_per_date"])
    _lists_sheet(wb, format_filter_options, fixture_slots)

    # Excel's data-validation list source cannot reliably reference a Table
    # on a different sheet than the dropdown cell itself (confirmed against
    # the actual target Excel install earlier in this PR); a workbook-scoped
    # defined Name wrapping the same structured reference works from any sheet.
    wb.defined_names["PlayerLabelList"] = DefinedName(
        "PlayerLabelList", attr_text="Players!Players_Table[Player Label]" if players else "Players!$A$2:$A$2"
    )
    wb.defined_names["TeamNameList"] = DefinedName(
        "TeamNameList", attr_text="Teams!Teams_Table[Team]" if rosters else "Teams!$A$2:$A$2"
    )

    roster_slots = max(8, min(max_roster, 16))
    slots = {"roster": roster_slots, "teams": max(4, max_teams), "dates": max(10, min(stats["max_dates"], 40)),
             "fixtures": fixture_slots, "ll_our_first": 12, "ll_opp_first": 15 + roster_slots}
    viewer = viewer_player(players, viewer_member_external_id)
    viewer_label = _player_label(viewer["name"], viewer["external_id"]) if viewer else None
    label_by_scope = {t["team_scope_key"]: t["team_label"] for t in teams}
    default_team = default_opp = default_date = None
    example = None
    if viewer:
        scopes = sorted({r["team_scope_key"] for r in rosters if r["player_id"] == viewer["id"]})
        default = war.default_matchup(match_day, scopes, stats["build_local"], label_by_scope)
        if default:
            default_team = label_by_scope.get(default["scope"])
            default_opp = label_by_scope.get(default["opponent_scope"] or "")
            default_date = (str(f.get("match_external_id")) if (f := (match_day.get("fixtures") or [])[
                default["side"]["fixture_index"]]) else None)
            example = worked_example(match_day, default, viewer_label, label_by_scope)
        elif len(scopes) == 1:
            default_team = label_by_scope.get(scopes[0])

    engine = war.build_engine(wb, slots=slots, tz_name=stats["tz"])
    war.build_match_day(wb, slots=slots, viewer_label=viewer_label,
                        viewer_key=str(viewer["external_id"]) if viewer else None,
                        card_number=viewer_card_number if viewer else None, default_team=default_team, stats=stats,
                        format_options_source="FormatFilterList")
    war.build_war_room(wb, slots=slots, engine=engine)
    war.build_lineup_lab(wb, slots=slots, default_team=default_team, default_opp=default_opp, default_date=default_date)
    war.build_scouting_cards(wb, slots=slots)
    war.build_captain_packet(wb, slots=slots, stats=stats)
    war.build_coach_dashboard(wb, format_options=_dashboard_format_options(pairs))
    war.build_coach_notes(wb)
    war.build_command_center(wb, slots=slots, stats=stats)
    war.build_start_here(wb, stats=stats, version=build_version(), example=example)
    if default_team and default_date:
        # Lineup Lab plans for the default fixture: its exact plan key, read from the Schedule rows
        # (the same cells uc_PlanKey concatenates, so the two are identical by construction).
        sched = wb["Schedule"]
        head = {c.value: c.column for c in sched[1]}
        scope = next((t["team_scope_key"] for t in teams if t["team_label"] == default_team), None)
        for r in range(2, sched.max_row + 1):
            v = lambda col: sched.cell(row=r, column=head[col]).value
            if v("Team Scope Key") == scope and str(v("Match ID")) == default_date:
                wb["Lineup Lab"]["C9"].value = (f"{v('Date Display')} · {v('Kickoff')} · {v('Home/Away')} vs "
                                                f"{v('Opponent')} · match {v('Match ID')}")
                break
        else:
            wb["Lineup Lab"]["C9"].value = None
    else:
        wb["Lineup Lab"]["C9"].value = None
    war.split_match_day_engine(wb)

    for target, name in enumerate(SHEET_ORDER):
        wb.move_sheet(wb[name], offset=target - wb.sheetnames.index(name))
    wb.active = wb["START HERE"]
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
