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

import re
import sys
from datetime import date

import pytest
from openpyxl import load_workbook

from analytics.ultimate_coach_match_day import build_match_day_section
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
                    {"team_external_id": "sharks-a", "team_name": "Sharks", "division_id": "d1", "session_name": "Spring 2026", "format": "EIGHT", "is_current": True, "skill_level": 4, "matches_won": 10, "matches_played": 15},
                ],
            },
            {
                "id": 2, "external_id": "1002", "name": "Bea Baker",
                "current_skill_level": None, "current_matches_won": None, "current_matches_played": None,
                "team_history": [
                    # Same team name, two genuinely different division/format
                    # scopes (real data has exactly this shape -- a same-named
                    # team split across an 8-Ball and a 9-Ball division) --
                    # must dedupe on the Team Rosters sheet, never merge.
                    {"team_external_id": "sharks-a", "team_name": "Sharks", "division_id": "d1", "session_name": "Spring 2026", "format": "EIGHT", "is_current": True, "skill_level": 5, "matches_won": 2, "matches_played": 6},
                    {"team_external_id": "sharks-b", "team_name": "Sharks", "division_id": "db", "session_name": "Spring 2026", "format": "NINE", "is_current": True, "skill_level": 5, "matches_won": 3, "matches_played": 6},
                ],
            },
            {
                "id": 3, "external_id": "1003", "name": "Cam Cole",
                "current_skill_level": 3, "current_matches_won": 3, "current_matches_played": 5,
                "team_history": [
                    {"team_external_id": "falcons-a", "team_name": "Falcons", "division_id": "d2", "session_name": "Spring 2026", "format": "EIGHT", "is_current": True, "skill_level": 3, "matches_won": 3, "matches_played": 5},
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
            # A real, distinct APA format outside 8-Ball/9-Ball (see
            # scraper.graphql_scraper._VALID_FORMATS) -- these two players
            # have NO 8-Ball/9-Ball history together, only this one. Must
            # stay reachable from the Coach Dashboard's Format dropdown
            # rather than silently reading as "no recorded direct meeting".
            {"player_id": 2, "opponent_id": 3, "format": "MASTERS", "result": "W"},
        ],
    }


def test_workbook_has_expected_sheets_and_no_fabricated_probability(tmp_path):
    path = write_workbook(_payload(), tmp_path / "uc.xlsx", built_at="test", source_db="test.db")
    wb = load_workbook(path)

    assert set(wb.sheetnames) == {
        "Build Info", "Data Trust", "Players", "Team Rosters", "Teams",
        "Player vs Player", "Coach Dashboard", "Match Night",
        "Match Day", "Print Matchup", "Player Teams", "Schedule", "Schedule Keys", "Lists",
        "Team Comparison", "Matchup Evidence",
    }
    assert wb.sheetnames[:4] == ["Match Day", "Print Matchup", "Match Night", "Coach Dashboard"]

    build_info = {row[0].value: row[1].value for row in wb["Build Info"].iter_rows(min_row=2, max_col=2) if row[0].value}
    assert build_info["Probability publication"] == "FORBIDDEN"
    assert build_info["Matchup probability"] is None
    assert build_info["Predictive confidence"] is None


def test_players_sheet_disambiguates_duplicate_names(tmp_path):
    path = write_workbook(_payload(), tmp_path / "uc.xlsx", built_at="test", source_db="test.db")
    wb = load_workbook(path)

    labels = [row[0].value for row in wb["Players"].iter_rows(min_row=2, max_col=1)]
    assert "Ann Archer (APA record ID 1001)" in labels
    assert "Ann Archer (APA record ID 1004)" in labels
    assert len(labels) == len(set(labels))


def test_team_rosters_sheet_keeps_same_named_scopes_separate(tmp_path):
    path = write_workbook(_payload(), tmp_path / "uc.xlsx", built_at="test", source_db="test.db")
    wb = load_workbook(path)

    rows = list(wb["Team Rosters"].iter_rows(min_row=2, values_only=True))
    # Team, session, and recorded format -- division only gets appended when
    # two scopes would otherwise produce an identical label. These two
    # scopes already differ by format (8-Ball vs 9-Ball), so neither needs
    # the "· Div" suffix.
    scope_a = "Sharks · Spring 2026 · 8-Ball"
    scope_b = "Sharks · Spring 2026 · 9-Ball"
    assert len([r for r in rows if r[0] == scope_a]) == 2  # Ann + Bea
    assert len([r for r in rows if r[0] == scope_b]) == 1  # Bea in another exact scope

    teams_rows = {r[0]: r for r in wb["Teams"].iter_rows(min_row=2, values_only=True)}
    assert teams_rows[scope_a][3] == 2
    assert teams_rows[scope_a][5] == 9
    assert teams_rows[scope_b][3] == 1
    assert teams_rows[scope_b][5] == 5


