"""Normalisation of APA GraphQL responses into ingestion-ready rows.

The fixtures below are INVENTED, not captured: fake team names, fake player
names, fake ids. Nothing here came from a real account, so there is nothing
to sanitise. Keep it that way -- a captured response belongs in a local file
you do not commit.

Shapes (which fields exist, and that any of them may be null) follow the
query documents in parser/apa_graphql.py.
"""

from __future__ import annotations

import pytest

from scraper.graphql_scraper import (
    AccessTokenMissing,
    _token,
    match_score,
    division_standings_rows,
    fetch_division_standings,
    roster_rows,
    standings_rows,
    schedule_rows,
    team_row,
)

TEAM_DATA = {
    "team": {
        "id": 13082948,
        "name": "Chalk It Up",
        "number": 4,
        "standing": 3,
        "isTied": False,
        "division": {"id": 436670, "name": "Thursday 8-Ball", "nightOfPlay": "THURSDAY", "format": "EIGHT_BALL"},
        "session": {"id": 9, "name": "Summer 2026"},
        "league": {"id": 1438, "slug": "example-league"},
        "location": {"name": "The Corner Pocket"},
    },
    "roster": [
        {
            "id": 1,
            "displayName": "Alex R.",
            "matchesWon": 8,
            "matchesPlayed": 10,
            "skillLevel": 5,
            "ppm": 2.1,
            "pa": 0.77,
            "member": {"id": 80200640},
        },
    ],
    "schedule": [
        {
            "id": 555001,
            "week": 1,
            "startTime": "2026-06-04T19:00:00Z",
            "status": "COMPLETED",
            "isBye": False,
            "isScored": True,
            "isFinalized": True,
            "home": {"id": 13082948, "name": "Chalk It Up"},
            "away": {"id": 13082949, "name": "Rack Attack"},
            "location": {"name": "The Corner Pocket"},
            "results": [
                {"homeAway": "HOME", "points": {"total": 3}},
                {"homeAway": "AWAY", "points": {"total": 2}},
            ],
        },
    ],
}


class TestTokenHandling:
    def test_missing_token_raises_with_actionable_message(self, monkeypatch):
        monkeypatch.delenv("APA_ACCESS_TOKEN", raising=False)
        with pytest.raises(AccessTokenMissing) as excinfo:
            _token({})
        assert "APA_ACCESS_TOKEN" in str(excinfo.value)

    def test_environment_token_is_used(self, monkeypatch):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "token-from-env")
        assert _token({}) == "token-from-env"


class TestTeamRow:
    def test_flattens_nested_metadata(self):
        row = team_row(TEAM_DATA)
        assert row["team_id"] == "13082948"
        assert row["team_name"] == "Chalk It Up"
        assert row["division_name"] == "Thursday 8-Ball"
        assert row["session_name"] == "Summer 2026"
        assert row["league_id"] == "1438"
        assert row["standing"] == 3

    def test_nulled_nested_objects_do_not_raise(self):
        """GraphQL nulls a field it cannot resolve; the key still exists."""
        row = team_row({"team": {"id": 1, "name": "X", "division": None, "session": None,
                                 "league": None, "location": None}})
        assert row["division_name"] == ""
        assert row["session_name"] == ""
        assert row["home_location"] == ""

    def test_missing_team_entirely(self):
        assert team_row({})["team_id"] == ""
        assert team_row({"team": None})["team_name"] == ""


class TestRosterRows:
    def test_maps_to_ingestion_field_names(self):
        row = roster_rows(TEAM_DATA)[0]
        assert row == {
            "player_id": "80200640",
            "player_name": "Alex R.",
            "skill_level": 5,
            "matches_won": 8,
            "matches_played": 10,
            "win_pct": 0.8,
            "ppm": 2.1,
            "pa": 0.77,
        }

    def test_null_member_falls_back_to_roster_id(self):
        """`member: null` used to raise AttributeError, not fall back."""
        row = roster_rows({"roster": [{"id": 42, "displayName": "Sam", "member": None}]})[0]
        assert row["player_id"] == "42"

    def test_zero_matches_played_does_not_divide_by_zero(self):
        row = roster_rows({"roster": [{"id": 1, "matchesPlayed": 0, "matchesWon": 0}]})[0]
        assert row["win_pct"] == 0.0

    def test_null_roster_yields_no_rows(self):
        assert roster_rows({"roster": None}) == []
        assert roster_rows({}) == []


class TestScheduleRows:
    def test_maps_a_completed_match(self):
        row = schedule_rows(TEAM_DATA)[0]
        assert row["match_id"] == "555001"
        assert row["home_team_name"] == "Chalk It Up"
        assert row["away_team_name"] == "Rack Attack"
        assert row["date"] == "2026-06-04T19:00:00Z"
        assert row["is_scored"] is True

    def test_bye_week_is_kept_with_no_opponent(self):
        rows = schedule_rows({"schedule": [
            {"id": 2, "week": 5, "isBye": True, "home": {"id": 1, "name": "Us"}, "away": None},
        ]})
        assert len(rows) == 1, "a bye is part of the schedule; dropping it loses a week"
        assert rows[0]["is_bye"] is True
        assert rows[0]["away_team_name"] == ""

    def test_null_match_in_the_list_does_not_raise(self):
        assert schedule_rows({"schedule": [None]})[0]["match_id"] == ""

    def test_null_schedule_yields_no_rows(self):
        assert schedule_rows({"schedule": None}) == []


