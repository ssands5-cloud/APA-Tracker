"""Row-mapping tests for the HANDOFF.md item 2 scaffolding
(eight_ball_stats_row / team_stat_rows).

These only exercise pure data transforms against sanitized fixtures --
exactly like every other *_rows()/*_row() test in this suite. Nothing here
calls the network, and nothing here decides which roster field is the
correct alias id: that's still the open question in HANDOFF.md item 2, and
these fixtures' alias id (900123) is fabricated, not a confirmed mapping.
"""

from __future__ import annotations

import json
from pathlib import Path

from scraper.graphql_scraper import eight_ball_stats_row, team_stat_rows

EIGHT_BALL_STATS = json.loads(
    (Path(__file__).parent / "fixtures" / "eight_ball_stats_response.json").read_text()
)["data"]["alias"]

TEAM_STAT = json.loads(
    (Path(__file__).parent / "fixtures" / "team_stat_response.json").read_text()
)["data"]["alias"]


class TestEightBallStatsRow:
    def test_flattens_both_formats_into_one_row(self):
        row = eight_ball_stats_row(EIGHT_BALL_STATS)
        assert row["display_name"] == "Jordan Rivera"
        assert row["eight_ball_matches_won"] == 64
        assert row["eight_ball_matches_played"] == 91
        assert row["nine_ball_matches_won"] == 22
        assert row["nine_ball_matches_played"] == 35

    def test_carries_the_alias_id_through_unchanged(self):
        row = eight_ball_stats_row(EIGHT_BALL_STATS)
        assert row["alias_id"] == 900123

    def test_missing_stats_block_does_not_crash(self):
        row = eight_ball_stats_row({"id": 1, "displayName": "Nobody"})
        assert row["eight_ball_matches_won"] is None
        assert row["nine_ball_matches_won"] is None

    def test_empty_alias_does_not_crash(self):
        row = eight_ball_stats_row({})
        assert row["display_name"] == ""
        assert row["alias_id"] is None


class TestTeamStatRows:
    def test_one_row_per_past_and_current_team(self):
        rows = team_stat_rows(TEAM_STAT)
        assert len(rows) == 2

    def test_past_team_is_flagged_not_current(self):
        rows = {r["team_name"]: r for r in team_stat_rows(TEAM_STAT)}
        assert rows["Rack Attack"]["is_current"] is False
        assert rows["Rack Attack"]["matches_won"] == 19
        assert rows["Rack Attack"]["rank"] == 2

    def test_current_team_is_flagged_current(self):
        rows = {r["team_name"]: r for r in team_stat_rows(TEAM_STAT)}
        assert rows["Chalk It Up"]["is_current"] is True
        assert rows["Chalk It Up"]["division_id"] == "436670"

    def test_null_rank_on_current_team_stays_none(self):
        rows = {r["team_name"]: r for r in team_stat_rows(TEAM_STAT)}
        assert rows["Chalk It Up"]["rank"] is None

    def test_no_teams_at_all_yields_no_rows(self):
        assert team_stat_rows({}) == []
        assert team_stat_rows({"pastTeams": [], "currentTeams": []}) == []
