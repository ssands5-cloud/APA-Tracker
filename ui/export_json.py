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
from analytics.skill_level_trends import skill_level_changes, skill_level_trend, skill_level_volatility
from database.queries import (
    all_matches,
    all_players,
    all_teams,
    career_stats,
    latest_standings,
    match_scores,
    matchups_with_neutral_fill,
    player_match_history,
    skill_level_history,
    team_history,
)

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
        "match_scores": _match_scores(db),
        "career_stats": _career_stats(db),
        "team_history": _team_history(db),
        "skill_level_history": _skill_level_history(db),
        "skill_level_summary": _skill_level_summary(db),
        "matchups": _matchups(db),
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
            "points": r.points,
            "captured_at": r.captured_at,
        }
        for r in latest_standings(db)
    ]


def _match_scores(db: Session) -> dict[str, list[dict]]:
    """Per-match scoresheets, keyed by the match's external id (the same
    id used in the `matches` list above) so a client can look up
    `match_scores[match.match_id]` directly instead of joining on the
    database's internal primary key, which it never sees.
    """
    document: dict[str, list[dict]] = {}
    for row in match_scores(db):
        if row.match is None:
            continue  # orphaned row; _resolve_match_pk should prevent this, but don't crash the export over it
        document.setdefault(row.match.external_id, []).append(
            {
                "player": row.player.name if row.player else "",
                "team_name": row.team_name,
                "skill_level": row.skill_level,
                "result": row.result,
                "points_earned": row.points_earned,
            }
        )
    return document


def _career_stats(db: Session) -> list[dict]:
    """Lifetime stats per (player, format) -- HANDOFF.md item 2, from
    getEightBallStats. Keyed loosely (a flat list, not grouped by player)
    since a player only ever has 1-2 rows (EIGHT and/or NINE)."""
    return [
        {
            "player": row.player.name if row.player else "",
            "format": row.format,
            "matches_won": row.matches_won,
            "matches_played": row.matches_played,
            "cla": row.cla,
            "defensive_shot_avg": row.defensive_shot_avg,
            "match_count_last_two_yrs": row.match_count_last_two_yrs,
            "last_played": row.last_played,
            "on_break_count": row.on_break_count,
            "break_and_runs": row.break_and_runs,
            "mini_slams": row.mini_slams,
            "rackless": row.rackless,
            "skunks": row.skunks,
        }
        for row in career_stats(db)
    ]


def _team_history(db: Session) -> list[dict]:
    """Cross-season team history -- HANDOFF.md item 2, from TeamStat."""
    return [
        {
            "player": row.player.name if row.player else "",
            "is_current": bool(row.is_current),
            "team_name": row.team_name,
            "division_id": row.division_id,
            "is_tournament": bool(row.is_tournament),
            "session_name": row.session_name,
            "nick_name": row.nick_name,
            "skill_level": row.skill_level,
            "rank": row.rank,
            "matches_won": row.matches_won,
            "matches_played": row.matches_played,
        }
        for row in team_history(db)
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
                "team": player.team.name if player.team else "",
                "skill_level": player.skill_level,
                "matches": played,
                "wins": wins,
                "losses": losses,
                "win_pct": win_pct,
                "ppm": player.ppm,
                "pa": player.pa,
                "avg_points": stat.avg_points,
                "total_eight_on_breaks": stat.total_eight_on_breaks,
                "total_eight_break_and_runs": stat.total_eight_break_and_runs,
                "total_nine_on_snaps": stat.total_nine_on_snaps,
                "total_nine_break_and_runs": stat.total_nine_break_and_runs,
                "source": source,
            }
        )
    return records


def _skill_level_history(db: Session) -> list[dict]:
    """Same source as export_excel._skill_level_history_dataframe -- one row
    per match-linked PlayerMatch that carries a skill level, so the demo can
    chart a player's skill level over the season instead of only showing
    the current snapshot."""
    return [
        {
            "player": row.player.name if row.player else "",
            "player_id": row.player.external_id if row.player else "",
            "week": row.match.week if row.match else None,
            "skill_level": row.skill_level,
            "match_date": row.match_date,
            "source": "scoresheet" if row.result is not None else "roster",
        }
        for row in skill_level_history(db)
    ]


def _skill_level_summary(db: Session) -> list[dict]:
    """One row per player with at least one skill_level reading: current
    level, trend (analytics.skill_level_trends), volatility, and the most
    recent change if there's been one. Grouped by Player.id (not name) --
    two Player rows sharing a display name (see ui/export_excel.py's Team
    column note) must not have their readings merged into one trend line.
    """
    by_player: dict[int, list] = {}
    for row in skill_level_history(db):
        by_player.setdefault(row.player_id, []).append(row)

    summaries = []
    for matches in by_player.values():
        player = matches[0].player
        changes = skill_level_changes(matches)
        last_change = changes[-1] if changes else None
        last_change_text = None
        if last_change:
            last_change_text = f"SL {last_change.from_level} → SL {last_change.to_level}"
            if last_change.week is not None:
                last_change_text += f" in Week {last_change.week}"

        summaries.append(
            {
                "player": player.name if player else "",
                "player_id": player.external_id if player else "",
                "current_skill_level": matches[-1].skill_level,
                "trend": skill_level_trend(matches),
                "volatility": skill_level_volatility(matches),
                "last_change": last_change_text,
            }
        )
    return summaries


def _matchups(db: Session) -> list[dict]:
    """Same source as export_excel._matchups_dataframe -- one row per
    (player, opponent) from the Matchup Advantage Engine
    (analytics.matchups / scripts/build_matchups.py), plus a neutral-50
    "has_history": false row for every known pair with no computed matchup
    yet (P1-8) -- database.queries.matchups_with_neutral_fill already
    returns exactly this shape, so nothing to remap here."""
    return matchups_with_neutral_fill(db)
