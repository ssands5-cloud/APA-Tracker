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
from analytics.ultimate_coach_match_day import viewer_current_teams, viewer_player

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
TITLE_FONT = Font(bold=True, size=16, color="1F3864")
LABEL_FONT = Font(bold=True)
MUTED_FONT = Font(italic=True, color="666666")


def _player_label(name: str, external_id: Any) -> str:
    return f"{name} (Member #{external_id})"


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
                row["team_label"], row["division_id"], row["session_name"],
                _player_label(row["player_name"], external_id), row["player_name"],
                row["skill_level"], row["skill_level_is_live"],
                row["matches_won"], row["matches_played"],
            ]
        )
    _apply_widths(sheet, TEAM_ROSTERS_COLUMNS, TEAM_ROSTERS_WIDTHS)
    _autotable(sheet, "TeamRosters_Table", TEAM_ROSTERS_COLUMNS, len(rosters))
    return rosters


TEAMS_COLUMNS = [
    "Team", "Division ID", "Session", "Roster Count", "Known-Skill Players", "Skill Total (known only)",
    # Appended at the end (never inserted earlier) so existing positional
    # column indices elsewhere stay correct. "Combo Key" is team_external_id
    # + "|" + session_name -- Match Day's own way to find an opponent's
    # current team_label without a cross-range array-formula MATCH, the
    # same "pre-join a key column, MATCH against it directly" pattern
    # Coach Dashboard's own Pair Key already uses.
    "Team External ID", "Combo Key",
]
TEAMS_WIDTHS = {
    "Team": 30, "Division ID": 14, "Session": 16, "Roster Count": 13, "Known-Skill Players": 17,
    "Skill Total (known only)": 20, "Team External ID": 16, "Combo Key": 24,
}