class TestMatchScore:
    def test_scored_match_returns_both_totals(self):
        assert match_score(schedule_rows(TEAM_DATA)[0]) == (3, 2)

    def test_unscored_match_is_none_not_zero(self):
        """0-0 and 'not played yet' must not look identical."""
        row = {"is_scored": False, "results": []}
        assert match_score(row) == (None, None)

    def test_partially_scored_match_reports_only_what_exists(self):
        row = {"is_scored": True, "results": [{"homeAway": "HOME", "points": {"total": 2}}]}
        assert match_score(row) == (2, None)

    def test_null_points_object(self):
        row = {"is_scored": True, "results": [{"homeAway": "HOME", "points": None}]}
        assert match_score(row) == (None, None)


class TestStandingsRows:
    def test_our_team_rank_and_points_come_from_the_api(self):
        data = dict(TEAM_DATA, points={"sessionTotalPoints": 57})
        row = standings_rows(data)[0]
        assert row["team_name"] == "Chalk It Up"
        assert row["rank"] == 3
        assert row["points"] == 57

    def test_wins_and_losses_derived_from_scored_matches(self):
        """The fixture's single scored match is a 3-2 home win."""
        row = standings_rows(TEAM_DATA)[0]
        assert (row["wins"], row["losses"]) == (1, 0)

    def test_no_scored_matches_yields_none_not_zero_zero(self):
        data = {
            "team": TEAM_DATA["team"],
            "schedule": [{"id": 1, "isScored": False, "home": {"id": 13082948, "name": "Chalk It Up"},
                          "away": {"id": 2, "name": "Rack Attack"}}],
        }
        row = standings_rows(data)[0]
        assert row["wins"] is None and row["losses"] is None, "unplayed is not 0-0"

    def test_byes_are_not_counted_as_results(self):
        data = {
            "team": TEAM_DATA["team"],
            "schedule": [{"id": 1, "isBye": True, "isScored": True,
                          "home": {"id": 13082948, "name": "Chalk It Up"}, "away": None}],
        }
        assert standings_rows(data)[0]["wins"] is None

    def test_no_team_means_no_snapshot(self):
        assert standings_rows({}) == []


# --- Real division standings (the query captured 2026-09-03) -----------------

DIVISION_STANDINGS = {
    "id": 436670,
    "teams": [
        {"id": 1, "name": "Rack Attack", "number": "1", "standing": 1, "pointsLastWeek": 12,
         "lastWeek": 1, "sessionTotalPoints": 72, "totalTeamMatchesPlayed": 10,
         "isTied": False, "isBye": False, "league": {"id": 1438, "slug": "x"}},
        {"id": 13082948, "name": "Chalk It Up", "number": "4", "standing": 3,
         "pointsLastWeek": 9, "lastWeek": 2, "sessionTotalPoints": 57,
         "totalTeamMatchesPlayed": 10, "isTied": False, "isBye": False,
         "league": {"id": 1438, "slug": "x"}},
    ],
}


class TestDivisionStandingsRows:
    """The real query returns the whole division, not just our team."""

    def test_every_team_in_the_division_becomes_a_row(self):
        rows = division_standings_rows(DIVISION_STANDINGS)
        assert len(rows) == 2
        assert {r["team_name"] for r in rows} == {"Rack Attack", "Chalk It Up"}

    def test_rank_and_points_come_straight_from_the_api(self):
        rows = division_standings_rows(DIVISION_STANDINGS)
        ours = next(r for r in rows if r["team_name"] == "Chalk It Up")
        assert ours["rank"] == 3
        assert ours["points"] == 57

    def test_wins_and_losses_are_none_not_guessed(self):
        """This endpoint doesn't return them; APA ranks on session points.
        A derived number here would look authoritative and be wrong."""
        for row in division_standings_rows(DIVISION_STANDINGS):
            assert row["wins"] is None
            assert row["losses"] is None

    def test_missing_or_empty_division_yields_no_rows(self):
        assert division_standings_rows({}) == []
        assert division_standings_rows({"teams": None}) == []

    def test_null_team_entry_does_not_raise(self):
        assert division_standings_rows({"teams": [None]})[0]["team_name"] == ""


class TestFetchDivisionStandings:
    def test_no_division_id_configured_returns_empty_not_an_error(self, monkeypatch):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "tok")
        assert fetch_division_standings({"team": {"team_id": "1"}}) == {}
        assert fetch_division_standings({"apa": {}}) == {}
