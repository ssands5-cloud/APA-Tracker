"""
Central map of CSS selectors / field names for each page type on the
league portal. Keeping these in one place means a markup change on the
site only requires edits here, not in every scraper module.

Updated with real selectors from league.poolplayers.com portal inspection.
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
    "columns": ["rank", "team_name", "wins", "losses", "points"],
}

TEAM_PAGE = {
    "roster_table_selector": "table.roster",
    "roster_row_selector": "tbody tr",
    "roster_columns": ["player_name", "skill_level", "matches_played"],
    "schedule_table_selector": "table.schedule",
    "schedule_row_selector": "tbody tr",
    "schedule_columns": ["date", "opponent", "location", "result"],
}

PLAYER_PAGE = {
    "stats_table_selector": "table.player-stats",
    "stats_row_selector": "tbody tr",
    "stats_columns": ["match_date", "opponent", "skill_level", "points_earned", "result"],
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
