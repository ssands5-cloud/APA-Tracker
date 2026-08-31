"""
Central map of CSS selectors / field names for each page type on the
league portal. Keeping these in one place means a markup change on the
site only requires edits here, not in every scraper module.

NOTE: These selectors are placeholders. Inspect the real HTML (View
Source / DevTools) on your league portal and update the values below to
match before running anything for real.
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