def _teams_sheet(wb: Workbook, rosters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    teams = build_teams_summary(rosters)
    sheet = wb.create_sheet("Teams")
    _style_header(sheet, TEAMS_COLUMNS)
    for t in teams:
        sheet.append(
            [
                t["team_label"], t["division_id"], t["session_name"],
                t["roster_count"], t["known_skill_count"], t["skill_total"],
                t["team_external_id"], f"{t['team_external_id']}|{t['session_name']}",
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
                _format_label(row["format"]),
                _player_label(row["opponent_name"], opponent.get("external_id")),
                row["wins"], row["losses"], row["games"], row["win_rate"],
                row["pair_key"],
            ]
        )
    _apply_widths(sheet, PVP_COLUMNS, PVP_WIDTHS)
    _autotable(sheet, "PlayerVsPlayer_Table", PVP_COLUMNS, len(pairs))
    return pairs


BOTH_EIGHT_NINE_LABEL = "(8-Ball & 9-Ball)"


def _match_day_format_options(payload: dict[str, Any], pairs: list[dict[str, Any]]) -> list[str]:
    """Match Day filters fixtures, not evidence -- a scheduled-but-unplayed
    match can carry a real format with zero Player vs Player evidence rows
    yet, so its own format list must include fixture formats too, not just
    whatever the dashboard's evidence-derived options already cover.
    """
    fixture_formats = {f.get("format") for f in (payload.get("fixtures") or []) if f.get("format")}
    evidence_formats = {row["format"] for row in pairs if row.get("format")}
    return _dashboard_format_options([{"format": fmt} for fmt in (fixture_formats | evidence_formats)])


def _history_scope_key(hist: dict[str, Any]) -> str:
    """Same (team_external_id, division_id, session_name) identity key as
    analytics.ultimate_coach_excel_payload._team_scope_key -- duplicated
    here (both are one-line constants) rather than importing a private
    helper across modules, same reasoning as this file's own FORMAT_LABELS.
    """
    return "|".join([
        str(hist.get("team_external_id") or hist.get("team_name") or ""),
        str(hist.get("division_id") or ""),
        str(hist.get("session_name") or ""),
    ])


MY_TEAMS_COLUMNS = ["Team Label", "Team External ID", "Session Name", "Division ID", "Format"]
MY_TEAMS_WIDTHS = {"Team Label": 36, "Team External ID": 16, "Session Name": 16, "Division ID": 14, "Format": 10}


def _my_teams_sheet(
    wb: Workbook, payload: dict[str, Any], rosters: list[dict[str, Any]], *, viewer_member_external_id: str | None
) -> list[dict[str, Any]]:
    """The configured viewer's own CURRENT teams only -- identity-backed
    (external_id match against the verified players list), never a name
    guess, never defaulted when unconfigured/unresolved/teamless. Reuses
    the exact team_label the Teams/Match Night sheets already show for
    this scope (via the rosters this workbook already built), so Match
    Day can never display a label that doesn't also appear there.
    """
    sheet = wb.create_sheet("My Teams")
    _style_header(sheet, MY_TEAMS_COLUMNS)
    label_by_scope = {r["team_scope_key"]: r["team_label"] for r in rosters}
    players = payload.get("players") or []
    teams = viewer_current_teams(players, viewer_member_external_id)
    rows = []
    for hist in teams:
        scope_key = _history_scope_key(hist)
        label = label_by_scope.get(scope_key)
        if label is None:
            # This viewer team scope has no current roster entry in the
            # rosters this workbook built from -- should be unreachable
            # (viewer_current_teams() only returns is_current rows, the
            # same source build_team_rosters() reads), but never fabricate
            # a label if it somehow happens; skip rather than guess.
            continue
        rows.append(
            {
                "team_label": label, "team_external_id": hist.get("team_external_id") or "",
                "session_name": hist.get("session_name") or "", "division_id": hist.get("division_id") or "",
                "format": hist.get("format") or "",
            }
        )
    for row in rows:
        sheet.append([row["team_label"], row["team_external_id"], row["session_name"], row["division_id"], row["format"]])
    _apply_widths(sheet, MY_TEAMS_COLUMNS, MY_TEAMS_WIDTHS)
    _autotable(sheet, "MyTeams_Table", MY_TEAMS_COLUMNS, len(rows))
    sheet.append([])
    note_row = sheet.max_row + 1
    resolved = viewer_player(players, viewer_member_external_id)
    if not viewer_member_external_id:
        note = ('No viewer identity configured. Set "ultimate_coach.viewer_member_external_id" in '
                'apa_config.yaml to your own APA member id to see your personal Match Day schedule.')
    elif resolved is None:
        note = "The configured viewer identity was not found among this build's verified players."
    elif not rows:
        note = f"No current team found for {resolved.get('name', 'the configured viewer')}."
    else:
        note = "Identity-backed: resolved by APA member id, never by matching a display name."
    sheet.cell(row=note_row, column=1, value=note).font = MUTED_FONT
    return rows


FIXTURES_COLUMNS = [
    "Local Date", "Match Date (source)", "Format", "Format Label", "Session",
    "Home Team ID", "Home Team Name", "Away Team ID", "Away Team Name",
    "Location", "Bye", "Status", "Home Score", "Away Score",
    # Per-row helper flags driving the Match Day sheet's lookup -- plain
    # scalar formulas referencing that sheet's resolved selection cells
    # (never a cross-range array formula; see _match_day_sheet's own
    # docstring for why). Visible, not hidden -- never a black box.
    "My Team Side?", "Date Matches?", "Format Matches?", "Match Day Selected?",
]
FIXTURES_WIDTHS = {
    "Local Date": 12, "Match Date (source)": 24, "Format": 10, "Format Label": 12, "Session": 16,
    "Home Team ID": 14, "Home Team Name": 26, "Away Team ID": 14, "Away Team Name": 26,
    "Location": 16, "Bye": 8, "Status": 12, "Home Score": 11, "Away Score": 11,
    "My Team Side?": 12, "Date Matches?": 13, "Format Matches?": 14, "Match Day Selected?": 16,
}


def _fixtures_sheet(wb: Workbook, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Every real scheduled/completed match (analytics.ultimate_coach_match_day's
    fixture rows, same data the HTML's Match Day card reads) as its own
    AutoFilter-backed reference table -- the reliable way to see every
    fixture on a date/team/format, including when more than one exists,
    without depending on a dynamic-array formula this workbook's target
    Excel does not support (confirmed via COM: FILTER fails as #NAME?).
    """
    fixtures = sorted(payload.get("fixtures") or [], key=lambda f: str(f.get("match_date") or ""))
    sheet = wb.create_sheet("Fixtures")
    _style_header(sheet, FIXTURES_COLUMNS)
    for i, f in enumerate(fixtures):
        r = i + 2  # header is row 1
        sheet.append(
            [
                f.get("local_date") or ("Unparseable: " + str(f.get("match_date") or "") if f.get("date_unparsed") else ""),
                f.get("match_date") or "",
                f.get("format") or "",
                _format_label(f.get("format") or ""),
                f.get("session_name") or "",
                f.get("home_team_id") or "", f.get("home_team_name") or "",
                f.get("away_team_id") or "", f.get("away_team_name") or "",
                f.get("location") or "",
                "Yes" if f.get("is_bye") else "No",
                f.get("status") or "",
                f.get("home_score"), f.get("away_score"),
                f'=OR(AND(F{r}=\'Match Day\'!$B$10,E{r}=\'Match Day\'!$B$11),AND(H{r}=\'Match Day\'!$B$10,E{r}=\'Match Day\'!$B$11))',
                f"=A{r}='Match Day'!$B$4",
                f'=IF(\'Match Day\'!$B$6="{BOTH_EIGHT_NINE_LABEL}",OR(C{r}="EIGHT",C{r}="NINE"),C{r}=\'Match Day\'!$B$12)',
                f"=AND(O{r},P{r},Q{r})",
            ]
        )
    _apply_widths(sheet, FIXTURES_COLUMNS, FIXTURES_WIDTHS)
    _autotable(sheet, "Fixtures_Table", FIXTURES_COLUMNS, len(fixtures))
    return fixtures


def _add_dropdown(sheet: Worksheet, cell: str, source_ref: str, *, title: str, message: str) -> None:
    validation = DataValidation(type="list", formula1=source_ref, allow_blank=True)
    validation.errorTitle = title
    validation.error = message
    validation.promptTitle = title
    validation.prompt = message
    sheet.add_data_validation(validation)
    validation.add(cell)


def _coach_dashboard_sheet(wb: Workbook, player_count: int, format_options: list[str]) -> None:
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
    sheet["B6"] = _format_label(format_options[0])

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
    sheet["B12"] = _format_code_formula(format_options, "B6")
    sheet["A13"] = "Pair key"
    sheet["B13"] = '=B10&"|"&B12&"|"&B11'
    sheet["A14"] = "Pair row in Player vs Player"
    sheet["B14"] = '=IFERROR(MATCH(B13,PlayerVsPlayer_Table[Pair Key],0),"")'
    for row in range(10, 15):
        sheet.cell(row=row, column=1).font = MUTED_FONT

    sheet["A17"] = "Player A current SL"
    # A plain IFERROR(INDEX(...),"—") only catches a failed MATCH (unknown
    # player). When the player IS found but their Current SL cell was never
    # written (current_skill_level is None -- openpyxl leaves the cell
    # truly empty rather than writing 0), INDEX returns numeric 0 for that
    # blank cell, which is not an error and reads as a real skill level 0 --
    # not a valid APA skill level, but easy to misread as "verified SL 0"
    # rather than "not captured". Test the indexed value against "" first.
    sheet["B17"] = (
        '=IFERROR(IF(INDEX(Players_Table[Current SL],MATCH(B4,Players_Table[Player Label],0))="",'
        '"—",INDEX(Players_Table[Current SL],MATCH(B4,Players_Table[Player Label],0))),"—")'
    )
    sheet["A18"] = "Player B current SL"
    sheet["B18"] = (
        '=IFERROR(IF(INDEX(Players_Table[Current SL],MATCH(B5,Players_Table[Player Label],0))="",'
        '"—",INDEX(Players_Table[Current SL],MATCH(B5,Players_Table[Player Label],0))),"—")'
    )

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


def _match_day_sheet(
    wb: Workbook, *, my_team_count: int, format_options: list[str]
) -> None:
    """Date + identity-backed My Team + format filter, resolving to the
    real scheduled fixture(s) on the Fixtures sheet -- never a dynamic-
    array formula (unsupported on the target Excel install), never a
    cross-range array-formula MATCH (would need CSE entry on that same
    install): every lookup here is either a plain per-cell formula or a
    MATCH/INDEX/COUNTIF against one pre-built key column, the same
    "pre-join a key, look it up directly" pattern Coach Dashboard's own
    Pair Key already uses. When more than one fixture matches, this sheet
    discloses the count and points at the Fixtures sheet's own AutoFilter
    for all of them -- it never silently picks one.
    """
    sheet = wb.create_sheet("Match Day", 0)
    sheet.sheet_view.showGridLines = False
    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 42

    sheet["A1"] = "Ultimate Coach — Match Day"
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = "Pick a date and your team to see your real scheduled matchup, then compare rosters on Match Night."
    sheet["A2"].font = MUTED_FONT

    sheet["A4"] = "Date (YYYY-MM-DD)"
    sheet["A4"].font = LABEL_FONT
    sheet["B4"] = ""
    sheet["B4"].number_format = "@"  # Text, not an Excel date serial -- compared as text against Fixtures' Local Date.
    sheet["A5"] = "My Team"
    sheet["A5"].font = LABEL_FONT
    sheet["B5"] = ""
    sheet["A6"] = "Format"
    sheet["A6"].font = LABEL_FONT
    format_labels = [_format_label(fmt) for fmt in format_options]
    sheet["B6"] = BOTH_EIGHT_NINE_LABEL

    if my_team_count:
        _add_dropdown(
            sheet, "B5", "MyTeamLabelList",
            title="Unknown team", message="Choose one of your own current teams (see the My Teams sheet).",
        )
    all_format_choices = [BOTH_EIGHT_NINE_LABEL] + format_labels
    _add_dropdown(
        sheet, "B6", '"' + ",".join(all_format_choices) + '"',
        title="Format", message="Choose " + " / ".join(all_format_choices) + ".",
    )

    sheet["A9"] = "Lookup detail"
    sheet["A9"].font = LABEL_FONT
    sheet["A10"] = "My Team external ID"
    sheet["B10"] = '=IFERROR(INDEX(MyTeams_Table[Team External ID],MATCH(B5,MyTeams_Table[Team Label],0)),"")'
    sheet["A11"] = "My Team session"
    sheet["B11"] = '=IFERROR(INDEX(MyTeams_Table[Session Name],MATCH(B5,MyTeams_Table[Team Label],0)),"")'
    sheet["A12"] = "Format code (blank = both 8-Ball/9-Ball)"
    sheet["B12"] = f'=IF(B6="{BOTH_EIGHT_NINE_LABEL}","",{_format_code_formula(format_options, "B6")[1:]})'
    sheet["A13"] = "Matches found"
    sheet["B13"] = '=COUNTIF(Fixtures_Table[Match Day Selected?],TRUE)'
    sheet["A14"] = "Fixture row (meaningful only when exactly 1 found)"
    sheet["B14"] = '=IFERROR(MATCH(TRUE,Fixtures_Table[Match Day Selected?],0),"")'
    for row in range(10, 15):
        sheet.cell(row=row, column=1).font = MUTED_FONT

    sheet["A16"] = "Disclosure"
    sheet["A16"].font = LABEL_FONT
    sheet["B16"] = (
        '=IF(OR(B4="",B5=""),"Choose a date and your team above.",'
        'IF(B13=0,"No scheduled match found for this team/date/format.",'
        'IF(B13>1,B13&" fixtures found for this team/date/format -- never silently picked one. '
        'See the Fixtures sheet, filtered to Match Day Selected? = TRUE, for all of them.",'
        '"1 fixture found -- details below.")))'
    )
    sheet["B16"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[16].height = 48

    sheet["A19"] = "Opponent"
    sheet["A19"].font = LABEL_FONT
    sheet["B19"] = '=IF(B13<>1,"",IF(INDEX(Fixtures_Table[Home Team ID],B14)=B10,INDEX(Fixtures_Table[Away Team Name],B14),INDEX(Fixtures_Table[Home Team Name],B14)))'
    sheet["A20"] = "Side"
    sheet["B20"] = '=IF(B13<>1,"",IF(INDEX(Fixtures_Table[Home Team ID],B14)=B10,"Home","Away"))'
    sheet["A21"] = "Format"
    sheet["B21"] = '=IF(B13<>1,"",INDEX(Fixtures_Table[Format Label],B14))'
    sheet["A22"] = "Session"
    sheet["B22"] = '=IF(B13<>1,"",INDEX(Fixtures_Table[Session],B14))'
    sheet["A23"] = "Date/time (source timezone retained)"
    sheet["B23"] = '=IF(B13<>1,"",INDEX(Fixtures_Table[Match Date (source)],B14))'
    sheet["A24"] = "Location"
    sheet["B24"] = '=IF(B13<>1,"",IF(INDEX(Fixtures_Table[Location],B14)="","No data",INDEX(Fixtures_Table[Location],B14)))'
    sheet["A25"] = "Bye"
    sheet["B25"] = '=IF(B13<>1,"",INDEX(Fixtures_Table[Bye],B14))'
    sheet["A26"] = "Schedule/result status"
    sheet["B26"] = '=IF(B13<>1,"",INDEX(Fixtures_Table[Status],B14))'
    for row in range(19, 27):
        sheet.cell(row=row, column=1).font = MUTED_FONT

    sheet["A29"] = "To compare rosters, select these on the Match Night sheet"
    sheet["A29"].font = LABEL_FONT
    sheet["A30"] = "Our Team (Match Night cell B5)"
    sheet["B30"] = '=IF(B13<>1,"",B5)'
    sheet["A31"] = "Opponent Team (Match Night cell C5)"
    sheet["B31"] = (
        '=IF(B13<>1,"",IFERROR(INDEX(Teams_Table[Team],MATCH('
        'IF(INDEX(Fixtures_Table[Home Team ID],B14)=B10,INDEX(Fixtures_Table[Away Team ID],B14),INDEX(Fixtures_Table[Home Team ID],B14))&"|"&B11,'
        'Teams_Table[Combo Key],0)),"No current roster captured for this opponent"))'
    )
    for row in (30, 31):
        sheet.cell(row=row, column=1).font = MUTED_FONT
    sheet["A33"] = (
        "Rosters shown on Match Night are each team's CURRENT roster, not a reconstruction "
        "of who actually played on the chosen date -- this data source doesn't capture "
        "historical lineups, so no date-specific lineup accuracy is promised."
    )
    sheet["A33"].font = MUTED_FONT
    sheet["A33"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.merge_cells("A33:B33")
    sheet.row_dimensions[33].height = 48

    if not my_team_count:
        sheet["A36"] = (
            'No viewer identity configured or no current team found -- see the My Teams sheet '
            'for the exact reason. Set "ultimate_coach.viewer_member_external_id" in '
            "apa_config.yaml to your own APA member id to enable this sheet."
        )
        sheet["A36"].font = MUTED_FONT
        sheet["A36"].alignment = Alignment(wrap_text=True, vertical="top")
        sheet.merge_cells("A36:B36")
        sheet.row_dimensions[36].height = 32


def build_workbook(
    payload: dict[str, Any],
    *,
    built_at: str = "",
    source_db: str = "",
    viewer_member_external_id: str | None = None,
) -> Workbook:
    wb = Workbook()
    _build_info_sheet(wb, payload, built_at=built_at, source_db=source_db)
    _data_trust_sheet(wb, payload)
    _players_sheet(wb, payload)
    rosters = _team_rosters_sheet(wb, payload)
    _teams_sheet(wb, rosters)
    pairs = _player_vs_player_sheet(wb, payload)
    my_teams = _my_teams_sheet(wb, payload, rosters, viewer_member_external_id=viewer_member_external_id)
    _fixtures_sheet(wb, payload)

    player_count = len(payload.get("players") or [])
    team_count = len({r["team_scope_key"] for r in rosters})

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
    if my_teams:
        wb.defined_names["MyTeamLabelList"] = DefinedName(
            "MyTeamLabelList", attr_text="'My Teams'!MyTeams_Table[Team Label]"
        )

    _match_night_sheet(wb, team_count)
    _coach_dashboard_sheet(wb, player_count, _dashboard_format_options(pairs))
    _match_day_sheet(
        wb, my_team_count=len(my_teams), format_options=_match_day_format_options(payload, pairs)
    )

    wb.active = wb["Match Day"]
    return wb


def write_workbook(
    payload: dict[str, Any],
    path: str | Path,
    *,
    built_at: str = "",
    source_db: str = "",
    viewer_member_external_id: str | None = None,
) -> Path:
    workbook = build_workbook(
        payload, built_at=built_at, source_db=source_db, viewer_member_external_id=viewer_member_external_id
    )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path
