"""Tests for ui.export_excel -- first coverage this module has had.

Mirrors tests/test_export_json.py's approach: seed a small in-memory
database through the real ingest functions, then check the actual
workbook produced, not just that export_to_excel() didn't raise.
"""

from __future__ import annotations

import zipfile
from xml.etree import ElementTree as ET

import openpyxl
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.ingest import (
    ingest_eight_ball_stats,
    ingest_head_to_head,
    ingest_match,
    ingest_match_scores,
    ingest_matchups,
    ingest_player_team_history,
    ingest_standings,
    upsert_player,
    upsert_team,
)
from analytics.close_match_performance import CLOSE_MATCH_BAND_MARGIN, close_match_band
from database.models import Base, Player, PlayerTrend
from ui.export_excel import (
    MATCHUPS_WIN_RATE_HIGH,
    MATCHUPS_WIN_RATE_LOW,
    TREND_ICON_DOWN,
    TREND_ICON_FLAT,
    TREND_ICON_UP,
    TRENDS_NO_DATA,
    export_to_excel,
    matchup_risk_band,
    trend_icon,
)

EXPECTED_SHEETS = {
    "Standings", "Player Stats", "Career Stats", "Team History", "Skill Level History",
    # Team_Stats: real, currently-computable team aggregates only -- see
    # analytics/team_stats.py's module docstring for what's deliberately
    # excluded (clutch rating, numeric trend score, break/run rate,
    # defensive-shot rate -- none are real fields anywhere in this project).
    "Team_Stats",
    # Close-Match Win Rate -- docs/planned_analytics_design.md -- one row
    # per player with at least one real head-to-head game.
    "Close_Match_Stats",
    "Matchups",
    # Head-to-Head Advantage Engine (docs/head_to_head.md) -- its own
    # sheet, alongside Matchups rather than replacing it.
    "Head-to-Head",
    # Player Trend Analyzer (docs/player_trends.md) -- its own sheet.
    "Player Trends",
    # Captain's Decision Engine (docs/captains_edge.md).
    "Captain's Edge",
}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _export(db, tmp_path):
    config = {"export": {"excel_output_path": str(tmp_path / "out.xlsx")}}
    path = export_to_excel(db, config)
    return openpyxl.load_workbook(path)


class TestEmptyDatabase:
    """A fresh checkout runs the demo/sync before anything is ingested --
    every sheet must exist, even with only a header row."""

    def test_all_four_sheets_exist(self, db, tmp_path):
        wb = _export(db, tmp_path)
        assert set(wb.sheetnames) == EXPECTED_SHEETS

    def test_career_stats_and_team_history_are_empty_not_missing(self, db, tmp_path):
        wb = _export(db, tmp_path)
        assert wb["Career Stats"].max_row == 1  # header only
        assert wb["Team History"].max_row == 1
        assert wb["Skill Level History"].max_row == 1
        assert wb["Matchups"].max_row == 1


