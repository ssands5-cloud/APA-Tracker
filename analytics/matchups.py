"""
Matchup Advantage Engine: turns a player's raw head-to-head history against
one opponent (database.queries.head_to_head_history /
database.queries.all_head_to_head, sourced from
scraper.graphql_scraper.head_to_head_rows) into a win rate, per-opponent
context, and a 0-100 matchup_score.

The trend/volatility modifiers come from analytics.skill_level_trends, over
the PLAYER's own skill level history (database.queries.skill_level_history)
-- not the opponent's, and not specific to this matchup. It's "is this
player trending up or down right now", the same signal the Skill Level tab
already shows, folded in here so a captain sees it alongside the matchup
rather than as a misleadingly matchup-specific number.
"""

from __future__ import annotations

from typing import Optional

from database.models import PlayerHeadToHead

_TREND_MODIFIER = {"up": 5, "down": -5}


def head_to_head_win_rate(rows: list[PlayerHeadToHead]) -> float:
    """Fraction of games won against this specific opponent. 0.0 for no
    history -- not None -- since an empty record is a real, reportable 0-0,
    not a missing value."""
    if not rows:
        return 0.0
    wins = sum(1 for r in rows if (r.result or "").strip().upper() == "W")
    return round(wins / len(rows), 3)


def average_points_earned(rows: list[PlayerHeadToHead]) -> Optional[float]:
    """None (not 0.0) when no row carries a points value -- a real 0 must
    stay distinguishable from "we don't know"."""
    points = [r.points_earned for r in rows if r.points_earned is not None]
    return round(sum(points) / len(points), 2) if points else None


def average_opponent_skill_level(rows: list[PlayerHeadToHead]) -> Optional[float]:
    """Context for the captain's own judgment -- see matchup_score's
    docstring for why this isn't folded into the score itself."""
    levels = [r.opponent_skill_level for r in rows if r.opponent_skill_level is not None]
    return round(sum(levels) / len(levels), 2) if levels else None


def trend_modifier(trend: str) -> int:
    """+5 trending up, -5 trending down, 0 for "stable" or "no data" --
    see analytics.skill_level_trends.skill_level_trend for what produces
    `trend`."""
    return _TREND_MODIFIER.get(trend, 0)


def volatility_penalty(volatility: int) -> int:
    """3 points per real skill-level change, capped at 15 so one wildly
    volatile player doesn't single-handedly zero out the score. See
    analytics.skill_level_trends.skill_level_volatility."""
    return min(volatility * 3, 15)


def matchup_score(rows: list[PlayerHeadToHead], trend: str, volatility: int) -> int:
    """0-100. Win rate does most of the work (a 50-point baseline, +/-40
    swing across an 0%-100% record); the player's own current trend and
    volatility nudge it a further +/-5 / -15.

    Deliberately NOT weighted by average_opponent_skill_level: APA's own
    point-per-skill-level handicap already compensates for a skill gap in
    the scoring itself, and baking in a second, unverified adjustment here
    risked double-counting a correction the league already makes.
    average_opponent_skill_level is reported alongside the score as
    context, not folded into it.

    50 (neutral, not a guess at "good" or "bad") for a pair with no head-
    to-head history at all -- there's nothing yet to score.
    """
    if not rows:
        return 50
    win_rate = head_to_head_win_rate(rows)
    score = 50 + (win_rate - 0.5) * 80 + trend_modifier(trend) - volatility_penalty(volatility)
    return int(round(max(0, min(100, score))))
