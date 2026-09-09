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

from analytics.close_match_performance import close_match_band, close_match_performance
from analytics.lineup_legality import (
    LINEUP_LEGALITY_SOURCE_URL,
    LINEUP_SIZE,
    TEAM_SKILL_LEVEL_LIMIT_4,
    TEAM_SKILL_LEVEL_LIMIT_5,
    check_lineup_legality,
)
from analytics.player_stats import summarize_player
from analytics.player_trends import trend_score
from analytics.skill_level_trends import skill_level_changes, skill_level_trend, skill_level_volatility
from database.models import Team
from database.queries import (
    all_head_to_head,
    all_matches,
    all_players,
    all_teams,
    career_stats,
    latest_standings,
    match_scores,
    matchups_with_neutral_fill,
    player_match_history,
    player_trends,
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
        "player_trends": _player_trends(db),
        "close_match_stats": _close_match_stats(db),
        "team_roster": _team_roster(db, config),
        "opponent_rosters": _opponent_rosters(db, config),
        "schedule": _schedule(db, config),
        "lineup_legality_rule": _lineup_legality_rule(),
        "lineup_legality": _lineup_legality(db),
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


def _player_trends(db: Session) -> list[dict]:
    """The Player Trend Analyzer's real, already-computed rows (nothing
    recomputed except trend_score, itself a pure function of two of this
    row's own real fields -- see analytics.player_trends.trend_score),
    plus trend_score itself. Previously not exported here at all -- the
    demo tab reads player_trends straight from the database instead; this
    brings the JSON export in line with what the Excel sheet and the tab
    already show.
    """
    rows = []
    for row in player_trends(db):
        rows.append({
            "player": row.player.name if row.player else "",
            "format": row.format,
            "session_name": row.session_name,
            "sample_size": row.sample_size,
            "current_skill_level": row.current_skill_level,
            "regression_slope": row.regression_slope,
            "volatility": row.volatility,
            "sl_stability": row.sl_stability,
            "hot_cold_flag": row.hot_cold_flag,
            "projected_sl_change_probability": row.projected_sl_change_probability,
            "trend_score": trend_score(row.regression_slope, row.volatility, row.sample_size),
        })
    return rows


def _close_match_stats(db: Session) -> list[dict]:
    """Close-Match Win Rate -- docs/planned_analytics_design.md. One row
    per player with at least one real PlayerHeadToHead game (same
    population, same shape, as ui.export_excel's Close_Match_Stats sheet
    -- close_match_band is the SAME shared function, so the two can never
    disagree about a player's band). Sorted by name for a deterministic
    row order.
    """
    from collections import defaultdict

    rows_by_player: dict[int, list] = defaultdict(list)
    for row in all_head_to_head(db):
        if row.player_id is not None:
            rows_by_player[row.player_id].append(row)

    records = []
    for rows in rows_by_player.values():
        player = rows[0].player
        result = close_match_performance(rows)
        records.append({
            "player": player.name if player else "",
            "overall_matches_played": result.overall_matches_played,
            "overall_win_rate": result.overall_win_rate,
            "close_matches_played": result.close_matches_played,
            "close_games_played": result.close_games_played,
            "close_win_rate": result.close_win_rate,
            "shrunk_win_rate": result.shrunk_win_rate,
            "close_match_band": close_match_band(result.shrunk_win_rate, result.overall_win_rate),
        })
    return sorted(records, key=lambda r: r["player"])


def _configured_team_id(config: dict) -> str:
    """The real, already-configured 'your team' id (apa_config.yaml's
    team.team_id) -- not a fabricated concept. Verified against the real
    database before this was built: the shipped config's team_id
    (13082948) resolves to a genuine Team row this project's own account
    actually plays on. Blank if unconfigured -- never a guessed default."""
    return str((config.get("team") or {}).get("team_id") or "")


def _match_scoped_team_ids(db: Session) -> dict[tuple[int, int], str]:
    """(player_id, match_id) -> the real team external_id that player was
    actually on IN THAT MATCH -- PlayerMatch.team_id, captured directly
    from that match's own roster/scoresheet (ingest_match_roster /
    ingest_match_scores), never Player.team_id.

    Player.team_id is a single "first real team ever seen, never updated"
    label (see ingest.backfill_player_team's own docstring for why it
    can't move once set) -- fine as a rough default elsewhere, but wrong
    for a real player who has since played matches for a DIFFERENT real
    team: every one of that player's later matches would misreport their
    old team forever. PlayerMatch.team_id has no such problem -- it's
    recorded fresh, per match, from that match's own real roster/scoresheet.

    Built from database.queries.match_scores() -- the same real "every
    PlayerMatch row tied to a specific match" population _match_scores()
    above already exports -- so this never introduces a second notion of
    what counts as a match-linked PlayerMatch row.
    """
    lookup: dict[tuple[int, int], str] = {}
    for pm in match_scores(db):
        if pm.team_id and pm.player_id is not None and pm.match_id is not None:
            lookup[(pm.player_id, pm.match_id)] = pm.team_id
    return lookup


def _roster_rows_from_matches(db: Session, team_external_id: str) -> list[dict]:
    """Real players confirmed on this team from match-level evidence only:
    every distinct player with at least one real PlayerMatch row whose own
    team_id (captured per match, from that match's own roster/scoresheet)
    equals this team's real external id -- NOT Team.players / Player.team_id
    (see _match_scoped_team_ids's docstring for why that label is wrong for
    a player who has since moved to a different real team: they'd still
    show up on their OLD team's roster forever, and never on their new
    one).

    skill_level comes from that same PlayerMatch row (that team's own real
    scoresheet/roster entry), not Player.skill_level -- Player.skill_level
    is only ever set by a roster ingest (upsert_roster), and the majority
    of real players here are never rostered at all, only ever seen via a
    scoresheet (see backfill_player_team's own docstring: "72 of 72
    distinct head-to-head players" had no roster ingest) -- Player.skill_level
    would be None for them forever. match_scores() is ordered by
    (match_id, id), so the LAST row per player here is that player's most
    recently ingested real entry for this team; ties/out-of-order backfills
    aren't otherwise resolved, since PlayerMatch carries no real
    chronological field to break them with (match_date is delivered text
    of inconsistent format -- see Match's own docstring).
    """
    latest_by_player = {}
    for pm in match_scores(db):
        if pm.team_id == team_external_id and pm.player_id is not None and pm.player is not None:
            latest_by_player[pm.player_id] = pm
    rows = [
        {"player": pm.player.name, "player_id": pm.player.external_id, "skill_level": pm.skill_level}
        for pm in latest_by_player.values()
    ]
    return sorted(rows, key=lambda r: r["player"])


def _team_roster(db: Session, config: dict) -> list[dict]:
    """The configured team's real roster only, from match-level evidence
    (see _roster_rows_from_matches) -- empty, not guessed, when no team is
    configured or it matches no real Team row.
    """
    team_id = _configured_team_id(config)
    if not team_id:
        return []
    if db.query(Team).filter_by(external_id=team_id).one_or_none() is None:
        return []
    return _roster_rows_from_matches(db, team_id)


def _schedule(db: Session, config: dict) -> list[dict]:
    """Real schedule rows for the configured team only: week, date,
    opponent team, your player, opponent player, both real skill levels,
    result, and the real match margin -- from Match + PlayerHeadToHead,
    the same real sources Close_Match_Stats and Matchups already use.

    Deliberately OMITS racks, notes, a "clutch" flag, and a "break/run"
    flag: none of these are real fields anywhere in this project's
    captured data (see docs/close_match_performance.md and
    docs/head_to_head.md's "Unavailable APA Fields"). Margin IS real and
    included, since it's already used for close-match detection elsewhere
    (analytics.close_match_performance.is_close_match).

    Empty when no team is configured, or it matches no real Team row --
    "your schedule" has no meaning without a real "you".

    Which side of a head-to-head row belongs to the configured team is
    resolved MATCH BY MATCH, from real PlayerMatch.team_id evidence for
    that exact (player, match) pair -- never from Player.team_id, a
    single "first real team ever seen, never updated" label that gets a
    real multi-team player's later matches wrong (see
    _match_scoped_team_ids's docstring). A head-to-head row with no
    matching PlayerMatch evidence for that match is excluded, not
    guessed at.
    """
    team_external_id = _configured_team_id(config)
    if not team_external_id:
        return []
    if db.query(Team).filter_by(external_id=team_external_id).one_or_none() is None:
        return []

    match_team_ids = _match_scoped_team_ids(db)
    rows = []
    for row in all_head_to_head(db):
        if row.player_id is None or row.match_id is None:
            continue
        if match_team_ids.get((row.player_id, row.match_id)) != team_external_id:
            continue
        match = row.match
        if match is None:
            continue
        if match.home_team_id == team_external_id:
            opponent_team_name = match.away_team_name
        elif match.away_team_id == team_external_id:
            opponent_team_name = match.home_team_name
        else:
            opponent_team_name = None
        margin = None
        if match.home_score is not None and match.away_score is not None:
            margin = abs(match.home_score - match.away_score)
        rows.append({
            "week": match.week,
            "date": match.match_date,
            "opponent_team": opponent_team_name,
            "your_player": row.player.name if row.player else "",
            "your_player_sl": row.own_skill_level,
            "opponent_player": row.opponent.name if row.opponent else "",
            "opponent_player_sl": row.opponent_skill_level,
            "result": row.result,
            "match_margin": margin,
        })
    return sorted(rows, key=lambda r: (r["week"] or 0, r["your_player"] or "", r["opponent_player"] or ""))


def _opponent_rosters(db: Session, config: dict) -> list[dict]:
    """Every OTHER real team's roster, per team -- "opponent" is defined
    relative to the configured team_id, the same real distinction
    _team_roster uses. Each roster is built from the same match-level
    evidence (_roster_rows_from_matches), not Team.players/Player.team_id.
    If no team is configured, every real team is listed here (there is no
    "yours" to exclude), rather than guessing.
    """
    team_id = _configured_team_id(config)
    return [
        {
            "team": team.name,
            "team_id": team.external_id,
            "roster": _roster_rows_from_matches(db, team.external_id),
        }
        for team in all_teams(db)
        if team.external_id != team_id
    ]


def _lineup_legality_rule() -> dict:
    """The real, sourced 23-Rule metadata itself (analytics.lineup_legality)
    -- not a computed check. Exported unconditionally, independent of
    whether any real match has enough evidence for a computed verdict
    (_lineup_legality below), so a consumer always knows what the rule
    actually is."""
    return {
        "lineup_size": LINEUP_SIZE,
        "skill_level_limit_5_player": TEAM_SKILL_LEVEL_LIMIT_5,
        "skill_level_limit_4_player": TEAM_SKILL_LEVEL_LIMIT_4,
        "source": LINEUP_LEGALITY_SOURCE_URL,
    }


def _lineup_legality(db: Session) -> list[dict]:
    """Real, historical lineup-legality checks against the 23-Rule -- one
    row per (match, team) where this project has captured exactly
    LINEUP_SIZE real PlayerMatch rows (a real player id plus a real skill
    level, from that match's own scoresheet/roster) for that team in that
    match.

    These are ACTUAL fielded lineups from already-played matches, checked
    retroactively -- never a hypothetical or invented lineup. There is no
    real "selected upcoming lineup" concept anywhere in this project's
    captured data (see docs/lineup_legality.md); fabricating one to give
    this a bigger row count would violate this project's no-fabrication
    rule. A team match with fewer or more than 5 real player rows captured
    for one side (a forfeit, an incomplete scoresheet, a 4-player fallback)
    has no verdict here, the same as check_lineup_legality's own None case
    -- not guessed at.

    Grouped by (PlayerMatch.match_id, PlayerMatch.team_id) from
    database.queries.match_scores() -- the same real, already-defined
    per-match PlayerMatch population _match_scores()/_match_scoped_team_ids
    above already use.
    """
    by_match_team: dict[tuple[int, str], list] = {}
    for pm in match_scores(db):
        if pm.team_id and pm.match_id is not None:
            by_match_team.setdefault((pm.match_id, pm.team_id), []).append(pm)

    rows = []
    for (_db_match_id, team_external_id), player_matches in by_match_team.items():
        players = [(pm.player_id, pm.skill_level) for pm in player_matches]
        legality = check_lineup_legality(players)
        if legality is None:
            continue

        match = player_matches[0].match
        if match is not None and match.home_team_id == team_external_id:
            team_name = match.home_team_name
        elif match is not None and match.away_team_id == team_external_id:
            team_name = match.away_team_name
        else:
            team_name = player_matches[0].team_name

        rows.append({
            "match_id": match.external_id if match else None,
            "week": match.week if match else None,
            "team_id": team_external_id,
            "team_name": team_name,
            "skill_total": legality.skill_total,
            "limit": legality.limit,
            "is_legal": legality.is_legal,
            "has_duplicate_players": legality.has_duplicate_players,
        })
    return sorted(rows, key=lambda r: (r["week"] or 0, r["team_id"] or "", r["match_id"] or ""))