def test_player_vs_player_sheet_has_pair_key_for_lookup(tmp_path):
    path = write_workbook(_payload(), tmp_path / "uc.xlsx", built_at="test", source_db="test.db")
    wb = load_workbook(path)

    rows = list(wb["Player vs Player"].iter_rows(min_row=2, values_only=True))
    keys = {r[7] for r in rows}
    assert "1|EIGHT|3" in keys
    assert "3|EIGHT|1" in keys


def test_coach_dashboard_format_dropdown_includes_non_eight_nine_formats(tmp_path):
    path = write_workbook(_payload(), tmp_path / "uc.xlsx", built_at="test", source_db="test.db")
    wb = load_workbook(path)
    dash = wb["Coach Dashboard"]

    validations = [dv for dv in dash.data_validations.dataValidation if "B6" in dv.sqref]
    assert len(validations) == 1
    # "MASTERS" evidence exists in the fixture with no matching 8-Ball/9-Ball
    # history -- if the dropdown only ever offered 8-Ball/9-Ball, that real
    # recorded meeting would be permanently unreachable from this sheet.
    assert validations[0].formula1 == '"8-Ball,9-Ball,Masters"'

    assert dash["B12"].value == (
        '=IF(B6="9-Ball","NINE",IF(B6="Masters","MASTERS","EIGHT"))'
    )

    rows = list(wb["Player vs Player"].iter_rows(min_row=2, values_only=True))
    masters_rows = [r for r in rows if r[7] == "2|MASTERS|3"]
    assert len(masters_rows) == 1
    assert masters_rows[0][1] == "Masters"  # display label, not raw "MASTERS"


def _team_match(**overrides):
    row = {
        "match_id": 500, "match_external_id": "500", "match_date": "2026-10-11T11:00:00-06:00",
        "format": "EIGHT", "format_raw": "8-Ball Open", "session_name": "Spring 2026", "week": 7,
        "status": "UNPLAYED", "location": None, "home_team_id": "sharks-a", "home_team_name": "Sharks",
        "away_team_id": "falcons-a", "away_team_name": "Falcons", "home_score": None,
        "away_score": None, "is_bye": False, "is_scored": False, "is_finalized": False,
    }
    row.update(overrides)
    return row


def _match_day_payload(team_matches=None):
    payload = _payload()
    payload["match_day"] = build_match_day_section(
        team_matches if team_matches is not None else [_team_match()], payload["players"]
    )
    return payload


def _rows_by_header(sheet):
    rows = list(sheet.iter_rows(values_only=True))
    header = rows[0]
    return [dict(zip(header, r)) for r in rows[1:]]


def _sharks_rows(wb):
    return [r for r in _rows_by_header(wb["Schedule"]) if r["Team Scope Key"] == "sharks-a|d1|Spring 2026"]


SHARKS_8 = "Sharks · Spring 2026 · 8-Ball"
FALCONS_8 = "Falcons · Spring 2026 · 8-Ball"


def test_schedule_uses_display_timezone_for_a_utc_midnight_crossing(tmp_path):
    payload = _match_day_payload([_team_match(match_date="2026-08-30T01:00:00Z")])
    wb = load_workbook(write_workbook(payload, tmp_path / "uc.xlsx"))
    row = _sharks_rows(wb)[0]
    assert row["Local Date"].date() == date(2026, 8, 29)
    assert row["Date Display"] == "Sat Aug 29, 2026"
    assert row["Kickoff"] == "7:00 PM MDT"
    assert row["Time Zone"] == "America/Denver (UTC-06:00)"
    assert row["Source Timestamp"] == "2026-08-30T01:00:00Z"
    keys = {r["Slot Key"] for r in _rows_by_header(wb["Schedule Keys"])}
    # Keyed on the Denver date's Excel serial (46263 = 2026-08-29), not the UTC day.
    assert "sharks-a|d1|Spring 2026|46263|89|1" in keys
    assert not any("|46264|" in k for k in keys)


