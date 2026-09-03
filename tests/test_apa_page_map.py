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
        for key in ("table_selector", "table_row_selector", "player_name_selector", "team_name_selector", "skill_level_col"):
            assert key in MATCH_PAGE

    def test_standings_page_is_intact(self):
        assert STANDINGS_PAGE["columns"] == ["rank", "team_name", "wins", "losses", "points"]


class TestDocstringDoesNotOverclaim:
    def test_names_the_placeholder_maps(self):
        doc = page_map.__doc__ or ""
        for name in ("STANDINGS_PAGE", "TEAM_PAGE", "PLAYER_PAGE"):
            assert name in doc
        assert "PLACEHOLDER" in doc

    def test_does_not_claim_blanket_verification(self):
        doc = (page_map.__doc__ or "").lower()
        assert "updated with real selectors from league.poolplayers.com portal inspection" not in doc