class TestSeededData:
    @pytest.fixture
    def seeded_db(self, db):
        team = upsert_team(db, "T1", "Mark It Up")
        player = upsert_player(db, "3349374", "Paul Smith", team)
        ingest_eight_ball_stats(db, player, {
            "eight_ball_matches_won": 64, "eight_ball_matches_played": 129,
            "eight_ball_cla": 1, "eight_ball_defensive_shot_avg": 1.26,
            "eight_ball_match_count_for_last_two_yrs": 123, "eight_ball_last_played": "2026-08-31",
            "eight_ball_on_break_count": 30, "eight_ball_break_and_runs": 5,
            "eight_ball_rackless": 2, "eight_ball_mini_slams": 1,
        })
        ingest_player_team_history(db, player, [{
            "is_current": True, "team_name": "Mark It Up", "division_id": "436670",
            "is_tournament": False, "session_name": "2026 Summer", "nick_name": "Paulie",
            "skill_level": 4, "rank": None, "matches_won": 2, "matches_played": 2,
        }])
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack",
                     status="COMPLETED", home_score=18, away_score=12)
        ingest_match_scores(db, "M1", [
            {"player_id": "3349374", "player_name": "Paul Smith", "team_id": "T1",
             "result": "W", "points_earned": 6},
        ])
        ingest_standings(db, [{"team_name": "Mark It Up", "rank": 1, "points": 45}])
        return db

    def test_career_stats_sheet_has_the_real_columns_and_values(self, seeded_db, tmp_path):
        wb = _export(seeded_db, tmp_path)
        ws = wb["Career Stats"]
        headers = [c.value for c in ws[1]]
        assert headers == [
            "Player", "Format", "Matches Won", "Matches Played", "CLA",
            "Defensive Shot Avg", "Matches (Last 2 Yrs)", "Last Played",
            "On Breaks", "Break & Runs", "Mini Slams", "Rackless", "Skunks",
        ]
        row = [c.value for c in ws[2]]
        assert row == [
            "Paul Smith", "EIGHT", 64, 129, 1, 1.26, 123, "2026-08-31",
            30, 5, 1, 2, None,  # Skunks is a nine-ball-only stat
        ]

    def test_team_history_sheet_has_the_real_columns_and_values(self, seeded_db, tmp_path):
        wb = _export(seeded_db, tmp_path)
        ws = wb["Team History"]
        headers = [c.value for c in ws[1]]
        assert headers == [
            "Player", "Current", "Team", "Division", "Tournament", "Session",
            "Nickname", "Skill Level", "Rank", "Matches Won", "Matches Played",
        ]
        row = [c.value for c in ws[2]]
        assert row == [
            "Paul Smith", True, "Mark It Up", "436670", False, "2026 Summer",
            "Paulie", 4, None, 2, 2,
        ]

    def test_standings_and_player_stats_still_work_alongside_the_new_sheets(self, seeded_db, tmp_path):
        wb = _export(seeded_db, tmp_path)
        assert wb["Standings"].max_row == 2  # header + 1 team
        assert wb["Player Stats"].max_row == 2  # header + 1 player

    def test_player_stats_shows_which_team_the_row_is_for(self, seeded_db, tmp_path):
        """A player on two teams during a season legitimately gets two rows
        here -- without a Team column that looked like an unexplained
        duplicate. Real report from Paul: seeing his own name twice, which
        turned out to be exactly this, not a bug."""
        wb = _export(seeded_db, tmp_path)
        rows = [[c.value for c in r] for r in wb["Player Stats"].iter_rows()]
        header, paul = rows[0], rows[1]
        record = dict(zip(header, paul))
        assert record["Team"] == "Mark It Up"

    def test_skill_level_history_sheet_has_the_real_columns_and_values(self, db, tmp_path):
        """Not a new extraction step -- ingest_match_scores already writes
        PlayerMatch.skill_level per match (seeded_db above doesn't set it,
        so this seeds its own match with one)."""
        upsert_team(db, "T1", "Mark It Up")
        upsert_team(db, "T2", "Rack Attack")
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack",
                     week=1, match_date="2026-06-01", status="COMPLETED",
                     home_score=6, away_score=3)
        ingest_match_scores(db, "M1", [
            {"player_id": "3349374", "player_name": "Paul Smith", "team_id": "T1",
             "skill_level": 5, "result": "W", "points_earned": 6},
        ])
        wb = _export(db, tmp_path)
        ws = wb["Skill Level History"]
        headers = [c.value for c in ws[1]]
        assert headers == ["Player Name", "Player ID", "Week", "Skill Level", "Match Date", "Source"]
        row = [c.value for c in ws[2]]
        assert row == ["Paul Smith", "3349374", 1, 5, "2026-06-01", "scoresheet"]

    def test_matchups_sheet_has_the_real_columns_and_values(self, db, tmp_path):
        """Not the scoring math (see tests/test_matchups.py) -- just that
        a computed PlayerMatchup row lands in the sheet correctly."""
        upsert_player(db, "501", "Player One")
        upsert_player(db, "601", "Player Four")
        ingest_matchups(db, [{
            "player_id": "501", "opponent_id": "601", "matches_played": 3,
            "win_rate": 0.667, "avg_points_earned": 5.0,
            "avg_opponent_skill_level": 5.0, "avg_own_skill_level": 4.0, "sl_delta": 1.0,
            "trend": "up", "volatility": 1, "matchup_score": 72, "confidence_score": 63,
        }])
        wb = _export(db, tmp_path)
        ws = wb["Matchups"]
        headers = [c.value for c in ws[1]]
        assert headers == [
            "Player", "Opponent", "Matches Played", "Win Rate", "Avg Points Earned",
            "Avg Opponent Skill Level", "Avg Own Skill Level", "SL Delta", "Trend", "Volatility",
            "Matchup Score", "Confidence Score", "Format", "Session", "Has History", "Risk Band",
        ]
        row = [c.value for c in ws[2]]
        # win_rate=0.667 clears MATCHUPS_WIN_RATE_HIGH, but sl_delta=1.0 is
        # a real (if modest) skill disadvantage, so Low's "AND sl_delta<=0"
        # doesn't hold -- Medium, not Low. See matchup_risk_band's docstring.
        assert row == [
            "Player One", "Player Four", 3, 0.667, 5.0, 5.0, 4.0, 1.0, "up", 1, 72, 63, None, None,
            "Yes", "Medium",
        ]

    def test_dropdown_and_table_auto_expand_with_the_real_row_count(self, db, tmp_path):
        """Column A's dropdown is sourced from this sheet's own Table
        (Players!A:A doesn't exist in this workbook -- see
        _format_matchups's docstring), so it must reference the Table by
        name via a structured reference, not a fixed range, or it goes
        stale the moment a new pairing is added on a later run."""
        upsert_player(db, "501", "Player One")
        upsert_player(db, "601", "Player Four")
        ingest_matchups(db, [{
            "player_id": "501", "opponent_id": "601", "matches_played": 3,
            "win_rate": 0.667, "avg_points_earned": 5.0,
            "avg_opponent_skill_level": 5.0, "avg_own_skill_level": 4.0, "sl_delta": 1.0,
            "trend": "up", "volatility": 1, "matchup_score": 72, "confidence_score": 63,
        }])
        wb = _export(db, tmp_path)
        ws = wb["Matchups"]

        assert "Matchups_Table" in ws.tables
        assert ws.tables["Matchups_Table"].ref == "A1:P2"

        [validation] = ws.data_validations.dataValidation
        assert validation.type == "list"
        # No leading "=" -- that's an Excel-dialog typing convention, not
        # part of the stored value. openpyxl writes formula1 into the
        # saved XML verbatim; a leading "=" there produces a formula1
        # Excel itself can't parse and triggers its "repair" prompt on
        # open (confirmed by inspecting a real generated .xlsx as a zip --
        # see TestGeneratedFileOpensWithoutRepair below for the regression
        # test against the actual saved bytes, not just this round-tripped
        # object).
        assert validation.formula1 == "Matchups_Table[Player]"
        assert "A2:A2" in str(validation.sqref) or "A2" in str(validation.sqref)

    def test_risk_band_column_and_colours(self, db, tmp_path):
        upsert_player(db, "501", "Player One")
        upsert_player(db, "601", "Player Two")
        ingest_matchups(db, [{
            "player_id": "501", "opponent_id": "601", "matches_played": 1,
            "win_rate": 0.5, "sl_delta": 0.0, "matchup_score": 50, "confidence_score": 50,
        }])
        wb = _export(db, tmp_path)
        ws = wb["Matchups"]
        headers = [c.value for c in ws[1]]
        assert headers[-1] == "Risk Band"

        rules = {
            rule.formula[0]: rule
            for rules in ws.conditional_formatting
            for rule in rules.rules
            if rule.formula and rule.formula[0].startswith('"')
        }
        assert '"Low"' in rules and rules['"Low"'].dxf.fill.fgColor.rgb.endswith("C6EFCE")
        assert '"High"' in rules and rules['"High"'].dxf.fill.fgColor.rgb.endswith("FFC7CE")
        assert '"Medium"' in rules and rules['"Medium"'].dxf.fill.fgColor.rgb.endswith("FFEB9C")

    def test_win_rate_colour_zone_boundaries(self, db, tmp_path):
        """Exactly 0.65 is Green-only and exactly 0.45 is Yellow-only --
        the spec's own "Yellow 0.45-0.65" / "Red <= 0.45" overlap at 0.45,
        resolved by giving Green/Red priority (stopIfTrue) over Yellow.
        See _format_matchups's docstring for the exact resolution."""
        upsert_player(db, "501", "Player One")
        upsert_player(db, "601", "Player Two")
        ingest_matchups(db, [{
            "player_id": "501", "opponent_id": "601", "matches_played": 1,
            "win_rate": 0.5, "matchup_score": 50, "confidence_score": 50,
        }])
        wb = _export(db, tmp_path)
        ws = wb["Matchups"]

        rules = {
            (rule.operator, tuple(rule.formula)): rule
            for rules in ws.conditional_formatting
            for rule in rules.rules
        }
        green = rules[("greaterThanOrEqual", (str(MATCHUPS_WIN_RATE_HIGH),))]
        red = rules[("lessThan", (str(MATCHUPS_WIN_RATE_LOW),))]
        yellow = rules[("between", (str(MATCHUPS_WIN_RATE_LOW), str(MATCHUPS_WIN_RATE_HIGH)))]

        assert green.stopIfTrue
        assert red.stopIfTrue
        assert not yellow.stopIfTrue

    def test_a_known_pair_with_no_history_gets_a_neutral_fifty_row(self, db, tmp_path):
        """P1-8: two players who've each played someone, but never each
        other, must still show up in the sheet, marked "No" under Has
        History, instead of being silently absent."""
        upsert_team(db, "T1", "Mark It Up")
        upsert_team(db, "T2", "Rack Attack")
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack")
        ingest_match(db, match_id="M2", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack")
        ingest_head_to_head(db, "M1", [
            {"match_id": "M1", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P2", "opponent_name": "Bob", "result": "W"},
        ])
        ingest_head_to_head(db, "M2", [
            {"match_id": "M2", "player_id": "P1", "player_name": "Alice",
             "opponent_id": "P3", "opponent_name": "Carol", "result": "L"},
        ])
        # No real matchup ever computed between Bob and Carol.

        wb = _export(db, tmp_path)
        rows = [dict(zip([c.value for c in wb["Matchups"][1]], [c.value for c in r]))
                for r in wb["Matchups"].iter_rows(min_row=2)]
        bob_carol = next(r for r in rows if r["Player"] == "Bob" and r["Opponent"] == "Carol")
        assert bob_carol["Matchup Score"] == 50
        assert bob_carol["Has History"] == "No"
        assert bob_carol["Matches Played"] == 0

    def test_player_never_rostered_still_shows_the_scoresheets_own_team(self, db, tmp_path):
        """A player known only from a scoresheet (never upsert_roster()) is
        not team-less: ingest_match_scores() backfills Player.team_id from
        the real team_id each scoresheet entry carries (see
        database.ingest.backfill_player_team) whenever nothing is known
        yet."""
        upsert_team(db, "T1", "Chalk It Up")
        upsert_team(db, "T2", "Rack Attack")
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Chalk It Up", away_team_name="Rack Attack",
                     status="COMPLETED", home_score=6, away_score=3)
        ingest_match_scores(db, "M1", [
            {"player_id": "P9", "player_name": "Opponent Guy", "team_id": "T2",
             "result": "L", "points_earned": 3},
        ])
        wb = _export(db, tmp_path)
        rows = [[c.value for c in r] for r in wb["Player Stats"].iter_rows()]
        record = dict(zip(rows[0], rows[1]))
        assert record["Team"] == "Rack Attack"

    def test_player_with_no_team_id_anywhere_shows_a_blank_team_not_a_crash(self, db, tmp_path):
        """The genuinely-no-evidence case: no roster ingest, and the
        scoresheet entry itself carries no team_id. Blank, not a guess."""
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Chalk It Up", away_team_name="Rack Attack",
                     status="COMPLETED", home_score=6, away_score=3)
        ingest_match_scores(db, "M1", [
            {"player_id": "P9", "player_name": "Opponent Guy",
             "result": "L", "points_earned": 3},
        ])
        wb = _export(db, tmp_path)
        rows = [[c.value for c in r] for r in wb["Player Stats"].iter_rows()]
        record = dict(zip(rows[0], rows[1]))
        # An empty string round-trips through openpyxl as a blank cell (None).
        assert not record["Team"]


