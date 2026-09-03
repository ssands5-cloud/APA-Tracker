"""
Exports the same data as ui.export_excel, as one JSON document instead of a
workbook -- for anything that wants to render the tracker's state rather
than open it in Excel (the demo dashboard, in particular).

Deliberately mirrors export_excel's two derived sheets (Standings, Player
Stats) plus the two things a workbook has no natural home for: the team
list and the match list, both needed for a page with team/match navigation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from analytics.player_stats import summarize_player
from database.queries import all_matches, all_players, all_teams, latest_standings, player_match_history

logger = logging.getLogger(__name__)


def export_to_json(db: Session, config: dict) -> str:
    output_path = Path(config["export"]["json_output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "teams": _teams(db),
        "matches": _matches(db),
        "standings": _standings(db),
        "player_stats": _player_stats(db),
    }

    output_path.write_text(json.dumps(document, indent=2, default=str), encoding="utf-8")
    logger.info("Exported JSON document to %s", output_path)
    return str(output_path)


def _teams(db: Session) -> list[dict]:
    return [{"team_id": t.external_id, "team_name": t.name} for t in all_teams(db)]


def _matches(db: Session) -> list[dict]:
    return [
        {
            "match_id": m.external_id,
            "week": m.week,
            "home_team_id": m.home_team_id,
            "home_team_name": m.home_team_name,
            "away_team_id": m.away_team_id,
            "away_team_name": m.away_team_name,
            "home_score": m.home_score,
            "away_score": m.away_score,
            "status": m.status,
            "match_date": m.match_date,
            "is_bye": bool(m.is_bye),
            "is_scored": bool(m.is_scored),
            "is_finalized": bool(m.is_finalized),
        }
        for m in all_matches(db)
    ]


def _standings(db: Session) -> list[dict]:
    return [
        {
            "rank": r.rank,
            "team_name": r.team_name,
            "wins": r.wins,
            "losses": r.losses,
            "points": r.points,
            "captured_at": r.captured_at,
        }
        for r in latest_standings(db)
    ]


def _player_stats(db: Session) -> list[dict]:
    """Same source-of-truth logic as export_excel._player_stats_dataframe --
    history wins where present, roster totals otherwise, "Source" says which.
    Kept in sync deliberately; if these two ever need to diverge, that's a
    sign the shared logic belongs in analytics.player_stats instead.
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
                "player": stat.player_name,
                "skill_level": player.skill_level,
                "matches": played,
                "wins": wins,
                "losses": losses,
                "win_pct": win_pct,
                "ppm": player.ppm,
                "pa": player.pa,
                "avg_points": stat.avg_points,
                "source": source,
            }
        )
    return records
