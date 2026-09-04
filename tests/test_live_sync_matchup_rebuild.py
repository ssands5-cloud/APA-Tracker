"""Live-path regression test for the Matchup Advantage Engine (P0 final).

Runs the REAL scheduler.graphql_sync.run_all_teams(export=True) -- the
actual live sync entry point, not a copy or a simplified stand-in -- with
only the lowest layer mocked: requests.post, the same mocking point
tests/test_graphql_client_errors.py already uses for this client. Every
fetch_*() function, every ingest_*() call, analytics.matchup_builder
.build_matchups() itself, and both real export functions run unmodified.

This is what P0-1's actual bug (run_all_teams() ingesting head-to-head
rows but never calling build_matchups()) needed and didn't have: every
existing matchup test either called ingest_matchups() directly with a
hand-built row (tests/test_export_excel.py, tests/test_export_json.py) or
exercised scripts/build_demo.py's separate offline pipeline
(tests/test_build_demo.py) -- neither one ever executed run_all_teams()
itself, so a regression in its wiring specifically had no test that would
catch it. build_matchups() is deliberately NOT mocked here, per that gap:
this proves the real function runs against real (fixture-driven) data,
not that it was merely called.

The GraphQL responses below are fabricated values in real field/operation-
name shapes (matching parser/apa_graphql.py's actual query text), except
the MatchPage payload, which is tests/fixtures/match_detail_response.json
verbatim -- the same fixture tests/test_match_detail_fixture.py's
TestHeadToHeadRows already proves produces real position-paired
head-to-head rows. Every other query returns the minimum needed to let
run_all_teams() complete without error (empty roster/standings/aliases):
this test is scoped to the head-to-head/matchup path specifically, not
full sync coverage, which is what tests/test_viewer_sync_fixture.py,
tests/test_match_detail_fixture.py, etc. already provide piece by piece.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import openpyxl
import pytest
import yaml

from scheduler.graphql_sync import run_all_teams

FIXTURES = Path(__file__).parent / "fixtures"
MATCH = json.loads((FIXTURES / "match_detail_response.json").read_text())["data"]["match"]
assert MATCH["id"] == 555001  # the id wired into MATCHES_BY_VIEWER below must agree

MEMBER_ID = 3349374
TEAM_ID = 13082948
DIVISION_ID = 436670

DASHBOARD_TEAMS = {
    "data": {
        "viewer": {
            "id": MEMBER_ID,
            "leagueTeams": [
                {
                    "id": TEAM_ID, "name": "Chalk It Up", "standing": 3,
                    "totalTeamMatchesPlayed": 10, "isTied": False,
                    "division": {"id": DIVISION_ID, "type": "EIGHT_BALL", "isTournament": False},
                    "league": {"id": 1438, "slug": "example-league"},
                    "session": {"name": "2026 Summer"},
                },
            ],
            "tournamentTeams": [],
        },
    },
}

MATCHES_BY_VIEWER = {
    "data": {
        "viewer": {
            "id": MEMBER_ID,
            "teams": [
                {
                    "id": TEAM_ID,
                    "name": "Chalk It Up",
                    "matches": [
                        {
                            "id": MATCH["id"], "week": 9, "startTime": "2026-08-27T19:00:00-04:00",
                            "status": "COMPLETED", "isBye": False, "isScored": True, "isFinalized": True,
                            "home": {"id": 90001, "name": "Chalk It Up"},
                            "away": {"id": 90002, "name": "Rack Attack"},
                            "results": [
                                {"homeAway": "HOME", "points": {"total": 18}},
                                {"homeAway": "AWAY", "points": {"total": 12}},
                            ],
                        },
                    ],
                },
            ],
        },
    },
}

DIVISION_STANDINGS = {"data": {"division": {"id": DIVISION_ID, "teams": []}}}
TEAM_PAGE = {"data": {"team": {"id": TEAM_ID, "name": "Chalk It Up"}}}
TEAM_ROSTER = {"data": {"team": {"roster": []}}}
TEAM_SCHEDULE = {"data": {"team": {"matches": [], "sessionPoints": 0, "sessionBonusPoints": 0, "sessionTotalPoints": 0}}}
MATCH_PAGE = {"data": {"match": MATCH}}
FORMATS_BY_MEMBER_ID = {"data": {"member": {"id": MEMBER_ID, "aliases": []}}}

# Keyed by the real operation name each query text opens with (verbatim
# from parser/apa_graphql.py, misspelling included -- "divsionStandings"
# is the real live API's own spelling, not a typo here).
OPERATIONS = {
    "query dashboardTeams": DASHBOARD_TEAMS,
    "query matchesByViewer": MATCHES_BY_VIEWER,
    "query divsionStandings": DIVISION_STANDINGS,
    "query teamPage": TEAM_PAGE,
    "query teamRoster": TEAM_ROSTER,
    "query teamSchedule": TEAM_SCHEDULE,
    "query MatchPage": MATCH_PAGE,
    "query FormatsByMemberId": FORMATS_BY_MEMBER_ID,
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


def _fake_post(url, json=None, **kwargs):
    query_text = (json or {}).get("query", "")
    for marker, payload in OPERATIONS.items():
        if marker in query_text:
            return FakeResponse(payload)
    raise AssertionError(f"Unmocked GraphQL operation in this test: {query_text[:120]!r}")


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APA_ACCESS_TOKEN", "fake-token-for-this-test-only")
    path = tmp_path / "test_config.yaml"
    path.write_text(yaml.dump({
        "database": {"path": "data/test_apa_tracker.db"},
        "export": {
            "excel_output_path": "exports/test_apa_stats.xlsx",
            "json_output_path": "exports/test_apa_data.json",
        },
    }))
    return path


class TestLiveSyncMatchupRebuild:
    def test_run_all_teams_ingests_h2h_and_rebuilds_matchups_end_to_end(self, tmp_path, config_path):
        with patch("requests.post", _fake_post):
            counts = run_all_teams(str(config_path), export=True)

        # scored MatchPage -> H2H ingestion occurred
        assert counts["head_to_head_rows"] > 0
        # build_matchups(db) ran (not mocked -- this is its real return value's
        # length, upserted into player_matchups by run_all_teams itself)
        assert counts["matchups"] > 0

        db_path = tmp_path / "data" / "test_apa_tracker.db"
        assert db_path.exists()
        import sqlite3

        conn = sqlite3.connect(db_path)
        h2h_count = conn.execute("SELECT COUNT(*) FROM player_head_to_head").fetchone()[0]
        matchup_count = conn.execute("SELECT COUNT(*) FROM player_matchups").fetchone()[0]
        conn.close()
        assert h2h_count > 0
        assert matchup_count > 0

        # the Excel Matchups sheet contains at least one real row
        workbook_path = tmp_path / "exports" / "test_apa_stats.xlsx"
        assert workbook_path.exists()
        wb = openpyxl.load_workbook(workbook_path)
        matchups_sheet = wb["Matchups"]
        assert matchups_sheet.max_row > 1, "Matchups sheet has no data rows"
        header = [c.value for c in matchups_sheet[1]]
        first_row = dict(zip(header, [c.value for c in matchups_sheet[2]]))
        assert first_row["Player"]
        assert first_row["Opponent"]

        # the JSON export contains at least one real matchup pair
        json_path = tmp_path / "exports" / "test_apa_data.json"
        assert json_path.exists()
        document = json.loads(json_path.read_text())
        assert document["matchups"], "JSON export's matchups key must not be empty"
        assert document["matchups"][0]["player"]
        assert document["matchups"][0]["opponent"]

    def test_an_unmocked_operation_fails_loudly_not_silently(self, config_path):
        """Confirms _fake_post's dispatcher itself is a real gate, not a
        pass-through -- a query this test doesn't recognize must raise,
        not return an empty 200."""
        with patch("requests.post", _fake_post):
            with pytest.raises(AssertionError, match="Unmocked GraphQL operation"):
                from auth.graphql_client import execute
                execute("query somethingNotInThisTest { x }", access_token="t")
