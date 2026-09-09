"""
Exports current standings and player stats to an Excel workbook for easy
sharing with teammates who don't want to touch the database.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from analytics.close_match_performance import close_match_band, close_match_performance
from analytics.player_stats import summarize_player
from analytics.player_trends import trend_score
from analytics.team_stats import (
    average_skill_level,
    opponent_strength_index,
    team_match_record,
)
from database.models import PlayerHeadToHead
from database.queries import (
    all_head_to_head,
    player_trends,
    head_to_head_advantage,
    all_matches,
    all_players,
    all_teams,
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
    team_stats_df = _team_stats_dataframe(db)
    close_match_stats_df = _close_match_stats_dataframe(db)
    matchups_df = _matchups_dataframe(db)
    head_to_head_df = _head_to_head_dataframe(db)
    player_trends_df = _player_trends_dataframe(db)
    captains_edge_df = _captains_edge_dataframe(config)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        standings_df.to_excel(writer, sheet_name="Standings", index=False)
        player_stats_df.to_excel(writer, sheet_name="Player Stats", index=False)
        career_stats_df.to_excel(writer, sheet_name="Career Stats", index=False)
        team_history_df.to_excel(writer, sheet_name="Team History", index=False)
        skill_level_history_df.to_excel(writer, sheet_name="Skill Level History", index=False)
        team_stats_df.to_excel(writer, sheet_name="Team_Stats", index=False)
        _format_team_stats(writer, team_stats_df)
        close_match_stats_df.to_excel(writer, sheet_name="Close_Match_Stats", index=False)
        _format_close_match_stats(writer, close_match_stats_df)
        matchups_df.to_excel(writer, sheet_name="Matchups", index=False)
        _format_matchups(writer, matchups_df)
        head_to_head_df.to_excel(writer, sheet_name="Head-to-Head", index=False)
        _format_head_to_head(writer, head_to_head_df)
        player_trends_df.to_excel(writer, sheet_name="Player Trends", index=False)
        _format_player_trends(writer, player_trends_df)
        captains_edge_df.to_excel(writer, sheet_name="Captain's Edge", index=False)
        _format_captains_edge(writer, captains_edge_df)

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


# --- Team_Stats ---------------------------------------------------------

TEAM_STATS_COLUMNS = [
    "Team Name", "Matches Played", "Matches Won", "Matches Lost", "Win %",
    "Home Record", "Away Record", "Average SL", "Opponent Strength Index",
]


def _team_stats_dataframe(db: Session) -> pd.DataFrame:
    """One row per team: a real win/loss record derived from Match rows
    (analytics.team_stats.team_match_record), the roster's own average
    skill level (average_skill_level), and the mean skill level of
    opponents this team's players have actually faced
    (opponent_strength_index, from real PlayerHeadToHead rows).

    Deliberately excludes Clutch Rating, a numeric Trend Score, Break/Run
    Rate and Defensive Shot Rate -- none of those are real fields anywhere
    in this project; see analytics/team_stats.py's module docstring.
    """
    matches = all_matches(db)
    rows = []
    for team in all_teams(db):
        record = team_match_record(matches, team.external_id)
        h2h_rows = (
            db.query(PlayerHeadToHead)
            .filter(PlayerHeadToHead.player_id.in_([p.id for p in team.players]))
            .all()
            if team.players else []
        )
        rows.append({
            "Team Name": team.name,
            "Matches Played": record.matches_played,
            "Matches Won": record.wins,
            "Matches Lost": record.losses,
            "Win %": record.win_percentage,
            "Home Record": record.home_record,
            "Away Record": record.away_record,
            "Average SL": average_skill_level(team.players),
            "Opponent Strength Index": opponent_strength_index(h2h_rows),
        })
    return pd.DataFrame(rows, columns=TEAM_STATS_COLUMNS)


def _format_team_stats(writer, frame: pd.DataFrame) -> None:
    """Freeze the header, filter every column, and render Win % as a
    percentage -- the same treatment every other sheet gets. No colour
    zones: a team's own win rate isn't a matchup being judged the way a
    single pairing's is on Matchups/Head-to-Head."""
    from openpyxl.utils import get_column_letter

    sheet = writer.sheets["Team_Stats"]
    sheet.freeze_panes = "A2"
    if frame.empty:
        return

    last_column = get_column_letter(len(frame.columns))
    last_row = len(frame) + 1
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"

    win_pct_column = TEAM_STATS_COLUMNS.index("Win %") + 1
    for row in sheet.iter_rows(min_row=2, min_col=win_pct_column, max_col=win_pct_column):
        for cell in row:
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0.0%"

    for index, name in enumerate(frame.columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = max(len(str(name)) + 4, 12)


# --- Close-Match Win Rate -- docs/planned_analytics_design.md ---------------
# close_match_band/CLOSE_MATCH_BAND_MARGIN live in analytics/close_match_
# performance.py, not here -- ui.export_json needs the exact same
# categorisation, and importing one shared function beats defining it
# twice and risking the workbook and the JSON document disagreeing about
# the same player's band.

CLOSE_MATCH_STATS_COLUMNS = [
    "Player", "Overall Matches", "Overall Win Rate", "Close Matches",
    "Close Win Rate", "Close-Match Win Rate (Shrunk)", "Close-Match Band",
]


def _close_match_stats_dataframe(db: Session) -> pd.DataFrame:
    """One row per player who has at least one real PlayerHeadToHead game
    -- a player never involved in a scored head-to-head has nothing to
    report here, the same reasoning the Matchups sheet already applies.
    Sorted by name for a deterministic row order (see
    tests/test_full_pipeline_integration.py's determinism check), not
    whatever order a dict of player ids happens to iterate in.
    """
    from collections import defaultdict

    rows_by_player: dict[int, list[PlayerHeadToHead]] = defaultdict(list)
    for row in all_head_to_head(db):
        if row.player_id is not None:
            rows_by_player[row.player_id].append(row)

    records = []
    for rows in rows_by_player.values():
        player = rows[0].player
        result = close_match_performance(rows)
        records.append({
            "Player": player.name if player else "",
            "Overall Matches": result.overall_matches_played,
            "Overall Win Rate": result.overall_win_rate,
            "Close Matches": result.close_matches_played,
            "Close Win Rate": result.close_win_rate,
            "Close-Match Win Rate (Shrunk)": result.shrunk_win_rate,
            "Close-Match Band": close_match_band(result.shrunk_win_rate, result.overall_win_rate),
        })
    frame = pd.DataFrame(records, columns=CLOSE_MATCH_STATS_COLUMNS)
    return frame.sort_values("Player", kind="stable").reset_index(drop=True)


def _format_close_match_stats(writer, frame: pd.DataFrame) -> None:
    """Freeze the header, filter every column, render the two rate columns
    as percentages, and colour Close-Match Band the same way Risk Band and
    Trend Icon already are -- one consistent green/yellow/red vocabulary
    across the workbook rather than a new one per sheet."""
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    sheet = writer.sheets["Close_Match_Stats"]
    sheet.freeze_panes = "A2"
    if frame.empty:
        return

    last_column = get_column_letter(len(frame.columns))
    last_row = len(frame) + 1
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"

    for name in ("Overall Win Rate", "Close-Match Win Rate (Shrunk)"):
        column = CLOSE_MATCH_STATS_COLUMNS.index(name) + 1
        for row in sheet.iter_rows(min_row=2, min_col=column, max_col=column):
            for cell in row:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = "0.0%"

    band_column = CLOSE_MATCH_STATS_COLUMNS.index("Close-Match Band") + 1
    band_letter = get_column_letter(band_column)
    band_range = f"{band_letter}2:{band_letter}{last_row}"
    for text, fill_colour, font_colour in (
        ("Strong", "C6EFCE", "006100"),
        ("Even", "FFEB9C", "9C6500"),
        ("Struggles", "FFC7CE", "9C0006"),
    ):
        sheet.conditional_formatting.add(
            band_range,
            CellIsRule(operator="equal", formula=[f'"{text}"'],
                       fill=PatternFill("solid", fgColor=fill_colour),
                       font=Font(color=font_colour, bold=True)),
        )

    for index, name in enumerate(frame.columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = max(len(str(name)) + 4, 12)


# Matchups sheet: Win Rate colour zones (0..1, an unweighted historical
# fraction -- see analytics.matchups.head_to_head_win_rate). The original ask
# named "win probability", but this sheet has no modelled probability field;
# the Head-to-Head sheet's own Win Probability column is the literal match
# for that, and already has its own Matchup-Score-based colouring
# (H2H_RECOMMEND_SCORE/H2H_AVOID_SCORE above) -- these are independent.
MATCHUPS_WIN_RATE_HIGH = 0.65
MATCHUPS_WIN_RATE_LOW = 0.45

# Risk Band: a NEW, transparent heuristic combining SL Delta and Win Rate
# into one label -- not a real APA field and not fitted to any data. The
# threshold below is a documented judgment call, the same kind FULL_
# CONFIDENCE_GAMES is in analytics/matchups.py, not a statistically derived
# cutoff. SL Delta is the existing opponent-minus-own column already on
# this sheet (positive = giving up skill level) -- this is a new way of
# reading it, not a second, duplicate column.
MATCHUPS_RISK_SL_GAP = 2


def matchup_risk_band(sl_delta: float | None, win_rate: float | None) -> str:
    """"Low" / "Medium" / "High" / "Unknown" for one Matchups row.

    High needs only one bad signal (a losing record, OR giving up
    MATCHUPS_RISK_SL_GAP+ skill levels) -- either alone is worth flagging.
    Low needs BOTH a strong record AND no skill disadvantage, the same
    both-signals-must-agree shape ui.tabs.matchups.classify() already uses
    for Head-to-Head's Risk Band below, even though the two sheets read
    different real fields (this one has no win_probability to reuse that
    function directly on).
    """
    if sl_delta is None or win_rate is None:
        return "Unknown"
    if win_rate <= MATCHUPS_WIN_RATE_LOW or sl_delta >= MATCHUPS_RISK_SL_GAP:
        return "High"
    if win_rate >= MATCHUPS_WIN_RATE_HIGH and sl_delta <= 0:
        return "Low"
    return "Medium"


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
                "Risk Band": matchup_risk_band(row["sl_delta"], row["win_rate"]),
            }
            for row in matchups_with_neutral_fill(db)
        ]
    )


