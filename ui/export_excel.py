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
from database.queries import all_players, career_stats, latest_standings, player_match_history, team_history

logger = logging.getLogger(__name__)


def export_to_excel(db: Session, config: dict) -> str:
    output_path = Path(config["export"]["excel_output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    standings_df = _standings_dataframe(db)
    player_stats_df = _player_stats_dataframe(db)
    career_stats_df = _career_stats_dataframe(db)
    team_history_df = _team_history_dataframe(db)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        standings_df.to_excel(writer, sheet_name="Standings", index=False)
        player_stats_df.to_excel(writer, sheet_name="Player Stats", index=False)
        career_stats_df.to_excel(writer, sheet_name="Career Stats", index=False)
        team_history_df.to_excel(writer, sheet_name="Team History", index=False)

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
                "Skill Level": player.skill_level,
                "Matches": played,
                "Wins": wins,
                "Losses": losses,
                "Win %": win_pct,
                "PPM": player.ppm,
                "PA": player.pa,
                "Avg Points": stat.avg_points,
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