class TestMatchupRiskBand:
    """matchup_risk_band -- a NEW, documented heuristic (see its own
    docstring), not a real APA field or a fitted model."""

    def test_a_losing_record_alone_is_high_risk(self):
        assert matchup_risk_band(sl_delta=0.0, win_rate=0.3) == "High"

    def test_a_big_skill_disadvantage_alone_is_high_risk_even_with_a_good_record(self):
        assert matchup_risk_band(sl_delta=3.0, win_rate=0.8) == "High"

    def test_a_strong_record_with_no_skill_disadvantage_is_low_risk(self):
        assert matchup_risk_band(sl_delta=-1.0, win_rate=0.8) == "Low"

    def test_a_strong_record_but_a_real_skill_disadvantage_is_not_low(self):
        """Both signals must agree for Low -- a good record alone, while
        still giving up skill level, doesn't clear the bar."""
        assert matchup_risk_band(sl_delta=1.0, win_rate=0.8) == "Medium"

    def test_an_even_middling_pairing_is_medium(self):
        assert matchup_risk_band(sl_delta=0.0, win_rate=0.5) == "Medium"

    def test_missing_either_input_is_unknown_not_a_guess(self):
        assert matchup_risk_band(sl_delta=None, win_rate=0.8) == "Unknown"
        assert matchup_risk_band(sl_delta=0.0, win_rate=None) == "Unknown"


