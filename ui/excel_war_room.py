"""Excel: the coach-facing half of the Ultimate Coach workbook.

Match Day is the control panel; everything else follows it:

    Match Day        Player -> Team -> Format -> Scheduled date -> Fixture
                     (yellow inputs), then the EFFECTIVE matchup (calculated).
    War Room         Captain's War Room for tonight: rosters, best-supported
                     sends, risks, Lineup Lab snapshot, color matrix, inspect
                     views, direct meetings, team comparison. Optional local
                     overrides (blank = follow Match Day).
    Lineup Lab       The captain's own planning marks (availability, lineup,
                     played, notes) + instant results. Marks are inputs, never
                     evidence.
    Scouting Cards   One card per opponent player.
    Captain Packet   Printable: page 1 summary, page 2+ detail.
    Coach Dashboard  Player A = you, Player B = an opponent from tonight's
                     roster or an explicit "All players..." choice.
    Engine           Every calculated selection as a named cell, kept apart
                     from inputs so exploring can't break the links.

Excel constraints honoured: ordinary formulas, tables, defined names and
data-validation dropdowns only -- no VBA/macros, no COM, no dynamic-array or
volatile functions. Where Excel can't do what the HTML does (erase a stale
input, move inputs when a roster changes, list every shared opponent), the
closest reliable workflow is used and the limitation is stated on-sheet.

Evidence rules come from analytics.ultimate_coach_matchup_evidence (ranking)
and analytics.ultimate_coach_war_room (categories, best sends, risks, cards);
nothing here re-scores or blends evidence.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.worksheet.pagebreak import Break

import ui.export_excel_ultimate_coach as base
from analytics.ultimate_coach_match_day import DEFAULT_MATCH_DAY_TIMEZONE, excel_date_serial
from analytics.ultimate_coach_matchup_evidence import (
    build_pair_index,
    fixture_scope_pairs,
    format_label,
    members_by_scope,
)
from analytics.ultimate_coach_war_room import (
    CATEGORY_LABELS,
    DIRECT_ORDER_NOTE,
    build_local_date,
    date_label,
    default_matchup,
    freshness,
    meetings_index,
    scope_dates,
    sl_bucket_index,
    stale_by_scope,
    stale_warning,
    suggested_date,
    war_room_pair,
    save_record_text,
    COACH_TAGS,
    MATCH_NIGHT_GUIDE,
    ONBOARDING_LIMITS,
    ONBOARDING_WHAT,
)

ME_COLUMNS = ["Key", "Rank", "Player", "SL", "Direct Record", "Shared-Opponent Evidence", "Basis", "Rows",
              "Player ID", "Category", "Cell", "Reason", "Captain Cell", "Rank Group", "Save Record",
              "Direct Wins", "Direct Games"]
TC_COLUMNS = [
    "Pair Key", "Format", "Our Team", "Opponent Team", "Our Rostered", "Opp Rostered", "Our Captured SL",
    "Opp Captured SL", "Our SL Total", "Opp SL Total", "Our Games", "Opp Games", "Our No-Game Players",
    "Opp No-Game Players", "Direct Meetings", "Opponents Met", "Pairings",
]
THREATS_COLUMNS = ["Key", "Opp Player ID", "Threat"]
CONCERNING_COLUMNS = ["Key", "Our Player ID", "Opp Player ID", "Pairing"]
MEETINGS_COLUMNS = ["Key", "Date", "Our Player", "Opponent", "Result", "Our SL", "Their SL", "Session", "Points",
                    "Pair Key"]
SCOUTING_COLUMNS = ["Key", "Opponent", "SL", "Team Record", "Lifetime", "Sample", "Vs Our Roster", "Met List",
                    "Shared Summary", "By SL", "Winning SL", "Losing SL", "Missing", "Quick Read"]
DATEKEYS_COLUMNS = ["Key", "Group Key", "Serial", "Date Display"]
SUGGESTED_COLUMNS = ["Group Key", "Serial", "Date Display"]

ALL_PLAYERS_CHOICE = "All players…"
AVAILABILITY_CHOICES = ["Available", "Unavailable", "Unknown"]
LINEUP_CHOICES = ["Planned", "Played"]
MEETING_SLOTS = 40

def _cf_fill(rgb: str) -> PatternFill:
    """A fill for CONDITIONAL formatting. Excel paints a conditional (dxf) solid fill from its background
    colour, so both colours are set -- with only fgColor the rule fires but nothing is painted (real-Excel
    UAT: uncoloured matrix, invisible packet card headers)."""
    return PatternFill(fill_type="solid", fgColor=rgb, bgColor=rgb)


CAT_FILLS = {code: _cf_fill(rgb) for code, rgb in
             (("G", "CFE8D4"), ("R", "F4CCCC"), ("E", "FFF0B3"), ("I", "FFF0B3"), ("X", "E3E3E3"))}
CARD_HEAD_FILL_RGB = "E8DCCB"   # light rail tint; the name is dark text so it prints readably without any fill
CALC_FILL = PatternFill("solid", fgColor="EEF3EF")
BIG_LINK = Font(color="1F5C99", underline="single", bold=True, size=12)
SMALL = Font(size=9)
WARN_FONT = Font(bold=True, color="8A5A00")


# ---------------------------------------------------------------------------
# Lookup tables (static, precomputed per directed team pairing with a fixture)
# ---------------------------------------------------------------------------

def _text(value: Any, empty: str = "No data") -> str:
    return empty if value is None or value == "" else str(value)


def write_lookup_tables(wb, *, payload: dict[str, Any], match_day: dict[str, Any], rosters: list[dict[str, Any]],
                        teams: list[dict[str, Any]], pairs: list[dict[str, Any]], built_at: str) -> dict[str, Any]:
    players = payload.get("players") or []
    labels = base._player_labels(players)
    tz_name = match_day.get("display_timezone") or DEFAULT_MATCH_DAY_TIMEZONE
    index = build_pair_index(pairs)
    members = members_by_scope(rosters, players)
    roster_ids = {r["player_id"] for r in rosters}
    sl_index = sl_bucket_index(payload.get("evidence") or [], roster_ids)
    games = meetings_index(payload.get("evidence") or [], roster_ids, tz_name)
    players_by_id = {p["id"]: p for p in players}
    label_by_scope = {t["team_scope_key"]: t["team_label"] for t in teams}
    session_by_scope = {t["team_scope_key"]: t["session_name"] for t in teams}

    me_rows: list[list[Any]] = []
    tc_rows: list[list[Any]] = []
    threat_rows: list[list[Any]] = []
    concern_rows: list[list[Any]] = []
    meeting_rows: list[list[Any]] = []
    card_rows: list[list[Any]] = []
    max_threats = max_concern = max_meetings = 0
    for our, opp, fmt in fixture_scope_pairs(match_day):
        if our not in members or opp not in members:
            continue
        wr = war_room_pair(members[our], members[opp], index, fmt, sl_index=sl_index, meetings=games,
                           players_by_id=players_by_id, session_name=session_by_scope.get(opp, ""))
        key = f"{our}|{opp}|{fmt}"
        c = wr["comparison"]
        tc_rows.append([
            key, c["format"], label_by_scope.get(our, our), label_by_scope.get(opp, opp),
            c["ours"]["rostered"], c["theirs"]["rostered"], c["ours"]["captured_sl"], c["theirs"]["captured_sl"],
            c["ours"]["sl_total"], c["theirs"]["sl_total"], c["ours"]["games"], c["theirs"]["games"],
            c["ours"]["no_games"], c["theirs"]["no_games"], c["direct_meetings"], c["opponents_met"], c["pairings"],
        ])
        for j, block in enumerate(wr["blocks"], start=1):
            me_rows.append([f"{key}|{j}", "vs", block["opponent_label"], base._sl_display(block["opponent"]),
                            block["opponent_sample"], "—", block["note"], len(block["rows"]),
                            block["opponent"]["id"], "—", "—", "—", "—", "—", "—", 0, 0])
            for row in block["rows"]:
                me_rows.append([None, row["rank"], row["player"], base._sl_display(row["member"]), row["direct_text"],
                                row["shared_text"], row["basis"], row["position"], row["member"]["id"],
                                row["category"], row["cell"], row["reason"], row["captain"],
                                # Next Send medals: players with the same evidence share a rank group (and a medal).
                                int(row["rank"].rstrip("=")) if row["category"] in ("G", "E") else "—", save_record_text(row),
                                row["direct"][0] if row["direct"] else 0, row["direct"][1] if row["direct"] else 0])
        for k, threat in enumerate(wr["threats"], start=1):
            threat_rows.append([f"{key}|{k}", threat["opponent"]["id"], threat["threat_text"]])
        max_threats = max(max_threats, len(wr["threats"]))
        for k, item in enumerate(wr["concerning"], start=1):
            concern_rows.append([f"{key}|{k}", item["our"]["id"], item["opp"]["id"], item["text"]])
        max_concern = max(max_concern, len(wr["concerning"]))
        for k, game in enumerate(wr["meetings"], start=1):
            meeting_rows.append([f"{key}|{k}", game["date"], labels.get(str(game["our"]["external_id"]), game["our"]["name"]),
                                 labels.get(str(game["opp"]["external_id"]), game["opp"]["name"]),
                                 _text(game["result"]), _text(game["own_sl"]), _text(game["opp_sl"]),
                                 _text(game["session"]), _text(game["points"]), key])
        max_meetings = max(max_meetings, len(wr["meetings"]))
        for j, card in enumerate(wr["cards"], start=1):
            card_rows.append([f"{key}|{j}", card["label"], card["sl"], card["team_record"], card["lifetime"],
                              card["sample"], card["vs_ours"], card["met_list"], card["shared_summary"],
                              card["by_sl"], card["winning_sl"], card["losing_sl"], card["missing"],
                              card["quick_read"]])

    def table(name: str, sheet_name: str, columns: list[str], rows: list[list[Any]], widths: dict[str, int]) -> None:
        ws = wb.create_sheet(sheet_name)
        base._style_header(ws, columns)
        for row in rows:
            ws.append(row)
        base._apply_widths(ws, columns, widths)
        base._autotable(ws, name, columns, len(rows))

    table("TeamComparison_Table", "Team Comparison", TC_COLUMNS, tc_rows,
          {"Pair Key": 40, "Our Team": 32, "Opponent Team": 32, "Direct Meetings": 28, "Pairings": 44})
    table("MatchupEvidence_Table", "Matchup Evidence", ME_COLUMNS, me_rows,
          {"Key": 44, "Rank": 6, "Player": 40, "SL": 8, "Direct Record": 20, "Shared-Opponent Evidence": 60,
           "Basis": 70, "Rows": 6, "Player ID": 10, "Category": 9, "Cell": 26, "Reason": 70})
    table("Threats_Table", "Threats", THREATS_COLUMNS, threat_rows, {"Key": 44, "Threat": 90})
    table("Concerning_Table", "Concerning", CONCERNING_COLUMNS, concern_rows, {"Key": 44, "Pairing": 90})
    table("Meetings_Table", "Meetings", MEETINGS_COLUMNS, meeting_rows,
          {"Key": 44, "Date": 17, "Our Player": 38, "Opponent": 38})
    table("Scouting_Table", "Scouting", SCOUTING_COLUMNS, card_rows,
          {"Key": 44, "Opponent": 38, "Vs Our Roster": 50, "Met List": 70, "By SL": 50, "Missing": 50, "Quick Read": 90})

    build_local = build_local_date(built_at, tz_name)
    dates = scope_dates(match_day)
    date_rows, suggested_rows = [], []
    max_dates = 0
    for (scope, code), isos in sorted(dates.items()):
        group = f"{scope}|{code}"
        for k, iso in enumerate(isos, start=1):
            date_rows.append([f"{group}|{k}", group, excel_date_serial(iso), date_label(iso)])
        max_dates = max(max_dates, len(isos))
        suggestion = suggested_date(isos, build_local)
        if suggestion:
            suggested_rows.append([group, excel_date_serial(suggestion), date_label(suggestion)])
    table("DateKeys_Table", "Date Keys", DATEKEYS_COLUMNS, date_rows, {"Key": 50, "Group Key": 44, "Date Display": 18})
    table("SuggestedDates_Table", "Suggested Dates", SUGGESTED_COLUMNS, suggested_rows,
          {"Group Key": 44, "Date Display": 18})
    # Per team scope: earlier fixtures that still have no result in this snapshot (the captain's own gap).
    table("StaleScopes_Table", "Stale Scopes", ["Scope Key", "Unplayed Before Build"],
          [[scope, n] for scope, n in sorted(stale_by_scope(match_day, build_local).items())],
          {"Scope Key": 44, "Unplayed Before Build": 22})
    return {
        "pairs": len(tc_rows), "evidence_rows": len(me_rows), "max_threats": max_threats,
        "max_concerning": max_concern, "max_meetings": max_meetings, "max_dates": max_dates,
        "build_local": build_local, "freshness": freshness(match_day, build_local), "tz": tz_name,
    }


# ---------------------------------------------------------------------------
# Engine: every calculated selection as a named cell
# ---------------------------------------------------------------------------

class Engine:
    def __init__(self, wb):
        self.wb = wb
        self.ws = wb.create_sheet("Engine")
        self.ws["A1"] = "Engine — calculated selections (do not edit)"
        self.ws["A1"].font = base.TITLE_FONT
        self.ws["A2"] = ("Every interactive tab reads these named cells. They are formulas derived from the yellow "
                         "input cells on Match Day, War Room, Lineup Lab and Coach Dashboard — editing here would break "
                         "the links, so change the inputs instead.")
        self.ws["A2"].font = base.MUTED_FONT
        for letter, width in zip("ABCDEFGHIJ", (34, 46, 30, 16, 16, 16, 16, 16, 16, 16)):
            self.ws.column_dimensions[letter].width = width
        self.row = 4

    def name(self, name: str, ref: str) -> None:
        self.wb.defined_names[name] = DefinedName(name, attr_text=ref)

    def cell(self, name: str, label: str, formula: str) -> str:
        r = self.row
        self.row += 1
        self.ws.cell(row=r, column=1, value=label).font = base.HELPER_FONT
        self.ws.cell(row=r, column=2, value=formula)
        self.ws.cell(row=r, column=3, value=name).font = base.HELPER_FONT
        self.name(name, f"Engine!$B${r}")
        return name

    def section(self, title: str) -> None:
        self.row += 1
        self.ws.cell(row=self.row, column=1, value=title).font = base.SUBHEAD_FONT
        self.row += 1

    def block(self, title: str, n: int, columns: list[tuple[str, Any]]) -> dict[str, tuple[str, int, int]]:
        """n rows; columns: (name, formula_fn(k, row) -> str). Registers a range name per column."""
        self.section(title)
        first = self.row
        out = {}
        for c, (name, _) in enumerate(columns, start=2):
            self.ws.cell(row=first - 1, column=c, value=name).font = base.HELPER_FONT
        for k in range(1, n + 1):
            r = first + k - 1
            self.ws.cell(row=r, column=1, value=f"{title} {k}").font = base.HELPER_FONT
            for c, (name, fn) in enumerate(columns, start=2):
                self.ws.cell(row=r, column=c, value=fn(k, r))
        last = first + n - 1
        for c, (name, _) in enumerate(columns, start=2):
            letter = get_column_letter(c)
            self.name(name, f"Engine!${letter}${first}:${letter}${last}")
            out[name] = (letter, first, last)
        self.row = last + 1
        return out


def _fmt_label_formula(code_ref: str) -> str:
    return (f'IF({code_ref}="EIGHT","8-Ball",IF({code_ref}="NINE","9-Ball",IF({code_ref}="MASTERS","Masters",'
            f'IF({code_ref}="MASTERS ALT","Masters Alt",{code_ref}))))')


def build_engine(wb, *, slots: dict[str, int], tz_name: str) -> dict[str, Any]:
    e = Engine(wb)
    R, T, D, F = slots["roster"], slots["teams"], slots["dates"], slots["fixtures"]
    md = "'Match Day'!"

    def guard(ref: str) -> str:
        return f'IF({ref}="","",{ref})'

    # ---- Match Day: player -> team -> format -> date -> fixture ----
    e.section("Match Day — player")
    e.cell("uc_ViewerKey", "Player record ID",
           f'=IF({md}$B$6="","",IF(ISNUMBER({md}$B$6),TEXT({md}$B$6,"0"),IFERROR(INDEX(Players_Table[External ID],'
           f'MATCH(TRIM({md}$B$6),Players_Table[Player Label],0)),TRIM({md}$B$6))))')
    e.cell("uc_ViewerName", "Player name",
           '=IF(uc_ViewerKey="","",IFERROR(INDEX(Players_Table[Player Name],MATCH(uc_ViewerKey,Players_Table[External ID],0)),""))')
    e.cell("uc_ViewerLabel", "Player label", '=IF(uc_ViewerKey="","",IFERROR(INDEX(Players_Table[Player Label],MATCH(uc_ViewerKey,Players_Table[External ID],0)),""))')
    e.cell("uc_TeamCount", "Current team scopes",
           '=IF(uc_ViewerName="",0,COUNTIF(PlayerTeams_Table[APA Record ID],uc_ViewerKey))')
    e.cell("uc_FormatInput", "Format input", "=" + guard(f"{md}$B$8"))
    e.cell("uc_Code", "Format filter code",
           '=IF(OR(uc_FormatInput="",uc_FormatInput="8-Ball & 9-Ball"),"89",IF(uc_FormatInput="All recorded formats","ALL","F:"&uc_FormatInput))')
    e.cell("uc_FormatLabel", "Format label",
           '=IF(uc_Code="89","8-Ball & 9-Ball",IF(uc_Code="ALL","All recorded formats",uc_FormatInput))')
    teams = e.block("Team slot", T, [
        ("uc_TeamList", lambda k, r: f'=IF(uc_ViewerName="","",IFERROR(INDEX(PlayerTeams_Table[Team],'
                                     f'MATCH(uc_ViewerKey&"|{k}",PlayerTeams_Table[Viewer Slot Key],0)),""))'),
        ("uc_TeamScopes", lambda k, r: f'=IF(B{r}="","",IFERROR(INDEX(PlayerTeams_Table[Team Scope Key],'
                                       f'MATCH(uc_ViewerKey&"|{k}",PlayerTeams_Table[Viewer Slot Key],0)),""))'),
        ("uc_TeamNextSerial", lambda k, r: f'=IF(C{r}="","",IFERROR(INDEX(SuggestedDates_Table[Serial],'
                                           f'MATCH(C{r}&"|"&uc_Code,SuggestedDates_Table[Group Key],0)),""))'),
        ("uc_TeamNextDisplay", lambda k, r: f'=IF(C{r}="","",IFERROR(INDEX(SuggestedDates_Table[Date Display],'
                                            f'MATCH(C{r}&"|"&uc_Code,SuggestedDates_Table[Group Key],0)),"No upcoming fixture captured"))'),
    ])
    e.section("Match Day — team")
    e.cell("uc_TeamInput", "Team input", "=" + guard(f"{md}$B$7"))
    e.cell("uc_TeamInputValid", "Team input valid", '=AND(uc_TeamInput<>"",COUNTIF(uc_TeamList,uc_TeamInput)>0)')
    e.cell("uc_EarliestSerial", "Earliest upcoming date among the player's teams", "=MIN(uc_TeamNextSerial)")
    e.cell("uc_EarliestSlot", "Team slot with the earliest upcoming date",
           '=IF(uc_EarliestSerial=0,"",MATCH(uc_EarliestSerial,uc_TeamNextSerial,0))')
    e.cell("uc_TeamLabel", "Effective team",
           '=IF(uc_TeamInputValid,uc_TeamInput,IF(uc_TeamCount=0,"",IF(uc_TeamCount=1,INDEX(uc_TeamList,1),'
           'IF(uc_EarliestSlot<>"",INDEX(uc_TeamList,uc_EarliestSlot),""))))')
    e.cell("uc_TeamMsg", "Team note",
           '=IF(uc_ViewerName="","",IF(uc_TeamCount=0,"No current team captured for "&uc_ViewerName&".",'
           'IF(uc_TeamInputValid,"Your choice.",IF(uc_TeamInput<>"","⚠ “"&uc_TeamInput&"” is not one of "&uc_ViewerName&'
           '"’s current teams — ignored. ","")&IF(uc_TeamLabel="","Choose a team.",IF(uc_TeamCount=1,"Their only current team.",'
           '"Suggested: the team with the earliest scheduled date on or after the build date.")))))')
    e.cell("uc_TeamScope", "Effective team scope key",
           '=IF(uc_TeamLabel="","",IFERROR(INDEX(Teams_Table[Scope Key],MATCH(uc_TeamLabel,Teams_Table[Team],0)),""))')
    e.cell("uc_TeamStale", "Team fixtures before the build with no result",
           '=IF(uc_TeamScope="",0,IFERROR(INDEX(StaleScopes_Table[Unplayed Before Build],'
           'MATCH(uc_TeamScope,StaleScopes_Table[Scope Key],0)),0))')
    e.cell("uc_TeamStaleText", "Team stale note",
           '=IF(uc_TeamStale=0,"","⚠ "&uc_TeamLabel&": "&uc_TeamStale&" earlier fixture"&IF(uc_TeamStale=1," has",'
           '"s have")&" no result in this snapshot. ")')
    e.cell("uc_DateGroup", "Date group key", '=IF(uc_TeamScope="","",uc_TeamScope&"|"&uc_Code)')
    e.cell("uc_DateCount", "Scheduled dates", '=IF(uc_DateGroup="",0,COUNTIF(DateKeys_Table[Group Key],uc_DateGroup))')
    dates = e.block("Date slot", D, [
        ("uc_DateList", lambda k, r: f'=IF({k}>uc_DateCount,"",IFERROR(INDEX(DateKeys_Table[Date Display],'
                                     f'MATCH(uc_DateGroup&"|{k}",DateKeys_Table[Key],0)),""))'),
        ("uc_DateSerials", lambda k, r: f'=IF(B{r}="","",INDEX(DateKeys_Table[Serial],'
                                        f'MATCH(uc_DateGroup&"|{k}",DateKeys_Table[Key],0)))'),
    ])
    e.section("Match Day — date")
    e.cell("uc_SuggestedSerial", "Suggested date (serial)",
           '=IF(uc_DateGroup="","",IFERROR(INDEX(SuggestedDates_Table[Serial],MATCH(uc_DateGroup,SuggestedDates_Table[Group Key],0)),""))')
    e.cell("uc_DateInput", "Date input", "=" + guard(f"{md}$B$9"))
    e.cell("uc_DateInputSerial", "Date input (serial)",
           '=IF(uc_DateInput="","",IF(ISNUMBER(uc_DateInput),INT(uc_DateInput),IFERROR(INDEX(uc_DateSerials,'
           'MATCH(uc_DateInput,uc_DateList,0)),IFERROR(INT(DATEVALUE(uc_DateInput)),"bad"))))')
    e.cell("uc_DateInputValid", "Date input valid",
           '=IF(ISNUMBER(uc_DateInputSerial),COUNTIF(uc_DateSerials,uc_DateInputSerial)>0,FALSE)')
    e.cell("uc_DateSerial", "Effective date (serial)",
           '=IF(uc_DateInput="",uc_SuggestedSerial,IF(uc_DateInputValid,uc_DateInputSerial,""))')
    e.cell("uc_DateDisplay", "Effective date",
           '=IF(uc_DateSerial="","",IFERROR(INDEX(uc_DateList,MATCH(uc_DateSerial,uc_DateSerials,0)),""))')
    e.cell("uc_DateMsg", "Date note",
           '=IF(uc_TeamScope="","",IF(uc_DateInput="",IF(uc_SuggestedSerial="","No upcoming scheduled date was captured '
           'for this team and format — choose a date.","Suggested: the earliest scheduled date on or after the build date."),'
           'IF(uc_DateInputValid,"Your choice.","⚠ “"&IF(ISNUMBER(uc_DateInput),TEXT(uc_DateInput,"dddd, mmm d, yyyy"),'
           'uc_DateInput)&"” has no "&uc_TeamLabel&" fixture ("&uc_FormatLabel&") — ignored. Pick a date from the list.")))')
    e.cell("uc_FixGroup", "Fixture group key",
           '=IF(OR(uc_TeamScope="",uc_DateSerial=""),"",uc_TeamScope&"|"&uc_DateSerial&"|"&uc_Code)')
    e.cell("uc_FixCount", "Fixtures on the date",
           '=IF(uc_FixGroup="",0,COUNTIF(ScheduleKeys_Table[Group Key],uc_FixGroup))')
    fixtures = e.block("Fixture slot", F, [
        ("uc_FixRows", lambda k, r: f'=IF({k}>uc_FixCount,"",IFERROR(INDEX(ScheduleKeys_Table[Schedule Row],'
                                    f'MATCH(uc_FixGroup&"|{k}",ScheduleKeys_Table[Slot Key],0)),""))'),
        ("uc_FixtureList", lambda k, r: f'=IF(B{r}="","","{k} · vs "&INDEX(Schedule_Table[Opponent],B{r})&" · "&'
                                        f'INDEX(Schedule_Table[Kickoff],B{r})&" · "&INDEX(Schedule_Table[Home/Away],B{r})&'
                                        f'" · "&INDEX(Schedule_Table[Format],B{r}))'),
    ])
    e.section("Match Day — fixture")
    e.cell("uc_FixInput", "Fixture input", "=" + guard(f"{md}$B$10"))
    # A blank input must not MATCH an empty ("") fixture slot -- Excel matches zero-length text.
    e.cell("uc_FixChoice", "Chosen fixture slot",
           '=IF(uc_FixCount=0,"",IF(uc_FixCount=1,1,IF(uc_FixInput="","",IFERROR(MATCH(uc_FixInput,uc_FixtureList,0),""))))')
    e.cell("uc_SchedRow", "Schedule row", '=IF(uc_FixChoice="","",INDEX(uc_FixRows,uc_FixChoice))')
    e.cell("uc_FixMsg", "Fixture note",
           '=IF(uc_DateSerial="","",IF(uc_FixCount=0,"No fixture on this date.",IF(uc_FixCount=1,"One fixture on this date — '
           'used automatically.",IF(uc_FixChoice="",IF(uc_FixInput<>"","⚠ The fixture you picked is not on this date — ignored. ",'
           '"")&uc_FixCount&" fixtures on this date — pick one in the Fixture cell (none is chosen for you).","Your choice of "&'
           'uc_FixCount&" fixtures on this date."))))')
    e.cell("uc_OppScope", "Opponent scope key",
           '=IF(uc_SchedRow="","",IF(INDEX(Schedule_Table[Opponent Scope Key],uc_SchedRow)="—","",'
           'INDEX(Schedule_Table[Opponent Scope Key],uc_SchedRow)))')
    e.cell("uc_OppLabel", "Opponent team", '=IF(uc_OppScope="","",INDEX(Schedule_Table[Opponent Team],uc_SchedRow))')
    e.cell("uc_Category", "Fixture format code", '=IF(uc_SchedRow="","",INDEX(Schedule_Table[Format Category],uc_SchedRow))')
    e.cell("uc_PairKey", "Match Day evidence pair key",
           '=IF(OR(uc_TeamScope="",uc_OppScope="",uc_Category=""),"",uc_TeamScope&"|"&uc_OppScope&"|"&uc_Category)')
    e.cell("uc_Fixture", "Fixture line",
           f'=IF(uc_SchedRow="","",INDEX(Schedule_Table[Date Display],uc_SchedRow)&" · "&INDEX(Schedule_Table[Kickoff],'
           f'uc_SchedRow)&" ({tz_name}) · "&INDEX(Schedule_Table[Home/Away],uc_SchedRow)&" vs "&INDEX(Schedule_Table[Opponent],'
           f'uc_SchedRow)&" · "&INDEX(Schedule_Table[Format],uc_SchedRow))')
    e.cell("uc_Venue", "Venue and status",
           '=IF(uc_SchedRow="","","Venue: "&INDEX(Schedule_Table[Venue],uc_SchedRow)&" · Status: "&INDEX(Schedule_Table[Status],'
           'uc_SchedRow)&" · Score (home–away): "&INDEX(Schedule_Table[Score (home–away)],uc_SchedRow)&" · Session: "&'
           'INDEX(Schedule_Table[Session],uc_SchedRow))')
    # The exact fixture a Lineup Lab plan belongs to: unique per fixture (it ends with the match id), so
    # two matches on the same day -- even against the same opponent -- never share marks (GPT audit #84).
    e.cell("uc_PlanKey", "Fixture plan key",
           '=IF(uc_SchedRow="","",INDEX(Schedule_Table[Date Display],uc_SchedRow)&" · "&INDEX(Schedule_Table[Kickoff],'
           'uc_SchedRow)&" · "&INDEX(Schedule_Table[Home/Away],uc_SchedRow)&" vs "&INDEX(Schedule_Table[Opponent],uc_SchedRow)&'
           '" · match "&INDEX(Schedule_Table[Match ID],uc_SchedRow))')
    e.name("uc_PlanKeyList", f"Engine!$B${e.row - 1}")
    e.cell("uc_OppMsg", "Opponent roster note",
           '=IF(uc_SchedRow="","",IF(uc_OppScope="","Opponent roster: "&INDEX(Schedule_Table[Opponent Roster],uc_SchedRow)&".",'
           '"Opponent roster: "&uc_OppLabel))')

    # ---- War Room effective (optional local overrides) ----
    wr = "'War Room'!"
    e.section("War Room — effective teams")
    e.cell("wr_OurInput", "Our team override", "=" + guard(f"{wr}$C$5"))
    e.cell("wr_OppInput", "Opponent override", "=" + guard(f"{wr}$C$6"))
    e.cell("wr_OurValid", "Our override valid", '=AND(wr_OurInput<>"",COUNTIF(Teams_Table[Team],wr_OurInput)>0)')
    e.cell("wr_OppValid", "Opponent override valid", '=AND(wr_OppInput<>"",COUNTIF(Teams_Table[Team],wr_OppInput)>0)')
    e.cell("wr_Local", "Using local selections", "=OR(wr_OurValid,wr_OppValid)")
    e.cell("wr_OurLabel", "Effective our team", "=IF(wr_OurValid,wr_OurInput,uc_TeamLabel)")
    e.cell("wr_OppLabel", "Effective opponent team", "=IF(wr_OppValid,wr_OppInput,uc_OppLabel)")
    e.cell("wr_OurScope", "Our scope key",
           '=IF(wr_OurLabel="","",IFERROR(INDEX(Teams_Table[Scope Key],MATCH(wr_OurLabel,Teams_Table[Team],0)),""))')
    e.cell("wr_OppScope", "Opponent scope key",
           '=IF(wr_OppLabel="","",IFERROR(INDEX(Teams_Table[Scope Key],MATCH(wr_OppLabel,Teams_Table[Team],0)),""))')
    e.cell("wr_Category", "Format code",
           '=IF(wr_Local,IFERROR(INDEX(Teams_Table[Format Category],MATCH(wr_OurLabel,Teams_Table[Team],0)),""),uc_Category)')
    e.cell("wr_FormatLabel", "Format", "=" + _fmt_label_formula("wr_Category"))
    e.cell("wr_PairKey", "Evidence pair key",
           '=IF(OR(wr_OurScope="",wr_OppScope="",wr_Category="",wr_Category="No data"),"",wr_OurScope&"|"&wr_OppScope&"|"&wr_Category)')
    e.cell("wr_HasEvidence", "Precomputed evidence exists",
           '=IF(wr_PairKey="",FALSE,ISNUMBER(MATCH(wr_PairKey&"|1",MatchupEvidence_Table[Key],0)))')
    e.cell("wr_Status", "Status line",
           '=IF(wr_Local,"Using local selections: ","Following Match Day: ")&IF(wr_OurLabel="","(no team)",wr_OurLabel)&'
           '" vs "&IF(wr_OppLabel="","(no opponent)",wr_OppLabel)&IF(wr_Local,""," · "&IF(uc_DateDisplay="","no date",'
           'uc_DateDisplay))&IF(wr_FormatLabel="",""," · "&wr_FormatLabel)')
    e.cell("wr_Msg", "War Room note",
           '=IF(AND(wr_OurInput<>"",NOT(wr_OurValid)),"⚠ “"&wr_OurInput&"” is not a team label — ignored. ","")&'
           'IF(AND(wr_OppInput<>"",NOT(wr_OppValid)),"⚠ “"&wr_OppInput&"” is not a team label — ignored. ","")&'
           'IF(wr_OurLabel="","Choose your team on Match Day.",IF(wr_OppLabel="","No opponent roster for the selected fixture.",'
           'IF(wr_HasEvidence,"","Evidence comparisons are precomputed for teams scheduled to play each other this session; '
           'this pairing has no scheduled fixture (or the formats differ), so only rosters are shown.")))')

    # ---- Lineup Lab guard ----
    ll = "'Lineup Lab'!"
    e.section("Lineup Lab — which teams the marks belong to")
    e.cell("ll_OurTeam", "Planning for our team", "=" + guard(f"{ll}$C$5"))
    e.cell("ll_OppTeam", "Planning for opponent", "=" + guard(f"{ll}$C$6"))
    # Availability / lineup / played describe ONE match night (GPT audit #84: team-only keys leaked
    # "Played" into the next fixture). They apply only when Lineup Lab's match date is the War Room's
    # Match Day date; a War Room local exploration (no fixture) applies them only with the date blank.
    # Coach notes describe a player and follow the opponent team regardless of date.
    e.cell("ll_PlanIn", "Planning for fixture", "=" + guard(f"{ll}$C$9"))
    e.cell("ll_FixOK", "Marks belong to the shown fixture",
           '=IF(wr_Local,ll_PlanIn="",AND(ll_PlanIn<>"",uc_PlanKey<>"",ll_PlanIn=uc_PlanKey))')
    e.cell("ll_OurTeamOK", "Our team matches", '=AND(ll_OurTeam<>"",ll_OurTeam=wr_OurLabel)')
    e.cell("ll_OppTeamOK", "Opponent team matches (notes)", '=AND(ll_OppTeam<>"",ll_OppTeam=wr_OppLabel)')
    e.cell("ll_OurOK", "Our marks apply", "=AND(ll_OurTeamOK,ll_FixOK)")
    e.cell("ll_OppOK", "Opponent marks apply", "=AND(ll_OppTeamOK,ll_FixOK)")
    e.cell("ll_OurScope", "Planning team scope",
           '=IF(ll_OurTeam="","",IFERROR(INDEX(Teams_Table[Scope Key],MATCH(ll_OurTeam,Teams_Table[Team],0)),""))')
    e.cell("ll_OppScope", "Planning opponent scope",
           '=IF(ll_OppTeam="","",IFERROR(INDEX(Teams_Table[Scope Key],MATCH(ll_OppTeam,Teams_Table[Team],0)),""))')
    e.cell("ll_Cap", "Reference cap (user-entered)", f'=IF(ISNUMBER({ll}$C$7),{ll}$C$7,"")')

    # ---- rosters for the effective pairing ----
    ll_our_first, ll_opp_first = slots["ll_our_first"], slots["ll_opp_first"]

    def roster_cols(prefix: str, scope: str, ll_first: int, ok: str, our: bool):
        cols = [
            (f"{prefix}Rows", lambda k, r: f'=IF({scope}="","",IFERROR(MATCH({scope}&"|{k}",TeamRosters_Table[Roster Slot Key],0),""))'),
            (f"{prefix}Pids", lambda k, r: f'=IF(B{r}="","",INDEX(TeamRosters_Table[Player ID],B{r}))'),
            (f"{prefix}Labels", lambda k, r: f'=IF(B{r}="","",INDEX(TeamRosters_Table[Player Label],B{r}))'),
            (f"{prefix}SL", lambda k, r: f'=IF(B{r}="","",INDEX(TeamRosters_Table[SL Display],B{r}))'),
            (f"{prefix}WL", lambda k, r: f'=IF(B{r}="","",INDEX(TeamRosters_Table[W-L Display],B{r}))'),
            (f"{prefix}SLNum", lambda k, r: f'=IF(B{r}="","",IF(INDEX(TeamRosters_Table[SL Display],B{r})="No data","",'
                                            f'INDEX(TeamRosters_Table[Skill Level],B{r})))'),
        ]
        if our:
            cols += [
                (f"{prefix}Avail", lambda k, r: f'=IF(B{r}="","",IF({ok},IF({ll}$C${ll_first + k - 1}="","Unknown",'
                                                f'{ll}$C${ll_first + k - 1}),"Unknown"))'),
                (f"{prefix}Lineup", lambda k, r: f'=IF(B{r}="","",IF({ok},IF({ll}$D${ll_first + k - 1}="","—",'
                                                 f'{ll}$D${ll_first + k - 1}),"—"))'),
                (f"{prefix}Remaining", lambda k, r: f'=AND(B{r}<>"",H{r}<>"Unavailable",I{r}<>"Played")'),
            ]
        else:
            cols += [
                (f"{prefix}Played", lambda k, r: f'=IF(B{r}="","",IF({ok},IF({ll}$C${ll_first + k - 1}="Played","Played","—"),"—"))'),
                (f"{prefix}Unplayed", lambda k, r: f'=AND(B{r}<>"",H{r}<>"Played")'),
                (f"{prefix}Notes", lambda k, r: f'=IF(B{r}="","",IFERROR(IF(INDEX(cn_Summary,MATCH(INDEX(TeamRosters_Table[Player Label],B{r}),'
                                                f'cn_Player,0))="","","Coach: "&INDEX(cn_Summary,MATCH(INDEX(TeamRosters_Table[Player Label],B{r}),'
                                                f'cn_Player,0))&IF(AND(ll_OppTeamOK,{ll}$D${ll_first + k - 1}<>"")," · ","")),"")&'
                                                f'IF(ll_OppTeamOK,IF({ll}$D${ll_first + k - 1}="","",'
                                                f'{ll}$D${ll_first + k - 1}),""))'),
                (f"{prefix}Start", lambda k, r: f'=IF(OR(B{r}="",NOT(wr_HasEvidence)),"",IFERROR(MATCH(wr_PairKey&"|{k}",'
                                                f'MatchupEvidence_Table[Key],0),""))'),
                (f"{prefix}Count", lambda k, r: f'=IF(K{r}="",0,INDEX(MatchupEvidence_Table[Rows],K{r}))'),
                (f"{prefix}Card", lambda k, r: f'=IF(OR(B{r}="",NOT(wr_HasEvidence)),"",IFERROR(MATCH(wr_PairKey&"|{k}",'
                                               f'Scouting_Table[Key],0),""))'),
            ]
        return cols

    ours = e.block("Our roster slot", R, roster_cols("wr_Our", "wr_OurScope", ll_our_first, "ll_OurOK", True))
    theirs = e.block("Opponent roster slot", R, roster_cols("wr_Opp", "wr_OppScope", ll_opp_first, "ll_OppOK", False))
    our_pid_col, our_first = ours["wr_OurPids"][0], ours["wr_OurPids"][1]
    opp_start_col, opp_count_col, opp_first = theirs["wr_OppStart"][0], theirs["wr_OppCount"][0], theirs["wr_OppStart"][1]

    # Lineup Lab display rosters (the planning team named on Lineup Lab).
    e.block("Planning our slot", R, [
        ("ll_OurLabels", lambda k, r: f'=IF(ll_OurScope="","",IFERROR(INDEX(TeamRosters_Table[Player Label],'
                                      f'MATCH(ll_OurScope&"|{k}",TeamRosters_Table[Roster Slot Key],0)),""))'),
        ("ll_OurSL", lambda k, r: f'=IF(B{r}="","",INDEX(TeamRosters_Table[SL Display],MATCH(ll_OurScope&"|{k}",TeamRosters_Table[Roster Slot Key],0)))'),
        ("ll_OurWL", lambda k, r: f'=IF(B{r}="","",INDEX(TeamRosters_Table[W-L Display],MATCH(ll_OurScope&"|{k}",TeamRosters_Table[Roster Slot Key],0)))'),
    ])
    e.block("Planning opponent slot", R, [
        ("ll_OppLabels", lambda k, r: f'=IF(ll_OppScope="","",IFERROR(INDEX(TeamRosters_Table[Player Label],'
                                      f'MATCH(ll_OppScope&"|{k}",TeamRosters_Table[Roster Slot Key],0)),""))'),
        ("ll_OppSL", lambda k, r: f'=IF(B{r}="","",INDEX(TeamRosters_Table[SL Display],MATCH(ll_OppScope&"|{k}",TeamRosters_Table[Roster Slot Key],0)))'),
        ("ll_OppWL", lambda k, r: f'=IF(B{r}="","",INDEX(TeamRosters_Table[W-L Display],MATCH(ll_OppScope&"|{k}",TeamRosters_Table[Roster Slot Key],0)))'),
    ])

    # ---- matrix: position of our player i inside opponent j's ranked block ----
    e.section("Matrix (row = our slot, column = opponent slot)")
    pos_first = e.row
    for j in range(1, R + 1):
        e.ws.cell(row=pos_first - 1, column=1 + j, value=f"pos opp {j}").font = base.HELPER_FONT
    grid = {}
    for i in range(1, R + 1):
        r = pos_first + i - 1
        e.ws.cell(row=r, column=1, value=f"pos our {i}").font = base.HELPER_FONT
        for j in range(1, R + 1):
            start = f"Engine!${opp_start_col}${opp_first + j - 1}"
            count = f"Engine!${opp_count_col}${opp_first + j - 1}"
            pid = f"Engine!${our_pid_col}${our_first + i - 1}"
            e.ws.cell(row=r, column=1 + j, value=(
                f'=IF(OR({pid}="",{start}=""),"",IFERROR(MATCH({pid},INDEX(MatchupEvidence_Table[Player ID],{start}+1):'
                f'INDEX(MatchupEvidence_Table[Player ID],{start}+{count}),0),""))'))
    e.row = pos_first + R + 1
    cat_first = e.row + 1
    e.ws.cell(row=cat_first - 1, column=1, value="Category grid").font = base.SUBHEAD_FONT
    cell_first = cat_first + R + 1
    e.ws.cell(row=cell_first - 1, column=1, value="Cell text grid").font = base.SUBHEAD_FONT
    cap_first = cell_first + R + 1
    e.ws.cell(row=cap_first - 1, column=1, value="Captain View grid").font = base.SUBHEAD_FONT
    captain = {}
    for i in range(1, R + 1):
        for j in range(1, R + 1):
            col = get_column_letter(1 + j)
            pos = f"${col}${pos_first + i - 1}"
            start = f"Engine!${opp_start_col}${opp_first + j - 1}"
            e.ws.cell(row=cat_first + i - 1, column=1 + j,
                      value=f'=IF({pos}="","",INDEX(MatchupEvidence_Table[Category],{start}+{pos}))')
            e.ws.cell(row=cell_first + i - 1, column=1 + j,
                      value=f'=IF({pos}="","",INDEX(MatchupEvidence_Table[Cell],{start}+{pos}))')
            grid[(i, j)] = (f"Engine!${col}${cat_first + i - 1}", f"Engine!${col}${cell_first + i - 1}",
                            f"Engine!${col}${pos_first + i - 1}")
            e.ws.cell(row=cap_first + i - 1, column=1 + j,
                      value=f'=IF({pos}="","",INDEX(MatchupEvidence_Table[Captain Cell],{start}+{pos}))')
            captain[(i, j)] = f"Engine!${col}${cap_first + i - 1}"
    last_col = get_column_letter(1 + R)
    for j in range(1, R + 1):
        col = get_column_letter(1 + j)
        e.name(f"wr_CatCol{j}", f"Engine!${col}${cat_first}:${col}${cat_first + R - 1}")
    e.row = cap_first + R + 1

    # ---- per-opponent counts: favorable / sendable remaining ----
    remaining = "wr_OurRemaining"
    e.block("Opponent evidence counts", R, [
        ("wr_GreenLeft", lambda k, r: f'=COUNTIFS(wr_CatCol{k},"G",{remaining},TRUE)'),
        ("wr_SendLeft", lambda k, r: f'=COUNTIFS(wr_CatCol{k},"G",{remaining},TRUE)+COUNTIFS(wr_CatCol{k},"E",{remaining},TRUE)'
                                     f'+COUNTIFS(wr_CatCol{k},"I",{remaining},TRUE)'),
        ("wr_RiskOpen", lambda k, r: f'=AND(INDEX(wr_OppUnplayed,{k}),B{r}=0)'),
        ("wr_RiskRun", lambda k, r: f'={"0" if k == 1 else f"E{r - 1}"}+IF(D{r},1,0)'),
    ])
    e.cell("wr_RiskCount", "Open risks", "=MAX(wr_RiskRun)")

    # ---- blind send: who do we put up when WE lead? (mirrors analytics.blind_send) ----
    # Every other recommendation in this workbook answers "they put up X, who answers?". In APA
    # the lead alternates, so a captain regularly chooses first and had no answer at all. Worst
    # case first: fewest concerning records among the opponents still unplayed, then most
    # favorable, then most even. Recorded results only -- nothing predicts their lineup.
    def _blind_count(kind: str):
        def f(k: int, r: int) -> str:
            return "=" + "+".join(
                f'IF(AND(INDEX(wr_OppUnplayed,{j}),{grid[(k, j)][0]}="{kind}"),1,0)'
                for j in range(1, R + 1))
        return f

    e.block("Blind send counts", R, [
        ("wr_BlindR", _blind_count("R")),
        ("wr_BlindG", _blind_count("G")),
        ("wr_BlindE", _blind_count("E")),
        # One sortable key, smallest wins: concerning dominates, then favorable, then even.
        # A player we are not sending gets no key at all rather than a losing one.
        ("wr_BlindKey", lambda k, r: f'=IF(AND(INDEX(wr_OurRemaining,{k}),wr_UnplayedCount>0),'
                                     f'B{r}*10000-C{r}*100-D{r},"")'),
        # Opponents we hold ANY direct record against. Silence is missing evidence, not safety,
        # so the reason below never claims "none concerning" without this beside it (BLIND-01).
        ("wr_BlindCov", lambda k, r: f'=IF(INDEX(wr_OurRemaining,{k}),B{r}+C{r}+D{r},"")'),
    ])
    # No opponents left to face, or nobody left to send: no recommendation rather than a wrong one.
    e.cell("wr_BlindBest", "Blind send key",
           '=IF(OR(wr_UnplayedCount=0,wr_RemainingCount=0),"",MIN(wr_BlindKey))')
    e.cell("wr_BlindIdx", "Blind send row", '=IF(wr_BlindBest="","",MATCH(wr_BlindBest,wr_BlindKey,0))')
    # Unranked when the LEADING candidate holds no direct record -- he only sorted above players
    # with a losing record. Unknown is not evidence of a safer lead (BLIND-01 boundary).
    e.cell("wr_BlindUnranked", "Blind send unranked",
           '=IF(wr_BlindIdx="",TRUE,INDEX(wr_BlindCov,wr_BlindIdx)=0)')
    e.cell("wr_BlindKnown", "Candidates with any direct record", '=COUNTIF(wr_BlindCov,">0")')
    e.cell("wr_BlindBad", "Candidates with a concerning record", '=COUNTIF(wr_BlindR,">0")')
    # Naming the first player in roster order implies an edge that does not exist (BLIND-01).
    e.cell("wr_BlindName", "Blind send player",
           '=IF(OR(wr_BlindIdx="",wr_BlindUnranked),"",INDEX(wr_OurLabels,wr_BlindIdx))')
    # Expose the existing roster-order fallback without claiming equal meeting records.
    e.cell("wr_BlindTieCount", "Blind send count ties",
           '=IF(OR(wr_BlindIdx="",wr_BlindUnranked),0,COUNTIFS(wr_OurRemaining,TRUE,'
           'wr_BlindR,INDEX(wr_BlindR,wr_BlindIdx),wr_BlindG,INDEX(wr_BlindG,wr_BlindIdx),'
           'wr_BlindE,INDEX(wr_BlindE,wr_BlindIdx)))')
    e.cell("wr_BlindTieNote", "Blind send tie disclosure",
           '=IF(wr_BlindTieCount>1," · "&wr_BlindTieCount&" tied by matchup counts; first shown by roster order. Compare individual records in Captain Matrix.","")')
    e.cell("wr_BlindWhy", "Blind send reason", '=IF(wr_BlindIdx="","",IF(wr_BlindUnranked,IF(wr_BlindKnown=0,"nothing recorded either way vs any of "&wr_UnplayedCount&" — your read decides","no record either way for our best-placed option — unknown, not safer"&IF(wr_BlindBad>0," · "&wr_BlindBad&" of your remaining have a concerning record","")&" · unranked, your read decides"),IF(INDEX(wr_BlindR,wr_BlindIdx)>0,IF(INDEX(wr_BlindG,wr_BlindIdx)=0,INDEX(wr_BlindR,wr_BlindIdx)&" concerning of "&wr_UnplayedCount&" — best available, not good"&IF(wr_UnplayedCount-INDEX(wr_BlindCov,wr_BlindIdx)>0," · no direct record vs "&(wr_UnplayedCount-INDEX(wr_BlindCov,wr_BlindIdx)),""),INDEX(wr_BlindG,wr_BlindIdx)&" favorable, "&INDEX(wr_BlindR,wr_BlindIdx)&" concerning of "&wr_UnplayedCount&IF(wr_UnplayedCount-INDEX(wr_BlindCov,wr_BlindIdx)>0," · no direct record vs "&(wr_UnplayedCount-INDEX(wr_BlindCov,wr_BlindIdx)),"")),IF(INDEX(wr_BlindG,wr_BlindIdx)>0,"favorable vs "&INDEX(wr_BlindG,wr_BlindIdx)&" of "&wr_UnplayedCount&IF(wr_UnplayedCount-INDEX(wr_BlindCov,wr_BlindIdx)>0," · no direct record vs "&(wr_UnplayedCount-INDEX(wr_BlindCov,wr_BlindIdx)),""),"even vs "&INDEX(wr_BlindE,wr_BlindIdx)&" of "&wr_UnplayedCount&IF(wr_UnplayedCount-INDEX(wr_BlindCov,wr_BlindIdx)>0," · no direct record vs "&(wr_UnplayedCount-INDEX(wr_BlindCov,wr_BlindIdx)),"")))))')
    # Captain Packet evidence list: where each opponent's rows start in one continuous, packed list.
    e.block("Packet evidence start", R, [
        ("wr_PkStart", lambda k, r: "=1" if k == 1 else f"=B{r - 1}+INDEX(wr_OppCount,{k - 1})"),
    ])
    e.cell("wr_PkTotal", "Packet evidence lines", "=SUM(wr_OppCount)")

    # ---- first by recorded direct results per opponent (ranking order, sendable + remaining) ----
    e.section("Recorded matchup options (per opponent: direct-record order)")
    # Per opponent j, one row per ranked candidate: pid, category, remaining, sendable (ok), running count of
    # sendable rows, evidence group key (MatchupEvidence_Table[Rank Group]), direct (G/E and ok), group number
    # among remaining direct candidates, last group key, and the display label: "1." / "1=" (tied) / "≈"
    # (shared-opponent only, never numbered). Mirrors analytics send_labels / best_send_text (GPT audit #84).
    bs_first = e.row + 1
    send_refs, send_rng = {}, {}
    heads = ("pid", "cat", "rem", "ok", "run", "key", "dir", "grp", "last", "lbl")
    for j in range(1, R + 1):
        base_col = 2 + (j - 1) * len(heads)
        for off, head in enumerate(heads):
            e.ws.cell(row=bs_first - 1, column=base_col + off, value=f"o{j} {head}").font = base.HELPER_FONT
        start = f"Engine!${opp_start_col}${opp_first + j - 1}"
        count = f"Engine!${opp_count_col}${opp_first + j - 1}"
        L = {h: get_column_letter(base_col + i) for i, h in enumerate(heads)}
        rng = {h: f"Engine!${L[h]}${bs_first}:${L[h]}${bs_first + R - 1}" for h in heads}
        for rr in range(1, R + 1):
            r = bs_first + rr - 1
            c = {h: f"{L[h]}{r}" for h in heads}
            p = {h: f"{L[h]}{r - 1}" for h in heads}
            formulas = {
                "pid": f'=IF(OR({start}="",{rr}>{count}),"",INDEX(MatchupEvidence_Table[Player ID],{start}+{rr}))',
                "cat": f'=IF({c["pid"]}="","",INDEX(MatchupEvidence_Table[Category],{start}+{rr}))',
                "rem": f'=IF({c["pid"]}="",FALSE,IFERROR(INDEX({remaining},MATCH({c["pid"]},wr_OurPids,0)),FALSE))',
                "ok": f'=AND({c["pid"]}<>"",OR({c["cat"]}="G",{c["cat"]}="E",{c["cat"]}="I"),{c["rem"]})',
                "run": f'=IF({c["ok"]},1,0)' if rr == 1 else f'={p["run"]}+IF({c["ok"]},1,0)',
                "key": f'=IF({c["pid"]}="","",INDEX(MatchupEvidence_Table[Rank Group],{start}+{rr}))',
                "dir": f'=AND({c["ok"]},OR({c["cat"]}="G",{c["cat"]}="E"))',
                "grp": (f'=IF({c["dir"]},1,0)' if rr == 1 else
                        f'=IF({c["dir"]},IF({p["grp"]}=0,1,IF({c["key"]}={p["last"]},{p["grp"]},{p["grp"]}+1)),{p["grp"]})'),
                "last": f'=IF({c["dir"]},{c["key"]},"")' if rr == 1 else f'=IF({c["dir"]},{c["key"]},{p["last"]})',
                "lbl": (f'=IF(NOT({c["ok"]}),"",IF({c["cat"]}="I","≈",{c["grp"]}&'
                        f'IF(COUNTIFS({rng["grp"]},{c["grp"]},{rng["dir"]},TRUE)>1,"=",".")))'),
            }
            for off, head in enumerate(heads):
                e.ws.cell(row=r, column=base_col + off, value=formulas[head])
        send_refs[j] = rng["run"]
        send_rng[j] = rng
    e.row = bs_first + R + 1

    def send_text(n: int, k: int) -> str:
        rng, m = send_rng[k], f"MATCH({n},{send_rng[k]['run']},0)"
        row = f"INDEX(wr_OppStart,{k})+{m}"
        return (f'=IF(OR(INDEX(wr_OppStart,{k})="",NOT(INDEX(wr_OppUnplayed,{k}))),"",IFERROR(INDEX({rng["lbl"]},{m})&" "&'
                f'INDEX(MatchupEvidence_Table[Player],{row})&" — "&IF(INDEX(MatchupEvidence_Table[Direct Games],{row})>0,'
                f'INDEX(MatchupEvidence_Table[Direct Record],{row})&IF(INDEX(MatchupEvidence_Table[Direct Games],{row})<3," · SMALL SAMPLE",""),'
                f'INDEX(MatchupEvidence_Table[Cell],{row})),""))')

    def best_text(k: int) -> str:
        rng, m = send_rng[k], f"MATCH(1,{send_rng[k]['run']},0)"
        row = f"INDEX(wr_OppStart,{k})+{m}"
        n_i = f'COUNTIFS({rng["cat"]},"I",{rng["ok"]},TRUE)'
        tie = f'COUNTIFS({rng["grp"]},1,{rng["dir"]},TRUE)'
        tag = (f'IF(INDEX({rng["cat"]},{m})="I","shared-opponent candidate, not ordered ("&IF({n_i}=1,"the only one",'
               f'"one of "&{n_i})&"): ",IF({tie}>1,"first by recorded direct results (tied with "&({tie}-1)&" other"&IF({tie}>2,"s","")&'
               f'", same evidence): ","first by recorded direct results: "))')
        return (f'=IF(OR(INDEX(wr_OppStart,{k})="",NOT(INDEX(wr_OppUnplayed,{k}))),"",IFERROR({tag}&'
                f'INDEX(MatchupEvidence_Table[Player],{row})&" — reason: "&INDEX(MatchupEvidence_Table[Reason],{row}),""))')

    e.block("Best send", R, [
        (f"wr_Send{n}", (lambda n: lambda k, r: send_text(n, k))(n)) for n in (1, 2, 3)
    ] + [
        # The labelled list (War Room, packet) and the single best send with its reason (Lineup Lab, Command Center).
        ("wr_SendList", lambda k, r: f'=B{r}&IF(C{r}="",""," · "&C{r})&IF(D{r}="",""," · "&D{r})'),
        ("wr_BestText", lambda k, r: best_text(k)),
    ])

    # ---- threats, concerning pairings, unique favorable options ----
    e.block("Threat row", R, [
        ("wr_ThreatRow", lambda k, r: f'=IF(NOT(wr_HasEvidence),"",IFERROR(MATCH(wr_PairKey&"|{k}",Threats_Table[Key],0),""))'),
        ("wr_ThreatOk", lambda k, r: f'=IF(B{r}="",FALSE,IFERROR(INDEX(wr_OppUnplayed,MATCH(INDEX(Threats_Table[Opp Player ID],B{r}),wr_OppPids,0)),FALSE))'),
        ("wr_ThreatRun", lambda k, r: (f'=IF(C{r},1,0)' if k == 1 else f'=D{r - 1}+IF(C{r},1,0)')),
    ])
    # Mirror live_threats: exact direct records against remaining players, not
    # static full-roster danger labels. No new evidence or predictive score.
    def direct_count(i, j, field):
        pos = grid[(i, j)][2]
        return f'IF({pos}="",0,INDEX(MatchupEvidence_Table[{field}],INDEX(wr_OppStart,{j})+{pos}))'

    def live_sum(j, field, remaining_only):
        terms = []
        for i in range(1, R + 1):
            value = direct_count(i, j, field)
            terms.append(f'IF(INDEX(wr_OurRemaining,{i}),{value},0)' if remaining_only else value)
        return '+'.join(terms)

    def live_met(j):
        return '+'.join(f'IF(AND(INDEX(wr_OurRemaining,{i}),{direct_count(i,j,"Direct Games")}>0),1,0)'
                        for i in range(1, R + 1))

    def live_text(k, r):
        label = f'INDEX(wr_OppLabels,{k})&" · Captured SL "&INDEX(wr_OppSL,{k})'
        remaining = 'COUNTIF(wr_OurRemaining,TRUE)'
        live = (f'{label}&" · "&B{r}&"-"&(C{r}-B{r})&" vs our roster still in play ("&C{r}&'
                f'IF(C{r}=1," meeting, "," meetings, ")&D{r}&" of "&{remaining}&" remaining players)"&'
                f'IF({remaining}>D{r}," · no direct record vs "&({remaining}-D{r})&" remaining players","")&'
                f'IF(C{r}<3," · SMALL SAMPLE","")&IF(C{r}=1," · Beat us once","")')
        historical = (f'{label}&" · historically "&E{r}&"-"&(F{r}-E{r})&" in "&F{r}&'
                      f'IF(F{r}=1," meeting"," meetings")&"; only vs players not in tonight\'s remaining lineup — "&'
                      f'"unknown vs who is left, not cleared"&IF(F{r}<3," · SMALL HISTORICAL SAMPLE","")')
        return f'=IF(G{r},{live},IF(H{r},{historical},""))'

    e.block("Live threat by opponent", R, [
        ("wr_LiveThreatWins", lambda k,r: f'={live_sum(k,"Direct Games",True)}-({live_sum(k,"Direct Wins",True)})'),
        ("wr_LiveThreatGames", lambda k,r: '='+live_sum(k,"Direct Games",True)),
        ("wr_LiveThreatMet", lambda k,r: '='+live_met(k)),
        ("wr_GoneThreatWins", lambda k,r: f'=({live_sum(k,"Direct Games",False)})-({live_sum(k,"Direct Wins",False)})-B{r}'),
        ("wr_GoneThreatGames", lambda k,r: f'=({live_sum(k,"Direct Games",False)})-C{r}'),
        ("wr_LiveThreatFlag", lambda k,r: f'=AND(INDEX(wr_OppUnplayed,{k}),C{r}>0,2*B{r}>C{r})'),
        ("wr_LiveThreatUnknown", lambda k,r: f'=AND(INDEX(wr_OppUnplayed,{k}),COUNTIF(wr_OurRemaining,TRUE)>0,C{r}=0,F{r}>0,2*E{r}>F{r})'),
        ("wr_LiveThreatNet", lambda k,r: f'=IF(G{r},2*B{r}-C{r},IF(H{r},2*E{r}-F{r},0))'),
        ("wr_LiveThreatOrder", lambda k,r:
            f'=IF(G{r},COUNTIFS(wr_LiveThreatFlag,TRUE,wr_LiveThreatNet,">"&I{r})+'
            f'COUNTIFS(INDEX(wr_LiveThreatFlag,1):INDEX(wr_LiveThreatFlag,{k}),TRUE,INDEX(wr_LiveThreatNet,1):INDEX(wr_LiveThreatNet,{k}),I{r}),'
            f'IF(H{r},COUNTIF(wr_LiveThreatFlag,TRUE)+COUNTIFS(wr_LiveThreatUnknown,TRUE,wr_LiveThreatNet,">"&I{r})+'
            f'COUNTIFS(INDEX(wr_LiveThreatUnknown,1):INDEX(wr_LiveThreatUnknown,{k}),TRUE,INDEX(wr_LiveThreatNet,1):INDEX(wr_LiveThreatNet,{k}),I{r}),""))'),
        ("wr_LiveThreatText", live_text),
    ])
    e.block("Meetings behind blind-send pairing counts", R, [
        ("wr_OurLiveMeetings", lambda i,r: '='+ '+'.join(
            f'IF(INDEX(wr_OppUnplayed,{j}),{direct_count(i,j,"Direct Games")},0)' for j in range(1,R+1))),
    ])
    e.cell("wr_BlindMeetings", "Blind-send direct meeting total",
           '=IF(wr_BlindIdx="",0,INDEX(wr_OurLiveMeetings,wr_BlindIdx))')
    e.cell("wr_BlindMeetingNote", "Blind-send evidence-strength disclosure",
           '=IF(OR(wr_BlindUnranked,wr_BlindName=""),""," · "&wr_BlindMeetings&IF(wr_BlindMeetings=1," direct meeting total"," direct meetings total")&" — pairing counts select first shown, not confidence")')
    e.block("Concerning row", slots["concerning"], [
        ("wr_ConcernRow", lambda k, r: f'=IF(NOT(wr_HasEvidence),"",IFERROR(MATCH(wr_PairKey&"|{k}",Concerning_Table[Key],0),""))'),
        ("wr_ConcernOk", lambda k, r: (
            f'=IF(B{r}="",FALSE,AND(IFERROR(INDEX(wr_OurRemaining,MATCH(INDEX(Concerning_Table[Our Player ID],B{r}),wr_OurPids,0)),FALSE),'
            f'IFERROR(INDEX(wr_OppUnplayed,MATCH(INDEX(Concerning_Table[Opp Player ID],B{r}),wr_OppPids,0)),FALSE)))')),
        ("wr_ConcernRun", lambda k, r: (f'=IF(C{r},1,0)' if k == 1 else f'=D{r - 1}+IF(C{r},1,0)')),
    ])
    e.section("Unique favorable options (row = our slot, column = opponent slot)")
    u_first = e.row + 1
    for i in range(1, R + 1):
        r = u_first + i - 1
        for j in range(1, R + 1):
            cat = grid[(i, j)][0]
            e.ws.cell(row=r, column=1 + j, value=(
                f'=AND({cat}="G",INDEX(wr_OurRemaining,{i}),INDEX(wr_OppUnplayed,{j}),INDEX(wr_GreenLeft,{j})=1)'))
        e.ws.cell(row=r, column=2 + R, value=f'=COUNTIF(B{r}:{last_col}{r},TRUE)')
        e.ws.cell(row=r, column=3 + R, value=f'=IFERROR(MATCH(TRUE,B{r}:{last_col}{r},0),"")')
        e.ws.cell(row=r, column=4 + R, value=(f'=IF({get_column_letter(2 + R)}{r}>0,1,0)' if i == 1 else
                                              f'={get_column_letter(4 + R)}{r - 1}+IF({get_column_letter(2 + R)}{r}>0,1,0)'))
    for off, name in enumerate(("wr_UniqueCount", "wr_UniqueFirst", "wr_UniqueRun")):
        col = get_column_letter(2 + R + off)
        e.name(name, f"Engine!${col}${u_first}:${col}${u_first + R - 1}")
    e.row = u_first + R + 1

    # ---- Next Send (Command Center): "they put up this player -- who do I send?" ----
    # Mirrors analytics.next_send: medals only for ordered direct candidates (favorable, then even) among our
    # remaining players, same rank group = same medal; shared-only candidates unordered; Avoid worst first.
    cc, ME = "'Command Center'!", "MatchupEvidence_Table"
    e.section("Next Send")
    e.cell("wr_NsInput", "They put up", "=" + guard(f"{cc}$C$6"))
    e.cell("wr_NsJ", "Opponent slot", '=IF(wr_NsInput="","",IFERROR(MATCH(wr_NsInput,wr_OppLabels,0),""))')
    e.cell("wr_NsOpen", "Opponent unplayed", '=IF(wr_NsJ="",FALSE,INDEX(wr_OppUnplayed,wr_NsJ))')
    e.cell("wr_NsStart", "Ranked block start", '=IF(wr_NsJ="","",INDEX(wr_OppStart,wr_NsJ))')
    e.cell("wr_NsCount", "Ranked rows", '=IF(OR(wr_NsJ="",wr_NsStart=""),0,INDEX(wr_OppCount,wr_NsJ))')
    e.cell("wr_NsSelfUnique", "One favorable option left vs them", '=IF(wr_NsJ="",FALSE,INDEX(wr_GreenLeft,wr_NsJ)=1)')
    def _save_targets(k: int, exclude_selected: bool, selected: int | None = None) -> str:
        pieces = []
        for j in range(1, R + 1):
            flag = f"Engine!${get_column_letter(1 + j)}${u_first + k - 1}"
            cond = f"AND({flag},{selected if selected is not None else 'wr_NsJ'}<>{j})" if exclude_selected else flag
            row = f"INDEX(wr_OppStart,{j})+{grid[(k, j)][2]}"
            pieces.append(f'IF({cond}," · vs "&INDEX(wr_OppLabels,{j})&" ("&INDEX({ME}[Save Record],{row})&")","")')
        joined = "&".join(pieces)
        return f'=IFERROR(MID({joined},7,32767),"")'

    e.block("Save evidence for remaining opponents", R, [
        ("wr_UniqueDetails", lambda k, r: _save_targets(k, False)),
        ("wr_NsSaveDetails", lambda k, r: _save_targets(k, True)),
    ])
    # Reuse the same unique-option flags for each printed opponent, rather than
    # relying on whichever opponent happens to be selected in Command Center.
    packet_saves = {}
    for j in range(1, R + 1):
        e.section(f"Packet future-save warning vs opponent slot {j}")
        first = e.row + 1
        for i in range(1, R + 1):
            r = first + i - 1
            e.ws.cell(row=r, column=2, value=_save_targets(i, True, j))
            cat = grid[(i,j)][0]
            e.ws.cell(row=r, column=3, value=(
                f'=IF(AND(INDEX(wr_OurRemaining,{i}),INDEX(wr_OppUnplayed,{j}),'
                f'OR({cat}="G",{cat}="E",{cat}="I"),B{r}<>""),'
                f'INDEX(wr_OurLabels,{i})&" — consider saving for "&B{r},"")'))
            e.ws.cell(row=r, column=4, value=(f'=C{r}' if i==1 else
                f'=D{r-1}&IF(AND(D{r-1}<>"",C{r}<>""),CHAR(10),"")&C{r}'))
        packet_saves[j] = f'Engine!$D${r}'
        e.row = r + 2
    e.block("Packet future-save warning by opponent", R, [
        ("wr_PacketSave", lambda k,r: '='+packet_saves[k]),
    ])
    packet_cautions = {}
    for j in range(1, R + 1):
        e.section(f"Packet loss cautions vs opponent slot {j}")
        first = e.row + 1
        for k in range(1, R + 1):
            r = first + k - 1
            e.ws.cell(row=r, column=2, value=f'=IF(OR(INDEX(wr_OppStart,{j})="",{k}>INDEX(wr_OppCount,{j})),"",INDEX(wr_OppStart,{j})+{k})')
            e.ws.cell(row=r, column=3, value=(f'=IF(B{r}="",FALSE,AND(INDEX(wr_OppUnplayed,{j}),'
                f'INDEX({ME}[Category],B{r})="R",IFERROR(INDEX(wr_OurRemaining,MATCH(INDEX({ME}[Player ID],B{r}),wr_OurPids,0)),FALSE)))'))
            e.ws.cell(row=r, column=4, value=(f'=IF(C{r},INDEX({ME}[Player],B{r})&" — "&INDEX({ME}[Direct Record],B{r})&'
                f'IF(INDEX({ME}[Direct Games],B{r})<3," · SMALL SAMPLE","")&'
                f'IF(INDEX({ME}[Direct Games],B{r})=1," · Lost once · Only 1 meeting",""),"")'))
            e.ws.cell(row=r, column=5, value=(f'=D{r}' if k==1 else
                f'=E{r-1}&IF(AND(E{r-1}<>"",D{r}<>""),CHAR(10),"")&D{r}'))
        packet_cautions[j]=f'Engine!$E${r}'
        e.row=r+2
    e.block("Packet loss cautions by opponent", R, [
        ("wr_PacketCautions",lambda k,r:'='+packet_cautions[k]),
    ])
    e.block("First direct record by opponent",R,[
        ("wr_FirstDirectRow",lambda k,r:f'=IFERROR(INDEX(wr_OppStart,{k})+MATCH(1,{send_rng[k]["run"]},0),"")'),
        ("wr_FirstDirectMeetings",lambda k,r:f'=IFERROR(IF(OR(INDEX({ME}[Category],B{r})="G",INDEX({ME}[Category],B{r})="E"),INDEX({ME}[Direct Games],B{r}),0),0)'),
    ])
    deeper_records={}
    for j in range(1,R+1):
        e.section(f"Deeper direct record context vs opponent slot {j}")
        first=e.row+1
        for k in range(1,R+1):
            r=first+k-1
            e.ws.cell(row=r,column=2,value=f'=IF(OR(INDEX(wr_OppStart,{j})="",{k}>INDEX(wr_OppCount,{j})),"",INDEX(wr_OppStart,{j})+{k})')
            e.ws.cell(row=r,column=3,value=(f'=IF(B{r}="",FALSE,AND(INDEX(wr_OppUnplayed,{j}),INDEX(wr_FirstDirectMeetings,{j})>0,'
                f'INDEX(wr_FirstDirectMeetings,{j})<3,INDEX({ME}[Direct Games],B{r})>INDEX(wr_FirstDirectMeetings,{j}),'
                f'IFERROR(INDEX(wr_OurRemaining,MATCH(INDEX({ME}[Player ID],B{r}),wr_OurPids,0)),FALSE)))'))
            cat=f'INDEX({ME}[Category],B{r})'
            e.ws.cell(row=r,column=4,value=(f'=IF(C{r},INDEX({ME}[Player],B{r})&" — "&INDEX({ME}[Direct Record],B{r})&'
                f'" · "&IF({cat}="G","favorable direct",IF({cat}="E","even direct","recorded loss"))&'
                f'IF(INDEX({ME}[Direct Games],B{r})<3," · SMALL SAMPLE",""),"")'))
            e.ws.cell(row=r,column=5,value=f'=D{r}' if k==1 else f'=E{r-1}&IF(AND(E{r-1}<>"",D{r}<>""),CHAR(10),"")&D{r}')
        deeper_records[j]=f'Engine!$E${r}'
        e.row=r+2
    e.block("Deeper records by opponent",R,[
        ("wr_DeeperRecords",lambda k,r:'='+deeper_records[k]),
    ])
    medal = '"Direct-record order "&H{r}'

    def _nm(expr: str, slot: str) -> str:
        # Lookup labels are already unique display names; identity columns are unchanged.
        return expr

    def _join(k: int, r: int, col: str, cond: str, text: str) -> str:
        """Running ", "-joined list down a column; the last row holds the whole list (no TEXTJOIN needed)."""
        if k == 1:
            return f'=IF({cond},{text},"")'
        prev = f"{col}{r - 1}"
        return f'=IF({cond},{prev}&IF({prev}="","",CHAR(10))&{text},{prev})'

    e.block("Next Send ranked row", R, [
        ("wr_NsRow", lambda k, r: f'=IF(OR(NOT(wr_NsOpen),{k}>wr_NsCount),"",wr_NsStart+{k})'),
        ("wr_NsSlot", lambda k, r: f'=IF(B{r}="","",IFERROR(MATCH(INDEX({ME}[Player ID],B{r}),wr_OurPids,0),""))'),
        ("wr_NsCat", lambda k, r: f'=IF(B{r}="","",INDEX({ME}[Category],B{r}))'),
        ("wr_NsRem", lambda k, r: f'=IF(C{r}="",FALSE,INDEX(wr_OurRemaining,C{r}))'),
        ("wr_NsKey", lambda k, r: f'=IF(B{r}="","",INDEX({ME}[Rank Group],B{r}))'),
        ("wr_NsElig", lambda k, r: f'=AND(E{r},OR(D{r}="G",D{r}="E"))'),
        ("wr_NsGrp", lambda k, r: (f'=IF(G{r},1,0)' if k == 1 else
                                    f'=IF(G{r},IF(H{r - 1}=0,1,IF(F{r}=I{r - 1},H{r - 1},H{r - 1}+1)),H{r - 1})')),
        ("wr_NsLastKey", lambda k, r: (f'=IF(G{r},F{r},"")' if k == 1 else f'=IF(G{r},F{r},I{r - 1})')),
        ("wr_NsMedalRun", lambda k, r: (f'=IF(G{r},1,0)' if k == 1 else f'=J{r - 1}+IF(G{r},1,0)')),
        ("wr_NsMedalText", lambda k, r: (
            f'=IF(G{r},{medal.format(r=r)}&" "&{_nm(f"INDEX({ME}[Player],B{r})", f"C{r}")}&" — "&SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(INDEX({ME}[Reason],B{r}),"meetings)","MEETINGS)"),"meeting)","MEETING)"),"small sample","SMALL SAMPLE")'
            f'&IF(COUNTIFS(wr_NsGrp,H{r},wr_NsElig,TRUE)>1," · tied (same evidence)","")'
            f'&IF(INDEX(wr_UniqueCount,C{r})-IF(AND(D{r}="G",wr_NsSelfUnique),1,0)>0,'
            f'" · consider saving — our only favorable direct option vs "&INDEX(wr_NsSaveDetails,C{r}),"")'
            f'&IF(INDEX(wr_OurAvail,C{r})="Unknown"," · availability unknown",""),"")')),
        ("wr_NsUnordRun", lambda k, r: (f'=IF(AND(E{r},D{r}="I"),1,0)' if k == 1 else f'=L{r - 1}+IF(AND(E{r},D{r}="I"),1,0)')),
        ("wr_NsUnordJoin", lambda k, r: _join(k, r, "M", f'AND(E{r},D{r}="I")', _nm(f"INDEX({ME}[Player],B{r})", f"C{r}")
                                              + f'&IF(INDEX(wr_NsSaveDetails,C{r})="",""," · consider saving — our only favorable direct option vs "&INDEX(wr_NsSaveDetails,C{r}))'
                                              + f'&IF(INDEX(wr_OurAvail,C{r})="Unknown"," (availability unknown)","")')),
        ("wr_NsUnkJoin", lambda k, r: _join(k, r, "N", f'AND(E{r},D{r}="X")', _nm(f"INDEX({ME}[Player],B{r})", f"C{r}"))),
        ("wr_NsRevRow", lambda k, r: f'=IF(OR(NOT(wr_NsOpen),{k}>wr_NsCount),"",wr_NsStart+{k})'),
        ("wr_NsAvoidOk", lambda k, r: (f'=IF(O{r}="",FALSE,AND(INDEX({ME}[Category],O{r})="R",IFERROR(INDEX(wr_OurRemaining,'
                                        f'MATCH(INDEX({ME}[Player ID],O{r}),wr_OurPids,0)),FALSE)))')),
        ("wr_NsAvoidJoin", lambda k, r: _join(k, r, "Q", f'P{r}',
                                              f'{_nm(f"INDEX({ME}[Player],O{r})", f"MATCH(INDEX({ME}[Player ID],O{r}),wr_OurPids,0)")}&" — "&INDEX({ME}[Direct Record],O{r})&IF(INDEX({ME}[Direct Games],O{r})<3," · SMALL SAMPLE","")')),
    ])
    e.cell("wr_NsHeadline", "Next Send headline", (
        '=IF(wr_NsInput="","Pick the opponent player they put up (cell C6).",IF(wr_NsJ="","That player is not on tonight’s opponent roster.",'
        'IF(NOT(wr_NsOpen),wr_NsInput&" has already played (Lineup Lab).",IF(MAX(wr_NsMedalRun)>0,"First direct-record group: "&'
        'INDEX(MatchupEvidence_Table[Direct Record],INDEX(wr_NsRow,MATCH(1,wr_NsMedalRun,0)))&'
        'IF(INDEX(MatchupEvidence_Table[Direct Games],INDEX(wr_NsRow,MATCH(1,wr_NsMedalRun,0)))<3," · SMALL SAMPLE","")&'
        '"; equal evidence stays tied.",IF(MAX(wr_NsUnordRun)>0,"No favorable/even direct option — '
        'shared-opponent candidates only (≈, not ordered)","No evidence-backed option left among our remaining players")))))'))
    # Each remaining player is in at most one of these lists, so together they name at most R players. One wrapped
    # cell (a line per list) can therefore be sized once for R names; three rows would each need room for all R
    # (real-Excel UAT 2a67d78 showed a 2-line row hiding the last "≈" candidate).
    e.cell("wr_NsUnordLine", "Next Send not-ordered line",
           f'=IF(INDEX(wr_NsUnordJoin,{R})="","","≈ Not ordered (shared-opponent results only): "&INDEX(wr_NsUnordJoin,{R}))')
    e.cell("wr_NsAvoidLine", "Next Send avoid line", f'=IF(INDEX(wr_NsAvoidJoin,{R})="","","⚠ Avoid: "&INDEX(wr_NsAvoidJoin,{R}))')
    e.cell("wr_NsUnkLine", "Next Send unknown line",
           f'=IF(INDEX(wr_NsUnkJoin,{R})="","","❓ Unknown (no verified evidence, not weak): "&INDEX(wr_NsUnkJoin,{R}))')
    e.cell("wr_NsLists", "Next Send lists (one line each)",
           '=wr_NsUnordLine&IF(AND(wr_NsUnordLine<>"",wr_NsAvoidLine&wr_NsUnkLine<>""),CHAR(10),"")'
           '&wr_NsAvoidLine&IF(AND(wr_NsAvoidLine<>"",wr_NsUnkLine<>""),CHAR(10),"")&wr_NsUnkLine')
    # The whole Next Send answer as ONE wrapped cell, a line per item: headline, every ranked line
    # (SEND-LAYOUT-01), then the lists. Fixed rows per medal left a tall empty gap between the medal and the lists
    # on screen and on paper (real-Excel UAT 0c2e474); one cell keeps the answer contiguous and is sized once.
    for n in range(1, R + 1):
        e.cell(f"wr_NsMedal{n}", f"Next Send medal line {n}", f'=IFERROR(INDEX(wr_NsMedalText,MATCH({n},wr_NsMedalRun,0)),"")')
    e.cell("wr_NsMethod", "Next Send ordering boundary", '="Not an overall player ranking. Favorable/even direct records use recorded win percentage, then meeting count. A 1-0 record can appear before 8-2; small samples do not reduce position. Loss cautions use most net losses first, then meetings. Shared-only comparisons are not ordered."')
    e.cell("wr_NsCard", "Next Send answer (one line each)", '=IF(wr_NsOpen,wr_NsMethod&CHAR(10),"")&wr_NsHeadline' + "".join(
        f'&IF({x}="","",CHAR(10)&{x})' for x in [f"wr_NsMedal{n}" for n in range(1, R + 1)] + ["wr_NsLists"]))
    e.cell("wr_NsDeeper","Selected opponent deeper-record context",
           '=IF(NOT(wr_NsOpen),"",IF(INDEX(wr_DeeperRecords,wr_NsJ)="","",'
           '"Deeper direct records — more meetings, not a new order:"&CHAR(10)&INDEX(wr_DeeperRecords,wr_NsJ)))')

    # Broader records are context only: never referenced by ranking or eligibility formulas.
    broader = ('="Not used in this ordering"&CHAR(10)&"Captured team/session records — not a lifetime record."'
               '&CHAR(10)&"Our roster: "&wr_OurLabel')
    for k in range(1, R + 1):
        broader += (f'&IF(INDEX(wr_OurRemaining,{k}),CHAR(10)&INDEX(wr_OurLabels,{k})&": "&INDEX(wr_OurWL,{k}),"")')
    broader += ('&CHAR(10)&"Opponent roster: "&wr_OppLabel&CHAR(10)&IF(wr_NsJ="","Choose the opponent above.",'
                'wr_NsInput&": "&INDEX(wr_OppWL,wr_NsJ))&CHAR(10)&"Meeting age, changes in skill level and Coach Observations do not adjust this order. Availability filters candidates; skill-budget checks are separate references. No verified direct/shared comparison means unknown, not weak."')
    e.cell("wr_NsBroader", "Next Send broader context", broader)

    # ---- Lineup Lab metrics ----
    e.section("Lineup Lab metrics")
    e.cell("wr_OurCount", "Our rostered", '=COUNTIF(wr_OurRows,">0")')
    e.cell("wr_RemainingCount", "Remaining players", "=COUNTIF(wr_OurRemaining,TRUE)")
    e.cell("wr_RemainingUnknown", "Remaining with unknown availability", '=COUNTIFS(wr_OurRemaining,TRUE,wr_OurAvail,"Unknown")')
    e.cell("wr_RemainingSL", "Remaining known SL total", "=SUMIFS(wr_OurSLNum,wr_OurRemaining,TRUE)")
    e.cell("wr_RemainingMissing", "Remaining without a captured SL", '=COUNTIFS(wr_OurRemaining,TRUE,wr_OurSLNum,"")')
    e.cell("wr_SelectedCount", "Selected lineup (Planned + Played)", '=COUNTIF(wr_OurLineup,"Planned")+COUNTIF(wr_OurLineup,"Played")')
    e.cell("wr_SelectedSL", "Selected known SL total",
           '=SUMIFS(wr_OurSLNum,wr_OurLineup,"Planned")+SUMIFS(wr_OurSLNum,wr_OurLineup,"Played")')
    e.cell("wr_SelectedMissing", "Selected without a captured SL",
           '=COUNTIFS(wr_OurLineup,"Planned",wr_OurSLNum,"")+COUNTIFS(wr_OurLineup,"Played",wr_OurSLNum,"")')
    e.cell("wr_UnplayedCount", "Opponents not yet played", "=COUNTIF(wr_OppUnplayed,TRUE)")
    e.cell("wr_GreenOpps", "Unplayed opponents with a favorable option left", '=COUNTIFS(wr_OppUnplayed,TRUE,wr_GreenLeft,">0")')
    e.cell("wr_SendOpps", "Unplayed opponents with any evidence-backed option left", '=COUNTIFS(wr_OppUnplayed,TRUE,wr_SendLeft,">0")')

    # ---- Coach Dashboard effective ----
    cd = "'Coach Dashboard'!"
    e.section("Coach Dashboard — effective players")
    e.block("Player B choice", R + 1, [
        ("cd_PlayerBList", lambda k, r: (f'=INDEX(wr_OppLabels,{k})' if k <= R else f'="{ALL_PLAYERS_CHOICE}"')),
    ])
    e.cell("cd_AInput", "Player A override", "=" + guard(f"{cd}$C$5"))
    e.cell("cd_BInput", "Player B choice", "=" + guard(f"{cd}$C$6"))
    e.cell("cd_AnyInput", "Any player", "=" + guard(f"{cd}$C$7"))
    e.cell("cd_FmtInput", "Format override", "=" + guard(f"{cd}$C$8"))
    e.cell("cd_Local", "Using local selections", '=OR(cd_AInput<>"",cd_FmtInput<>"")')
    e.cell("cd_ALabel", "Player A", '=IF(cd_AInput<>"",cd_AInput,uc_ViewerLabel)')
    e.cell("cd_BLabel", "Player B", f'=IF(cd_BInput="","",IF(cd_BInput="{ALL_PLAYERS_CHOICE}",cd_AnyInput,cd_BInput))')
    e.cell("cd_AID", "Player A id", '=IFERROR(INDEX(Players_Table[Player ID],MATCH(cd_ALabel,Players_Table[Player Label],0)),"")')
    e.cell("cd_BID", "Player B id", '=IFERROR(INDEX(Players_Table[Player ID],MATCH(cd_BLabel,Players_Table[Player Label],0)),"")')
    e.cell("cd_FmtLabel", "Format", '=IF(cd_FmtInput<>"",cd_FmtInput,IF(wr_FormatLabel="","8-Ball",wr_FormatLabel))')
    e.cell("cd_Status", "Status line",
           '=IF(cd_Local,"Using local selections","Following Match Day")&": "&IF(cd_ALabel="","(Player A)",cd_ALabel)&" vs "&'
           f'IF(cd_BLabel="","(choose Player B)",cd_BLabel)&" · "&cd_FmtLabel')

    return {"grid": grid, "captain": captain, "ours": ours, "theirs": theirs}


# ---------------------------------------------------------------------------
# Sheet helpers
# ---------------------------------------------------------------------------

def _dv(sheet, cell: str, source: str, prompt: str) -> None:
    v = DataValidation(type="list", formula1=source, allow_blank=True)
    v.promptTitle, v.prompt = "Choose", prompt
    sheet.add_data_validation(v)
    v.add(cell)


def _calc(cell, value: Any, *, bold: bool = False) -> None:
    cell.value = value
    cell.fill = CALC_FILL
    cell.font = Font(bold=bold)
    cell.alignment = Alignment(wrap_text=True, vertical="top")


def _link(sheet, row: int, col: int, text: str, target: str, *, font: Font = base.LINK_FONT) -> None:
    c = sheet.cell(row=row, column=col, value=text)
    c.hyperlink = Hyperlink(ref=c.coordinate, location=f"'{target}'!A1", display=text)
    c.font = font


def _head(sheet, title: str, subtitle: str, *, last: int, current: str) -> None:
    sheet.sheet_view.showGridLines = False
    sheet["A1"] = title
    sheet["A1"].font = base.TITLE_FONT
    sheet.row_dimensions[1].height = 30
    sheet["A2"] = subtitle
    sheet["A2"].font = base.SUBTITLE_FONT
    sheet["A2"].alignment = base.WRAP_TOP
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last)
    nav = ["Match Day", "War Room", "Lineup Lab", "Scouting Cards", "Captain Packet", "Coach Dashboard"]
    sheet.cell(row=3, column=1, value="Go to:").font = base.MUTED_FONT
    col = 2
    for name in nav:
        if name == current:
            continue
        _link(sheet, 3, col, name, name)
        col += 1


def _span(sheet, row: int, c1: int, c2: int, value: Any, *, font: Font | None = None, fill=None, wrap: bool = True,
          height: float | None = None, shrink: bool = False) -> None:
    """Write one value across a merged span.

    `shrink` is for single-line unwrapped cells whose text is variable-length
    identity data (names, record IDs, shared-opponent counts). Excel only spills
    unwrapped text into a genuinely EMPTY neighbour, and in a packed row there is
    none -- so without shrink-to-fit the overflow is silently clipped on paper.
    Shrinking keeps the row on one line, which is what preserves the Captain
    Packet's tuned one-scale page geometry. It has no effect when `wrap` is on,
    because Excel ignores shrinkToFit for wrapped cells.
    """
    cell = sheet.cell(row=row, column=c1, value=value)
    if font is not None:
        cell.font = font
    if fill is not None:
        for c in range(c1, c2 + 1):
            sheet.cell(row=row, column=c).fill = fill
    if wrap:
        cell.alignment = base.WRAP_TOP
    elif shrink:
        cell.alignment = Alignment(shrinkToFit=True, vertical="top")
    if c2 > c1:
        sheet.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
    if height:
        sheet.row_dimensions[row].height = height


def _blank_if(ref: str, expr: str) -> str:
    return f'=IF({ref}="","",{expr})'


# ---------------------------------------------------------------------------
# Match Day (control panel)
# ---------------------------------------------------------------------------

def _meeting_sl_display(row: str, column: str) -> str:
    """Keep uncaptured historical SL out of the captain-facing numeric scale."""
    value = f"INDEX(Meetings_Table[{column}],{row})"
    return f'IFERROR(IF(1*{value}>0,1*{value},"?"),"?")'


def build_match_day(wb, *, slots: dict[str, int], viewer_label: str | None, viewer_key: str | None,
                    card_number: str | None, default_team: str | None, stats: dict[str, Any],
                    format_options_source: str) -> None:
    ws = wb.create_sheet("Match Day", 0)
    for letter, width in zip("ABCDEFGHIJKL", (24, 46, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14)):
        ws.column_dimensions[letter].width = width
    _head(ws, "Ultimate Coach — Match Day",
          "Set up tonight's matchup once — every tab follows it. Yellow cells are yours; green-gray cells are calculated.",
          last=12, current="Match Day")
    fresh = stats["freshness"]
    stale = stale_warning(fresh)
    line = ((stale + " " if stale else "")
            + f"Built {fresh['build_date']} · offline snapshot: latest recorded result {fresh['latest_result']}"
            + f" · times in {stats['tz']} · this file never refreshes itself.")
    # The selected team's own missing results lead the line (uc_TeamStaleText is "" when there are none).
    _span(ws, 4, 1, 12, '=uc_TeamStaleText&"' + line.replace('"', '""') + '"',
          font=WARN_FONT if stale else base.MUTED_FONT, height=58 if stale else 30)
    base._section(ws, 5, "1 · Set up the matchup (yellow = your input)", last_col=12)
    rows = [
        (6, "Player", viewer_label or "", "Pick your name/label. Record IDs are available on Players.",
         "PlayerLabelList"),
        (7, "Team", default_team or "", "Only this player's current teams (team · session · format).", "uc_TeamList"),
        (8, "Format", "8-Ball & 9-Ball", "Default: every 8-Ball and 9-Ball variant. Or pick one recorded format.",
         format_options_source),
        (9, "Scheduled date", "", "Blank = suggested date (the earliest scheduled date on or after the build date). "
                                  "Or pick one of this team's real dates.", "uc_DateList"),
        (10, "Fixture", "", "Only needed when the date has more than one fixture — nothing is chosen for you.",
         "uc_FixtureList"),
    ]
    for r, label, value, help_text, source in rows:
        ws.cell(row=r, column=1, value=label).font = base.LABEL_FONT
        base._input(ws.cell(row=r, column=2), value)
        ws.cell(row=r, column=2).number_format = "@" if r in (6, 7) else "General"
        _dv(ws, f"B{r}", source, help_text)
        _span(ws, r, 3, 12, help_text, font=base.MUTED_FONT, height=30)
    _span(ws, 11, 1, 12, "Excel can't erase what you typed: when an input stops fitting (for example after you change the "
                         "player), it is ignored and the reason is shown in step 2 — no stale results are kept.",
          font=base.MUTED_FONT, height=30)
    base._section(ws, 12, "2 · Effective matchup (calculated — every tab uses this)", last_col=12)
    eff = [
        (13, "Player", '=IF(uc_ViewerLabel<>"",uc_ViewerLabel,IF(uc_ViewerKey="","Choose a player in step 1.",'
                       '"⚠ No verified player matches “"&\'Match Day\'!$B$6&"”."))',
         (f'=IF(uc_ViewerKey="{viewer_key}","League card #{card_number} was verified to this record when the build was '
          f'configured (display only; card numbers are per league and never used as identity).","")'
          if viewer_key and card_number else '=""')),
        (14, "Team", '=IF(uc_TeamLabel="","—",uc_TeamLabel)', "=uc_TeamMsg"),
        (15, "Format", "=uc_FormatLabel", '=""'),
        (16, "Date", '=IF(uc_DateDisplay="","—",uc_DateDisplay)', "=uc_DateMsg"),
        (17, "Fixture", '=IF(uc_Fixture="","—",uc_Fixture)', "=uc_FixMsg"),
        (18, "Venue · status", '=IF(uc_Venue="","—",uc_Venue)', '=""'),
        (19, "Opponent roster", '=IF(uc_OppMsg="","—",uc_OppMsg)', '=""'),
    ]
    for r, label, value, note in eff:
        ws.cell(row=r, column=1, value=label).font = base.LABEL_FONT
        _calc(ws.cell(row=r, column=2), value, bold=True)
        _span(ws, r, 3, 12, note, font=base.MUTED_FONT)
        ws.row_dimensions[r].height = 30
    links = [("→ Captain's War Room", "War Room"), ("→ Lineup Lab", "Lineup Lab"), ("→ Scouting Cards", "Scouting Cards"),
             ("→ Captain Packet (print)", "Captain Packet"), ("→ Coach Dashboard", "Coach Dashboard")]
    for k, (text, target) in enumerate(links):
        _link(ws, 21, 1 + k * 2, text, target, font=BIG_LINK)
    ws.row_dimensions[21].height = 22

    base._section(ws, 23, "Fixtures on the effective date", last_col=12)
    heads = ["Fixture", "Kickoff", "Home/Away", "Format", "Opponent", "Venue", "Status", "Score (home–away)", "Opponent Roster"]
    base._subheader(ws, 24, [(1, "Fixture"), (3, "Kickoff"), (4, "Home/Away"), (5, "Format"), (6, "Opponent"),
                             (8, "Venue"), (9, "Status"), (10, "Score (home–away)"), (11, "Opponent Roster")])
    for k in range(1, slots["fixtures"] + 1):
        r = 24 + k
        row_ref = f"INDEX(uc_FixRows,{k})"
        _span(ws, r, 1, 2, f'=IF({row_ref}="","",INDEX(uc_FixtureList,{k}))', wrap=True)
        for col, name, c2 in ((3, "Kickoff", 3), (4, "Home/Away", 4), (5, "Format", 5), (6, "Opponent", 7), (8, "Venue", 8),
                              (9, "Status", 9), (10, "Score (home–away)", 10), (11, "Opponent Roster", 12)):
            _span(ws, r, col, c2, f'=IF({row_ref}="","",INDEX(Schedule_Table[{name}],{row_ref}))', font=SMALL)
        for c in range(1, 13):
            ws.cell(row=r, column=c).border = base.CELL_BORDER
    top = 26 + slots["fixtures"]
    base._section(ws, top, "Your teams (dropdown source for step 1)", last_col=12)
    base._subheader(ws, top + 1, [(1, "Slot"), (2, "Team"), (3, "Next scheduled date (this format)")])
    for k in range(1, slots["teams"] + 1):
        r = top + 1 + k
        ws.cell(row=r, column=1, value=f'=IF(INDEX(uc_TeamList,{k})="","","Team {k}")')
        ws.cell(row=r, column=2, value=f'=INDEX(uc_TeamList,{k})')
        _span(ws, r, 3, 6, f'=IF(INDEX(uc_TeamList,{k})="","",INDEX(uc_TeamNextDisplay,{k}))', wrap=False)
    top = top + slots["teams"] + 3
    base._section(ws, top, "Scheduled dates for the effective team and format", last_col=12)
    for k in range(1, slots["dates"] + 1):
        r = top + 1 + (k - 1) // 4
        c = 1 + ((k - 1) % 4) * 3
        ws.cell(row=r, column=c, value=f'=INDEX(uc_DateList,{k})')
    top = top + 2 + (slots["dates"] - 1) // 4
    base._section(ws, top, "About this data", last_col=12)
    notes = [
        "Dates, weekdays and kickoff times are converted to " + stats["tz"] + ". A fixture stored as 2026-08-30T01:00:00Z "
        "is Saturday Aug 29 at 7:00 PM in Denver.",
        "APA record ID = APA's member record number (the identity used everywhere). It is not the league card number "
        "printed on a member card.",
        "Rosters are each team's CURRENT captured roster, not a reconstruction of who played on a past date.",
    ]
    for k, text in enumerate(notes, start=1):
        _span(ws, top + k, 1, 12, text, font=base.MUTED_FONT, height=30)
    ws.freeze_panes = "A4"


# ---------------------------------------------------------------------------
# War Room
# ---------------------------------------------------------------------------

def _roster_section(ws, top: int, R: int, *, title_ours: str, title_theirs: str) -> int:
    base._subheader(ws, top, [(1, "OUR TEAM"), (7, "OPPONENT")])
    ws.cell(row=top, column=1).fill = base.SECTION_FILL
    ws.cell(row=top, column=1).font = base.SECTION_FONT
    ws.cell(row=top, column=7).fill = base.OPPONENT_FILL
    ws.cell(row=top, column=7).font = base.SECTION_FONT
    _span(ws, top, 2, 5, title_ours, font=base.SUBHEAD_FONT)
    _span(ws, top, 8, 12, title_theirs, font=base.SUBHEAD_FONT)
    base._subheader(ws, top + 1, [(1, "Player"), (3, "SL"), (4, "Team W-L"), (5, "Availability · lineup"),
                                  (7, "Player"), (9, "SL"), (10, "Team W-L"), (11, "vs our roster"),
                                  (12, "Played")])
    for k in range(1, R + 1):
        r = top + 1 + k
        _span(ws, r, 1, 2, f'=INDEX(wr_OurLabels,{k})', font=SMALL)
        ws.cell(row=r, column=3, value=f'=INDEX(wr_OurSL,{k})')
        ws.cell(row=r, column=4, value=f'=INDEX(wr_OurWL,{k})')
        ws.cell(row=r, column=5, value=f'=IF(INDEX(wr_OurLabels,{k})="","",INDEX(wr_OurAvail,{k})&" · "&INDEX(wr_OurLineup,{k}))')
        _span(ws, r, 7, 8, f'=INDEX(wr_OppLabels,{k})', font=SMALL)
        ws.cell(row=r, column=9, value=f'=INDEX(wr_OppSL,{k})')
        ws.cell(row=r, column=10, value=f'=INDEX(wr_OppWL,{k})')
        ws.cell(row=r, column=11, value=f'=IF(INDEX(wr_OppCard,{k})="","",INDEX(Scouting_Table[Vs Our Roster],INDEX(wr_OppCard,{k})))')
        ws.cell(row=r, column=11).font = SMALL
        ws.cell(row=r, column=11).alignment = base.WRAP_TOP
        ws.cell(row=r, column=12, value=f'=INDEX(wr_OppPlayed,{k})')
        for c in range(1, 13):
            ws.cell(row=r, column=c).border = base.CELL_BORDER
        ws.row_dimensions[r].height = 28
    return top + 2 + R


def build_war_room(wb, *, slots: dict[str, int], engine: dict[str, Any]) -> dict[str, int]:
    R = slots["roster"]
    ws = wb.create_sheet("War Room", 1)
    for letter, width in zip("ABCDEFGHIJKLM", (30, 15, 9, 11, 22, 3, 15, 15, 9, 11, 30, 10, 3)):
        ws.column_dimensions[letter].width = width
    _head(ws, "Captain's War Room — Match Night",
          "Who should I put up next? Everything for tonight's fixture, from recorded evidence only — no odds, no guarantees.",
          last=12, current="War Room")
    _span(ws, 4, 1, 12, "=wr_Status", font=Font(bold=True, size=12, color=base.FELT_DEEP))
    for r, label, help_text in ((5, "Our team (optional override)", "Blank = follow Match Day. Enter another team to explore; clear it to return."),
                                (6, "Opponent (optional override)", "Blank = follow Match Day's fixture opponent.")):
        _span(ws, r, 1, 2, label, font=base.LABEL_FONT)
        base._input(ws.cell(row=r, column=3))
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
        _dv(ws, f"C{r}", "TeamNameList", help_text)
        _span(ws, r, 7, 12, help_text, font=base.MUTED_FONT)
    _span(ws, 7, 1, 12, "=wr_Msg", font=WARN_FONT)
    base._section(ws, 8, "Match summary", last_col=12)
    _span(ws, 9, 1, 12, '=IF(wr_Local,"Local exploration — not tied to Match Day’s fixture.",IF(uc_Fixture="","No fixture selected on Match Day.",uc_Fixture))',
          font=Font(bold=True, size=12), height=22)
    _span(ws, 10, 1, 12, '=IF(wr_Local,"",uc_Venue)', font=base.MUTED_FONT)

    base._section(ws, 12, "Rosters (SL = this team's captured skill level for its format)", last_col=12)
    end = _roster_section(ws, 13, R, title_ours="=wr_OurLabel", title_theirs="=wr_OppLabel")
    _span(ws, end, 1, 12, '=IF(AND(ll_OurTeamOK,ll_OppTeamOK,NOT(ll_FixOK)),"⚠ Lineup Lab marks are for "&IF(ll_PlanIn="",'
                          '"no fixture",ll_PlanIn)&" — not applied to this fixture. ","")&'
                          'IF(AND(ll_OurTeam<>"",NOT(ll_OurTeamOK)),"⚠ Lineup Lab marks are for "&ll_OurTeam&" — not applied to "&'
                          'wr_OurLabel&". ","")&IF(AND(ll_OppTeam<>"",NOT(ll_OppOK)),"⚠ Opponent marks are for "&ll_OppTeam&'
                          '" — not applied. ","")&"Team W-L = this team’s captured record this session. “No data” = not captured. '
                          'Availability, lineup and played are your Lineup Lab marks, never evidence; Unknown is not Unavailable."',
          font=base.MUTED_FONT, height=30)

    top = end + 2
    base._section(ws, top, "Top opportunities — first by recorded direct results (favorable direct first, then even, then indirect)",
                  last_col=12)
    for k in range(1, R + 1):
        r = top + k
        _span(ws, r, 1, 2, f'=IF(INDEX(wr_OppLabels,{k})="","","vs "&INDEX(wr_OppLabels,{k})&" · SL "&INDEX(wr_OppSL,{k}))',
              font=SMALL)
        _span(ws, r, 3, 12, (f'=IF(INDEX(wr_OppLabels,{k})="","",IF(NOT(INDEX(wr_OppUnplayed,{k})),"Already played.",'
                             f'IF(INDEX(wr_Send1,{k})="",IF(wr_HasEvidence,"No favorable, even or indirect evidence among our remaining players.",""),'
                             f'INDEX(wr_SendList,{k}))))'), font=SMALL)
        ws.row_dimensions[r].height = 28
    top = top + R + 2
    base._section(ws, top, "Top risks", last_col=12)
    _span(ws, top + 1, 1, 12, "Tonight's flags — remaining players vs unplayed opponents; historical-only flags are unknown, not cleared",
          font=base.SUBHEAD_FONT, fill=base.SUBHEAD_FILL, height=30)
    for n in range(1, R + 1):
        row = f"MATCH({n},wr_LiveThreatOrder,0)"
        note = f"INDEX(wr_OppNotes,{row})"
        _span(ws, top + 1 + n, 1, 12, f'=IFERROR(INDEX(wr_LiveThreatText,{row})&IFERROR(IF({note}="",""," · 📝 "&{note}&'
                                      f'" (your opinion, not APA facts)"),""),'
                                      f'IF({n}=1,IF(wr_HasEvidence,IF(COUNTIF(wr_OurRemaining,TRUE)=0,"No remaining players — no live comparison.","No winning-record flag vs remaining players; missing records are unknown."),""),""))',
              font=SMALL, height=45)
    t2 = top + R + 2
    _span(ws, t2, 1, 12, "Recorded loss cautions — first 5 remaining pairings; most net losses first, then meetings; all in Captain Matrix",
          font=base.SUBHEAD_FONT, fill=base.SUBHEAD_FILL, height=30)
    for n in range(1, 6):
        _span(ws, t2 + n, 1, 12, f'=IFERROR(INDEX(Concerning_Table[Pairing],INDEX(wr_ConcernRow,MATCH({n},wr_ConcernRun,0))),'
                                 f'IF({n}=1,IF(wr_HasEvidence,"No concerning direct records among remaining pairings.",""),""))',
              font=SMALL)
    t3 = t2 + 7
    _span(ws, t3, 1, 12, "Open risks — unplayed opponents with no favorable direct option left among our remaining players",
          font=base.SUBHEAD_FONT, fill=base.SUBHEAD_FILL)
    for n in range(1, R + 1):
        _span(ws, t3 + n, 1, 12, f'=IFERROR(INDEX(wr_OppLabels,MATCH({n},wr_RiskRun,0))&" — "&IF(INDEX(wr_SendLeft,MATCH({n},wr_RiskRun,0))>0,'
                                 f'"only even or indirect evidence left","no evidence-backed option left"),IF({n}=1,IF(wr_HasEvidence,'
                                 f'"None — every unplayed opponent still has a favorable direct option.",""),""))', font=SMALL)

    top = t3 + R + 2
    base._section(ws, top, "Lineup Lab snapshot (your marks applied; edit them on Lineup Lab)", last_col=12)
    metrics = [
        ("Remaining players", '=IF(wr_OurCount=0,"—",wr_RemainingCount&" of "&wr_OurCount&IF(wr_RemainingUnknown>0," ("&'
                              'wr_RemainingUnknown&" with unknown availability — still counted as remaining)",""))'),
        ("Remaining skill total", '=IF(wr_OurCount=0,"—",IF(wr_RemainingMissing=0,wr_RemainingSL&" (all remaining players have a captured SL)",'
                                  'wr_RemainingSL&" known subtotal · "&wr_RemainingMissing&" remaining player(s) without a captured SL — not a complete total"))'),
        ("Selected lineup (Planned + Played)", '=IF(wr_SelectedCount=0,"No players marked Planned or Played yet.",IF(wr_SelectedMissing=0,'
                                               '"Skill total "&wr_SelectedSL&" for "&wr_SelectedCount&" selected player(s)","Known subtotal "&wr_SelectedSL&'
                                               '" · "&wr_SelectedMissing&" selected player(s) without a captured SL")&IF(ll_Cap="",""," · your reference cap: "&'
                                               'll_Cap&" (user-entered, not verified)")&" — not a lineup-legality check.")'),
        ("Roster flexibility", '=IF(wr_UnplayedCount=0,"—","Favorable direct option left vs "&wr_GreenOpps&" of "&wr_UnplayedCount&'
                               '" unplayed opponents · any evidence-backed option vs "&wr_SendOpps&" of "&wr_UnplayedCount)'),
    ]
    for k, (label, formula) in enumerate(metrics, start=1):
        _span(ws, top + k, 1, 2, label, font=base.LABEL_FONT)
        _span(ws, top + k, 3, 12, formula, font=SMALL)
    u_top = top + len(metrics) + 1
    _span(ws, u_top, 1, 12, "Unique favorable options — consider saving (the only remaining favorable direct option vs an unplayed opponent)",
          font=base.SUBHEAD_FONT, fill=base.SUBHEAD_FILL)
    for n in range(1, R + 1):
        _span(ws, u_top + n, 1, 12,
              f'=IFERROR(INDEX(wr_OurLabels,MATCH({n},wr_UniqueRun,0))&" — only favorable direct option vs "&'
              f'INDEX(wr_UniqueDetails,MATCH({n},wr_UniqueRun,0)),IF({n}=1,IF(wr_HasEvidence,"None right now.",""),""))',
              font=SMALL)


    top = u_top + R + 2
    base._section(ws, top, "Matchup matrix — our players (rows) vs their players (columns)", last_col=12)
    _span(ws, top + 1, 1, 9, "Green = more direct wins than losses · Red = more direct losses than wins · Yellow = even direct "
                             "record, or shared-opponent evidence only (≈ ours vs theirs) · Gray = no verified evidence in this snapshot. Numbers in () are "
                             "meetings (Evidence view). Captain view: 🟢🟡⚪🔴 + our direct record. Not odds or predictions.",
          font=base.MUTED_FONT, height=30)
    ws.cell(row=top + 1, column=10, value="View").font = base.LABEL_FONT
    base._input(ws.cell(row=top + 1, column=11), "Evidence view")
    ws.merge_cells(start_row=top + 1, start_column=11, end_row=top + 1, end_column=12)
    _dv(ws, f"K{top + 1}", '"Evidence view,Captain view"', "Captain view: 🟢🟡⚪🔴 and the record. Evidence view: sample sizes too.")
    view_ref = f"$K${top + 1}"
    header = top + 2
    ws.cell(row=header, column=1, value="Our player ↓ / opponent →").font = base.SUBHEAD_FONT
    ws.cell(row=header, column=1).alignment = base.WRAP_TOP
    matrix_cols = [2, 3, 4, 5, 7, 8, 9, 10, 11, 12][:R]
    for j, col in enumerate(matrix_cols, start=1):
        c = ws.cell(row=header, column=col, value=f'=INDEX(wr_OppLabels,{j})')
        c.font = Font(bold=True, size=8, color=base.FELT_DEEP)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    narrow = min(ws.column_dimensions[get_column_letter(col)].width for col in matrix_cols)
    ws.row_dimensions[header].height = _worst_height(_longest_label(wb), narrow, 8, 42)
    grid = engine["grid"]
    helper_col0 = 15  # O.. : a same-sheet copy of the category grid for conditional formatting
    for i in range(1, R + 1):
        r = header + i
        ws.cell(row=r, column=1, value=f'=INDEX(wr_OurLabels,{i})').font = SMALL
        ws.cell(row=r, column=1).alignment = base.WRAP_TOP
        for j, col in enumerate(matrix_cols, start=1):
            cat_ref, cell_ref, _ = grid[(i, j)]
            c = ws.cell(row=r, column=col, value=f'=IF({view_ref}="Captain view",{engine["captain"][(i, j)]},{cell_ref})')
            c.font = SMALL
            c.alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(row=r, column=helper_col0 + j - 1, value=f"={cat_ref}").font = base.HELPER_FONT
        ws.row_dimensions[r].height = _worst_height(WORST_EVIDENCE, narrow, 9, 30)
    first_row, last_row = header + 1, header + R
    for j in range(R):
        ws.column_dimensions[get_column_letter(helper_col0 + j)].hidden = True
    for j, col in enumerate(matrix_cols, start=1):
        letter = get_column_letter(col)
        helper = get_column_letter(helper_col0 + j - 1)
        for code, fill in CAT_FILLS.items():
            ws.conditional_formatting.add(f"{letter}{first_row}:{letter}{last_row}",
                                          FormulaRule(formula=[f'${helper}{first_row}="{code}"'], fill=fill, stopIfTrue=True))

    top = last_row + 2
    base._section(ws, top, "Inspect — choose an opponent to see all our candidates, or one of our players to see all opponents",
                  last_col=12)
    _span(ws, top + 1, 1, 2, "Inspect opponent", font=base.LABEL_FONT)
    base._input(ws.cell(row=top + 1, column=3))
    ws.merge_cells(start_row=top + 1, start_column=3, end_row=top + 1, end_column=5)
    _dv(ws, f"C{top + 1}", "wr_OppLabels", "Pick an opponent player from tonight's roster.")
    insp = f"$C${top + 1}"
    _span(ws, top + 1, 7, 12, f'=IF({insp}="","Pick an opponent to rank our players against them (ranking rule below).","")',
          font=base.MUTED_FONT)
    j_ref = f'IFERROR(MATCH({insp},wr_OppLabels,0),"")'
    base._subheader(ws, top + 2, [(1, "Our player"), (3, "Rank"), (4, "SL"), (5, "Direct record"),
                                  (7, "Shared-opponent evidence (samples)"), (10, "Basis · ties · missing evidence")])
    for rr in range(1, R + 1):
        r = top + 2 + rr
        # Excel evaluates EVERY argument of OR(), so each guard term must itself be error-free: with nothing
        # picked, INDEX(...,"") is #VALUE! (real-Excel UAT showed #VALUE! here; GPT #84 P1).
        s = f'IFERROR(INDEX(wr_OppStart,{j_ref}),"")'
        n = f'IFERROR(INDEX(wr_OppCount,{j_ref}),0)'
        cond = f'OR({insp}="",{j_ref}="",{s}="",{rr}>{n})'
        _span(ws, r, 1, 2, f'=IF({cond},"",INDEX(MatchupEvidence_Table[Player],{s}+{rr}))', font=SMALL)
        # Top-aligned like the rest of the row: in a tall row a bottom-aligned rank sat beside the NEXT player's
        # name (real-Excel UAT 787f6d7).
        ws.cell(row=r, column=3, value=f'=IF({cond},"",INDEX(MatchupEvidence_Table[Rank],{s}+{rr}))').alignment = base.WRAP_TOP
        ws.cell(row=r, column=4, value=f'=IF({cond},"",INDEX(MatchupEvidence_Table[SL],{s}+{rr}))').alignment = base.WRAP_TOP
        _span(ws, r, 5, 6, f'=IF({cond},"",INDEX(MatchupEvidence_Table[Direct Record],{s}+{rr}))', font=SMALL)
        _span(ws, r, 7, 9, f'=IF({cond},"",INDEX(MatchupEvidence_Table[Shared-Opponent Evidence],{s}+{rr}))', font=SMALL)
        _span(ws, r, 10, 12, f'=IF({cond},"",INDEX(MatchupEvidence_Table[Basis],{s}+{rr}))', font=SMALL)
        basis_width = sum(ws.column_dimensions[get_column_letter(c)].width for c in (10, 11, 12))
        ws.row_dimensions[r].height = _worst_height(WORST_BASIS, basis_width, 9, 30)
    top2 = top + 3 + R + 1
    _span(ws, top2, 1, 2, "Inspect our player", font=base.LABEL_FONT)
    base._input(ws.cell(row=top2, column=3))
    ws.merge_cells(start_row=top2, start_column=3, end_row=top2, end_column=5)
    _dv(ws, f"C{top2}", "wr_OurLabels", "Pick one of our players.")
    insp2 = f"$C${top2}"
    i_ref = f'IFERROR(MATCH({insp2},wr_OurLabels,0),"")'
    base._subheader(ws, top2 + 1, [(1, "Opponent"), (3, "Evidence"), (5, "Direct record"),
                                   (7, "Shared-opponent evidence (samples)"), (10, "Rank vs this opponent")])
    for j in range(1, R + 1):
        r = top2 + 1 + j
        s = f"INDEX(wr_OppStart,{j})"
        cond = f'OR({insp2}="",{i_ref}="",{s}="")'
        # position of our player i inside opponent j's block: recompute with MATCH on the block's ids
        p = (f'MATCH(INDEX(wr_OurPids,{i_ref}),INDEX(MatchupEvidence_Table[Player ID],{s}+1):'
             f'INDEX(MatchupEvidence_Table[Player ID],{s}+INDEX(wr_OppCount,{j})),0)')
        _span(ws, r, 1, 2, f'=IF({cond},"",INDEX(wr_OppLabels,{j}))', font=SMALL)
        _span(ws, r, 3, 4, (f'=IF({cond},"",IFERROR(IF(INDEX(MatchupEvidence_Table[Category],{s}+{p})="G","Favorable direct",'
                            f'IF(INDEX(MatchupEvidence_Table[Category],{s}+{p})="R","Concerning direct",IF(INDEX(MatchupEvidence_Table[Category],'
                            f'{s}+{p})="E","Even direct",IF(INDEX(MatchupEvidence_Table[Category],{s}+{p})="I","Indirect only","Insufficient")))),""))'),
              font=SMALL)
        _span(ws, r, 5, 6, f'=IF({cond},"",IFERROR(INDEX(MatchupEvidence_Table[Direct Record],{s}+{p}),""))', font=SMALL)
        _span(ws, r, 7, 9, f'=IF({cond},"",IFERROR(INDEX(MatchupEvidence_Table[Shared-Opponent Evidence],{s}+{p}),""))', font=SMALL)
        _span(ws, r, 10, 12, f'=IF({cond},"",IFERROR(INDEX(MatchupEvidence_Table[Rank],{s}+{p}),""))', font=SMALL)
        ws.row_dimensions[r].height = 30

    top = top2 + 2 + R + 1
    base._section(ws, top, "Direct meetings between the rosters (newest first)", last_col=12)
    base._subheader(ws, top + 1, [(1, "Date"), (2, "Our player"), (5, "Opponent"), (9, "Result (ours)"), (10, "SL ours/theirs"),
                                  (11, "Session")])
    for k in range(1, MEETING_SLOTS + 1):
        r = top + 1 + k
        row = f'IFERROR(MATCH(wr_PairKey&"|{k}",Meetings_Table[Key],0),"")'
        cond = f'OR(NOT(wr_HasEvidence),{row}="")'
        ws.cell(row=r, column=1, value=f'=IF({cond},"",INDEX(Meetings_Table[Date],{row}))').font = SMALL
        _span(ws, r, 2, 4, f'=IF({cond},"",INDEX(Meetings_Table[Our Player],{row}))', font=SMALL, wrap=False)
        _span(ws, r, 5, 8, f'=IF({cond},"",INDEX(Meetings_Table[Opponent],{row}))', font=SMALL, wrap=False)
        ws.cell(row=r, column=9, value=f'=IF({cond},"",INDEX(Meetings_Table[Result],{row}))').font = SMALL
        ws.cell(row=r, column=10, value=f'=IF({cond},"",{_meeting_sl_display(row, "Our SL")}&" / "&{_meeting_sl_display(row, "Their SL")})').font = SMALL
        _span(ws, r, 11, 12, f'=IF({cond},"",INDEX(Meetings_Table[Session],{row}))', font=SMALL, wrap=False)
    _span(ws, top + 2 + MEETING_SLOTS, 1, 12,
          f'="? = SL not captured. "&IF(AND(wr_HasEvidence,ISNUMBER(MATCH(wr_PairKey&"|{MEETING_SLOTS + 1}",Meetings_Table[Key],0))),"More meetings exist — '
          f'filter the Meetings sheet by this pairing.",IF(AND(wr_HasEvidence,NOT(ISNUMBER(MATCH(wr_PairKey&"|1",Meetings_Table[Key],0)))),'
          f'"No recorded direct meetings between these rosters.",""))', font=base.MUTED_FONT)

    top = top + 4 + MEETING_SLOTS
    base._section(ws, top, "Team comparison", last_col=12)
    t = f'IFERROR(MATCH(wr_PairKey,TeamComparison_Table[Pair Key],0),"")'
    comps = [("Players rostered", "Our Rostered", "Opp Rostered"), ("Players with a captured SL", "Our Captured SL", "Opp Captured SL"),
             ("Skill total (captured SLs only)", "Our SL Total", "Opp SL Total"), ("Recorded games (all opponents)", "Our Games", "Opp Games"),
             ("Players with no recorded games", "Our No-Game Players", "Opp No-Game Players")]
    for k, (label, a, b) in enumerate(comps, start=1):
        r = top + k
        _span(ws, r, 1, 2, label, font=base.LABEL_FONT)
        _span(ws, r, 3, 5, f'=IF({t}="","",INDEX(TeamComparison_Table[{a}],{t}))', wrap=False)
        _span(ws, r, 7, 9, f'=IF({t}="","",INDEX(TeamComparison_Table[{b}],{t}))', wrap=False)
    for k, (label, col) in enumerate((("Direct meetings between the rosters", "Direct Meetings"),
                                      ("Opponent players our roster has met directly", "Opponents Met"),
                                      ("Player pairings by evidence", "Pairings")), start=len(comps) + 1):
        r = top + k
        _span(ws, r, 1, 2, label, font=base.LABEL_FONT)
        _span(ws, r, 3, 12, f'=IF({t}="","",INDEX(TeamComparison_Table[{col}],{t}))', wrap=False)
    top = top + len(comps) + 5
    base._section(ws, top, "How to read this", last_col=12)
    for k, text in enumerate([
        "Ranking rule (reviewed, unchanged): players with direct meetings first (by observed direct record, then more meetings), "
        "then shared-opponent results only (by our record against opponents both players faced, then more shared opponents, "
        "then more games); no verified evidence = listed last, not ranked. Ties are shown as “2=” and named.",
        "Recorded sends keep that order and drop only concerning (losing direct) and no-evidence pairings. A direct "
        "record ranks ahead of indirect evidence even when it is small — read the records and sample sizes.",
        "No recorded meetings with our roster does not mean a weak opponent — it means unknown.",
        "Nothing here is a win probability (none is calibrated), a confidence claim or a guaranteed lineup.",
    ], start=1):
        _span(ws, top + k, 1, 12, text, font=base.MUTED_FONT, height=30)
    ws.freeze_panes = "A5"
    return {"matrix_header": header}


# ---------------------------------------------------------------------------
# Lineup Lab
# ---------------------------------------------------------------------------

_MD_PREFIX = {"wr_": "md_", "ll_": "lm_"}
_MD_SHEETS = ("Lineup Lab", "Scouting Cards", "Captain Packet", "Coach Dashboard", "Command Center")


def _to_md(text: str, engine_title: str, md_title: str) -> str:
    import re
    text = re.sub(r"(?<![A-Za-z0-9_])(wr|ll)_", lambda m: _MD_PREFIX[m.group(1) + "_"], text)
    return text.replace(f"{engine_title}!", f"'{md_title}'!")


def split_match_day_engine(wb) -> None:
    """Local overrides affect only their own tab (Paul, GPT audit #84).

    The War Room's override cells feed the wr_* pairing. Every other output --
    Lineup Lab, Scouting Cards, Captain Packet, Coach Dashboard -- must keep
    following Match Day, so the whole pairing engine is copied once to "Engine MD"
    with wr_/ll_ renamed md_/lm_ and the War Room override inputs pinned blank:
    md_* is always Match Day's fixture. Those four sheets (and the Coach
    Dashboard's engine cells) are re-pointed at md_*/lm_*, so a War Room override
    can never put one fixture's heading over another opponent's roster.
    """
    import re
    src = wb["Engine"]
    md = wb.copy_worksheet(src)
    md.title = "Engine MD"
    for row in md.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                c.value = _to_md(c.value, "Engine", "Engine MD")
    for name in list(wb.defined_names):
        if name[:3] in _MD_PREFIX:
            target = _MD_PREFIX[name[:3]] + name[3:]
            text = wb.defined_names[name].attr_text.replace("Engine!", "'Engine MD'!")
            wb.defined_names[target] = DefinedName(target, attr_text=text)
    for name in ("md_OurInput", "md_OppInput"):
        ref = wb.defined_names[name].attr_text.split("!")[1].replace("$", "")
        md[ref].value = '=""'
    # The Coach Dashboard's engine cells (Player B pool, format) follow Match Day too.
    cd_rows = []
    for name in wb.defined_names:
        if name.startswith("cd_"):
            m = re.search(r"\$?[A-Z]+\$?(\d+)", wb.defined_names[name].attr_text.split("!")[1])
            cd_rows.append(int(m.group(1)))
    for row in src.iter_rows(min_row=min(cd_rows) - 2):
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                c.value = _to_md(c.value, "Engine", "Engine")
    for sheet in _MD_SHEETS:
        ws = wb[sheet]
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    c.value = _to_md(c.value, "Engine", "Engine MD")
        for dv in ws.data_validations.dataValidation:
            if dv.formula1:
                dv.formula1 = _to_md(dv.formula1, "Engine", "Engine MD")
    md.sheet_state = "hidden" if src.sheet_state == "hidden" else src.sheet_state


# A War Room override accepts ANY Teams_Table label (wr_OurValid/wr_OppValid are a COUNTIF over
# that column, ui/excel_war_room.py:419-424), so these warnings can be asked to quote the real
# candidate's 327-character label. Sizing the row for that made it 144pt of mostly empty space;
# sizing it for the schedule's 24 characters clipped the override case (GPT, issue #84 comment
# 6104357111 -- confirmed against the source, my "follows Match Day" reasoning was wrong). So bound
# the TEXT: the label is context, the clause saying the marks are NOT applied is the point, and a
# clipped row loses the clause while a clipped label loses nothing that matters.
LABEL_CLIP = 60


def build_lineup_lab(wb, *, slots: dict[str, int], default_team: str | None, default_opp: str | None,
                     default_date: str | None = None) -> None:
    R = slots["roster"]
    ws = wb.create_sheet("Lineup Lab", 2)
    for letter, width in zip("ABCDEFGH", (6, 44, 18, 30, 10, 12, 3, 3)):
        ws.column_dimensions[letter].width = width
    status_width = sum(ws.column_dimensions[c].width for c in "DEF")   # the merged status span
    _head(ws, "Lineup Lab", "Your planning marks for tonight — inputs, never evidence. Results update instantly on this "
                            "sheet and on the War Room.", last=6, current="Lineup Lab")
    rows = [(5, "Planning for our team", default_team or "", "TeamNameList",
             '=IF(ll_OurTeamOK,"✓ Matches Match Day’s team.",IF(ll_OurTeam="","Name the team you are planning for.",'
             '"⚠ Match Day shows "&IF(LEN(IF(wr_OurLabel="","no team",wr_OurLabel))>60,LEFT(IF(wr_OurLabel="","no team",wr_OurLabel),59)&"…",IF(wr_OurLabel="","no team",wr_OurLabel))&" — these marks are NOT applied there."))'),
            (6, "Planning for opponent", default_opp or "", "TeamNameList",
             '=IF(ll_OppOK,"✓ Matches Match Day’s opponent.",IF(ll_OppTeam="","Name the opponent team.","⚠ Match Day’s opponent is "&'
             'IF(LEN(IF(wr_OppLabel="","none",wr_OppLabel))>60,LEFT(IF(wr_OppLabel="","none",wr_OppLabel),59)&"…",IF(wr_OppLabel="","none",wr_OppLabel))&" — opponent marks are NOT applied there."))'),
            (7, "Reference skill cap (optional)", "", None,
             '="Your own reference number (e.g. your division rule). Never assumed, never applied automatically."')]
    for r, label, value, source, status in rows:
        _span(ws, r, 1, 2, label, font=base.LABEL_FONT)
        base._input(ws.cell(row=r, column=3), value)
        if source:
            _dv(ws, f"C{r}", source, "Pick a team.")
        _span(ws, r, 4, 6, status, font=base.MUTED_FONT)
        # Excel never auto-fits a FORMULA row, so a fixed height silently clips the longer
        # branch. The mismatch warnings are the whole point of these cells, so size them for
        # the widest team label this workbook can actually name (native run 2026-10-11).
        # The quoted label is clipped to LABEL_CLIP in the formulas above, so this worst case holds
        # for ANY label the data or a War Room override can produce.
        ws.row_dimensions[r].height = _worst_height(
            "⚠ Match Day’s opponent is " + "W" * LABEL_CLIP + " — opponent marks are NOT applied there.",
            status_width, 11, 30)
    _span(ws, 8, 1, 6, "Marks are for ONE fixture (below, ending in its match number). Pick another fixture on Match Day "
                       "— even later the same day — and these marks stop applying (it says so). Clear them, pick the new "
                       "fixture in the cell below, and plan again. Coach notes describe the player and always follow the "
                       "opponent team.",
          font=base.MUTED_FONT, height=44)
    _span(ws, 9, 1, 2, "Planning for fixture", font=base.LABEL_FONT)
    base._input(ws.cell(row=9, column=3), default_date or "")
    _dv(ws, "C9", "uc_PlanKeyList", "Pick Match Day's current fixture (the list offers exactly that one).")
    _span(ws, 9, 4, 6, '=IF(ll_FixOK,"✓ Matches Match Day’s fixture — availability, lineup and played applied.",'
                       'IF(uc_PlanKey="","Choose a fixture on Match Day first.",'
                       '"⚠ Match Day’s fixture is "&uc_PlanKey&" — availability, lineup and played are NOT applied. Notes still are."))',
          font=base.MUTED_FONT)
    # Clipped on the real candidate at a fixed 30pt: the warning rendered only up to the match
    # number and cut the clause saying the marks are NOT applied, while the marks stayed visible
    # in the table below it. Size it for the longest fixture key this workbook can offer.
    ws.row_dimensions[9].height = _worst_height(
        f"⚠ Match Day’s fixture is {_longest_plan_key(wb)} — availability, lineup and played are "
        "NOT applied. Notes still are.", status_width, 11, 30)
    # Planning selections must remain identifiable beside the status text. Excel
    # does not auto-fit these rows, and the input occupies only narrow column C.
    for r in (5, 6, 9):
        cell = ws.cell(row=r, column=3)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        context = _longest_plan_key(wb) if r == 9 else _longest_team_label(wb)
        context = max((context, str(cell.value or "")), key=len)
        ws.row_dimensions[r].height = _worst_height(
            context, ws.column_dimensions["C"].width, cell.font.sz,
            ws.row_dimensions[r].height or 30)
    base._section(ws, 10, "Our roster — availability and lineup (blank availability = Unknown)", last_col=6)
    base._subheader(ws, 11, [(1, "#"), (2, "Player"), (3, "Availability"), (4, "Lineup"), (5, "SL"), (6, "Team W-L")])
    our_first = 12
    avail = DataValidation(type="list", formula1='"' + ",".join(AVAILABILITY_CHOICES) + '"', allow_blank=True)
    lineup = DataValidation(type="list", formula1='"' + ",".join(LINEUP_CHOICES) + '"', allow_blank=True)
    played = DataValidation(type="list", formula1='"Played"', allow_blank=True)
    for dvx in (avail, lineup, played):
        ws.add_data_validation(dvx)
    for k in range(1, R + 1):
        r = our_first + k - 1
        ws.cell(row=r, column=1, value=f'=IF(INDEX(ll_OurLabels,{k})="","",{k})')
        ws.cell(row=r, column=2, value=f'=INDEX(ll_OurLabels,{k})')
        for c in (3, 4):
            base._input(ws.cell(row=r, column=c))
            ws.cell(row=r, column=c).font = Font(bold=True)
        avail.add(f"C{r}")
        lineup.add(f"D{r}")
        ws.cell(row=r, column=5, value=f'=INDEX(ll_OurSL,{k})')
        ws.cell(row=r, column=6, value=f'=INDEX(ll_OurWL,{k})')
    opp_top = our_first + R + 1
    base._section(ws, opp_top, "Opponent roster — who has played, and your scouting notes", last_col=6)
    base._subheader(ws, opp_top + 1, [(1, "#"), (2, "Player"), (3, "Played"), (4, "Coach notes"), (5, "SL"),
                                      (6, "Team W-L")])
    opp_first = opp_top + 2
    for k in range(1, R + 1):
        r = opp_first + k - 1
        ws.cell(row=r, column=1, value=f'=IF(INDEX(ll_OppLabels,{k})="","",{k})')
        ws.cell(row=r, column=2, value=f'=INDEX(ll_OppLabels,{k})')
        for c in (3, 4):
            base._input(ws.cell(row=r, column=c))
            ws.cell(row=r, column=c).font = Font(bold=True)
        played.add(f"C{r}")
        ws.cell(row=r, column=4).alignment = base.WRAP_TOP
        ws.cell(row=r, column=5, value=f'=INDEX(ll_OppSL,{k})')
        ws.cell(row=r, column=6, value=f'=INDEX(ll_OppWL,{k})')
    assert our_first == slots["ll_our_first"] and opp_first == slots["ll_opp_first"]
    res = opp_first + R + 1
    base._section(ws, res, "Results (instant, for the War Room's matchup)", last_col=6)
    lines = [
        ("Remaining players", '=IF(wr_OurCount=0,"—",wr_RemainingCount&" of "&wr_OurCount&IF(wr_RemainingUnknown>0," ("&wr_RemainingUnknown&" unknown availability)",""))'),
        ("Remaining skill total", '=IF(wr_OurCount=0,"—",IF(wr_RemainingMissing=0,wr_RemainingSL,wr_RemainingSL&" known · "&wr_RemainingMissing&" missing SL"))'),
        ("Selected lineup total", '=IF(wr_SelectedCount=0,"—",IF(wr_SelectedMissing=0,wr_SelectedSL&" ("&wr_SelectedCount&" players)",'
                                  'wr_SelectedSL&" known · "&wr_SelectedMissing&" missing SL")&IF(ll_Cap="",""," vs your reference "&ll_Cap))'),
        ("Flexibility", '=IF(wr_UnplayedCount=0,"—","Favorable option left vs "&wr_GreenOpps&" of "&wr_UnplayedCount&" unplayed opponents")'),
        ("Open risks", '=IF(wr_UnplayedCount=0,"—",wr_RiskCount&" unplayed opponent(s) with no favorable direct option left")'),
    ]
    for k, (label, formula) in enumerate(lines, start=1):
        _span(ws, res + k, 1, 2, label, font=base.LABEL_FONT)
        _span(ws, res + k, 3, 6, formula, font=SMALL)
    bs = res + len(lines) + 1
    _span(ws, bs, 1, 6, "Recorded option per unplayed opponent — and why (listed by results, not confidence)",
          font=base.SUBHEAD_FONT, fill=base.SUBHEAD_FILL)
    best_height = _worst_height(_best_send_worst(wb, R),
                                sum(ws.column_dimensions[c].width for c in "ABCDEF"), 9, 30)
    for k in range(1, R + 1):
        _span(ws, bs + k, 1, 6, f'=IF(OR(INDEX(wr_OppLabels,{k})="",NOT(INDEX(wr_OppUnplayed,{k}))),"","vs "&INDEX(wr_OppLabels,{k})&": "&'
                                f'IF(INDEX(wr_BestText,{k})="","no evidence-backed option left among our remaining players",'
                                f'INDEX(wr_BestText,{k})))', font=SMALL, height=best_height)
    ws.freeze_panes = "A4"


# ---------------------------------------------------------------------------
# Scouting Cards
# ---------------------------------------------------------------------------

CARD_FIELDS = [("Quick read", "Quick Read"), ("Team record", "Team Record"), ("League lifetime", "Lifetime"), ("Recorded games", "Sample"),
               ("Vs our roster", "Vs Our Roster"), ("Meetings with our players", "Met List"),
               ("Shared-opponent evidence", "Shared Summary"), ("Record by opponent SL", "By SL"),
               ("Winning records vs", "Winning SL"), ("Losing records vs", "Losing SL"), ("Missing information", "Missing")]


def scouting_quick_read_height(texts, width: float, size: float = 9) -> float:
    """Reserve room for any precomputed answer; merged formula cells never auto-fit."""
    return max((_worst_height(str(text or ""), width, size, 18) for text in texts), default=18)


COACH_NOTE_PREVIEW_SUFFIX = " ... (preview; full note on Coach Notes / Lineup Lab)"


def _coach_note_preview(k: int, limit: int) -> str:
    """Bound only the printed observation; preserve the complete input and its Coach label."""
    notes = f'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(INDEX(wr_OppNotes,{k}),CHAR(13)," "),CHAR(10)," "),CHAR(9)," ")'
    return f'IF(LEN({notes})>{limit},LEFT({notes},{limit})&"{COACH_NOTE_PREVIEW_SUFFIX}",{notes})'


def _card_block(ws, top: int, k: int, *, compact: bool = False, quick_height: float | None = None) -> int:
    card = f"INDEX(wr_OppCard,{k})"
    _span(ws, top, 1, 12, f'=IF(INDEX(wr_OppLabels,{k})="","",INDEX(wr_OppLabels,{k})&" · SL "&INDEX(wr_OppSL,{k})&'
                          f'IF(INDEX(wr_OppPlayed,{k})="Played"," · already played",""))',
          font=Font(bold=True, size=12, color="FFFFFF"), fill=base.OPPONENT_FILL)
    fields = CARD_FIELDS if not compact else [f for f in CARD_FIELDS if f[1] in ("Quick Read", "Vs Our Roster", "Met List", "By SL", "Missing")]
    for n, (label, col) in enumerate(fields, start=1):
        r = top + n
        _span(ws, r, 1, 2, f'=IF(INDEX(wr_OppLabels,{k})="","","{label}")', font=base.LABEL_FONT)
        _span(ws, r, 3, 12, f'=IF(OR(INDEX(wr_OppLabels,{k})="",{card}=""),IF(INDEX(wr_OppLabels,{k})="","","Not precomputed for this pairing"),'
                            f'INDEX(Scouting_Table[{col}],{card}))', font=Font(size=11), height=quick_height if col == "Quick Read" else None)
    r = top + len(fields) + 1
    _span(ws, r, 1, 2, f'=IF(INDEX(wr_OppLabels,{k})="","","Coach observations")', font=base.LABEL_FONT)
    # Merged formula rows cannot auto-fit when a captain adds notes later.
    # Flatten line breaks for this bounded print preview; keep the stored note intact.
    preview = _coach_note_preview(k, 500)
    width = sum(ws.column_dimensions[get_column_letter(c)].width for c in range(3, 13))
    height = _worst_height("W " * ((500 + len(COACH_NOTE_PREVIEW_SUFFIX) + 1) // 2), width, 11, 18)
    _span(ws, r, 3, 12, f'=IF(INDEX(wr_OppLabels,{k})="","",IF(INDEX(wr_OppNotes,{k})="","(add notes on Coach Notes or Lineup Lab)",{preview}))',
          font=Font(size=11), height=height)
    return r + 1


def build_scouting_cards(wb, *, slots: dict[str, int]) -> None:
    R = slots["roster"]
    ws = wb.create_sheet("Scouting Cards", 3)
    for letter, width in zip("ABCDEFGHIJKL", (22, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12)):
        ws.column_dimensions[letter].width = width
    _head(ws, "Opponent Scouting Cards", "One card per opponent player — recorded facts, sample sizes, what's missing, "
                                         "and your notes.", last=12, current="Scouting Cards")
    _span(ws, 4, 1, 12, "=wr_Status", font=Font(bold=True, color=base.FELT_DEEP))
    _span(ws, 5, 1, 12, "Full-roster history; ignores tonight's marks. Recorded results only — not predictions. Missing history is unknown, not weak.",
          font=Font(size=10, color="5B6A61"), height=24)
    lookup = wb["Scouting"]
    col = SCOUTING_COLUMNS.index("Quick Read") + 1
    texts = (row[0] for row in lookup.iter_rows(min_row=2, min_col=col, max_col=col, values_only=True))
    width = sum(ws.column_dimensions[get_column_letter(c)].width for c in range(3, 13))
    quick_height = scouting_quick_read_height(texts, width, 11)
    top = 6
    card_tops = []
    for k in range(1, R + 1):
        card_tops.append(top)
        if k > 1:
            ws.row_breaks.append(Break(id=top - 1))
        top = _card_block(ws, top, k, quick_height=quick_height) + 1
    _span(ws, top, 1, 12, "“Winning/losing records vs SLx” only state the direction of recorded results against opponents "
                          "of that skill level, with the record shown — never a prediction. No meetings with our roster means "
                          "unknown, not weak.", font=base.MUTED_FONT, height=30)
    ws.freeze_panes = "A5"
    # Fixed scale respects manual card boundaries; Fit-to-page can ignore them.
    title_height = sum(ws.row_dimensions[r].height or 15 for r in range(1, 6))
    ends = card_tops[1:] + [top + 1]
    tallest = max(sum(ws.row_dimensions[r].height or 15 for r in range(start, end))
                  for start, end in zip(card_tops, ends)) + title_height
    page_width = sum(_width_pt(ws.column_dimensions[get_column_letter(c)].width) for c in range(1, 13))
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.sheet_properties.pageSetUpPr.fitToPage = False
    # Reserve width for Excel/printer column rounding; the mathematical edge
    # produced a separate sliver page in native Excel despite fitting nominally.
    ws.page_setup.scale = max(10, int(min(1, 0.9 * PACKET_PRINTABLE[0] / page_width,
                                        PACKET_PRINTABLE[1] / tallest) * 100))
    # Excel resolves this local built-in name again when Match Day changes.
    # Keep one context page when there is no opponent; never print unused slots.
    stride = len(CARD_FIELDS) + 3
    area = (f"'{ws.title}'!$A$1:INDEX('{ws.title}'!$L:$L,"
            f'{card_tops[0] - 1}+{stride}*MAX(1,COUNTIF(md_OppLabels,"?*")))')
    ws.defined_names.add(DefinedName("_xlnm.Print_Area", attr_text=area))
    ws.print_title_rows = "1:5"
    ws.page_margins.left = ws.page_margins.right = 0.35
    ws.page_margins.top = ws.page_margins.bottom = 0.45


# ---------------------------------------------------------------------------
# Captain Packet (print)
# ---------------------------------------------------------------------------

# Captain Packet layout constants (Excel width units, points). Paul's real-Excel UAT (#84): readable
# text, no clipped Basis, no orphan opponent headings, no empty bands, keep the five-page grouping.
PACKET_WIDTHS = (26, 22, 7, 11, 24, 2, 14, 10, 9, 10, 22, 10)        # A..L
PACKET_PRINTABLE = ((11 - 2 * 0.35) * 72, (8.5 - 2 * 0.45) * 72)     # landscape Letter, margins below
PACKET_TITLE_ROWS = (26, 20)                                          # rows 1-2 repeat on every page
# Printed pages the evidence section is allowed to occupy. It is the densest section, so this
# number sets the print scale for the ENTIRE packet (see build_captain_packet): 2 -> 58% and
# 6.2pt body text, 3 -> 67% and 7.0pt, 4 -> 72% and 7.5pt once the scouting cards also break.
EVIDENCE_PAGES = 3
# Printed pages for the scouting-card section, which binds the scale next once evidence has
# room: 1 -> 0.667 (7.0pt body), 2 -> the front page binds at 0.717 (7.5pt). The front page is
# deliberately NOT split -- it is the at-a-glance summary and its value is being one page.
CARD_PAGES = 2


def _width_pt(width: float) -> float:
    return int(width * 7 + 5) * 0.75


def build_captain_packet(wb, *, slots: dict[str, int], stats: dict[str, Any]) -> dict[str, Any]:
    """Printable Captain Packet that follows Match Day (md_* after split_match_day_engine).

    Every printed row has an explicit height and every column an explicit width, so the page geometry
    is known at build time; one print scale is then chosen so the tallest page fits, and each page uses
    the largest font its row heights allow. Variable-length sections are PACKED (no reserved blank slot
    bands): evidence is one continuous list in which every line names its opponent, so a page break can
    never orphan an opponent heading. Facts are unchanged; only presentation differs from the War Room.
    """
    R = slots["roster"]
    ws = wb.create_sheet("Captain Packet", 4)
    for letter, width in zip("ABCDEFGHIJKL", PACKET_WIDTHS):
        ws.column_dimensions[letter].width = width
    for letter in "PQR":
        ws.column_dimensions[letter].width = 6
    ws.sheet_view.showGridLines = False
    heights: dict[int, float] = {}

    def h(row: int, pt: float) -> None:
        ws.row_dimensions[row].height = pt
        heights[row] = pt

    def font(size: float, **kw) -> Font:
        return Font(size=size, **kw)

    white = "FFFFFF"
    ws["A1"] = "Captain Packet — Match Night"
    ws["A1"].font = font(16, bold=True, color=base.FELT_DEEP)
    ws.merge_cells("A1:L1")
    h(1, PACKET_TITLE_ROWS[0])
    _span(ws, 2, 1, 12, '=IF(uc_Fixture="","Choose a fixture on Match Day.",uc_Fixture)',
          font=font(12, bold=True, color=base.FELT_DEEP))
    h(2, PACKET_TITLE_ROWS[1])
    _span(ws, 3, 1, 12, '=uc_Venue', font=font(9.5, color="5B6A61"))
    h(3, 15)
    h(4, 4)

    # ---------------- page 1 (decision first): the lead, best sends, risks, then rosters ----------------
    r = 4
    # The lead answer comes before everything else on the printed page: every other line in this
    # packet assumes we already know who they put up, and when WE lead there is nobody to look up.
    r += 1
    _span(ws, r, 1, 2, "IF WE PUT UP FIRST", font=font(9, bold=True, color="5B6A61"))
    _span(ws, r, 3, 12,
          '=IF(wr_UnplayedCount=0,"Every opponent has already played.",'
          'IF(wr_BlindName="","No evidence-backed pick — "&wr_BlindWhy,'
          'wr_BlindName&" — "&wr_BlindWhy&wr_BlindTieNote&wr_BlindMeetingNote&'
          'IF(INDEX(wr_OurAvail,wr_BlindIdx)="Unknown"," · availability unknown","")))',
          font=font(12, bold=True, color=base.FELT_DEEP))
    blind_worst = (_longest_label(wb) + f" — {R} concerning of {R} — best available, not good · no direct record vs {R}"
                   + f" · {R} tied by matchup counts; first shown by roster order. Compare individual records in Captain Matrix."
                   + " · 999999 direct meetings total — pairing counts select first shown, not confidence · availability unknown")
    h(r, _worst_height(blind_worst, sum(PACKET_WIDTHS[2:]), 12, 30))
    r += 1
    base._section(ws, r, "Recorded options preview — direct order: win percentage, then meetings; not confidence",
                  last_col=12)
    h(r, 18)
    for k in range(1, R + 1):
        r += 1
        _span(ws, r, 1, 2, f'=IF(INDEX(wr_OppLabels,{k})="","","vs "&INDEX(wr_OppLabels,{k}))', font=font(10, bold=True))
        _span(ws, r, 3, 12, f'=IF(INDEX(wr_OppLabels,{k})="","",IF(NOT(INDEX(wr_OppUnplayed,{k})),"Already played.",'
                            f'IF(INDEX(wr_Send1,{k})="","No evidence-backed option left among our remaining players.",'
                            f'INDEX(wr_Send1,{k})&IF(INDEX(wr_Send2,{k})="",""," · "&INDEX(wr_Send2,{k}))))'
                            f'&IF(INDEX(wr_PacketSave,{k})="","",CHAR(10)&INDEX(wr_PacketSave,{k}))'
                            f'&IF(INDEX(wr_PacketCautions,{k})="","",CHAR(10)&"Loss cautions — recorded losses, not exclusions:"&CHAR(10)&INDEX(wr_PacketCautions,{k}))'
                            f'&IF(INDEX(wr_DeeperRecords,{k})="","",CHAR(10)&"Deeper direct records — more meetings, not a new order:"&CHAR(10)&INDEX(wr_DeeperRecords,{k})))',
              font=font(10))
        save_worst = _packet_save_worst(wb, sum(PACKET_WIDTHS[2:]))
        h(r, _worst_height(_longest_label(wb)*2+" — 999-999 (1998 meetings) · SMALL SAMPLE\n"+save_worst+'\n'+_packet_caution_worst(wb)+'\n'+_deeper_records_worst(wb), sum(PACKET_WIDTHS[2:]), 10, 27))
    r += 1
    base._section(ws, r, "Top risks — first 3 flags / 3 loss cautions; tonight's remaining roster; historical-only = unknown", last_col=12)
    h(r, 18)
    risk_lines = [f'=IFERROR(INDEX(wr_LiveThreatText,MATCH({n},wr_LiveThreatOrder,0)),"")'
                  for n in range(1, 4)]
    risk_lines += [f'=IFERROR("Recorded loss: "&INDEX(Concerning_Table[Pairing],INDEX(wr_ConcernRow,MATCH({n},wr_ConcernRun,0))),"")'
                   for n in range(1, 4)]
    risk_lines.append('=IF(wr_UnplayedCount=0,"","Open risks: "&wr_RiskCount&" unplayed opponent(s) with no favorable '
                      'direct option left among our remaining players.")')
    for formula in risk_lines:
        r += 1
        _span(ws, r, 1, 12, formula, font=font(10.5))
        h(r, _worst_height(_longest_label(wb)+" · Captured SL No data · historically 999999-999999 in 1999998 meetings; only vs players not in tonight's remaining lineup — unknown vs who is left, not cleared · SMALL HISTORICAL SAMPLE", sum(PACKET_WIDTHS), 10.5, 30))
    r += 1
    overview_break = r - 1
    for c1, c2, text, sub, fill in ((1, 1, "OUR TEAM", "=wr_OurLabel", base.SECTION_FILL),
                                    (7, 7, "OPPONENT", "=wr_OppLabel", base.OPPONENT_FILL)):
        ws.cell(row=r, column=c1, value=text).font = font(10.5, bold=True, color=white)
        ws.cell(row=r, column=c1).fill = fill
        _span(ws, r, c1 + 1, c1 + 4 if c1 == 1 else 12, sub, font=font(10.5, bold=True, color=base.FELT_DEEP))
    h(r, 18)
    r += 1
    for col, text in ((1, "Player"), (3, "SL"), (4, "Team W-L"), (5, "Availability · lineup"),
                      (7, "Player"), (11, "SL · Team W-L"), (12, "Played")):
        cell = ws.cell(row=r, column=col, value=text)
        cell.font = font(9, bold=True, color=base.FELT_DEEP)
        cell.fill = base.SUBHEAD_FILL
    h(r, 16)
    roster_first = r + 1
    for k in range(1, R + 1):
        r = roster_first + k - 1
        f11 = font(11)
        _span(ws, r, 1, 2, f'=INDEX(wr_OurLabels,{k})', font=f11, wrap=False)
        ws.cell(row=r, column=3, value=f'=INDEX(wr_OurSL,{k})').font = f11
        ws.cell(row=r, column=4, value=f'=INDEX(wr_OurWL,{k})').font = f11
        ws.cell(row=r, column=5, value=f'=IF(INDEX(wr_OurLabels,{k})="","",INDEX(wr_OurAvail,{k})&" · "&INDEX(wr_OurLineup,{k}))').font = f11
        _span(ws, r, 7, 10, f'=INDEX(wr_OppLabels,{k})', font=f11, wrap=False)
        ws.cell(row=r, column=11, value=f'=IF(INDEX(wr_OppLabels,{k})="","","SL "&INDEX(wr_OppSL,{k})&" · "&INDEX(wr_OppWL,{k}))').font = f11
        ws.cell(row=r, column=12, value=f'=INDEX(wr_OppPlayed,{k})').font = f11
        for c in range(1, 13):
            if c != 6:
                ws.cell(row=r, column=c).border = base.CELL_BORDER
        h(r, 16)
    r = roster_first + R
    _span(ws, r, 1, 12, '=IF(AND(ll_OurTeamOK,ll_OppTeamOK,NOT(ll_FixOK)),"⚠ Lineup Lab marks are for another fixture — not '
                        'applied here. ","")&"Team W-L = this team’s captured record this session · “No data” = not captured · '
                        'availability, lineup and played are your Lineup Lab marks for this fixture, never evidence; Unknown is '
                        'not Unavailable."', font=font(9, color="5B6A61"))
    h(r, 26)
    r += 1
    fresh = stats["freshness"]
    _span(ws, r, 1, 12, f"Built {fresh['build_date']} · offline snapshot (latest recorded result {fresh['latest_result']}) · "
                        f"times {stats['tz']} · rosters = current captured rosters · SL = team-scope, format-specific · "
                        "colors/ranks = recorded evidence only, NOT CALIBRATED odds. "
                        "Workbook marks and phone marks are separate. Reprint after changing Lineup Lab marks.", font=font(9, color="5B6A61"))
    h(r, 36)
    pages = [(1, r)]

    # ---------------- page 2: scouting cards, two across ----------------
    p2 = r + 1
    ws.row_breaks.append(Break(id=p2 - 1))
    base._section(ws, p2, "Scouting cards — full-roster history (ignores marks) — the full cards are on the Scouting Cards sheet", last_col=12)
    h(p2, 18)
    r = p2
    # Reserve the compact preview even when notes are entered after export.
    # Use the narrower side and preserve the complete precomputed missing-data warning.
    missing_col = SCOUTING_COLUMNS.index("Missing") + 1
    missing_texts = [str(row[0] or "") for row in wb["Scouting"].iter_rows(
        min_row=2, min_col=missing_col, max_col=missing_col, values_only=True)]
    note_worst = "W " * ((160 + len(COACH_NOTE_PREVIEW_SUFFIX) + 1) // 2)
    note_height = max((_worst_height(text + " \u00b7 Notes: " + note_worst,
                                    min(sum(PACKET_WIDTHS[1:5]), sum(PACKET_WIDTHS[8:12])), 9.5, 24)
                       for text in missing_texts), default=24)
    card_fields = [("Vs our roster", "Vs Our Roster", 24), ("Met", "Met List", 36), ("By opponent SL", "By SL", 24),
                   ("Missing · notes", None, note_height)]
    sides = ((1, 1, 2, 5), (7, 8, 9, 12))            # (header from, label from, value from, to)
    header_rows = []
    bands = (R + 1) // 2
    # Each band is two self-labelled cards, so a band boundary is a clean page break and needs no
    # repeated header. Splitting here stops this section binding the whole sheet's print scale
    # (it allowed 0.667 as one page; Paul authorised extra pages for readable text).
    card_splits = {bands * k // CARD_PAGES for k in range(1, CARD_PAGES)}
    for band in range(bands):
        if band in card_splits:
            ws.row_breaks.append(Break(id=r))
        r += 1
        header_rows.append(r)
        h(r, 18)
        for side, (c0, cl, cv, c9) in enumerate(sides):
            k = band * 2 + side + 1
            if k > R:
                continue
            lbl = f"INDEX(wr_OppLabels,{k})"
            _span(ws, r, c0, c9, f'=IF({lbl}="","",{lbl}&" · SL "&INDEX(wr_OppSL,{k})&IF(INDEX(wr_OppPlayed,{k})="Played",'
                                 f'" · already played",""))', font=font(10.5, bold=True, color="3B2410"), wrap=False)
        for i, (label, col, pt) in enumerate(card_fields, start=1):
            rr = r + i
            h(rr, pt)
            for side, (c0, cl, cv, c9) in enumerate(sides):
                k = band * 2 + side + 1
                if k > R:
                    continue
                lbl, card = f"INDEX(wr_OppLabels,{k})", f"INDEX(wr_OppCard,{k})"
                _span(ws, rr, cl, cv - 1, f'=IF({lbl}="","","{label}")', font=font(9, bold=True, color="5B6A61"))
                value = (f'INDEX(Scouting_Table[{col}],{card})' if col else
                         f'INDEX(Scouting_Table[Missing],{card})&IF(INDEX(wr_OppNotes,{k})="",""," · Notes: "&{_coach_note_preview(k, 160)})')
                _span(ws, rr, cv, c9, f'=IF(OR({lbl}="",{card}=""),IF({lbl}="","","Not precomputed for this pairing"),{value})',
                      font=font(9.5))
        r += len(card_fields)
    for hr in header_rows:
        for c0, c9 in ((1, 5), (7, 12)):
            first, last = get_column_letter(c0), get_column_letter(c9)
            ws.conditional_formatting.add(f"{first}{hr}:{last}{hr}",
                                          FormulaRule(formula=[f'${first}${hr}<>""'], fill=_cf_fill(CARD_HEAD_FILL_RGB)))
    pages.append((p2, r))

    # ---------------- pages 3-4: evidence, packed, opponent named on every line ----------------
    p3 = r + 1
    ws.row_breaks.append(Break(id=p3 - 1))
    base._section(ws, p3, "Evidence by opponent — every line names the opponent", last_col=12)
    h(p3, 18)
    _span(ws, p3 + 1, 1, 12, "Direct evidence first; favorable/even by win percentage then meetings; loss cautions by net losses then meetings · “≈” = shared-opponent evidence "
                             "only, NOT ordered among themselves · “—” = no verified evidence · “2=” = tied (every row with the same "
                             "“n=” under one opponent is tied). Evidence: W-L (meetings) = direct record; ≈ ours vs theirs "
                             "(n shared) = records against shared opponents. Basis = the evidence category.",
          font=font(9, color="5B6A61"))
    h(p3 + 1, 26)
    EVIDENCE_HEADINGS = ((1, "Opponent"), (3, "Rank"), (4, "Our player"),
                         (8, "Evidence"), (11, "Basis"))

    def _evidence_header(row: int) -> None:
        for col, text in EVIDENCE_HEADINGS:
            ws.cell(row=row, column=col, value=text).font = font(9, bold=True, color=base.FELT_DEEP)
        for c in range(1, 13):
            ws.cell(row=row, column=c).fill = base.SUBHEAD_FILL
        h(row, 16)

    hdr = p3 + 2
    _evidence_header(hdr)
    ev_first = hdr + 1
    # This section is deliberately spread over two printed pages (the scale budget below halves
    # it). Left to an automatic break the continued page carried no column headers at all, so the
    # reader had to flip back to tell Rank from Basis -- print_title_rows can only repeat TOP rows,
    # never this mid-sheet one. Split it explicitly at the halfway row and repeat the header there.
    # Excel applies ONE scale to the whole sheet, so this section was setting the print size of
    # every other page: measured on the bound candidate it allowed 0.294 alone and 0.588 over two
    # pages, against 0.717 for the front page, 0.667 for the cards, 0.782 for the history and 0.805
    # for the sheet width. That is where 58% came from -- 10.5pt body text printing at 6.2pt, below
    # newspaper fine print. A third page costs one sheet of paper and lifts the whole packet to the
    # next binding constraint (0.667, ~7.0pt). The ceiling is the WIDTH at 0.805, so more pages than
    # this buy progressively less; raise it only together with the sections that then bind.
    splits = {R * R * k // EVIDENCE_PAGES for k in range(1, EVIDENCE_PAGES)}
    r = ev_first - 1
    for n in range(1, R * R + 1):
        r += 1
        if n - 1 in splits:
            ws.row_breaks.append(Break(id=r - 1))
            _evidence_header(r)
            r += 1
        ws.cell(row=r, column=16, value=f'=IF({n}>wr_PkTotal,"",MATCH({n},wr_PkStart,1))').font = base.HELPER_FONT
        ws.cell(row=r, column=17, value=f'=IF(P{r}="","",{n}-INDEX(wr_PkStart,P{r})+1)').font = base.HELPER_FONT
        ws.cell(row=r, column=18, value=f'=IF(P{r}="","",INDEX(wr_OppStart,P{r})+Q{r})').font = base.HELPER_FONT
        f10 = font(10.5)
        _span(ws, r, 1, 2, f'=IF(P{r}="","","vs "&INDEX(wr_OppLabels,P{r}))', font=f10, wrap=False, shrink=True)
        ws.cell(row=r, column=3, value=f'=IF(P{r}="","",INDEX(MatchupEvidence_Table[Rank],R{r}))').font = f10
        _span(ws, r, 4, 7, f'=IF(P{r}="","",INDEX(MatchupEvidence_Table[Player],R{r}))', font=f10, wrap=False, shrink=True)
        games = f'INDEX(MatchupEvidence_Table[Direct Games],R{r})'
        _span(ws, r, 8, 10, f'=IF(P{r}="","",IF({games}>0,INDEX(MatchupEvidence_Table[Direct Record],R{r}),INDEX(MatchupEvidence_Table[Cell],R{r})))', font=f10, wrap=False, shrink=True)
        cat = f'INDEX(MatchupEvidence_Table[Category],R{r})'
        _span(ws, r, 11, 12, f'=IF(P{r}="","",IF(AND({games}>0,{games}<3),"SMALL SAMPLE",IF({cat}="G","Favorable direct",IF({cat}="R","Concerning direct",'
                             f'IF({cat}="E","Even direct",IF({cat}="I","Indirect only","No verified evidence"))))))', font=f10, wrap=False)
        h(r, 14.5)
    last_ev = r
    ws.conditional_formatting.add(f"A{ev_first}:L{last_ev}",
                                  FormulaRule(formula=[f'AND($P{ev_first}<>"",$Q{ev_first}=1)'], fill=_cf_fill(base.FELT_SOFT),
                                              font=Font(bold=True)))
    pages.append((p3, last_ev))

    # ---------------- page 5: meeting history ----------------
    # Paul (#84 UAT): every recorded meeting readable on page 5, larger text, clear row dividers. Excel without
    # macros cannot size rows to how many meetings a fixture has, so the page holds a fixed 40 slots as 20 rows x
    # 2 meetings (numbered newest first, filled row by row so short histories stay together at the top). Each
    # meeting is one row of two lines -- "n. date / result · SL" and "our player / vs opponent" (names + IDs).
    # A count line says how many meetings exist; any beyond 40 are on the Meetings sheet, never silently dropped.
    p5 = last_ev + 1
    ws.row_breaks.append(Break(id=p5 - 1))
    base._section(ws, p5, "Meeting history — direct meetings between the rosters (newest first)", last_col=12)
    h(p5, 18)
    total = 'IF(wr_PairKey="",0,COUNTIF(Meetings_Table[Pair Key],wr_PairKey))'
    _span(ws, p5 + 1, 1, 12, f'=IF({total}=0,"No recorded direct meetings between these rosters in this format.",'
                             f'"Showing "&MIN({total},{MEETING_SLOTS})&" of "&{total}&" recorded meeting(s)"&IF({total}>{MEETING_SLOTS},'
                             f'" — the older "&({total}-{MEETING_SLOTS})&" are listed on the Meetings sheet.","."))&" · ? = SL not captured"',
          font=font(10.5, bold=True, color=base.FELT_DEEP), wrap=False)
    h(p5 + 1, 16)
    hdr = p5 + 2
    blocks = ((1, 1, 2, 5), (7, 8, 9, 12))     # (first col, date/result to, names from, names to)
    for c0, cd, cn, c9 in blocks:
        _span(ws, hdr, c0, cd, "No. Date / Result · SL ours/theirs", font=font(9, bold=True, color=base.FELT_DEEP))
        _span(ws, hdr, cn, c9, "Our player / vs Opponent", font=font(9, bold=True, color=base.FELT_DEEP))
    for c in range(1, 13):
        ws.cell(row=hdr, column=c).fill = base.SUBHEAD_FILL
    h(hdr, 16)
    rows_per_side = MEETING_SLOTS // 2
    meet_first = hdr + 1
    for i in range(rows_per_side):
        r = meet_first + i
        for side, (c0, cd, cn, c9) in enumerate(blocks):
            k = i * 2 + side + 1
            row = f'IFERROR(MATCH(wr_PairKey&"|{k}",Meetings_Table[Key],0),"")'
            cond = f'OR(NOT(wr_HasEvidence),{row}="")'
            f12 = font(10.5)
            _span(ws, r, c0, cd, f'=IF({cond},"","{k}. "&INDEX(Meetings_Table[Date],{row})&CHAR(10)&INDEX(Meetings_Table[Result],{row})&'
                                 f'" · SL "&{_meeting_sl_display(row, "Our SL")}&"/"&{_meeting_sl_display(row, "Their SL")})', font=f12)
            _span(ws, r, cn, c9, f'=IF({cond},"",INDEX(Meetings_Table[Our Player],{row})&CHAR(10)&"vs "&'
                                 f'INDEX(Meetings_Table[Opponent],{row}))', font=f12)
        h(r, 29)
    meet_last = meet_first + rows_per_side - 1
    # Dividers and subtle alternating shading on rows that hold a meeting; black rules print in black & white.
    from openpyxl.styles import Border, Side
    rule = Border(top=Side(style="thin", color="000000"), bottom=Side(style="thin", color="000000"))
    for c0, c9 in ((1, 5), (7, 12)):
        a, b = get_column_letter(c0), get_column_letter(c9)
        rng = f"{a}{meet_first}:{b}{meet_last}"
        ws.conditional_formatting.add(rng, FormulaRule(formula=[f'AND(${a}{meet_first}<>"",MOD(ROW(),2)=0)'], border=rule,
                                                       fill=_cf_fill("F2F2F2"), stopIfTrue=True))
        ws.conditional_formatting.add(rng, FormulaRule(formula=[f'${a}{meet_first}<>""'], border=rule))
    last = meet_last + 1
    _span(ws, last, 1, 12, '="Shared-opponent totals per pairing are in the evidence pages; the per-opponent breakdown is in the '
                           'HTML cockpit. This page always holds 40 slots (Excel cannot resize rows to a fixture without macros)."',
          font=font(9, color="5B6A61"))
    h(last, 24)
    pages.append((p5, last))

    # ---------------- one print scale for the whole sheet ----------------
    width_pt = sum(_width_pt(w) for w in PACKET_WIDTHS)
    title_pt = sum(PACKET_TITLE_ROWS)
    page_heights = []
    for i, (a, b) in enumerate(pages):
        body = sum(heights.get(x, 15) for x in range(a, b + 1))
        page_heights.append(body if i == 0 else body + title_pt)
    # Evidence (pages 3-4) is one section spread over two printed pages.
    section_pages = (1, CARD_PAGES, EVIDENCE_PAGES, 1)
    budget = [ph / section_pages[i] for i, ph in enumerate(page_heights)]
    # Do not shrink every packet page because fuller risk explanations need room.
    # Split the overview before rosters only when it exceeds the width-fit budget.
    width_scale = min(1.0, PACKET_PRINTABLE[0] / width_pt)
    if page_heights[0] * width_scale > PACKET_PRINTABLE[1]:
        # Break only between whole rows; one opponent's warning stays with its preview.
        used = 0
        overview_pages = []
        for rr in range(1,pages[0][1]+1):
            height = heights.get(rr,15)
            if used + height > PACKET_PRINTABLE[1] / width_scale and rr>3:
                ws.row_breaks.append(Break(id=rr-1))
                overview_pages.append(used)
                used = title_pt
            used += height
        overview_pages.append(used)
        budget[0] = max(overview_pages)
    ws.row_breaks.brk.sort(key=lambda b: b.id)
    scale = min(1.0, PACKET_PRINTABLE[0] / width_pt, *(PACKET_PRINTABLE[1] / b for b in budget))
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.sheet_properties.pageSetUpPr.fitToPage = False
    ws.page_setup.scale = max(10, int(scale * 100))
    ws.print_area = f"A1:L{last}"
    ws.print_title_rows = "1:2"
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.35
    ws.page_margins.top = ws.page_margins.bottom = 0.45
    ws.page_margins.header = ws.page_margins.footer = 0.2
    _link(ws, 1, 14, "← Match Day", "Match Day")
    _link(ws, 2, 14, "← War Room", "War Room")
    return {"pages": pages, "page_heights": page_heights, "width_pt": width_pt, "scale": ws.page_setup.scale,
            "roster_first": roster_first, "evidence_first": ev_first}


# ---------------------------------------------------------------------------
# Coach Dashboard
# ---------------------------------------------------------------------------

def build_coach_dashboard(wb, *, format_options: list[str]) -> None:
    ws = wb.create_sheet("Coach Dashboard", 5)
    for letter, width in zip("ABCDEFG", (30, 6, 44, 18, 18, 18, 18)):
        ws.column_dimensions[letter].width = width
    _head(ws, "Coach Dashboard — Player vs Player", "Player A defaults to you; Player B comes from tonight's opponent roster "
                                                    "(or “All players…”). Nothing is preselected.", last=7, current="Coach Dashboard")
    _span(ws, 4, 1, 7, "=cd_Status", font=Font(bold=True, color=base.FELT_DEEP))
    inputs = [(5, "Player A (optional override)", "PlayerLabelList", "Blank = you (Match Day's player)."),
              (6, "Player B", "cd_PlayerBList", "Pick an opponent from tonight's roster, or “All players…” and choose below."),
              (7, "Any player (Player B = All players…)", "PlayerLabelList", "Only used when Player B is “All players…”."),
              (8, "Format (optional override)", '"' + ",".join(base._format_label(f) for f in format_options) + '"',
               "Blank = tonight's format.")]
    for r, label, source, help_text in inputs:
        _span(ws, r, 1, 2, label, font=base.LABEL_FONT)
        base._input(ws.cell(row=r, column=3))
        _dv(ws, f"C{r}", source, help_text)
        _span(ws, r, 4, 7, help_text, font=base.MUTED_FONT)
    base._section(ws, 10, "Effective comparison (calculated)", last_col=7)
    for r, label, formula in ((11, "Player A", '=IF(cd_ALabel="","—",cd_ALabel)'),
                              (12, "Player B", '=IF(cd_BLabel="","Choose Player B above.",IF(cd_BID="","⚠ “"&cd_BLabel&"” is not a verified player label.",cd_BLabel))'),
                              (13, "Format", "=cd_FmtLabel")):
        _span(ws, r, 1, 2, label, font=base.LABEL_FONT)
        _calc(ws.cell(row=r, column=3), formula, bold=True)
    fmt_code = base._format_code_formula(format_options, "cd_FmtLabel")[1:]
    ws["A15"] = "Pair key"
    ws["C15"] = f'=IF(OR(cd_AID="",cd_BID=""),"",cd_AID&"|"&{fmt_code}&"|"&cd_BID)'
    ws["A16"] = "Pair row in Player vs Player"
    for helper_row in (15, 16):          # internal lookup keys: kept for the formulas, hidden from the captain
        ws.row_dimensions[helper_row].hidden = True
    ws["C16"] = '=IF(C15="","",IFERROR(MATCH(C15,PlayerVsPlayer_Table[Pair Key],0),""))'
    for ref in ("A15", "C15", "A16", "C16"):
        ws[ref].font = base.HELPER_FONT
    base._section(ws, 18, "Direct record (Player A's perspective)", last_col=7)
    for r, label, formula in (
        (19, "Record", '=IF(OR(cd_AID="",cd_BID=""),"—",IF(C16="","No recorded direct meeting in this format",'
                       'INDEX(PlayerVsPlayer_Table[Wins],C16)&"-"&INDEX(PlayerVsPlayer_Table[Losses],C16)))'),
        (20, "Recorded meetings", '=IF(OR(cd_AID="",cd_BID=""),"—",IF(C16="","0 — absence of evidence, not a 0-0 tie",'
                                  'INDEX(PlayerVsPlayer_Table[Games],C16)))'),
        (21, "Captured SL tonight", '=IF(cd_ALabel="","A: —",IFERROR("A: "&INDEX(wr_OurSL,MATCH(cd_ALabel,wr_OurLabels,0)),"A: not on tonight’s roster"))&'
                                    '" · "&IF(cd_BLabel="","B: —",IFERROR("B: "&INDEX(wr_OppSL,MATCH(cd_BLabel,wr_OppLabels,0)),"B: not on tonight’s opponent roster"))'),
    ):
        _span(ws, r, 1, 2, label, font=base.LABEL_FONT)
        _calc(ws.cell(row=r, column=3), formula)
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=7)
    _span(ws, 23, 1, 7, "Records only — no win percentage or odds are shown (none is calibrated). For shared-opponent evidence "
                        "between tonight's rosters, use the War Room's Inspect views.", font=base.MUTED_FONT, height=30)
    ws.freeze_panes = "A5"


# ---------------------------------------------------------------------------
# START HERE + Captain Command Center (Paul, "Make this a captain's weapon")
# ---------------------------------------------------------------------------

def _fit_height(text: Any, width_units: float, size: float, minimum: float) -> float:
    """Row height (points) that shows all of a wrapped literal text; formulas keep the given minimum."""
    if not isinstance(text, str) or text.startswith("="):
        return minimum
    per_line = max(10, int(width_units * 11 / size * 1.05))
    lines = max(1, -(-len(text) // per_line))
    return max(minimum, round(lines * size * 1.35 + 4, 1))


def _worst_height(text: str, width_units: float, size: float, minimum: float) -> float:
    """Row height (points) for the longest text a FORMULA cell can show. Excel never auto-fits formula rows,
    so this word-wraps the worst case (real-Excel UAT 2a67d78: clipped Next Send list and matrix cells)."""
    per_line = max(6, int(width_units * 10 / size))   # measured in real Excel: ~10 chars per 9 units at 9 pt
    lines = 0
    for paragraph in text.split("\n"):
        lines, used = lines + 1, 0
        for word in paragraph.split(" "):
            while len(word) > per_line:
                lines, used, word = lines + (used > 0), 0, word[per_line:]
            if used and used + 1 + len(word) > per_line:
                lines, used = lines + 1, len(word)
            else:
                used += (1 if used else 0) + len(word)
    return max(minimum, round(lines * size * 1.4 + 6, 1))


def _packet_save_worst(wb, width: float) -> str:
    """Size existing warnings from captured records, including any later availability marks.

    Each future opponent can have at most one sole favorable option. Reserve its
    longest possible owner, rather than an eight-by-eight band of impossible warnings.
    This only sizes printed rows; formulas still decide which warnings apply.
    """
    pairs: dict[str, list[dict[str, Any]]] = {}
    block = None
    for row in wb['Matchup Evidence'].iter_rows(min_row=2, values_only=True):
        rec = dict(zip(ME_COLUMNS, row))
        if rec['Rank']=='vs':
            block={'label':rec['Player'],'rows':[]}
            pairs.setdefault(rec['Key'].rsplit('|',1)[0],[]).append(block)
        elif block is not None and rec['Player ID'] is not None:
            block['rows'].append(rec)
    possibilities = ['']
    for blocks in pairs.values():
        for target in blocks:
            candidates={r['Player ID'] for r in target['rows'] if r['Category'] in ('G','E','I')}
            lines=[]
            for future in blocks:
                if future is target:continue
                owners=[r['Player']+' — consider saving for '+future['label']+' ('+r['Save Record']+')'
                        for r in future['rows'] if r['Category']=='G' and r['Player ID'] in candidates]
                if owners:lines.append(max(owners,key=len))
            possibilities.append('\n'.join(lines))
    return max(possibilities,key=lambda text:_worst_height(text,width,10,0))


def _packet_caution_worst(wb) -> str:
    """Printed cautions can shrink with marks, but cannot exceed the captured loss rows."""
    blocks=[[]]
    for row in wb['Matchup Evidence'].iter_rows(min_row=2,values_only=True):
        rec=dict(zip(ME_COLUMNS,row))
        if rec['Rank']=='vs':blocks.append([])
        elif rec['Category']=='R':
            blocks[-1].append(rec['Player']+' — '+rec['Direct Record']+
                (' · SMALL SAMPLE' if rec['Direct Games']<3 else '')+
                (' · Lost once · Only 1 meeting' if rec['Direct Games']==1 else ''))
    return 'Loss cautions — recorded losses, not exclusions:\n'+max(('\n'.join(b) for b in blocks),key=len)


def _deeper_records_worst(wb) -> str:
    blocks=[[]]
    for row in wb['Matchup Evidence'].iter_rows(min_row=2,values_only=True):
        rec=dict(zip(ME_COLUMNS,row))
        if rec['Rank']=='vs':blocks.append([])
        elif rec['Direct Games'] and rec['Direct Games']>1:
            blocks[-1].append(rec['Player']+' — '+rec['Direct Record']+' · recorded loss · SMALL SAMPLE')
    return 'Deeper direct records — more meetings, not a new order:\n'+max(('\n'.join(b) for b in blocks),key=len)


def _next_send_worst(label: str, roster: int, medals: int) -> str:
    """The longest Next Send answer with `medals` medal lines and the remaining players in the lists."""
    headline = "Not an overall player ranking. Direct-record order uses recorded win percentage, then meeting count. A 1-0 record can appear before 8-2; small samples do not reduce position. Shared-only comparisons are not ordered.\nOrdered direct records among remaining players; equal evidence stays tied."
    medal = (f"Direct-record order 1 {label} — 12-0 direct record (12 MEETINGS) — favorable · tied (same evidence) · consider saving — "
             "our only favorable direct option vs another unplayed opponent · Meeting opponent SL 1, 2, 3, 4, 5, 6, 7, 8, 9; roster capture SL 9; some meeting SLs not captured · Latest dated meeting: Wed Sep 30, 2026; some meeting dates not captured · availability unknown")
    rest = max(roster - medals, 0)
    lines = [headline] + [medal] * medals
    if rest:
        lines.append("≈ Not ordered (shared-opponent results only): "
                     + "\n".join([f"{label} (availability unknown)"] * max(rest - 2, 1)))
        lines += [f"⚠ Avoid: {label} — 0-12 (12 meetings)", f"❓ Unknown (no verified evidence, not weak): {label}"]
    return "\n".join(lines)



def _best_send_worst(wb, roster: int) -> str:
    label = _longest_label(wb)
    prefix = f"vs {label}: first by recorded direct results (tied with {max(1, roster - 1)} others, same evidence): {label} \u2014 reason: "
    column = ME_COLUMNS.index("Reason") + 1
    texts = (str(row[0] or "") for row in wb["Matchup Evidence"].iter_rows(
        min_row=2, min_col=column, max_col=column, values_only=True))
    return prefix + max(texts, key=len, default="no evidence-backed option left among our remaining players")

def _longest_label(wb) -> str:
    """The longest player label in this workbook (Players sheet), or a long generic one when there is none."""
    labels = []
    if "Players" in wb.sheetnames:
        ws = wb["Players"]
        head = [c.value for c in ws[1]]
        if "Player Label" in head:
            col = head.index("Player Label") + 1
            labels = [str(v) for (v,) in ws.iter_rows(min_row=2, min_col=col, max_col=col, values_only=True) if v]
    return max(labels, key=len) if labels else WORST_LABEL


def _longest_plan_key(wb) -> str:
    """The longest fixture plan key this workbook can offer (Schedule sheet), or a long generic one.

    uc_PlanKey concatenates these five schedule columns, so the warning that quotes it is
    only as wide as the widest fixture actually present.
    """
    parts = ("Date Display", "Kickoff", "Home/Away", "Opponent", "Match ID")
    keys = []
    if "Schedule" in wb.sheetnames:
        ws = wb["Schedule"]
        head = [c.value for c in ws[1]]
        if all(name in head for name in parts):
            idx = [head.index(name) for name in parts]
            for row in ws.iter_rows(min_row=2, values_only=True):
                got = [row[i] for i in idx]
                if all(v not in (None, "") for v in got):
                    keys.append(f"{got[0]} · {got[1]} · {got[2]} vs {got[3]} · match {got[4]}")
    return max(keys, key=len) if keys else WORST_PLAN_KEY


def _longest_team_label(wb) -> str:
    """The longest team label these warnings can actually show, or a long generic one.

    They quote wr_OurLabel / wr_OppLabel, which follow Match Day's fixture, so the realistic
    domain is the schedule rather than every team in the workbook. That matters: the Teams
    sheet on the real candidate holds a 327-character label, and sizing three rows for it made
    them 144pt -- nearly two inches of empty space on screen for a case the fixture warnings
    cannot reach. The schedule's longest is 24 characters.
    """
    labels = []
    if "Schedule" in wb.sheetnames:
        ws = wb["Schedule"]
        head = [c.value for c in ws[1]]
        cols = [head.index(n) for n in ("Team", "Opponent") if n in head]
        if cols:
            for row in ws.iter_rows(min_row=2, values_only=True):
                labels += [str(row[i]) for i in cols if i < len(row) and row[i]]
    return max(labels, key=len) if labels else WORST_TEAM_LABEL


# A long but realistic player label, and the longest matrix evidence text, for sizing formula rows.
WORST_LABEL = "Christopher Fitzgerald (APA record ID 3487149)"
WORST_PLAN_KEY = "Sun Oct 11, 2026 · 11:00 AM MDT · Away vs A Long Opponent Team Name · match 51419777"
WORST_TEAM_LABEL = "A Long Opponent Team Name · Fall 2026 · 8-Ball Open"
WORST_EVIDENCE = "≈ 41-53 vs 81-58 (61 shared)"
WORST_BASIS = ("Shared-opponent results only (no verified direct meetings in this snapshot) — not ordered against other indirect candidates; "
               "compare ours vs theirs")


def _card(ws, top: int, c1: int, c2: int, title: str, lines: list[Any], *, size: float = 11, title_fill=None,
          line_height: float = 18) -> int:
    """A titled card: a coloured title bar and plain lines underneath, framed by a light border. A line given as
    (value, worst_case_text) is sized for that text, since a formula line's height can't be fitted from itself."""
    from openpyxl.styles import Border, Side
    edge = Side(style="thin", color="CFC6B4")
    _span(ws, top, c1, c2, title, font=Font(bold=True, size=12, color="FFFFFF"), fill=title_fill or base.SECTION_FILL,
          wrap=False, height=22)
    r = top
    width = sum(ws.column_dimensions[get_column_letter(c)].width or 8.43 for c in range(c1, c2 + 1))
    for line in lines:
        r += 1
        line, worst = line if isinstance(line, tuple) else (line, None)
        floor = _worst_height(worst, width, size, line_height) if worst else line_height
        _span(ws, r, c1, c2, line, font=Font(size=size),
              height=max(_fit_height(line, width, size, floor), ws.row_dimensions[r].height or 0))
    for rr in range(top, r + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(row=rr, column=c)
            cell.border = Border(left=edge if c == c1 else None, right=edge if c == c2 else None,
                                 top=edge if rr == top else None, bottom=edge if rr == r else None)
    return r


TAB_TOUR = [
    ("START HERE", "This page: what Ultimate Coach does and how to use it in three minutes."),
    ("Command Center", "Tonight at a glance: opponent, date, venue, availability counts, the opponent roster and the evidence summary."),
    ("Match Day", "THE control panel. Pick player → team → format → date → fixture once; every other tab follows it."),
    ("War Room", "The match-night overview: both rosters, best sends per opponent, dangerous opponents, avoid sends, open risks, the colour matrix, and Inspect (shared-opponent evidence for one opponent or one of our players). Its own optional overrides only change this tab."),
    ("Lineup Lab", "Mark our players Available / Unavailable / Unknown and Planned / Played, and which opponents already played. Marks belong to one fixture."),
    ("Scouting Cards", "One card per opponent: records, meetings with our players, record by skill level, missing information and your observations."),
    ("Coach Notes", "Your own observations per player (tags such as 'Slow shooter' plus free text). Opinions, not APA facts — kept apart from evidence."),
    ("Captain Packet", "The printable match-night packet: page 1 summary, then scouting cards, evidence and meeting history."),
    ("Coach Dashboard", "One player vs one player: their direct record and number of meetings, plus tonight's captured skill levels. Defaults to you vs tonight's opponents. (Shared-opponent evidence is in War Room → Inspect.)"),
    ("Schedule, Team Rosters, Players …", "The recorded data behind everything above — reference only."),
]


def build_start_here(wb, *, stats: dict[str, Any], version: str, example: list[str] | None = None) -> None:
    ws = wb.create_sheet("START HERE", 0)
    for letter, width in zip("ABCDEFGHIJ", (3, 26, 26, 3, 26, 26, 3, 26, 26, 3)):
        ws.column_dimensions[letter].width = width
    ws.sheet_view.showGridLines = False
    _span(ws, 1, 2, 9, "Ultimate Coach — Captain's War Room", font=Font(bold=True, size=22, color=base.FELT_DEEP), wrap=False,
          height=36)
    _span(ws, 2, 2, 9, "Who should I put up next? Recorded, identity-verified APA evidence — organised for match night.",
          font=Font(italic=True, size=12, color="5B6A61"), height=20)
    fresh = stats["freshness"]
    _span(ws, 3, 2, 9, f"Workbook version {version} · built {fresh['build_date']} · data current to the latest recorded result "
                       f"{fresh['latest_result']} · times in {stats['tz']} · this file never refreshes itself.",
          font=Font(size=10, color="5B6A61"), height=18)
    top = 5
    a = _card(ws, top, 2, 3, "1 · What Ultimate Coach does", list(ONBOARDING_WHAT))
    steps = ["Step 1 · Go to Match Day", "Step 2 · Select Player (you)", "Step 3 · Select Team (and Format)",
             "Step 4 · Select Match Date (and Fixture if two share a day)", "Step 5 · Review the Command Center",
             "Step 6 · Lineup Lab: mark who's here — marks belong to that one fixture", "Step 7 · Review the War Room matchups",
             "Step 8 · Print the Captain Packet"]
    b = _card(ws, top, 5, 6, "2 · Quick start (3 minutes)", steps, title_fill=base.OPPONENT_FILL)
    flow = ["Match Day decides the fixture.", "↓ Command Center · War Room · Lineup Lab", "↓ Scouting Cards · Coach Dashboard",
            "↓ Captain Packet (print)", "Change Match Day and every tab follows.",
            "A tab's own override changes only that tab — clear it to follow Match Day again."]
    c = _card(ws, top, 8, 9, "4 · Match night workflow", flow)
    r = max(a, b, c) + 2
    # A worked example taken from THIS build's own data (the configured viewer's next fixture) -- selections
    # only, never results, and never hard-coded in the source.
    r = _card(ws, r, 2, 9, "Worked example from this build — what Match Day picks for you",
              example or ["No viewer is configured for this build: pick yourself on Match Day and it fills in team, date "
                          "and fixture the same way."], title_fill=base.OPPONENT_FILL) + 2
    _span(ws, r, 2, 9, "3 · Workbook tour", font=Font(bold=True, size=12, color="FFFFFF"), fill=base.SECTION_FILL, wrap=False, height=22)
    for name, text in TAB_TOUR:
        r += 1
        cell = ws.cell(row=r, column=2, value=name)
        cell.font = Font(bold=True, size=11, color=base.FELT_DEEP)
        if name in wb.sheetnames or name in ("Command Center", "Coach Notes"):
            cell.hyperlink = Hyperlink(ref=f"B{r}", location=f"'{name}'!A1", display=name)
            cell.font = Font(bold=True, size=11, color="1F5C99", underline="single")
        cell.alignment = base.WRAP_TOP
        _span(ws, r, 3, 9, text, font=Font(size=11),
              height=max(_fit_height(text, sum(ws.column_dimensions[c].width for c in "CDEFGHI"), 11, 20),
                         _fit_height(name, ws.column_dimensions["B"].width, 11, 20)))
    r += 2
    lim = _card(ws, r, 2, 9, "5 · Important limitations", list(ONBOARDING_LIMITS), title_fill=PatternFill("solid", fgColor="8A5A00"))
    r = _card(ws, lim + 2, 2, 9, "6 · Mobile match night (phone)", list(MATCH_NIGHT_GUIDE)) + 2
    _card(ws, r, 2, 9, "7 · Build information",
          [f"Workbook version: {version}", f"Build date: {fresh['build_date']}",
           f"Data freshness: latest recorded result {fresh['latest_result']}"
           + (f" · {fresh['unplayed_before_build']} earlier fixtures still show UNPLAYED in this snapshot"
              if fresh["unplayed_before_build"] else "")])
    _link(ws, 4, 2, "→ Start: Match Day", "Match Day", font=BIG_LINK)
    _link(ws, 4, 5, "→ Command Center", "Command Center", font=BIG_LINK)
    ws.freeze_panes = "A4"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def build_command_center(wb, *, slots: dict[str, int], stats: dict[str, Any]) -> None:
    """Tonight in 30 seconds. Reads the Match Day pairing (md_* after split_match_day_engine)."""
    R = slots["roster"]
    ws = wb.create_sheet("Command Center", 1)
    for letter, width in zip("ABCDEFGHIJKL", (3, 30, 12, 14, 3, 30, 12, 14, 3, 34, 14, 3)):
        ws.column_dimensions[letter].width = width
    ws.sheet_view.showGridLines = False
    _span(ws, 1, 2, 11, "Captain Command Center — tonight at a glance", font=Font(bold=True, size=20, color=base.FELT_DEEP),
          wrap=False, height=32)
    _span(ws, 2, 2, 11, '=IF(uc_Fixture="","Choose a fixture on Match Day (player → team → format → date → fixture).",uc_Fixture)',
          font=Font(bold=True, size=14, color=base.FELT_DEEP), height=24)
    _span(ws, 3, 2, 11, '=IF(wr_OppLabel="",uc_OppMsg,"Opponent: "&wr_OppLabel&" · "&uc_Venue)', font=Font(size=11, color="5B6A61"),
          height=34)
    fresh = stats["freshness"]
    stale = stale_warning(fresh)
    # A stale snapshot is a warning here, not small print: it is why a captain's own recent results can be missing.
    line = ((stale + " " if stale else "")
            + f"Data freshness: built {fresh['build_date']} · latest recorded result {fresh['latest_result']} · "
              "the file never refreshes itself.")
    _span(ws, 4, 2, 11, '=uc_TeamStaleText&"' + line.replace('"', '""') + '"',
          font=Font(size=10, bold=True, color="8A5A00") if stale else Font(size=10, color="5B6A61"),
          height=44 if stale else 16)
    _link(ws, 5, 2, "→ Match Day (change matchup)", "Match Day")
    _link(ws, 5, 6, "→ Lineup Lab (mark availability)", "Lineup Lab")
    _link(ws, 5, 10, "→ Captain Packet (print)", "Captain Packet")
    # Decision first: who do I send against the player they just put up? (Engine "Next Send", mirrors next_send.)
    _span(ws, 6, 2, 2, "They put up:", font=Font(bold=True, size=12, color=base.FELT_DEEP))
    base._input(ws.cell(row=6, column=3))
    ws.merge_cells(start_row=6, start_column=3, end_row=6, end_column=8)
    _dv(ws, "C6", "wr_OppLabels", "Pick the opponent player they just put up.")
    _span(ws, 6, 10, 11, '=IF(wr_OppLabel="","","Mark sends Played on Lineup Lab — they drop out here.")',
          font=Font(size=10, color="5B6A61"), height=22)
    # Excel does not auto-fit merged inputs. Keep the selected opponent readable
    # at its existing font size, reserving space for any player label in the file.
    ws["C6"].alignment = Alignment(wrap_text=True, vertical="center")
    input_width = sum(ws.column_dimensions[get_column_letter(c)].width for c in range(3, 9))
    ws.row_dimensions[6].height = _worst_height(_longest_label(wb), input_width, 12, 22)
    # The whole answer is ONE wrapped cell (wr_NsCard: headline, every ranked line, then the lists), so it reads top
    # to bottom with no empty medal rows in between. Each remaining player appears at most once in it, so size the
    # cell for the worst mix -- k medal lines plus the other R-k names in the lists -- with this workbook's
    # longest label, or Excel hides the last names.
    worst = max((_next_send_worst(_longest_label(wb), R, k) for k in range(0, R + 1)),
                key=lambda t: _worst_height(t, 166, 11, 0))
    ns_lines = [
        ("=wr_NsCard", worst),
        '=IF(wr_NsJ="","",IF(INDEX(wr_OppNotes,wr_NsJ)="","","📝 "&INDEX(wr_OppNotes,wr_NsJ)&" (your opinion, not APA facts)"))',
    ]
    top = _card(ws, 7, 2, 11, "NEXT SEND - RECORDED MATCHUP OPTIONS", ns_lines, size=11, line_height=30) + 2
    top = _card(ws,top,2,11,"DEEPER RECORD CONTEXT — WHEN THE FIRST RECORD HAS 1–2 MEETINGS",
                [("=wr_NsDeeper",_deeper_records_worst(wb))],size=11,line_height=30)+2
    broad_worst = ("Not used in this ordering\nCaptured team/session records — not a lifetime record.\nOur roster: "
                   + _longest_team_label(wb) + "\n" + "\n".join([_longest_label(wb)+": 100-100"] * R)
                   + "\nOpponent roster: " + _longest_team_label(wb) + "\n" + _longest_label(wb)+": 100-100\n"
                   + "Meeting age, changes in skill level and Coach Observations do not adjust this order. Availability filters candidates; skill-budget checks are separate references. No verified direct/shared comparison means unknown, not weak.")
    top = _card(ws, top, 2, 11, "BROADER RECORDS - NOT USED IN THIS ORDERING", [("=wr_NsBroader", broad_worst)], size=11) + 2
    cnt = lambda v: f'COUNTIF(wr_OurAvail,"{v}")'
    _card(ws, top, 2, 4, "MY TEAM", [
        '=IF(wr_OurLabel="","Choose your team on Match Day.",wr_OurLabel)',
        f'=IF(wr_OurCount=0,"","Available: "&{cnt("Available")})',
        f'=IF(wr_OurCount=0,"","Unavailable: "&{cnt("Unavailable")})',
        f'=IF(wr_OurCount=0,"","Unknown: "&{cnt("Unknown")}&" (not the same as unavailable)")',
        '=IF(wr_OurCount=0,"","Already used: "&COUNTIF(wr_OurLineup,"Played")&" · planned: "&COUNTIF(wr_OurLineup,"Planned"))',
        '=IF(wr_OurCount=0,"","Remaining skill total: "&IF(wr_RemainingMissing=0,wr_RemainingSL,wr_RemainingSL&" known ('
        '"&wr_RemainingMissing&" without SL)"))',
    ])
    opp_lines = ['=IF(wr_OppLabel="","No opponent roster for the selected fixture.",wr_OppLabel)']
    for k in range(1, R + 1):
        opp_lines.append(f'=IF(INDEX(wr_OppLabels,{k})="","",INDEX(wr_OppLabels,{k})&" · SL "&INDEX(wr_OppSL,{k})&'
                         f'IF(INDEX(wr_OppPlayed,{k})="Played"," · played",""))')
    opp_end = _card(ws, top, 6, 8, "OPPONENT TEAM", opp_lines, size=10, title_fill=base.OPPONENT_FILL, line_height=16)
    _span(ws, opp_end + 1, 6, 8, '=IF(wr_OppLabel="","","Missing information: "&COUNTIF(wr_OppSL,"No data")&" player(s) without a '
                                 'captured SL · "&wr_UnplayedCount&" not yet played")', font=Font(size=10, color="5B6A61"), height=30)
    cats = lambda code: "+".join(f'COUNTIF(wr_CatCol{j},"{code}")' for j in range(1, R + 1))
    summary = [
        '=IF(wr_PairKey="","Evidence summary appears once Match Day names a fixture with an opponent roster.",'
        '"Pairings between the two rosters, by recorded evidence:")',
        f'=IF(wr_PairKey="","","Favorable direct record (any sample size): "&({cats("G")}))',
        f'=IF(wr_PairKey="","","Concerning (more direct losses than wins): "&({cats("R")}))',
        f'=IF(wr_PairKey="","","Limited evidence: "&({cats("E")})&" even direct · "&({cats("I")})&" shared-opponent only")',
        f'=IF(wr_PairKey="","","Insufficient verified evidence in this snapshot: "&({cats("X")}))',
        '=IF(wr_PairKey="","","Open risks: "&wr_RiskCount&" unplayed opponent(s) with no favorable direct option left")',
    ]
    _card(ws, top, 10, 11, "COACHING SUMMARY", summary, size=10.5, line_height=30)
    r = max(opp_end + 2, top + len(summary) + 2) + 1
    send_lines = []
    for k in range(1, R + 1):
        send_lines.append((f'=IF(OR(INDEX(wr_OppLabels,{k})="",NOT(INDEX(wr_OppUnplayed,{k}))),"","vs "&INDEX(wr_OppLabels,{k})&": "&'
                          f'IF(INDEX(wr_BestText,{k})="","no evidence-backed option left",INDEX(wr_BestText,{k})))', _best_send_worst(wb, R)))
    _card(ws, r, 2, 11, "RECORDED OPTION PER UNPLAYED OPPONENT — and its evidence",
          send_lines, size=10.5, line_height=30)
    ws.freeze_panes = "A7"
    ws.page_setup.orientation = "landscape"
    # Fit the WIDTH only: squeezing the whole sheet onto one page shrank it below readable size (real-Excel print
    # preview, 0c2e474). Extra pages are fine; the Captain Packet is the one-page-per-topic print.
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


COACH_NOTE_ROWS = 200


def build_coach_notes(wb) -> None:
    """Durable coach observations per player -- opinions, kept apart from evidence. The first row naming a
    player feeds that player's scouting cards and packet ("Coach: ..."); APA records are never changed."""
    ws = wb.create_sheet("Coach Notes")
    for letter, width in zip("ABCDEFG", (44, 24, 24, 60, 14, 3, 70)):
        ws.column_dimensions[letter].width = width
    _span(ws, 1, 1, 5, "Coach Notes — your observations (opinions, not APA facts)", font=Font(bold=True, size=18, color=base.FELT_DEEP),
          wrap=False, height=30)
    _span(ws, 2, 1, 5, "One row per player. Pick the player name/label, up to two tags, and write what you saw. "
                       "These notes appear on that player's scouting card and in the Captain Packet, always marked “Coach:”. "
                       "They never change any recorded result.", font=Font(size=10, color="5B6A61"), height=30)
    _link(ws, 1, 7, "← START HERE", "START HERE")
    heads = ["Player", "Tag 1", "Tag 2", "Observation", "Date noted"]
    for c, text in enumerate(heads, start=1):
        cell = ws.cell(row=4, column=c, value=text)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = base.SECTION_FILL
    ws.cell(row=4, column=7, value="Summary used on cards (calculated)").font = base.HELPER_FONT
    first, last = 5, 4 + COACH_NOTE_ROWS
    player = DataValidation(type="list", formula1="PlayerLabelList", allow_blank=True)
    tags = DataValidation(type="list", formula1='"' + ",".join(COACH_TAGS) + '"', allow_blank=True)
    ws.add_data_validation(player)
    ws.add_data_validation(tags)
    for r in range(first, last + 1):
        for c in range(1, 6):
            base._input(ws.cell(row=r, column=c))
        player.add(f"A{r}")
        tags.add(f"B{r}")
        tags.add(f"C{r}")
        ws.cell(row=r, column=4).alignment = base.WRAP_TOP
        ws.cell(row=r, column=7, value=f'=IF(A{r}="","",TRIM(B{r}&IF(AND(B{r}<>"",C{r}<>"")," · ","")&C{r}&'
                                       f'IF(AND(OR(B{r}<>"",C{r}<>""),D{r}<>""),": ","")&D{r}))').font = base.HELPER_FONT
    wb.defined_names["cn_Player"] = DefinedName("cn_Player", attr_text=f"'Coach Notes'!$A${first}:$A${last}")
    wb.defined_names["cn_Summary"] = DefinedName("cn_Summary", attr_text=f"'Coach Notes'!$G${first}:$G${last}")
    ws.freeze_panes = "A5"
