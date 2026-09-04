"""Viewer-scoped team discovery, against the sanitized fixture.

tests/fixtures/dashboard_teams_response.json is fabricated data shaped to
match the real dashboardTeams capture
(docs/graphql-captures/2026-09-03-full-session/), which proved the account
plays on 4 teams -- not the 1 hardcoded in apa_config.yaml's team.team_id.
No live call is made anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

from scraper.graphql_scraper import dashboard_teams_rows

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "dashboard_teams_response.json").read_text()
)
VIEWER = FIXTURE["data"]["viewer"]


class TestDashboardTeamsRows:
    def test_one_row_per_team_across_both_league_and_tournament(self):
        rows = dashboard_teams_rows(VIEWER)
        assert len(rows) == 4
        assert {r["team_name"] for r in rows} == {
            "Chalk It Up", "Rack Attack", "Side Pocket Squad", "Weekend Warriors",
        }

    def test_league_team_fields_are_read_correctly(self):
        rows = {r["team_name"]: r for r in dashboard_teams_rows(VIEWER)}
        chalk = rows["Chalk It Up"]
        assert chalk["team_id"] == "13082948"
        assert chalk["standing"] == 3
        assert chalk["matches_played"] == 9
        assert chalk["is_tied"] is False
        assert chalk["division_id"] == "436670"
        assert chalk["division_type"] == "EIGHT"
        assert chalk["is_tournament"] is False
        assert chalk["league_id"] == "1438"
        assert chalk["league_slug"] == "sample-league"
        assert chalk["session_name"] == "2026 Summer"

    def test_tied_team_is_flagged(self):
        rows = {r["team_name"]: r for r in dashboard_teams_rows(VIEWER)}
        assert rows["Side Pocket Squad"]["is_tied"] is True

    def test_tournament_team_is_included_and_flagged(self):
        rows = {r["team_name"]: r for r in dashboard_teams_rows(VIEWER)}
        warriors = rows["Weekend Warriors"]
        assert warriors["is_tournament"] is True
        assert warriors["standing"] is None  # an active tournament team may have no standing yet

    def test_a_team_with_no_division_info_does_not_crash(self):
        assert dashboard_teams_rows({"leagueTeams": [{"id": 1, "name": "X"}]}) == [
            {
                "team_id": "1", "team_name": "X", "standing": None, "matches_played": None,
                "is_tied": False, "division_id": "", "division_type": None,
                "is_tournament": False, "league_id": "", "league_slug": "", "session_name": "",
            }
        ]

    def test_no_teams_at_all_yields_no_rows(self):
        assert dashboard_teams_rows({}) == []
        assert dashboard_teams_rows({"leagueTeams": [], "tournamentTeams": []}) == []