def test_bye_row_says_no_opponent_and_offers_no_roster_lookup(tmp_path):
    payload = _match_day_payload([_team_match(is_bye=True, away_team_id="13082714", away_team_name="BYE")])
    wb = load_workbook(write_workbook(payload, tmp_path / "uc.xlsx"))
    row = _sharks_rows(wb)[0]
    assert row["Opponent"] == "Bye — no opponent"
    assert row["Opponent Roster"] == "Not applicable (bye)"
    assert row["Opponent Team"] == "—"
    assert row["Opponent Scope Key"] == "—"


def test_missing_names_status_and_venue_read_no_data_while_real_zero_scores_survive(tmp_path):
    payload = _match_day_payload([_team_match(
        away_team_name="", status=None, location="  ", is_scored=True, home_score=0, away_score=3,
    )])
    wb = load_workbook(write_workbook(payload, tmp_path / "uc.xlsx"))
    row = _sharks_rows(wb)[0]
    assert row["Opponent"] == "No data"
    assert row["Status"] == "No data"
    assert row["Venue"] == "No data"
    assert row["Score (home–away)"] == "0 – 3"
    assert row["Home Score"] == 0 and row["Away Score"] == 3  # numeric zero kept, not blanked


def test_unscored_fixture_score_reads_not_recorded_never_zero(tmp_path):
    wb = load_workbook(write_workbook(_match_day_payload(), tmp_path / "uc.xlsx"))
    row = _sharks_rows(wb)[0]
    assert row["Score (home–away)"] == "Not recorded"
    assert row["Home Score"] is None and row["Away Score"] is None


def test_every_column_match_day_reads_through_index_is_fully_populated(tmp_path):
    """Excel evaluates a blank cell reached through INDEX as 0 -- the bug
    class behind the old Match Day B19/B26/B31 cells. Every Table column any
    Match Day / Match Night formula INDEXes must therefore contain no blanks."""
    payload = _match_day_payload([
        _team_match(match_id=1, match_external_id="1", away_team_name="", status=None),
        _team_match(match_id=2, match_external_id="2", is_bye=True, away_team_id="x", away_team_name="BYE",
                    match_date="2026-10-11T19:00:00-06:00"),
        _team_match(match_id=3, match_external_id="3", match_date=None),
        _team_match(match_id=4, match_external_id="4", match_date="garbage"),
    ])
    wb = load_workbook(write_workbook(payload, tmp_path / "uc.xlsx", viewer_member_external_id="1001"))
    tables = {}
    for ws in wb.worksheets:
        for name, ref in ws.tables.items():
            tables[name] = (ws, ref)
    referenced = set()
    for sheet_name in ("Match Day", "Match Night", "Print Matchup"):
        for row in wb[sheet_name].iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    referenced.update(re.findall(r"INDEX\((\w+)\[([^\]]+)\]", cell.value))
    assert ("Schedule_Table", "Opponent") in referenced
    assert ("TeamRosters_Table", "SL Display") in referenced
    for table_name, column in referenced:
        ws, ref = tables[table_name]
        values = [r for r in ws[ref]]
        header = [c.value for c in values[0]]
        idx = header.index(column)
        blanks = [c.coordinate for c in (r[idx] for r in values[1:]) if c.value is None or c.value == ""]
        assert blanks == [], f"{table_name}[{column}] has blank cells {blanks}"


