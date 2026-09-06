"""
Exports current standings and player stats to an Excel workbook for easy
sharing with teammates who don't want to touch the database.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from analytics.player_stats import summarize_player
from database.queries import (
    player_trends,
    head_to_head_advantage,
    all_players,
    career_stats,
    latest_standings,
    matchups_with_neutral_fill,
    player_match_history,
    skill_level_history,
    team_history,
)

logger = logging.getLogger(__name__)


def export_to_excel(db: Session, config: dict) -> str:
    output_path = Path(config["export"]["excel_output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    standings_df = _standings_dataframe(db)
    player_stats_df = _player_stats_dataframe(db)
    career_stats_df = _career_stats_dataframe(db)
    team_history_df = _team_history_dataframe(db)
    skill_level_history_df = _skill_level_history_dataframe(db)
    matchups_df = _matchups_dataframe(db)
    head_to_head_df = _head_to_head_dataframe(db)
    player_trends_df = _player_trends_dataframe(db)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        standings_df.to_excel(writer, sheet_name="Standings", index=False)
        player_stats_df.to_excel(writer, sheet_name="Player Stats", index=False)
        career_stats_df.to_excel(writer, sheet_name="Career Stats", index=False)
        team_history_df.to_excel(writer, sheet_name="Team History", index=False)
        skill_level_history_df.to_excel(writer, sheet_name="Skill Level History", index=False)
        matchups_df.to_excel(writer, sheet_name="Matchups", index=False)
        head_to_head_df.to_excel(writer, sheet_name="Head-to-Head", index=False)
        _format_head_to_head(writer, head_to_head_df)
        player_trends_df.to_excel(writer, sheet_name="Player Trends", index=False)
        _format_player_trends(writer, player_trends_df)

    logger.info("Exported workbook to %s", output_path)
    return str(output_path)


def _standings_dataframe(db: Session) -> pd.DataFrame:
    rows = latest_standings(db)
    return pd.DataFrame(
        [
            {
                "Rank": r.rank,
                "Team": r.team_name,
                "Wins": r.wins,
                "Losses": r.losses,
                "Points": r.points,
                "As Of": r.captured_at,
            }
            for r in rows
        ]
    )


def _player_stats_dataframe(db: Session) -> pd.DataFrame:
    """One row per player, from match history where we have it.

    The two ingest paths carry different things. Per-match history (scraped
    stats pages) supports counting wins and losses directly. The GraphQL
    roster carries season totals only -- no individual results -- so a player
    known only through it has no match rows, and deriving from history alone
    printed a live 8-2 player as 0-0.

    History wins where present, roster totals fill in otherwise, and "Source"
    says which -- so a zero is never ambiguous between "played none" and "this
    path carries no match detail".

    "Team" is the player's current roster team (Player.team, set by
    upsert_roster()) -- blank for a player only ever seen via a match
    scoresheet, since ingest_match_scores() never assigns a team. A player
    on two of the account's teams during a season can legitimately appear
    as two separate rows here, one per team; without this column that
    looked like an unexplained duplicate. If two rows for the same name
    ever show the SAME team, that's not a real multi-team split -- it means
    two different external_ids got assigned to one real person, a separate
    bug worth chasing.
    """
    records = []
    for player in all_players(db):
        matches = player_match_history(db, player.external_id)
        stat = summarize_player(player.name, matches)

        if stat.matches_played:
            played, wins = stat.matches_played, stat.wins
            losses, win_pct = stat.losses, stat.win_pct
            source = "match history"
        else:
            played = player.matches_played or 0
            wins = player.matches_won or 0
            losses = max(played - wins, 0)
            win_pct = round(player.win_pct, 3) if player.win_pct is not None else 0.0
            source = "roster totals" if played else "no data"

        records.append(
            {
                "Player": stat.player_name,
                "Team": player.team.name if player.team else "",
                "Skill Level": player.skill_level,
                "Matches": played,
                "Wins": wins,
                "Losses": losses,
                "Win %": win_pct,
                "PPM": player.ppm,
                "PA": player.pa,
                "Avg Points": stat.avg_points,
                "8-Ball On Breaks": stat.total_eight_on_breaks,
                "8-Ball Break & Runs": stat.total_eight_break_and_runs,
                "9-Ball On Snaps": stat.total_nine_on_snaps,
                "9-Ball Break & Runs": stat.total_nine_break_and_runs,
                "Source": source,
            }
        )
    return pd.DataFrame(records)


def _career_stats_dataframe(db: Session) -> pd.DataFrame:
    """HANDOFF.md item 2: lifetime stats per (player, format), from
    getEightBallStats. Empty for anyone the alias-id resolution never ran
    for (opponents; a player whose Player row didn't exist yet at sync
    time) -- absent from this sheet, not a zero row."""
    return pd.DataFrame(
        [
            {
                "Player": row.player.name if row.player else "",
                "Format": row.format,
                "Matches Won": row.matches_won,
                "Matches Played": row.matches_played,
                "CLA": row.cla,
                "Defensive Shot Avg": row.defensive_shot_avg,
                "Matches (Last 2 Yrs)": row.match_count_last_two_yrs,
                "Last Played": row.last_played,
                "On Breaks": row.on_break_count,
                "Break & Runs": row.break_and_runs,
                "Mini Slams": row.mini_slams,
                "Rackless": row.rackless,
                "Skunks": row.skunks,
            }
            for row in career_stats(db)
        ]
    )


def _team_history_dataframe(db: Session) -> pd.DataFrame:
    """HANDOFF.md item 2: cross-season team history, from TeamStat."""
    return pd.DataFrame(
        [
            {
                "Player": row.player.name if row.player else "",
                "Current": row.is_current,
                "Team": row.team_name,
                "Division": row.division_id,
                "Tournament": row.is_tournament,
                "Session": row.session_name,
                "Nickname": row.nick_name,
                "Skill Level": row.skill_level,
                "Rank": row.rank,
                "Matches Won": row.matches_won,
                "Matches Played": row.matches_played,
            }
            for row in team_history(db)
        ]
    )


def _skill_level_history_dataframe(db: Session) -> pd.DataFrame:
    """Match-by-match skill level, from PlayerMatch.skill_level -- lets a
    change mid-season actually be seen, instead of only ever showing the
    current value (Player.skill_level / the "Skill Level" column on
    Player Stats). "Source" is inferred from which fields the row carries
    (see ingest_match_roster/ingest_match_scores in database/ingest.py --
    there's no explicit column for it): a scoresheet row always sets
    `result`, a roster row never does.
    """
    return pd.DataFrame(
        [
            {
                "Player Name": row.player.name if row.player else "",
                "Player ID": row.player.external_id if row.player else "",
                "Week": row.match.week if row.match else None,
                "Skill Level": row.skill_level,
                "Match Date": row.match_date,
                "Source": "scoresheet" if row.result is not None else "roster",
            }
            for row in skill_level_history(db)
        ]
    )


def _matchups_dataframe(db: Session) -> pd.DataFrame:
    """Matchup Advantage Engine: one row per (player, opponent), from
    analytics.matchups via scripts/build_matchups.py, PLUS a neutral-50
    "Has History" = No row for every known pair with no computed matchup
    yet (database.queries.matchups_with_neutral_fill -- P1-8: a player
    who's never faced a specific opponent shows up as "no history yet"
    here rather than being silently absent from the sheet). See
    database/models.py's PlayerMatchup docstring for why "Avg Points
    Earned" and "Avg Opponent Skill Level" stand in for the requested
    "innings"/"defensive shots vs opponent" columns -- neither is a real
    field this API has ever returned at this granularity.
    """
    return pd.DataFrame(
        [
            {
                "Player": row["player"],
                "Opponent": row["opponent"],
                "Matches Played": row["matches_played"],
                "Win Rate": row["win_rate"],
                "Avg Points Earned": row["avg_points_earned"],
                "Avg Opponent Skill Level": row["avg_opponent_skill_level"],
                "Avg Own Skill Level": row["avg_own_skill_level"],
                "SL Delta": row["sl_delta"],
                "Trend": row["trend"],
                "Volatility": row["volatility"],
                "Matchup Score": row["matchup_score"],
                "Confidence Score": row["confidence_score"],
                "Format": row["format"],
                "Session": row["session_name"],
                "Has History": "Yes" if row["has_history"] else "No",
            }
            for row in matchups_with_neutral_fill(db)
        ]
    )


# --- Head-to-Head Advantage Engine -------------------------------------------

# Same two-sided rule the demo tab uses (ui/tabs/matchups.py): a pairing has
# to score well AND be probable before it is highlighted, so a 1-0 fluke or a
# skill mismatch the player keeps losing cannot turn the cell green.
H2H_RECOMMEND_SCORE = 60
H2H_RECOMMEND_PROBABILITY = 0.60
H2H_AVOID_SCORE = 40
H2H_AVOID_PROBABILITY = 0.40


def _head_to_head_dataframe(db: Session) -> pd.DataFrame:
    """The Head-to-Head Advantage Engine's table, one row per pairing.

    Straight out of player_h2h_advantage -- nothing is recomputed here, so
    the sheet cannot disagree with the database or the demo tab. Innings and
    per-opponent defensive shots are absent because APA does not expose
    them; see docs/head_to_head.md.
    """
    return pd.DataFrame(
        [
            {
                "Player": row.player.name if row.player else "",
                "Opponent": row.opponent.name if row.opponent else "",
                "Format": row.format or "",
                "Session": row.session_name or "",
                "Games": row.total_matches,
                "Wins": row.wins,
                "Losses": row.losses,
                "SL Delta": row.sl_delta,
                "Trend Modifier": row.trend_modifier,
                "Matchup Score": row.matchup_score,
                "Win Probability": row.win_probability,
                "Expected Points": row.expected_points,
                "Expected Balls": row.expected_balls,
            }
            for row in head_to_head_advantage(db)
        ]
    )


def _format_head_to_head(writer, frame: pd.DataFrame) -> None:
    """Freeze the header, filter every column, and colour the score green or
    red so a captain can scan the sheet without reading numbers.

    Conditional formatting is applied to Matchup Score rather than to a
    separate tag column: the score is the thing being judged, and colouring
    it in place keeps the sheet one column narrower.
    """
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    sheet = writer.sheets["Head-to-Head"]
    sheet.freeze_panes = "A2"
    if frame.empty:
        return

    last_column = get_column_letter(len(frame.columns))
    last_row = len(frame) + 1
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"

    score_range = f"J2:J{last_row}"  # Matchup Score
    sheet.conditional_formatting.add(
        score_range,
        CellIsRule(operator="greaterThanOrEqual", formula=[str(H2H_RECOMMEND_SCORE)],
                   fill=PatternFill("solid", fgColor="C6EFCE"),
                   font=Font(color="006100", bold=True)),
    )
    sheet.conditional_formatting.add(
        score_range,
        CellIsRule(operator="lessThanOrEqual", formula=[str(H2H_AVOID_SCORE)],
                   fill=PatternFill("solid", fgColor="FFC7CE"),
                   font=Font(color="9C0006", bold=True)),
    )

    # Win Probability reads as a percentage, not a bare 0.73.
    for row in sheet.iter_rows(min_row=2, min_col=11, max_col=11):
        for cell in row:
            cell.number_format = "0%"

    for index, name in enumerate(frame.columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = max(len(str(name)) + 4, 12)

# --- Player Trend Analyzer ---------------------------------------------------

# Spec: NULL is displayed as "No data", never 0 and never a blank cell that
# could be read as zero.
TRENDS_NO_DATA = "No data"

# Header order is part of the spec.
TRENDS_COLUMNS = [
    "Player", "Format", "Session", "Sample Size", "Current SL",
    "Regression Slope", "Volatility", "SL Stability", "Hot/Cold",
    "Projected SL Change Probability",
]


def _player_trends_dataframe(db: Session) -> pd.DataFrame:
    """The Player Trend Analyzer's table, one row per (player, format,
    session).

    Straight out of player_trends -- nothing is recomputed, so the sheet
    cannot disagree with the database or the demo tab.

    NULLs become the literal string "No data" per spec. That makes those
    columns mixed-type, which is the intended trade: a captain must never
    mistake "not enough history" for "zero". Slope, volatility and stability
    keep their numeric values wherever they exist.
    """
    def shown(value):
        return TRENDS_NO_DATA if value is None else value

    return pd.DataFrame(
        [
            {
                "Player": row.player.name if row.player else "",
                "Format": row.format or "",
                "Session": row.session_name or "",
                "Sample Size": row.sample_size,
                "Current SL": row.current_skill_level,
                "Regression Slope": shown(row.regression_slope),
                "Volatility": shown(row.volatility),
                "SL Stability": shown(row.sl_stability),
                "Hot/Cold": shown(row.hot_cold_flag),
                "Projected SL Change Probability": shown(
                    row.projected_sl_change_probability
                ),
            }
            for row in player_trends(db)
        ],
        columns=TRENDS_COLUMNS,
    )


def _format_player_trends(writer, frame: pd.DataFrame) -> None:
    """Freeze the header, filter every column, colour Hot green and Cold red,
    and render the probability as a percentage.

    NEUTRAL is left unhighlighted per spec -- only the actionable states
    draw the eye.
    """
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    sheet = writer.sheets["Player Trends"]
    sheet.freeze_panes = "A2"
    if frame.empty:
        return

    last_column = get_column_letter(len(frame.columns))
    last_row = len(frame) + 1
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"

    flag_column = TRENDS_COLUMNS.index("Hot/Cold") + 1
    flag_range = (f"{get_column_letter(flag_column)}2:"
                  f"{get_column_letter(flag_column)}{last_row}")
    for text, fill_colour, font_colour in (
        ("HOT", "C6EFCE", "006100"),
        ("COLD", "FFC7CE", "9C0006"),
    ):
        sheet.conditional_formatting.add(
            flag_range,
            CellIsRule(operator="equal", formula=[f'"{text}"'],
                       fill=PatternFill("solid", fgColor=fill_colour),
                       font=Font(color=font_colour, bold=True)),
        )

    # Percentage format applied per-cell: a "No data" string formatted as a
    # percentage would still render as text, so only the real numbers are
    # touched.
    probability_column = TRENDS_COLUMNS.index("Projected SL Change Probability") + 1
    for row in sheet.iter_rows(min_row=2, min_col=probability_column,
                               max_col=probability_column):
        for cell in row:
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0.0%"

    for index, name in enumerate(frame.columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = max(len(str(name)) + 4, 12)
