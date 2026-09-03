"""Viewer-scoped match history across all teams, against the sanitized
fixture.

tests/fixtures/matches_by_viewer_response.json is fabricated data shaped to
match the real matchesByViewer capture
(docs/graphql-captures/2026-09-03-full-session/), the single query that
returns every match for every team an account plays on -- no team_id
needed. No live call is made anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

from scraper.graphql_scraper import viewer_matches_rows

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "matches_by_viewer_response.json").read_text()
)
VIEWER = FIXTURE["data"]["viewer"]


class TestViewerMatchesRows:
    def test_one_row_per_match_across_both_teams(self):
        rows = viewer_matches_rows(VIEWER)
        assert len(rows) == 2

    def test_matches_are_tagged_with_the_owning_team(self):
        """Without team_id/team_name, two teams' matches would be
        indistinguishable once flattened into one list."""
        rows = {r["match_id"]: r for r in viewer_matches_rows(VIEWER)}
        assert rows["51478063"]["team_id"] == "13082948"
        assert rows["51478063"]["team_name"] == "Chalk It Up"
        assert rows["51419677"]["team_id"] == "13082718"
        assert rows["51419677"]["team_name"] == "Rack Attack"

    def test_scored_match_fields_are_read_correctly(self):
        rows = {r["match_id"]: r for r in viewer_matches_rows(VIEWER)}
        m = rows["51478063"]
        assert m["week"] == 9
        assert m["status"] == "COMPLETED"
        assert m["is_scored"] is True
        assert m["is_finalized"] is True
        assert m["is_bye"] is False
        assert m["home_score"] == 18
        assert m["away_score"] == 12
        assert m["home_team_name"] == "Chalk It Up"
        assert m["away_team_name"] == "Rack Attack"

    def test_a_bye_is_kept_not_dropped(self):
        """A missing week should never read as lost data."""
        rows = {r["match_id"]: r for r in viewer_matches_rows(VIEWER)}
        bye = rows["51419677"]
        assert bye["is_bye"] is True
        assert bye["is_scored"] is False
        assert bye["home_score"] is None and bye["away_score"] is None

    def test_a_bye_with_no_away_team_does_not_crash(self):
        rows = {r["match_id"]: r for r in viewer_matches_rows(VIEWER)}
        assert rows["51419677"]["away_team_id"] == ""
        assert rows["51419677"]["away_team_name"] == ""

    def test_no_teams_at_all_yields_no_rows(self):
        assert viewer_matches_rows({}) == []
        assert viewer_matches_rows({"teams": []}) == []

    def test_a_team_with_no_matches_yields_no_rows_for_that_team(self):
        assert viewer_matches_rows({"teams": [{"id": 1, "name": "X", "matches": []}]}) == []