class TestHeadToHeadRiskBandFormatting:
    def test_the_two_signal_formula_references_the_real_columns(self, db, tmp_path):
        """A formula-string bug here (the wrong column letter) would fail
        silently -- Excel just never highlights anything -- so the exact
        formula is checked directly rather than trusted by inspection."""
        upsert_player(db, "P1", "Alice")
        upsert_player(db, "P2", "Bob")
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Home", away_team_name="Away", status="COMPLETED")
        ingest_head_to_head(db, "M1", [{
            "match_id": "M1", "player_id": "P1", "player_name": "Alice",
            "opponent_id": "P2", "opponent_name": "Bob",
            "own_skill_level": 5, "opponent_skill_level": 5, "result": "W",
        }])
        from database.ingest import ingest_h2h_advantage
        from scripts.build_head_to_head import build_rows
        ingest_h2h_advantage(db, build_rows(db))

        wb = _export(db, tmp_path)
        ws = wb["Head-to-Head"]
        headers = [c.value for c in ws[1]]
        score_letter = chr(ord("A") + headers.index("Matchup Score"))
        probability_letter = chr(ord("A") + headers.index("Win Probability"))

        formulas = [rule.formula[0] for rules in ws.conditional_formatting for rule in rules.rules]
        assert f"AND({score_letter}2>=60,{probability_letter}2>=0.6)" in formulas
        assert f"AND({score_letter}2<=40,{probability_letter}2<=0.4)" in formulas


