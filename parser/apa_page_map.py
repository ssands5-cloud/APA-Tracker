"""
Central map of CSS selectors / field names for each page type on the
league portal. Keeping these in one place means a markup change on the
site only requires edits here, not in every scraper module.

VERIFICATION STATUS -- read before trusting any selector here.

  MATCH_PAGE      Derived from real league.poolplayers.com markup.
  LOGIN_FORM      Field names are plausible but UNVERIFIED against a live
                  login page; the portal front end is a JavaScript app, so
                  a server-rendered form may not exist at all.
  STANDINGS_PAGE  PLACEHOLDER. `table.standings` is a guess, not observed.
  TEAM_PAGE       PLACEHOLDER. Only the schedule_* keys are used, and they
                  are likewise unobserved.
  PLAYER_PAGE     PLACEHOLDER. Nothing here is currently read by any code.

An earlier version of this docstring claimed every selector had been taken
from portal inspection. That was true of MATCH_PAGE only, and the claim is
what made the placeholders look load-bearing.

Removed deliberately, do not reinstate without checking the parsers first:
TEAM_PAGE["roster_table_selector" / "roster_row_selector" / "roster_columns"]
and PLAYER_PAGE["stats_columns" / "stats_table_selector"]. All were dead --
roster parsing reads MATCH_PAGE, and player parsing read nothing. The
stats_columns order also contradicted the order _parse_match_row actually
uses, so wiring the map back up would have silently misfiled skill level as
the match result.
"""

LOGIN_FORM = {
    "csrf_field_name": "csrf_token",
    "username_field": "username",
    "password_field": "password",
    "success_markers": ("Log Out", "Logout", "My Account", "Sign Out"),
}

STANDINGS_PAGE = {
    "table_selector": "table.standings",
    "row_selector": "tbody tr",
    "columns": ["rank", "team_name", "points"],
}

TEAM_PAGE = {
    # roster_* keys removed: roster parsing uses MATCH_PAGE selectors
    # (scraper/team_scraper.py:60,64,77), never these.
    "schedule_table_selector": "table.schedule",
    "schedule_row_selector": "tbody tr",
    "schedule_columns": ["date", "opponent", "location", "result"],
}

PLAYER_PAGE = {
    # stats_table_selector and stats_columns removed: nothing read them, and
    # the column order they declared disagreed with the order
    # scraper/player_scraper.py:_parse_match_row actually uses at positions
    # 2, 3 and 4. Activating them would have misfiled every row.
    "stats_row_selector": "tbody tr",
    "summary_selector": "div.player-summary",
}

# MATCH PAGE - Real selectors from portal inspection
MATCH_PAGE = {
    "table_selector": ".table-responsive table.table",
    "table_row_selector": "tbody tr",
    "player_name_selector": "div.player a",
    "skill_level_col": 1,  # Index in row
    "matches_won_lost_col": 2,
    "win_pct_col": 3,
    "ppm_col": 4,
    "pa_col": 5,
    # Column headers from real portal
    "columns": [
        "player_name",
        "skill_level",
        "matches_won_played",
        "win_pct",
        "ppm",
        "pa",
    ],
    "team_section_selector": "div.col-md-6",
    "team_name_selector": "h3.teamName a",
    "match_metadata_selectors": {
        "location": "span.location",
        "date_time": "span.match-date-time",
        "status": "span.match-status",
    },
}
