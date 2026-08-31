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
from database.queries import all_players, latest_standings, player_match_history

logger = logging.getLogger(__name__)


def export_to_excel(db: Session, config: dict) -> str:
    output_path = Path(config["export"]["excel_output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    standings_df = _standings_dataframe(db)
    player_stats_df = _player_stats_dataframe(db)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        standings_df.to_excel(writer, sheet_name="Standings", index=False)
        player_stats_df.to_excel(writer, sheet_name="Player Stats", index=False)

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
    records = []
    for player in all_players(db):
        matches = player_match_history(db, player.external_id)
        stat = summarize_player(player.name, matches)
        records.append(
            {
                "Player": stat.player_name,
                "Matches": stat.matches_played,
                "Wins": stat.wins,
                "Losses": stat.losses,
                "Win %": stat.win_pct,
                "Avg Points": stat.avg_points,
            }
        )
    return pd.DataFrame(records)
