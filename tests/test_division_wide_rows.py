"""Tests for the division-wide row-mapper functions in scraper/graphql_scraper.py.

DIVISION_ROSTERS_QUERY and DIVISION_SCHEDULE_QUERY were already defined in
parser/apa_graphql.py but never wired to a caller. These pin the two new
row mappers (division_roster_team_rows, division_schedule_rows) against
real field/shape-accurate fixtures before any network call is made.
"""

from __future__ import annotations

from scraper.graphql_scraper import division_roster_team_rows, division_schedule_rows

DIVISION_ROSTERS = {
    "id": 300, "teams": [
        {
            "isBye": False, "id": 301, "name": "Fixture Sharks", "number": 1,
            "roster": [
                {"id": 1, "memberNumber": "M1", "displayName": "Ann Fixture",
                 "matchesWon": 6, "matchesPlayed": 9, "pa": 0.5, "ppm": 1.2,
                 "skillLevel": 6, "member": {"id": 9001}},
                {"id": 2, "memberNumber": "M2", "displayName": "Ben Fixture",
                 "matchesWon": 5, "matchesPlayed": 9, "pa": 0.5, "ppm": 1.0,
                 "skillLevel": 5, "member": {"id": 9002}},
            ],
        },
        {
            "isBye": False, "id": 302, "name": "Fixture Renegades", "number": 2,
            "roster": [
                {"id": 3, "memberNumber": "M3", "displayName": "Uma Sample",
                 "matchesWon": 4, "matchesPlayed": 9, "pa": 0.4, "ppm": 0.9,
                 "skillLevel": 5, "member": {"id": 9003}},
            ],
        },
        {"isBye": True, "id": 999, "name": "BYE", "number": 3, "roster": []},
    ],
}

DIVISION_SCHEDULE = {
    "id": 300, "teams": [{"id": 301, "name": "Fixture Sharks", "number": 1,
                           "active": True, "isBye": False}],
    "schedule": [
        {
            "id": 1, "description": "Week 1", "date": "2026-01-15", "weekOfPlay": 1, "skip": False,
            "matches": [
                {
                    "id": 90401, "isBye": False, "status": "COMPLETED", "startTime": "2026-01-15",
                    "isScored": True, "isFinalized": True, "isPlayoff": False, "tableNumber": 1,
                    "results": [
                        {"homeAway": "HOME", "points": {"total": 18}},
                        {"homeAway": "AWAY", "points": {"total": 12}},
                    ],
                    "home": {"id": 301, "name": "Fixture Sharks", "number": 1},
                    "away": {"id": 302, "name": "Fixture Renegades", "number": 2},
                },
            ],
        },
        {
            "id": 2, "description": "Week 2", "date": "2026-01-22", "weekOfPlay": 2, "skip": False,
            "matches": [
                {
                    "id": 90402, "isBye": False, "status": "SCHEDULED", "startTime": "2026-01-22",
                    "isScored": False, "isFinalized": False, "isPlayoff": False, "tableNumber": None,
                    "results": [],
                    "home": {"id": 302, "name": "Fixture Renegades", "number": 2},
                    "away": {"id": 301, "name": "Fixture Sharks", "number": 1},
                },
                {
                    "id": 90403, "isBye": True, "status": "COMPLETED", "startTime": "2026-01-22",
                    "isScored": False, "isFinalized": True, "isPlayoff": False, "tableNumber": None,
                    "results": [],
                    "home": {"id": 303, "name": "Bye Team", "number": 3},
                    "away": None,
                },
            ],
        },
    ],
}


class TestDivisionRosterTeamRows:
    def test_every_real_team_becomes_an_entry(self):
        teams = division_roster_team_rows(DIVISION_ROSTERS)

        assert {t["team_id"] for t in teams} == {"301", "302"}

    def test_a_bye_slot_is_excluded(self):
        teams = division_roster_team_rows(DIVISION_ROSTERS)

        assert "999" not in {t["team_id"] for t in teams}

    def test_each_roster_entry_carries_the_real_fields(self):
        teams = division_roster_team_rows(DIVISION_ROSTERS)
        sharks = next(t for t in teams if t["team_id"] == "301")

        ann = next(p for p in sharks["roster"] if p["player_name"] == "Ann Fixture")
        assert ann["player_id"] == "9001"
        assert ann["skill_level"] == 6
        assert ann["matches_won"] == 6
        assert ann["matches_played"] == 9

    def test_an_opponent_only_teams_roster_is_present(self):
        """The whole point: a team the account never played is still here."""
        teams = division_roster_team_rows(DIVISION_ROSTERS)
        renegades = next(t for t in teams if t["team_id"] == "302")

        assert len(renegades["roster"]) == 1
        assert renegades["roster"][0]["player_name"] == "Uma Sample"

    def test_missing_or_empty_division_yields_no_teams(self):
        assert division_roster_team_rows({}) == []
        assert division_roster_team_rows({"teams": None}) == []

    def test_null_team_and_null_player_entries_do_not_raise(self):
        teams = division_roster_team_rows({"teams": [None]})
        assert teams[0]["team_id"] == ""

        teams = division_roster_team_rows({"teams": [{"id": 1, "name": "T", "roster": [None]}]})
        assert teams[0]["roster"][0]["player_name"] == ""


class TestDivisionScheduleRows:
    def test_every_real_match_across_every_week_becomes_a_row(self):
        rows = division_schedule_rows(DIVISION_SCHEDULE)

        assert {r["match_id"] for r in rows} == {"90401", "90402", "90403"}

    def test_week_comes_from_the_enclosing_week_block(self):
        rows = division_schedule_rows(DIVISION_SCHEDULE)
        match = next(r for r in rows if r["match_id"] == "90401")

        assert match["week"] == 1

    def test_a_scored_match_carries_real_scores_and_flags(self):
        rows = division_schedule_rows(DIVISION_SCHEDULE)
        match = next(r for r in rows if r["match_id"] == "90401")

        assert match["home_score"] == 18
        assert match["away_score"] == 12
        assert match["is_scored"] is True
        assert match["is_finalized"] is True
        assert match["home_team_id"] == "301"
        assert match["away_team_id"] == "302"

    def test_a_team_the_account_never_played_still_produces_a_real_match(self):
        """Neither side of match 90402 is a team from `teams` in this
        fixture in the account's own sense -- this is a match between two
        OTHER teams' schedule, exactly what matchesByViewer cannot show."""
        rows = division_schedule_rows(DIVISION_SCHEDULE)
        match = next(r for r in rows if r["match_id"] == "90402")

        assert match["home_team_id"] == "302"
        assert match["away_team_id"] == "301"
        assert match["is_scored"] is False

    def test_a_bye_is_flagged_not_dropped(self):
        rows = division_schedule_rows(DIVISION_SCHEDULE)
        bye = next(r for r in rows if r["match_id"] == "90403")

        assert bye["is_bye"] is True
        assert bye["away_team_id"] == ""

    def test_missing_or_empty_division_yields_no_rows(self):
        assert division_schedule_rows({}) == []
        assert division_schedule_rows({"schedule": None}) == []

    def test_null_week_block_and_null_match_do_not_raise(self):
        assert division_schedule_rows({"schedule": [None]}) == []
        rows = division_schedule_rows({"schedule": [{"weekOfPlay": 1, "matches": [None]}]})
        assert rows[0]["match_id"] == ""
