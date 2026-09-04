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

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        standings_df.to_excel(writer, sheet_name="Standings", index=False)
        player_stats_df.to_excel(writer, sheet_name="Player Stats", index=False)
        career_stats_df.to_excel(writer, sheet_name="Career Stats", index=False)
        team_history_df.to_excel(writer, sheet_name="Team History", index=False)
        skill_level_history_df.to_excel(writer, sheet_name="Skill Level History", index=False)
        matchups_df.to_excel(writer, sheet_name="Matchups", index=False)

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