def test_schedule_keys_list_every_fixture_in_kickoff_order_and_never_pick_one(tmp_path):
    payload = _match_day_payload([
        _team_match(match_id=1, match_external_id="1", match_date="2026-10-11T19:00:00-06:00"),
        _team_match(match_id=2, match_external_id="2", match_date="2026-10-11T11:00:00-06:00",
                    format="EIGHT", format_raw="8-Ball Doubles"),
        _team_match(match_id=3, match_external_id="3", match_date="2026-10-11T13:00:00-06:00",
                    format="MASTERS", format_raw="Masters"),
    ])
    wb = load_workbook(write_workbook(payload, tmp_path / "uc.xlsx"))
    schedule = _rows_by_header(wb["Schedule"])
    keys = {r["Slot Key"]: r["Schedule Row"] for r in _rows_by_header(wb["Schedule Keys"])}
    serial = 46306  # 2026-10-11
    group = f"sharks-a|d1|Spring 2026|{serial}"
    # Default 8-Ball & 9-Ball: both 8-Ball variants, in kickoff order; Masters excluded.
    assert schedule[keys[f"{group}|89|1"] - 1]["Kickoff"] == "11:00 AM MDT"
    assert schedule[keys[f"{group}|89|2"] - 1]["Kickoff"] == "7:00 PM MDT"
    assert f"{group}|89|3" not in keys
    # All recorded formats: all three. A single raw format: only that one.
    assert [schedule[keys[f"{group}|ALL|{k}"] - 1]["Format"] for k in (1, 2, 3)] == ["8-Ball Doubles", "Masters", "8-Ball Open"]
    assert schedule[keys[f"{group}|F:Masters|1"] - 1]["Format"] == "Masters"
    # Season list for the team uses the same codes.
    assert "sharks-a|d1|Spring 2026|ALL|89|2" in keys
    lists = [c.value for c in wb["Lists"]["A"][1:] if c.value]
    assert lists[:2] == ["8-Ball & 9-Ball", "All recorded formats"]
    assert {"8-Ball Doubles", "8-Ball Open", "Masters"} <= set(lists)


def test_ambiguous_or_missing_opponent_roster_is_disclosed(tmp_path):
    payload = _payload()
    for pid, div in ((10, "dA"), (11, "dB")):
        payload["players"].append({
            "id": pid, "external_id": str(2000 + pid), "name": f"Owl {pid}", "current_skill_level": 4,
            "current_matches_won": 1, "current_matches_played": 2,
            "team_history": [{"team_external_id": "owls", "team_name": "Owls", "division_id": div,
                              "session_name": "Spring 2026", "format": "EIGHT", "is_current": True,
                              "skill_level": 4, "matches_won": 1, "matches_played": 2}],
        })
    payload["match_day"] = build_match_day_section([
        _team_match(match_id=1, match_external_id="1", away_team_id="owls", away_team_name="Owls"),
        _team_match(match_id=2, match_external_id="2", away_team_id="ghosts", away_team_name="Ghosts",
                    match_date="2026-10-11T19:00:00-06:00"),
    ], payload["players"])
    wb = load_workbook(write_workbook(payload, tmp_path / "uc.xlsx"))
    by_opp = {r["Opponent"]: r for r in _sharks_rows(wb)}
    assert by_opp["Owls"]["Opponent Roster"] == "Ambiguous: 2 roster scopes match — compare manually"
    assert by_opp["Owls"]["Opponent Scope Key"] == "—"
    assert by_opp["Ghosts"]["Opponent Roster"] == "No current roster captured"
    assert by_opp["Ghosts"]["Opponent Scope Key"] == "—"


def test_resolved_opponent_roster_scope_matches_a_teams_label(tmp_path):
    wb = load_workbook(write_workbook(_match_day_payload(), tmp_path / "uc.xlsx"))
    row = _sharks_rows(wb)[0]
    assert row["Opponent Team"] == FALCONS_8
    assert row["Opponent Scope Key"] == "falcons-a|d2|Spring 2026"
    teams = {r["Scope Key"]: r for r in _rows_by_header(wb["Teams"])}
    assert teams["falcons-a|d2|Spring 2026"]["Team"] == FALCONS_8


def test_player_teams_lists_each_current_scope_separately_by_record_id(tmp_path):
    wb = load_workbook(write_workbook(_match_day_payload(), tmp_path / "uc.xlsx"))
    rows = _rows_by_header(wb["Player Teams"])
    bea = [r for r in rows if r["APA Record ID"] == "1002"]
    assert [r["Viewer Slot Key"] for r in bea] == ["1002|1", "1002|2"]
    assert {r["Team"] for r in bea} == {SHARKS_8, "Sharks · Spring 2026 · 9-Ball"}
    # The second "Ann Archer" (record 1004) has no team -- never inherits the other Ann's.
    assert not [r for r in rows if r["APA Record ID"] == "1004"]