class TestCloseMatchStatsSheet:
    def _seed_close_and_blowout_games(self, db):
        upsert_player(db, "P1", "Alice")
        upsert_player(db, "P2", "Bob")
        for i in range(3):
            match_id = f"CLOSE{i}"
            ingest_match(db, match_id=match_id, home_team_id="T1", away_team_id="T2",
                         home_team_name="Home", away_team_name="Away",
                         status="COMPLETED", home_score=18, away_score=16,
                         is_scored=True, is_finalized=True)
            ingest_head_to_head(db, match_id, [{
                "match_id": match_id, "player_id": "P1", "player_name": "Alice",
                "opponent_id": "P2", "opponent_name": "Bob",
                "own_skill_level": 5, "opponent_skill_level": 5, "result": "W",
            }])
        for i in range(7):
            match_id = f"BLOWOUT{i}"
            ingest_match(db, match_id=match_id, home_team_id="T1", away_team_id="T2",
                         home_team_name="Home", away_team_name="Away",
                         status="COMPLETED", home_score=25, away_score=5,
                         is_scored=True, is_finalized=True)
            ingest_head_to_head(db, match_id, [{
                "match_id": match_id, "player_id": "P1", "player_name": "Alice",
                "opponent_id": "P2", "opponent_name": "Bob",
                "own_skill_level": 5, "opponent_skill_level": 5, "result": "L",
            }])

    def test_real_columns_and_a_strong_band(self, db, tmp_path):
        self._seed_close_and_blowout_games(db)
        wb = _export(db, tmp_path)
        ws = wb["Close_Match_Stats"]
        headers = [c.value for c in ws[1]]
        assert headers == [
            "Player", "Overall Matches", "Overall Win Rate", "Close Matches",
            "Close Games", "Close Win Rate", "Close-Match Win Rate (Shrunk)", "Close-Match Band",
        ]
        row = dict(zip(headers, [c.value for c in ws[2]]))
        assert row["Player"] == "Alice"
        assert row["Overall Matches"] == 10
        assert row["Close Matches"] == 3
        assert row["Close Games"] == 3
        assert row["Close Win Rate"] == 1.0
        # Shrunk rate sits between the perfect close record and the poor
        # overall one -- real shrinkage, not a face-value 1.0.
        assert 0.0 < row["Close-Match Win Rate (Shrunk)"] < 1.0
        assert row["Close-Match Band"] == close_match_band(
            row["Close-Match Win Rate (Shrunk)"], row["Overall Win Rate"]
        )

    def test_a_player_never_seen_in_head_to_head_is_not_listed(self, db, tmp_path):
        upsert_player(db, "P9", "Never Played Anyone")
        wb = _export(db, tmp_path)
        names = [row[0] for row in wb["Close_Match_Stats"].iter_rows(min_row=2, values_only=True)]
        assert "Never Played Anyone" not in names


class TestCloseMatchBand:
    def test_a_rate_well_above_overall_is_strong(self):
        assert close_match_band(0.8, 0.8 - CLOSE_MATCH_BAND_MARGIN - 0.01) == "Strong"

    def test_a_rate_well_below_overall_is_struggles(self):
        assert close_match_band(0.4, 0.4 + CLOSE_MATCH_BAND_MARGIN + 0.01) == "Struggles"

    def test_a_rate_close_to_overall_is_even(self):
        assert close_match_band(0.5, 0.5) == "Even"

    def test_missing_either_rate_is_unknown_not_a_guess(self):
        assert close_match_band(None, 0.5) == "Unknown"
        assert close_match_band(0.5, None) == "Unknown"


