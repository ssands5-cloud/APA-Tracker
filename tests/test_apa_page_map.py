"""Guards on parser/apa_page_map.py.

The removed keys were dead config that would have misfiled data if anyone
wired them back up -- see apa-ground-truth.html,
https://claude.ai/code/artifact/ee8264ee-ac00-4563-b1c8-08d9e20b3a24
These tests fail if they reappear without the parsers changing too.
"""

from __future__ import annotations

import parser.apa_page_map as page_map
from parser.apa_page_map import MATCH_PAGE, PLAYER_PAGE, STANDINGS_PAGE, TEAM_PAGE


class TestDeadKeysStayRemoved:
    def test_team_page_has_no_roster_keys(self):
        assert not [k for k in TEAM_PAGE if k.startswith("roster_")], (
            "roster parsing reads MATCH_PAGE selectors; a roster_* key here is "
            "dead config that looks authoritative"
        )

    def test_player_page_has_no_stats_columns(self):
        assert "stats_columns" not in PLAYER_PAGE, (
            "stats_columns declared a column order contradicting the one "
            "_parse_match_row uses at positions 2, 3 and 4"
        )

    def test_player_page_has_no_stats_table_selector(self):
        assert "stats_table_selector" not in PLAYER_PAGE


class TestKeysStillInUseArePresent:
    def test_team_page_keeps_schedule_keys(self):
        for key in ("schedule_table_selector", "schedule_row_selector", "schedule_columns"):
            assert key in TEAM_PAGE

    def test_match_page_keeps_the_verified_selectors(self):
        for key in ("table_selector", "table_row_selector", "player_name_selector",
                    "team_name_selector", "skill_level_col"):
            assert key in MATCH_PAGE

    def test_standings_page_is_intact(self):
        assert STANDINGS_PAGE["columns"] == ["rank", "team_name", "points"]


class TestDocstringDoesNotOverclaim:
    """The old docstring said every selector came from portal inspection.
    Only MATCH_PAGE did, and that claim is what made placeholders look real.
    """

    def test_names_the_placeholder_maps(self):
        doc = page_map.__doc__ or ""
        for name in ("STANDINGS_PAGE", "TEAM_PAGE", "PLAYER_PAGE"):
            assert name in doc
        assert "PLACEHOLDER" in doc

    def test_does_not_claim_blanket_verification(self):
        doc = (page_map.__doc__ or "").lower()
        assert "updated with real selectors from league.poolplayers.com portal inspection" not in doc
