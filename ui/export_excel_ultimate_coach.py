"""Ultimate Coach Excel companion: a standalone workbook built from the same
verified cockpit payload (analytics.ultimate_coach_cockpit_identity_bridge)
as the standalone HTML, so the two cannot silently disagree about who is a
verified player or which games count as evidence.

Sheets:
    Build Info          Build/source metadata -- static.
    Data Trust           Identity/evidence trust counters -- static.
    Players               One row per verified player -- reference table.
    Team Rosters           One row per (team, player) current membership --
                        an Excel Table with native AutoFilter, the reliable
                        way to answer "who is on team X" without a formula
                        that depends on dynamic-array functions this
                        workbook cannot assume the opener's Excel has.
    Teams                One row per current team -- roster size/skill
                        summary, aggregated live via SUMIF/COUNTIF against
                        Team Rosters (safe, non-volatile, universally
                        available formulas).
    Player vs Player      One row per (player, opponent, format) with at
                        least one recorded meeting -- the lookup table the
                        Coach Dashboard's INDEX/MATCH formulas read from.
    Coach Dashboard        Two player dropdowns + a format dropdown; pulls
                        the real direct-evidence record for that exact pair
                        via INDEX/MATCH, or discloses "no recorded direct
                        meeting" -- never a fabricated 0-0.
    Match Night            Two team dropdowns; live roster-size/skill
                        aggregates for each side via SUMIF/COUNTIF, plus
                        instructions to filter Team Rosters and cross-check
                        individual pairings on Coach Dashboard.

Player names collide in the real data (184 duplicate names among 15,180
verified players) -- see analytics.ultimate_coach_excel_payload and its
tests. A dropdown keyed on name alone would silently resolve to whichever
duplicate MATCH finds first: exactly the "fuzzy name matching as identity"
and "silent identity merge" the project's hard safety locks forbid. Every
player-picking dropdown here is keyed on "Name (Member #<external id>)"
instead, which is unique per verified identity.

No macros. No volatile formulas (NOW/TODAY/RAND/OFFSET/INDIRECT). No
functions newer than Excel 2016 (confirmed via COM against the actual
target Excel install that dynamic-array functions like FILTER are not
available there and fail as #NAME?).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from analytics.ultimate_coach_excel_payload import (
    build_player_vs_player_pairs,
    build_team_rosters,
    build_teams_summary,
)

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
TITLE_FONT = Font(bold=True, size=16, color="1F3864")
LABEL_FONT = Font(bold=True)
MUTED_FONT = Font(italic=True, color="666666")


def _player_label(name: str, external_id: Any) -> str:
    return f"{name} (Member #{external_id})"


def _style_header(sheet: Worksheet, columns: list[str], *, freeze: str = "A2") -> None:
    sheet.append(columns)
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
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
        # conflicting autoFilter declarations for the same range. openpyxl's
        # own reader tolerates it, but real Excel treats the file as
        # invalid and refuses to open it at all (confirmed via COM
        # automation against the actual target Excel install, not just a
        # repair-prompt warning -- Workbooks.Open fails outright, even with
        # CorruptLoad forced). Only set the plain autoFilter when there is
        # no table to own it.
        table = Table(displayName=name, ref=full_range)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        sheet.add_table(table)
    else:
        sheet.auto_filter.ref = full_range


def _build_info_sheet(wb: Workbook, payload: dict[str, Any], *, built_at: str, source_db: str) -> None:
    sheet = wb.active
    sheet.title = "Build Info"
    sheet.column_dimensions["A"].width = 32
    sheet.column_dimensions["B"].width = 70

    trust = payload.get("trust") or {}
    counts = payload.get("counts") or {}
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
    ]
    sheet.append(["Field", "Value"])
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    for label, value in rows:
        sheet.append([label, value])
    for row in sheet.iter_rows(min_row=2, max_col=1):
        row[0].font = LABEL_FONT
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


def _data_trust_sheet(wb: Workbook, payload: dict[str, Any]) -> None:
    sheet = wb.create_sheet("Data Trust")
    sheet.column_dimensions["A"].width = 42
    sheet.column_dimensions["B"].width = 16
    trust = payload.get("trust") or {}
    sheet.append(["Metric", "Count"])
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
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
    sheet.cell(row=sheet.max_row, column=1).font = MUTED_FONT


PLAYERS_COLUMNS = [
    "Player Label", "Player ID", "External ID", "Player Name",
    "Current SL", "Current Matches Won", "Current Matches Played",
]
PLAYERS_WIDTHS = {
    "Player Label": 34, "Player ID": 10, "External ID": 12, "Player Name": 22,
    "Current SL": 11, "Current Matches Won": 16, "Current Matches Played": 18,
}


def _players_sheet(wb: Workbook, payload: dict[str, Any]) -> None:
    sheet = wb.create_sheet("Players")
    _style_header(sheet, PLAYERS_COLUMNS)
    players = sorted(payload.get("players") or [], key=lambda p: p["name"])
    for p in players:
        sheet.append(
            [
                _player_label(p["name"], p["external_id"]),
                p["id"], p["external_id"], p["name"],
                p.get("current_skill_level"), p.get("current_matches_won"), p.get("current_matches_played"),
            ]
        )
    _apply_widths(sheet, PLAYERS_COLUMNS, PLAYERS_WIDTHS)
    _autotable(sheet, "Players_Table", PLAYERS_COLUMNS, len(players))


TEAM_ROSTERS_COLUMNS = [
    "Team", "Division ID", "Session", "Player Label", "Player Name",
    "Skill Level", "Skill Level Is Live", "Matches Won", "Matches Played",
]
TEAM_ROSTERS_WIDTHS = {
    "Team": 30, "Division ID": 14, "Session": 16, "Player Label": 34, "Player Name": 22,
    "Skill Level": 12, "Skill Level Is Live": 16, "Matches Won": 12, "Matches Played": 14,
}


def _team_rosters_sheet(wb: Workbook, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rosters = build_team_rosters(payload)
    players_by_id = {p["id"]: p for p in payload.get("players") or []}
    sheet = wb.create_sheet("Team Rosters")
    _style_header(sheet, TEAM_ROSTERS_COLUMNS)
    for row in rosters:
        external_id = players_by_id.get(row["player_id"], {}).get("external_id")
        sheet.append(
            [
                row["team_name"], row["division_id"], row["session_name"],
                _player_label(row["player_name"], external_id), row["player_name"],
                row["skill_level"], row["skill_level_is_live"],
                row["matches_won"], row["matches_played"],
            ]
        )
    _apply_widths(sheet, TEAM_ROSTERS_COLUMNS, TEAM_ROSTERS_WIDTHS)
    _autotable(sheet, "TeamRosters_Table", TEAM_ROSTERS_COLUMNS, len(rosters))
    return rosters


TEAMS_COLUMNS = ["Team", "Division ID", "Session", "Roster Count", "Known-Skill Players", "Skill Total (known only)"]
TEAMS_WIDTHS = {"Team": 30, "Division ID": 14, "Session": 16, "Roster Count": 13, "Known-Skill Players": 17, "Skill Total (known only)": 20}


def _teams_sheet(wb: Workbook, rosters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    teams = build_teams_summary(rosters)
    sheet = wb.create_sheet("Teams")
    _style_header(sheet, TEAMS_COLUMNS)
    for t in teams:
        sheet.append(
            [
                t["team_name"], t["division_id"], t["session_name"],
                t["roster_count"], t["known_skill_count"], t["skill_total"],
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
PVP_WIDTHS = {"Player Label": 34, "Format": 10, "Opponent Label": 34, "Wins": 8, "Losses": 8, "Games": 8, "Win Rate": 10, "Pair Key": 20}


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
                "8-Ball" if row["format"] == "EIGHT" else "9-Ball" if row["format"] == "NINE" else row["format"],
                _player_label(row["opponent_name"], opponent.get("external_id")),
                row["wins"], row["losses"], row["games"], row["win_rate"],
                row["pair_key"],
            ]
        )
    _apply_widths(sheet, PVP_COLUMNS, PVP_WIDTHS)
    _autotable(sheet, "PlayerVsPlayer_Table", PVP_COLUMNS, len(pairs))
    return pairs


def _add_dropdown(sheet: Worksheet, cell: str, source_ref: str, *, title: str, message: str) -> None:
    validation = DataValidation(type="list", formula1=source_ref, allow_blank=True)
    validation.errorTitle = title
    validation.error = message
    validation.promptTitle = title
    validation.prompt = message
    sheet.add_data_validation(validation)
    validation.add(cell)


def _coach_dashboard_sheet(wb: Workbook, player_count: int, pvp_count: int) -> None:
    sheet = wb.create_sheet("Coach Dashboard", 0)
    sheet.sheet_view.showGridLines = False
    sheet.column_dimensions["A"].width = 22
    sheet.column_dimensions["B"].width = 36
    sheet.column_dimensions["C"].width = 20
    sheet.column_dimensions["D"].width = 30

    sheet["A1"] = "Ultimate Coach — Coach Dashboard"
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = "Player vs Player, evidence-backed. Pick two players and a format below."
    sheet["A2"].font = MUTED_FONT

    sheet["A4"] = "Player A"
    sheet["A4"].font = LABEL_FONT
    sheet["A5"] = "Player B"
    sheet["A5"].font = LABEL_FONT
    sheet["A6"] = "Format"
    sheet["A6"].font = LABEL_FONT
    sheet["B4"] = ""
    sheet["B5"] = ""
    sheet["B6"] = "8-Ball"

    if player_count:
        _add_dropdown(
            sheet, "B4", "PlayerLabelList",
            title="Unknown player", message="Choose a player already listed on the Players sheet.",
        )
        _add_dropdown(
            sheet, "B5", "PlayerLabelList",
            title="Unknown player", message="Choose a player already listed on the Players sheet.",
        )
    _add_dropdown(sheet, "B6", '"8-Ball,9-Ball"', title="Format", message="Choose 8-Ball or 9-Ball.")

    # Helper block: resolve dropdown labels to canonical IDs and build the
    # same pair key the Player vs Player sheet was written with. Kept on the
    # visible sheet (not hidden) so the lookup chain is inspectable, not a
    # black box -- consistent with this project's "never hide the trust
    # contract" stance elsewhere in the workbook.
    sheet["A9"] = "Lookup detail"
    sheet["A9"].font = LABEL_FONT
    sheet["A10"] = "Player A ID"
    sheet["B10"] = '=IFERROR(INDEX(Players_Table[Player ID],MATCH(B4,Players_Table[Player Label],0)),"")'
    sheet["A11"] = "Player B ID"
    sheet["B11"] = '=IFERROR(INDEX(Players_Table[Player ID],MATCH(B5,Players_Table[Player Label],0)),"")'
    sheet["A12"] = "Format code"
    sheet["B12"] = '=IF(B6="9-Ball","NINE","EIGHT")'
    sheet["A13"] = "Pair key"
    sheet["B13"] = '=B10&"|"&B12&"|"&B11'
    sheet["A14"] = "Pair row in Player vs Player"
    sheet["B14"] = '=IFERROR(MATCH(B13,PlayerVsPlayer_Table[Pair Key],0),"")'
    for row in range(10, 15):
        sheet.cell(row=row, column=1).font = MUTED_FONT

    sheet["A17"] = "Player A current SL"
    sheet["B17"] = '=IFERROR(INDEX(Players_Table[Current SL],MATCH(B4,Players_Table[Player Label],0)),"—")'
    sheet["A18"] = "Player B current SL"
    sheet["B18"] = '=IFERROR(INDEX(Players_Table[Current SL],MATCH(B5,Players_Table[Player Label],0)),"—")'

    sheet["A20"] = "Direct record (Player A perspective)"
    sheet["A20"].font = LABEL_FONT
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
    sheet["B25"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[25].height = 48

    sheet["A28"] = "Probability status"
    sheet["A28"].font = LABEL_FONT
    sheet["B28"] = (
        "NOT CALIBRATED. This dashboard shows real recorded evidence only. No matchup "
        "probability is shown until a separately back-tested calibration gate passes."
    )
    sheet["B28"].font = MUTED_FONT
    sheet["B28"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[28].height = 32

    if not player_count:
        sheet["A31"] = "No verified players were available when this workbook was built."
        sheet["A31"].font = MUTED_FONT


def _match_night_sheet(wb: Workbook, team_count: int) -> None:
    sheet = wb.create_sheet("Match Night", 1)
    sheet.sheet_view.showGridLines = False
    sheet.column_dimensions["A"].width = 26
    sheet.column_dimensions["B"].width = 30
    sheet.column_dimensions["C"].width = 30

    sheet["A1"] = "Ultimate Coach — Match Night"
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = "Pick our team and the opponent team for a live roster-size/skill comparison."
    sheet["A2"].font = MUTED_FONT

    sheet["B4"] = "Our Team"
    sheet["C4"] = "Opponent Team"
    for cell in ("B4", "C4"):
        sheet[cell].font = LABEL_FONT
    sheet["B5"] = ""
    sheet["C5"] = ""
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
    sheet["A12"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.merge_cells("A12:C12")
    sheet.row_dimensions[12].height = 48

    sheet["A15"] = "How to scout this matchup"
    sheet["A15"].font = LABEL_FONT
    sheet["A16"] = (
        "1. On the Team Rosters sheet, use the AutoFilter arrow on the Team column to see the full roster "
        "for each side (this workbook does not attempt a live spill-list here -- the AutoFilter is instant "
        "and works in every Excel version, unlike dynamic-array formulas).\n"
        "2. For any specific pairing, open Coach Dashboard and pick that Player A / Player B to see their "
        "real direct-evidence record.\n"
        "3. No lineup recommendation here is a solved optimal assignment or a win-probability claim -- "
        "matchup_probability stays unpublished throughout this workbook."
    )
    sheet["A16"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.merge_cells("A16:C16")
    sheet.row_dimensions[16].height = 96

    if not team_count:
        sheet["A19"] = "No current team rosters were available when this workbook was built."
        sheet["A19"].font = MUTED_FONT


def build_workbook(payload: dict[str, Any], *, built_at: str = "", source_db: str = "") -> Workbook:
    wb = Workbook()
    _build_info_sheet(wb, payload, built_at=built_at, source_db=source_db)
    _data_trust_sheet(wb, payload)
    _players_sheet(wb, payload)
    rosters = _team_rosters_sheet(wb, payload)
    _teams_sheet(wb, rosters)
    _player_vs_player_sheet(wb, payload)

    player_count = len(payload.get("players") or [])
    team_count = len({r["team_name"] for r in rosters})

    # Excel's data-validation list source cannot reliably reference a Table
    # on a different sheet than the dropdown cell itself -- confirmed via
    # COM automation against the actual target Excel install: a direct
    # cross-sheet "SheetTable[Column]" formula1 makes Workbooks.Open fail
    # outright (not even a repair prompt). A workbook-scoped defined Name
    # wrapping the same structured reference works from any sheet.
    if player_count:
        wb.defined_names["PlayerLabelList"] = DefinedName(
            "PlayerLabelList", attr_text="Players!Players_Table[Player Label]"
        )
    if rosters:
        wb.defined_names["TeamNameList"] = DefinedName(
            "TeamNameList", attr_text="Teams!Teams_Table[Team]"
        )

    _match_night_sheet(wb, team_count)
    _coach_dashboard_sheet(wb, player_count, len(rosters))

    wb.active = wb["Coach Dashboard"]
    return wb


def write_workbook(payload: dict[str, Any], path: str | Path, *, built_at: str = "", source_db: str = "") -> Path:
    workbook = build_workbook(payload, built_at=built_at, source_db=source_db)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path