class TestTeamStatsSheet:
    def test_real_columns_and_values_for_a_decided_home_win(self, db, tmp_path):
        home = upsert_team(db, "T1", "Mark It Up")
        away = upsert_team(db, "T2", "Rack Attack")
        alice = upsert_player(db, "P1", "Alice", home)
        alice.skill_level = 5
        bob = upsert_player(db, "P2", "Bob", home)
        bob.skill_level = 3
        db.commit()

        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack",
                     status="COMPLETED", home_score=18, away_score=12)
        ingest_head_to_head(db, "M1", [{
            "match_id": "M1", "player_id": "P1", "player_name": "Alice",
            "opponent_id": "P2", "opponent_name": "Bob",
            "own_skill_level": 5, "opponent_skill_level": 6, "result": "W",
        }])

        wb = _export(db, tmp_path)
        ws = wb["Team_Stats"]
        headers = [c.value for c in ws[1]]
        assert headers == [
            "Team Name", "Matches Played", "Matches Won", "Matches Lost", "Win %",
            "Home Record", "Away Record", "Average SL", "Opponent Strength Index",
        ]
        rows = {r[0]: r for r in ws.iter_rows(min_row=2, values_only=True)}

        home_row = rows["Mark It Up"]
        assert home_row[1:] == (1, 1, 0, 1.0, "1-0", "0-0", 4.0, 6.0)

        away_row = rows["Rack Attack"]
        assert away_row[1:5] == (1, 0, 1, 0.0)
        assert away_row[5:7] == ("0-0", "0-1")

    def test_no_decided_matches_yet_is_none_not_zero(self, db, tmp_path):
        upsert_team(db, "T1", "Mark It Up")
        wb = _export(db, tmp_path)
        ws = wb["Team_Stats"]
        row = dict(zip([c.value for c in ws[1]], [c.value for c in ws[2]]))
        assert row["Matches Played"] == 0
        assert row["Win %"] is None
        assert row["Average SL"] is None
        assert row["Opponent Strength Index"] is None


class TestTrendIcon:
    """trend_icon() is driven entirely by the already-computed Hot/Cold
    flag (analytics.player_trends.hot_cold_flag), never a second,
    independent numeric threshold -- see the function's own docstring for
    why a naive slope cutoff would disagree with real rows."""

    def test_hot_is_the_up_arrow(self):
        assert trend_icon("HOT") == TREND_ICON_UP

    def test_cold_is_the_down_arrow(self):
        assert trend_icon("COLD") == TREND_ICON_DOWN

    def test_neutral_is_the_flat_arrow(self):
        assert trend_icon("NEUTRAL") == TREND_ICON_FLAT

    def test_missing_evidence_is_no_data_not_an_arrow(self):
        """A real NEUTRAL (measured, unremarkable) must never look like the
        same thing as "not enough history yet" -- only a real flag gets a
        directional glyph at all."""
        assert trend_icon(None) == TRENDS_NO_DATA

    def test_an_unrecognized_flag_is_no_data_not_a_guess(self):
        assert trend_icon("something-unexpected") == TRENDS_NO_DATA


class TestTrendIconInWorkbook:
    def test_a_real_hot_row_shows_the_up_arrow_and_a_real_trend_score(self, db, tmp_path):
        player = upsert_player(db, "P1", "Alice")
        db.add(PlayerTrend(
            player_id=player.id, format="8-ball", session_name="Fall 2026",
            sample_size=8, current_skill_level=5, regression_slope=0.08,
            volatility=0.2, sl_stability=0.83, hot_cold_flag="HOT",
            projected_sl_change_probability=0.6,
        ))
        db.commit()

        wb = _export(db, tmp_path)
        ws = wb["Player Trends"]
        headers = [c.value for c in ws[1]]
        # Trend Score is appended after Trend Icon, not in place of it.
        assert headers[-2:] == ["Trend Icon", "Trend Score"]

        row = dict(zip(headers, [c.value for c in ws[2]]))
        assert row["Hot/Cold"] == "HOT"
        assert row["Trend Icon"] == TREND_ICON_UP
        assert row["Trend Score"] == round(0.08 / (0.2 + 0.05), 4)