def test_team_rosters_have_slot_keys_and_display_text_for_missing_values(tmp_path):
    wb = load_workbook(write_workbook(_match_day_payload(), tmp_path / "uc.xlsx"))
    rows = _rows_by_header(wb["Team Rosters"])
    sharks = sorted((r for r in rows if r["Team Scope Key"] == "sharks-a|d1|Spring 2026"), key=lambda r: r["Roster Slot Key"])
    # Highest skill level first: Bea's division SL 5 (no live rating -> "5*"), then Ann's live SL 4.
    assert [(r["Roster Slot Key"], r["Player Name"], r["SL Display"]) for r in sharks] == [
        ("sharks-a|d1|Spring 2026|1", "Bea Baker", "5*"),
        ("sharks-a|d1|Spring 2026|2", "Ann Archer", "4"),
    ]
    assert sharks[1]["W-L Display"] == "10-5"


def test_match_day_sheet_inputs_dropdowns_and_viewer_default(tmp_path):
    path = write_workbook(_match_day_payload(), tmp_path / "uc.xlsx", built_at="test", source_db="test.db",
                          viewer_member_external_id="1001", viewer_card_number="80000001")
    wb = load_workbook(path)
    assert wb.active.title == "Match Day"
    md = wb["Match Day"]
    sources = {str(dv.sqref): dv.formula1 for dv in md.data_validations.dataValidation}
    assert sources["B7"] == "PlayerLabelList"  # pick "Name (APA record ID n)" or type the ID
    assert sources["B8"] == "MyTeamSlotList"
    assert sources["B9"] == "FormatFilterList"
    assert sources["B10"] == "FixtureNumberList"
    assert [dv.type for dv in md.data_validations.dataValidation if str(dv.sqref) == "B6"] == ["date"]
    assert md["B7"].value == "Ann Archer (APA record ID 1001)"  # name shown alongside the verified record ID
    assert md["B9"].value == "8-Ball & 9-Ball"
    assert "80000001" in md["B15"].value and "never used as identity" in md["B15"].value
    assert md["A7"].value == "2 · I am"
    for name in ("MyTeamSlotList", "FormatFilterList", "FixtureNumberList", "PlayerLabelList", "TeamNameList"):
        assert name in wb.defined_names
    assert md.print_area and md.page_setup.orientation == "landscape"
    links = [c.hyperlink.location for c in md[3] if c.hyperlink]
    assert "'Match Night'!A1" in links and "'Schedule'!A1" in links


def test_unresolved_viewer_is_never_prefilled_or_guessed(tmp_path):
    wb = load_workbook(write_workbook(_match_day_payload(), tmp_path / "uc.xlsx", viewer_member_external_id="99999"))
    assert wb["Match Day"]["B7"].value in (None, "")
    assert wb["Match Day"]["B15"].value == "—"
    wb = load_workbook(write_workbook(_match_day_payload(), tmp_path / "uc2.xlsx"))
    assert wb["Match Day"]["B7"].value in (None, "")


FORBIDDEN_FUNCTIONS = ("FILTER(", "SORT(", "UNIQUE(", "SEQUENCE(", "XLOOKUP(", "LET(", "LAMBDA(",
                       "OFFSET(", "INDIRECT(", "TODAY(", "NOW(", "RAND(", "RANDBETWEEN(")


def test_workbook_uses_no_dynamic_array_volatile_or_unbalanced_formulas(tmp_path):
    wb = load_workbook(write_workbook(_match_day_payload(), tmp_path / "uc.xlsx", viewer_member_external_id="1001"))
    checked = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                value = cell.value
                if not (isinstance(value, str) and value.startswith("=")):
                    continue
                checked += 1
                outside_strings = re.sub(r'"[^"]*"', '""', value)
                assert not any(fn in outside_strings.upper() for fn in FORBIDDEN_FUNCTIONS), cell.coordinate
                assert outside_strings.count("(") == outside_strings.count(")"), f"{ws.title}!{cell.coordinate}"
                assert value.count('"') % 2 == 0, f"{ws.title}!{cell.coordinate}"
    assert checked > 100
    assert not wb.vba_archive if hasattr(wb, "vba_archive") else True


def test_reference_sheets_freeze_headers_and_use_the_shared_palette(tmp_path):
    wb = load_workbook(write_workbook(_match_day_payload(), tmp_path / "uc.xlsx"))
    for name in ("Players", "Team Rosters", "Teams", "Player vs Player", "Schedule", "Schedule Keys", "Player Teams"):
        ws = wb[name]
        assert ws.freeze_panes in ("A2", "B2"), name
        assert ws["A1"].fill.fgColor.rgb.endswith("14532D"), name