def _format_matchups(writer, frame: pd.DataFrame) -> None:
    """Freeze the header, filter every column, wrap the sheet in an Excel
    Table (so a dropdown sourced from it auto-expands as rows are added on
    a later run), add a Data Validation dropdown restricting Column A
    ("Player") to real names from that Table, and colour Win Rate
    green/yellow/red.

    The original ask's dropdown source was "Players!A:A" / "Opponents!A:A"
    -- sheets that don't exist in this workbook, which has one whole-league
    Matchups view rather than a your-roster/opponent-roster split. Using
    this sheet's own Player column via a Table's structured reference gets
    the same real, auto-expanding, always-current effect without inventing
    sheets nothing else here populates.

    Column A already carries a real name on every row from the pipeline --
    a dropdown doesn't change those, only what a future manual edit in that
    column can be replaced with.
    """
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.worksheet.table import Table, TableStyleInfo

    sheet = writer.sheets["Matchups"]
    sheet.freeze_panes = "A2"
    if frame.empty:
        return

    last_column = get_column_letter(len(frame.columns))
    last_row = len(frame) + 1
    full_range = f"A1:{last_column}{last_row}"
    sheet.auto_filter.ref = full_range

    table = Table(displayName="Matchups_Table", ref=full_range)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    sheet.add_table(table)

    validation = DataValidation(type="list", formula1="=Matchups_Table[Player]", allow_blank=True)
    validation.error = "Choose a player already on this sheet, or leave blank."
    validation.errorTitle = "Unknown player"
    sheet.add_data_validation(validation)
    validation.add(f"A2:A{last_row}")

    win_rate_column = list(frame.columns).index("Win Rate") + 1
    win_rate_letter = get_column_letter(win_rate_column)
    win_rate_range = f"{win_rate_letter}2:{win_rate_letter}{last_row}"

    # Spec boundary note: the ask's "Yellow 0.45-0.65" and "Red <= 0.45"
    # both include 0.45. Resolved by giving Green and Red stopIfTrue, so
    # exactly 0.65 is Green-only (>= 0.65 stops before Yellow's inclusive
    # upper bound can also match) and exactly 0.45 is Yellow-only (Red is
    # strictly < 0.45), with no cell ever matching two colours at once.
    sheet.conditional_formatting.add(
        win_rate_range,
        CellIsRule(operator="greaterThanOrEqual", formula=[str(MATCHUPS_WIN_RATE_HIGH)],
                   stopIfTrue=True,
                   fill=PatternFill("solid", fgColor="C6EFCE"),
                   font=Font(color="006100", bold=True)),
    )
    sheet.conditional_formatting.add(
        win_rate_range,
        CellIsRule(operator="lessThan", formula=[str(MATCHUPS_WIN_RATE_LOW)],
                   stopIfTrue=True,
                   fill=PatternFill("solid", fgColor="FFC7CE"),
                   font=Font(color="9C0006", bold=True)),
    )
    sheet.conditional_formatting.add(
        win_rate_range,
        CellIsRule(operator="between",
                   formula=[str(MATCHUPS_WIN_RATE_LOW), str(MATCHUPS_WIN_RATE_HIGH)],
                   fill=PatternFill("solid", fgColor="FFEB9C"),
                   font=Font(color="9C6500", bold=True)),
    )

    for row in sheet.iter_rows(min_row=2, min_col=win_rate_column, max_col=win_rate_column):
        for cell in row:
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0%"

    # Risk Band: text match, same colours as Win Rate's own zones so the
    # two columns read as one consistent signal rather than a second,
    # differently-coloured scale.
    risk_column = list(frame.columns).index("Risk Band") + 1
    risk_letter = get_column_letter(risk_column)
    risk_range = f"{risk_letter}2:{risk_letter}{last_row}"
    for text, fill_colour, font_colour in (
        ("Low", "C6EFCE", "006100"),
        ("Medium", "FFEB9C", "9C6500"),
        ("High", "FFC7CE", "9C0006"),
    ):
        sheet.conditional_formatting.add(
            risk_range,
            CellIsRule(operator="equal", formula=[f'"{text}"'],
                       fill=PatternFill("solid", fgColor=fill_colour),
                       font=Font(color=font_colour, bold=True)),
        )

    for index, name in enumerate(frame.columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = max(len(str(name)) + 4, 12)


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
    """Freeze the header, filter every column, and colour Matchup Score
    green or red -- but only when Win Probability agrees, using the exact
    two-sided rule ui.tabs.matchups.classify() already uses for the demo
    tab (H2H_RECOMMEND_SCORE/PROBABILITY, H2H_AVOID_SCORE/PROBABILITY
    above), so the workbook and the tab can never flag the same pairing
    differently. This is the Risk Band the SL-gap-and-win-rate request
    asked to add to this sheet: conditional formatting applied to Matchup
    Score in place rather than a separate column, per this sheet's existing
    design (one column narrower); "SL Delta" is already a real column here
    -- one of classify()'s two real inputs (score) is already computed
    from it, so it is not a third, independent signal being ignored.
    """
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    sheet = writer.sheets["Head-to-Head"]
    sheet.freeze_panes = "A2"
    if frame.empty:
        return

    last_column = get_column_letter(len(frame.columns))
    last_row = len(frame) + 1
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"

    score_column = list(frame.columns).index("Matchup Score") + 1
    probability_column = list(frame.columns).index("Win Probability") + 1
    score_letter = get_column_letter(score_column)
    probability_letter = get_column_letter(probability_column)
    score_range = f"{score_letter}2:{score_letter}{last_row}"

    # A formula rule, not two independent CellIsRules: a plain "Matchup
    # Score >= 60" cell rule has no way to also require a DIFFERENT
    # column's value in the same row.
    sheet.conditional_formatting.add(
        score_range,
        FormulaRule(
            formula=[f"AND({score_letter}2>={H2H_RECOMMEND_SCORE},"
                     f"{probability_letter}2>={H2H_RECOMMEND_PROBABILITY})"],
            fill=PatternFill("solid", fgColor="C6EFCE"),
            font=Font(color="006100", bold=True),
        ),
    )
    sheet.conditional_formatting.add(
        score_range,
        FormulaRule(
            formula=[f"AND({score_letter}2<={H2H_AVOID_SCORE},"
                     f"{probability_letter}2<={H2H_AVOID_PROBABILITY})"],
            fill=PatternFill("solid", fgColor="FFC7CE"),
            font=Font(color="9C0006", bold=True),
        ),
    )

    # Win Probability reads as a percentage, not a bare 0.73.
    for row in sheet.iter_rows(min_row=2, min_col=probability_column, max_col=probability_column):
        for cell in row:
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0%"

    for index, name in enumerate(frame.columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = max(len(str(name)) + 4, 12)

# --- Player Trend Analyzer ---------------------------------------------------

# Spec: NULL is displayed as "No data", never 0 and never a blank cell that
# could be read as zero.
TRENDS_NO_DATA = "No data"

# Header order is part of the spec. "Trend Icon" is appended after it, not
# inserted into it -- an addition, not a change to that documented contract.
TRENDS_COLUMNS = [
    "Player", "Format", "Session", "Sample Size", "Current SL",
    "Regression Slope", "Volatility", "SL Stability", "Hot/Cold",
    "Projected SL Change Probability",
]
TRENDS_ICON_COLUMN = "Trend Icon"
TRENDS_SCORE_COLUMN = "Trend Score"

# A directional glyph driven ENTIRELY by the Hot/Cold flag already computed
# by analytics.player_trends.hot_cold_flag (HOT_SLOPE_MIN/COLD_SLOPE_MAX,
# gated by volatility and sample size) -- not a second, independent
# threshold on Regression Slope. A naive "slope >= +0.10" rule would
# disagree with real rows: that engine's real HOT floor is +0.05, gated by
# volatility <= 0.40 and sample_size >= 5, so a slope of 0.07 at high
# volatility is real NEUTRAL, not HOT. Two arrows on the same row telling a
# captain different things would be worse than one.
TREND_ICON_UP = "▲"       # HOT
TREND_ICON_FLAT = "▶"     # NEUTRAL -- a measured, unremarkable trend
TREND_ICON_DOWN = "▼"     # COLD


def trend_icon(hot_cold_flag) -> str:
    """TREND_ICON_UP/FLAT/DOWN for a real HOT/NEUTRAL/COLD flag; TRENDS_NO_DATA
    (never an icon) when the flag itself is unknown -- "no evidence yet" must
    never be drawn as the same flat arrow as "measured and unremarkable"."""
    if hot_cold_flag == "HOT":
        return TREND_ICON_UP
    if hot_cold_flag == "COLD":
        return TREND_ICON_DOWN
    if hot_cold_flag == "NEUTRAL":
        return TREND_ICON_FLAT
    return TRENDS_NO_DATA


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
                TRENDS_ICON_COLUMN: trend_icon(row.hot_cold_flag),
                TRENDS_SCORE_COLUMN: shown(
                    trend_score(row.regression_slope, row.volatility, row.sample_size)
                ),
            }
            for row in player_trends(db)
        ],
        columns=TRENDS_COLUMNS + [TRENDS_ICON_COLUMN, TRENDS_SCORE_COLUMN],
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

    # Trend Icon: coloured the same way as Hot/Cold, since it's the same
    # flag rendered as a glyph -- the two columns must never look like they
    # disagree. TRENDS_NO_DATA gets no colour: a real "no evidence yet" is
    # not the same as measured-and-flat.
    icon_column = list(frame.columns).index(TRENDS_ICON_COLUMN) + 1
    icon_range = (f"{get_column_letter(icon_column)}2:"
                  f"{get_column_letter(icon_column)}{last_row}")
    for text, fill_colour, font_colour in (
        (TREND_ICON_UP, "C6EFCE", "006100"),
        (TREND_ICON_DOWN, "FFC7CE", "9C0006"),
    ):
        sheet.conditional_formatting.add(
            icon_range,
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


# --- Captain's Decision Engine ----------------------------------------------

EDGE_NO_DATA = "No data"
EDGE_HIGH_CONFIDENCE = 0.70
EDGE_HIGH_RISK = 0.50

EDGE_COLUMNS = [
    "Player", "Opponent", "Matchup Score", "Risk", "Confidence",
    "Recommended Order", "Rationale",
]

# The Lineup Optimizer is built after this workbook is initially written (the
# builder uses a separate read-only SQLite connection).  The pipeline appends
# this sheet once ``exports/lineups.json`` exists; keeping the column contract
# here makes the Excel view agree with the JSON and HTML views without asking
# the ORM session to read a file it cannot yet know about.
LINEUP_SHEET = "Lineup Optimizer"
LINEUP_COLUMNS = [
    "Team", "Opponent Team", "Format", "Session", "Player", "Opponent",
    "Matchup Score", "Win Probability", "Confidence", "Risk", "Final Score",
    "Rank", "Source Pairing", "Rationale",
]


def _captains_edge_dataframe(config: dict | None = None) -> pd.DataFrame:
    """The recommended lineup, read from exports/captains_edge.json (or
    `config["export"]["captains_edge_json_path"]`, when set).

    Reads the decision document rather than recomputing: the ranking is the
    builder's output, and a second computation here could disagree with the
    JSON and the HTML tab about the same player.

    An absent document yields an empty sheet rather than an error -- the
    workbook is built before the decision JSON on a first run. The config
    override exists so a hermetic test (or a build redirected via
    pipeline.exports.configured_exports_dir) can point this at a scratch
    path instead of silently reading whatever real document happens to sit
    in the real project's exports/ -- see tests/test_captains_decision.py's
    TestCaptainsEdgeSheet, which used to do exactly that.
    """
    import json

    override = ((config or {}).get("export") or {}).get("captains_edge_json_path")
    document_path = Path(override) if override else (
        Path(__file__).resolve().parent.parent / "exports" / "captains_edge.json"
    )
    if not document_path.is_file():
        return pd.DataFrame(columns=EDGE_COLUMNS)

    try:
        document = json.loads(document_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read %s -- Captain's Edge sheet left empty", document_path)
        return pd.DataFrame(columns=EDGE_COLUMNS)

    def shown(value):
        return EDGE_NO_DATA if value is None else value

    records = []
    for lineup in document.get("lineups") or []:
        for player in lineup.get("players") or []:
            records.append({
                "Player": player.get("player_name") or "",
                "Opponent": shown(player.get("opponent_name")),
                "Matchup Score": shown(player.get("matchup_score")),
                "Risk": shown(player.get("risk_factor")),
                "Confidence": shown(player.get("confidence")),
                "Recommended Order": shown(player.get("recommended_order")),
                "Rationale": player.get("rationale") or "",
            })

    records.sort(key=lambda r: (r["Recommended Order"] == EDGE_NO_DATA,
                                r["Recommended Order"] if isinstance(
                                    r["Recommended Order"], int) else 0))
    return pd.DataFrame(records, columns=EDGE_COLUMNS)


def _format_captains_edge(writer, frame: pd.DataFrame) -> None:
    """Freeze the header, filter every column, and colour high confidence
    green and high risk red.

    The two are independent signals applied to different columns, so a
    player can carry both -- a strong run on an unsettled skill level is
    exactly the call worth flagging twice.
    """
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    sheet = writer.sheets["Captain's Edge"]
    sheet.freeze_panes = "A2"
    if frame.empty:
        return

    last_column = get_column_letter(len(frame.columns))
    last_row = len(frame) + 1
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"

    confidence_letter = get_column_letter(EDGE_COLUMNS.index("Confidence") + 1)
    sheet.conditional_formatting.add(
        f"{confidence_letter}2:{confidence_letter}{last_row}",
        CellIsRule(operator="greaterThanOrEqual", formula=[str(EDGE_HIGH_CONFIDENCE)],
                   fill=PatternFill("solid", fgColor="C6EFCE"),
                   font=Font(color="006100", bold=True)),
    )
    risk_letter = get_column_letter(EDGE_COLUMNS.index("Risk") + 1)
    sheet.conditional_formatting.add(
        f"{risk_letter}2:{risk_letter}{last_row}",
        CellIsRule(operator="greaterThanOrEqual", formula=[str(EDGE_HIGH_RISK)],
                   fill=PatternFill("solid", fgColor="FFC7CE"),
                   font=Font(color="9C0006", bold=True)),
    )

    widths = {"Rationale": 62, "Player": 20, "Opponent": 20}
    for index, name in enumerate(frame.columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = widths.get(
            name, max(len(str(name)) + 4, 12)
        )


def lineup_optimizer_rows(document: dict) -> list[dict]:
    """Flatten a Lineup Optimizer JSON document for the Excel sheet.

    ``None`` is shown as the literal ``No data``.  The optimizer's neutral
    defaults are an internal arithmetic detail and must never appear as if
    they were observed measurements in a captain-facing workbook.
    """

    no_data = "No data"

    def shown(value):
        return no_data if value is None else value

    rows: list[dict] = []
    for lineup in document.get("lineups") or []:
        for assignment in lineup.get("assignments") or []:
            rows.append({
                "Team": lineup.get("team_name") or lineup.get("team_id") or "",
                "Opponent Team": lineup.get("opponent_team_name") or lineup.get("opponent_team_id") or "",
                "Format": lineup.get("format") or "",
                "Session": lineup.get("session_name") or "",
                "Player": assignment.get("player_name") or "",
                "Opponent": assignment.get("opponent_name") or no_data,
                # Raw stored score, not the normalized/internal score.
                "Matchup Score": shown(assignment.get("matchup_score_raw")),
                "Win Probability": shown(assignment.get("win_probability")),
                "Confidence": shown(assignment.get("confidence")),
                "Risk": shown(assignment.get("risk_factor")),
                "Final Score": shown(assignment.get("final_score")),
                "Rank": shown(assignment.get("lineup_rank")),
                "Source Pairing": "Yes" if assignment.get("source_pairing") else "No",
                "Rationale": assignment.get("rationale") or "",
            })

    rows.sort(key=lambda row: (
        row["Team"], row["Opponent Team"], row["Format"], row["Session"],
        row["Rank"] == no_data,
        row["Rank"] if isinstance(row["Rank"], int) else 0,
    ))
    return rows


def append_lineup_optimizer_sheet(
    workbook_path: str | Path,
    document_path: str | Path,
) -> str:
    """Append/replace the Lineup Optimizer sheet in an existing workbook.

    The workbook is produced before the read-only lineup builder in the normal
    pipeline.  This small post-process keeps that ordering intact while
    ensuring a captain opening Excel sees the same solved assignments as the
    JSON and HTML artifacts.  The operation is idempotent: a rerun replaces a
    prior sheet rather than accumulating duplicate tabs.
    """

    import json

    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook_file = Path(workbook_path)
    document_file = Path(document_path)
    document = json.loads(document_file.read_text(encoding="utf-8"))
    rows = lineup_optimizer_rows(document)

    workbook = load_workbook(workbook_file)
    if LINEUP_SHEET in workbook.sheetnames:
        del workbook[LINEUP_SHEET]
    sheet = workbook.create_sheet(LINEUP_SHEET)

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F3864")
    sheet.append(LINEUP_COLUMNS)
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        sheet.append([row[column] for column in LINEUP_COLUMNS])

    sheet.freeze_panes = "A2"
    last_column = get_column_letter(len(LINEUP_COLUMNS))
    sheet.auto_filter.ref = f"A1:{last_column}{max(sheet.max_row, 1)}"

    probability_column = LINEUP_COLUMNS.index("Win Probability") + 1
    for cells in sheet.iter_rows(
        min_row=2, min_col=probability_column, max_col=probability_column
    ):
        for cell in cells:
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0%"

    widths = {"Rationale": 62, "Team": 20, "Opponent Team": 20,
              "Player": 20, "Opponent": 20}
    for index, name in enumerate(LINEUP_COLUMNS, start=1):
        width = widths.get(name, max(len(name) + 4, 12))
        if rows:
            width = max(width, min(max(len(str(row[name])) for row in rows) + 2, 42))
        sheet.column_dimensions[get_column_letter(index)].width = width

    workbook.save(workbook_file)
    return str(workbook_file)