OOXML_MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
OOXML_PACKAGE_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OOXML_DOC_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class TestGeneratedFileOpensWithoutRepair:
    """Real regression tests against the SAVED FILE'S OWN BYTES -- not the
    openpyxl object model tests elsewhere in this file already exercise.

    Real bug found by inspecting a generated .xlsx as a zip after Excel
    reported it needed repair: ui.export_excel wrote the Matchups sheet's
    dropdown as `formula1="=Matchups_Table[Player]"`. openpyxl stores
    formula1 into the saved XML verbatim -- the leading "=" is a
    convention of Excel's OWN dialog UI, not part of the stored value --
    so the saved file carried a `<formula1>` Excel itself can't parse.
    Every existing test in this file round-trips through
    `openpyxl.load_workbook()`, which reads that same malformed string
    back into the very same object attribute without complaining, so
    nothing here could have caught it: TestSeededData and friends check
    that the WORKBOOK MODEL looks right, not that the bytes Excel actually
    opens are well-formed. These tests read the zip directly instead.
    """

    @pytest.fixture
    def seeded_db(self, db):
        """Populates enough real data that every sheet with a Table,
        autoFilter, conditional formatting, or data validation actually
        gets one -- an empty Matchups sheet, in particular, never reaches
        the code path that adds its DataValidation at all (see
        ui.export_excel._format_matchups's `if frame.empty: return`), so
        a fixture with no real matchup rows would let this exact class of
        bug through undetected.
        """
        team = upsert_team(db, "T1", "Mark It Up")
        opponent = upsert_team(db, "T2", "Rack Attack")
        alice = upsert_player(db, "P1", "Alice", team)
        upsert_player(db, "P2", "Bob", opponent)
        ingest_match(db, match_id="M1", home_team_id="T1", away_team_id="T2",
                     home_team_name="Mark It Up", away_team_name="Rack Attack",
                     status="COMPLETED", home_score=18, away_score=16,
                     is_scored=True, is_finalized=True)
        ingest_match_scores(db, "M1", [
            {"player_id": "P1", "player_name": "Alice", "team_id": "T1",
             "skill_level": 5, "result": "W", "points_earned": 6},
            {"player_id": "P2", "player_name": "Bob", "team_id": "T2",
             "skill_level": 5, "result": "L", "points_earned": 3},
        ])
        ingest_head_to_head(db, "M1", [{
            "match_id": "M1", "player_id": "P1", "player_name": "Alice",
            "opponent_id": "P2", "opponent_name": "Bob",
            "own_skill_level": 5, "opponent_skill_level": 5, "result": "W",
        }])
        ingest_matchups(db, [{
            "player_id": "P1", "opponent_id": "P2", "matches_played": 1,
            "win_rate": 1.0, "avg_points_earned": 6.0,
            "avg_opponent_skill_level": 5.0, "avg_own_skill_level": 5.0,
            "sl_delta": 0.0, "trend": "up", "volatility": 0,
            "matchup_score": 72, "confidence_score": 63,
        }])
        ingest_standings(db, [{"team_name": "Mark It Up", "rank": 1, "points": 45}])
        db.add(PlayerTrend(
            player_id=alice.id, format="8-ball", session_name="Fall 2026",
            sample_size=8, current_skill_level=5, regression_slope=0.08,
            volatility=0.2, sl_stability=0.83, hot_cold_flag="HOT",
            projected_sl_change_probability=0.6,
        ))
        db.commit()
        return db

    def _saved_zip(self, seeded_db, tmp_path):
        config = {"export": {"excel_output_path": str(tmp_path / "out.xlsx")}}
        path = export_to_excel(seeded_db, config)
        return zipfile.ZipFile(path)

    def test_every_part_is_well_formed_xml(self, seeded_db, tmp_path):
        """The most basic thing Excel's strict parser checks: a malformed
        or truncated node in ANY part fails the whole file to open."""
        zf = self._saved_zip(seeded_db, tmp_path)
        for name in zf.namelist():
            if name.endswith((".xml", ".rels")):
                ET.fromstring(zf.read(name))  # raises ET.ParseError if malformed

    def test_no_data_validation_formula_carries_a_leading_equals_sign(self, seeded_db, tmp_path):
        """The exact real bug this class of test exists to catch -- see
        this class's own docstring."""
        zf = self._saved_zip(seeded_db, tmp_path)
        checked_any = False
        for name in zf.namelist():
            if not name.startswith("xl/worksheets/sheet"):
                continue
            root = ET.fromstring(zf.read(name))
            for formula_tag in ("formula1", "formula2"):
                for node in root.iter(f"{OOXML_MAIN_NS}{formula_tag}"):
                    checked_any = True
                    assert not (node.text or "").startswith("="), (
                        f"{name}'s <{formula_tag}> stores a leading '=': {node.text!r} "
                        "-- that's an Excel-dialog typing convention, not part of the "
                        "value openpyxl should persist."
                    )
        assert checked_any, "fixture produced no dataValidation to check -- test would pass vacuously"

    def test_every_table_ref_matches_its_sheets_autofilter_ref(self, seeded_db, tmp_path):
        """A Table whose `ref` disagrees with its own sheet's `autoFilter`
        range is exactly the kind of internal inconsistency Excel's
        strict parser rejects.

        Which SHEET owns a given `xl/tables/tableN.xml` is only knowable
        from that sheet's own `_rels` file (a table's number and its
        owning sheet's number are independent -- table1.xml can belong to
        sheet8.xml, say) -- never by matching the two numbers in the file
        names, which happened to coincide the first time this test was
        written and is not a real invariant.
        """
        zf = self._saved_zip(seeded_db, tmp_path)
        names = zf.namelist()
        table_names = {n for n in names if n.startswith("xl/tables/table")}
        assert table_names, "fixture produced no real Table to check -- test would pass vacuously"

        table_to_sheet: dict[str, str] = {}
        for rels_name in names:
            if not rels_name.startswith("xl/worksheets/_rels/"):
                continue
            sheet_name = "xl/worksheets/" + rels_name.rsplit("/", 1)[1].removesuffix(".rels")
            for rel in ET.fromstring(zf.read(rels_name)).iter(f"{OOXML_PACKAGE_REL_NS}Relationship"):
                target = rel.get("Target").lstrip("/")
                if target in table_names:
                    table_to_sheet[target] = sheet_name

        assert set(table_to_sheet) == table_names, (
            f"table(s) with no owning sheet found via _rels: {table_names - set(table_to_sheet)}"
        )
        for table_name, sheet_name in table_to_sheet.items():
            table_ref = ET.fromstring(zf.read(table_name)).get("ref")
            sheet_root = ET.fromstring(zf.read(sheet_name))
            autofilter = sheet_root.find(f"{OOXML_MAIN_NS}autoFilter")
            assert autofilter is not None, f"{sheet_name} has a Table but no autoFilter"
            assert autofilter.get("ref") == table_ref, (
                f"{table_name}'s table ref {table_ref!r} != {sheet_name}'s autoFilter ref "
                f"{autofilter.get('ref')!r}"
            )

    def test_every_relationship_target_actually_exists_in_the_archive(self, seeded_db, tmp_path):
        """A `.rels` part pointing at a file that isn't in the zip is a
        broken reference Excel refuses to silently ignore."""
        zf = self._saved_zip(seeded_db, tmp_path)
        names = set(zf.namelist())
        rels_files = [n for n in names if n.endswith(".rels")]
        assert rels_files
        for rels_name in rels_files:
            base_dir = rels_name.split("_rels/")[0]
            root = ET.fromstring(zf.read(rels_name))
            for rel in root.iter(f"{OOXML_PACKAGE_REL_NS}Relationship"):
                target = rel.get("Target")
                if target.startswith("/"):
                    resolved = target.lstrip("/")
                else:
                    resolved = (base_dir + target).replace("./", "")
                assert resolved in names, f"{rels_name} points at missing part {target!r}"

    def test_every_tablepart_reference_resolves_to_a_real_relationship(self, seeded_db, tmp_path):
        """A `<tableParts>` entry whose r:id has no matching Relationship
        in that sheet's own `_rels` file is a dangling reference."""
        zf = self._saved_zip(seeded_db, tmp_path)
        names = set(zf.namelist())
        checked_any = False
        for name in names:
            if not name.startswith("xl/worksheets/sheet") or name.endswith(".rels"):
                continue
            sheet_root = ET.fromstring(zf.read(name))
            table_parts = sheet_root.find(f"{OOXML_MAIN_NS}tableParts")
            if table_parts is None:
                continue
            sheet_number = name.replace("xl/worksheets/sheet", "").replace(".xml", "")
            rels_name = f"xl/worksheets/_rels/sheet{sheet_number}.xml.rels"
            assert rels_name in names, f"{name} declares tableParts but has no {rels_name}"
            rel_ids = {
                rel.get("Id")
                for rel in ET.fromstring(zf.read(rels_name)).iter(f"{OOXML_PACKAGE_REL_NS}Relationship")
            }
            for part in table_parts.iter(f"{OOXML_MAIN_NS}tablePart"):
                checked_any = True
                r_id = part.get(f"{OOXML_DOC_REL_NS}id")
                assert r_id in rel_ids, f"{name}'s tablePart r:id={r_id!r} has no matching relationship"
        assert checked_any, "fixture produced no tableParts to check -- test would pass vacuously"