def test_players_record_id_is_text_so_a_typed_id_matches_exactly(tmp_path):
    wb = load_workbook(write_workbook(_match_day_payload(), tmp_path / "uc.xlsx"))
    rows = _rows_by_header(wb["Players"])
    assert all(isinstance(r["External ID"], str) for r in rows)


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

        dash.Range("B4").Value = "Ann Archer (APA record ID 1001)"
        dash.Range("B5").Value = "Cam Cole (APA record ID 1003)"
        dash.Range("B6").Value = "8-Ball"
        excel.CalculateFullRebuild()
        assert dash.Range("B21").Value == 1  # Wins
        assert dash.Range("B22").Value == 1  # Losses
        assert dash.Range("B23").Value == 2  # Recorded meetings
        assert "50.0%" in str(dash.Range("B24").Value)

        dash.Range("B5").Value = "Bea Baker (APA record ID 1002)"
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

        dash.Range("B4").Value = "Bea Baker (APA record ID 1002)"
        dash.Range("B5").Value = "Cam Cole (APA record ID 1003)"
        dash.Range("B6").Value = "Masters"
        excel.CalculateFullRebuild()
        # Real recorded evidence exists for this pair only under "Masters" --
        # must be reachable via the dropdown, not reported as no evidence.
        assert dash.Range("B21").Value == 1  # Wins
        assert dash.Range("B23").Value == 1  # Recorded meetings
        assert "Direct evidence found" in str(dash.Range("B25").Value)

        night = wb.Worksheets("Match Night")
        night.Range("B5").Value = "Sharks · Spring 2026 · 8-Ball"
        night.Range("C5").Value = "Falcons · Spring 2026 · 8-Ball"
        excel.CalculateFullRebuild()
        assert night.Range("B7").Value == 2  # exact Sharks d1 scope only
        assert night.Range("C7").Value == 1  # Falcons roster count
        assert night.Range("B9").Value == 9  # exact Sharks d1 skill total: 4 + 5
        assert night.Range("C9").Value == 3  # Falcons skill total
    finally:
        wb.Close(False)
        excel.Quit()


def test_print_matchup_sheet_is_a_focused_landscape_print_with_ranking_on_its_own_pages(tmp_path):
    wb = load_workbook(write_workbook(_match_day_payload(), tmp_path / "uc.xlsx", viewer_member_external_id="1001"))
    sheet = wb["Print Matchup"]
    assert sheet.print_area.endswith("$A$1:$K$" + sheet.print_area.rsplit("$", 1)[1])
    assert sheet.page_setup.orientation == "landscape"
    assert (sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight) == (1, 0)  # as many pages as needed
    assert sheet.print_title_rows == "$1:$2"  # fixture headline repeats on every printed page
    ranking_row = next(c.row for c in sheet["A"] if c.value == "Evidence ranking vs each opponent (not win odds)")
    assert [b.id for b in sheet.row_breaks.brk] == [ranking_row - 1]  # ranking starts a new page
    assert "not a win probability" in sheet.cell(row=ranking_row + 1, column=1).value
    assert "even when it is small or a loss" in sheet.cell(row=ranking_row + 1, column=1).value
    assert any(c.value == "Team comparison" for c in sheet["A"])
    assert sheet.sheet_properties.pageSetUpPr.fitToPage is True
    assert sheet["A6"].value == "OUR TEAM" and sheet["G6"].value == "OPPONENT"
    for left in ("A", "G"):
        row = [sheet[f"{chr(ord(left) + i)}9"].value for i in range(5)]
        assert row == ["#", "Player", "APA record ID", "SL", "Current W-L"]
    legend = " ".join(str(c.value) for c in sheet["A"] if isinstance(c.value, str) and c.value.startswith(("Legend", "Rosters", "No win")))
    assert "“No data”: not captured" in legend and "SL with *" in legend and "never counted as 0" in legend
    assert "NOT CALIBRATED" in legend and "CURRENT captured roster" in legend
    # Helper/lookup cells and navigation stay outside the printed range.
    last_print_row = int(sheet.print_area.rsplit("$", 1)[1])
    assert any(c.hyperlink for c in sheet[last_print_row + 2])
