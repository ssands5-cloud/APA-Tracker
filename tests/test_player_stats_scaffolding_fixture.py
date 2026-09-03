"""Row-mapping tests for HANDOFF.md item 2
(eight_ball_stats_row / team_stat_rows / member_aliases_rows /
alias_id_for_league).

These only exercise pure data transforms against sanitized fixtures --
exactly like every other *_rows()/*_row() test in this suite. Nothing here
calls the network. The alias id these fixtures use (900123 and friends) is
fabricated -- the CONFIRMED mapping (which query bridges a member id to an
alias id) is documented in parser/apa_graphql.py's comment above
FORMATS_BY_MEMBER_ID_QUERY, confirmed against a real account's real ids.
"""

from __future__ import annotations

import json
from pathlib import Path

from scraper.graphql_scraper import (
    alias_id_for_league,
    eight_ball_stats_row,
    member_aliases_rows,
    team_stat_rows,
)

EIGHT_BALL_STATS = json.loads(
    (Path(__file__).parent / "fixtures" / "eight_ball_stats_response.json").read_text()
)["data"]["alias"]

TEAM_STAT = json.loads(
    (Path(__file__).parent / "fixtures" / "team_stat_response.json").read_text()
)["data"]["alias"]

MEMBER_ALIASES = json.loads(
    (Path(__file__).parent / "fixtures" / "formats_by_member_id_response.json").read_text()
)["data"]["member"]


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

    def test_match_count_for_last_two_years_is_present(self):
        """Real query requests this field (and the fixture carries it) --
        the row-mapper originally dropped it silently."""
        row = eight_ball_stats_row(EIGHT_BALL_STATS)
        assert row["eight_ball_match_count_for_last_two_yrs"] == 40
        assert row["nine_ball_match_count_for_last_two_yrs"] == 15

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


class TestMemberAliasesRows:
    """The confirmed HANDOFF.md item 2 bridge: member id -> per-league
    alias id, via FormatsByMemberId."""

    def test_one_row_per_league(self):
        rows = member_aliases_rows(MEMBER_ALIASES)
        assert len(rows) == 2
        assert {r["league_id"] for r in rows} == {"1438", "1500"}

    def test_a_league_can_cover_more_than_one_format(self):
        rows = {r["league_id"]: r for r in member_aliases_rows(MEMBER_ALIASES)}
        assert rows["1438"]["formats"] == ["EIGHT", "NINE"]
        assert rows["1500"]["formats"] == ["EIGHT"]

    def test_no_aliases_yields_no_rows(self):
        assert member_aliases_rows({}) == []
        assert member_aliases_rows({"aliases": []}) == []


class TestAliasIdForLeague:
    def test_finds_the_matching_leagues_alias(self):
        assert alias_id_for_league(MEMBER_ALIASES, "1438") == 700001
        assert alias_id_for_league(MEMBER_ALIASES, "1500") == 700002

    def test_format_disambiguates_when_given(self):
        assert alias_id_for_league(MEMBER_ALIASES, "1438", format_="NINE") == 700001
        assert alias_id_for_league(MEMBER_ALIASES, "1500", format_="NINE") is None

    def test_no_matching_league_returns_none_not_a_guess(self):
        assert alias_id_for_league(MEMBER_ALIASES, "999999") is None

    def test_empty_member_returns_none(self):
        assert alias_id_for_league({}, "1438") is None
