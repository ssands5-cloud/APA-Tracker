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

# MATCH PAGE - Validated selectors from live portal inspection
# Real HTML: player name is in <span class="sm-block"> inside the first <td>
# Player ID (#xxxxxxx) appears as plain text in the same <td>, not in an href
# All numeric columns use class="text-center"
# Each team has its own .table-responsive wrapper; no div.col-md-6 team sections
MATCH_PAGE = {
    "table_selector": ".table-responsive table.table",
    "table_row_selector": "tbody tr",
    "player_name_selector": "td span.sm-block",  # FIXED: plain span, not <a> link
    "skill_level_col": 1,
    "matches_won_lost_col": 2,
    "win_pct_col": 3,
    "ppm_col": 4,
    "pa_col": 5,
    "columns": [
        "player_name",
        "skill_level",
        "matches_won_played",
        "win_pct",
        "ppm",
        "pa",
    ],
    # Each .table-responsive block is one team's table; no wrapping section divs
    "team_section_selector": ".table-responsive",
    "team_name_selector": "h3.teamName, h3, .team-name",  # best-effort; may be absent
    "match_metadata_selectors": {
        "location": "span.location",
        "date_time": "span.match-date-time",
        "status": "span.match-status",
    },
}
