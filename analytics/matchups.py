"""
Matchup Advantage Engine: turns a player's raw head-to-head history against
one opponent (database.queries.head_to_head_history /
database.queries.all_head_to_head, sourced from
scraper.graphql_scraper.head_to_head_rows) into a win rate, per-opponent
context, a confidence_score, and a 0-100 matchup_score.

`rows` MUST already be in chronological order, oldest first -- same
requirement as analytics.skill_level_trends -- since recency weighting
doesn't re-sort. database.queries.head_to_head_history/all_head_to_head
both guarantee that order (by Match.match_date, falling back to insertion
order when a date is missing or tied).

The trend/volatility inputs come from analytics.skill_level_trends, over
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
_TREND_STABILITY = {"stable": 100, "up": 70, "down": 70}

FULL_CONFIDENCE_GAMES = 10
"""Games against one specific opponent at which sample-size weighting
stops damping the score -- a heuristic choice (a captain rarely faces the
same specific opponent this many times in a season), not a statistically
fitted threshold. See sample_size_weight()."""


def head_to_head_win_rate(rows: list[PlayerHeadToHead]) -> float:
    """Fraction of games won against this specific opponent, unweighted --
    the real, simple record (this is what the exported "Win Rate" column
    shows). 0.0 for no history -- not None -- since an empty record is a
    real, reportable 0-0, not a missing value. See weighted_win_rate() for
    the recency-weighted version matchup_score actually uses."""
    if not rows:
        return 0.0
    wins = sum(1 for r in rows if (r.result or "").strip().upper() == "W")
    return round(wins / len(rows), 3)


def _recency_weights(n: int) -> list[float]:
    """Linear ramp, 0.7 (oldest) to 1.3 (most recent) -- "slightly more"
    influence for recent games, not a dominant one. A single game's weight
    doesn't matter (there's only one to weigh), so n<=1 gets a flat 1.0."""
    if n <= 1:
        return [1.0] * n
    return [0.7 + 0.6 * (i / (n - 1)) for i in range(n)]


def weighted_win_rate(rows: list[PlayerHeadToHead]) -> float:
    """Recency-weighted win rate: a win/loss from a more recent game counts
    slightly more than an older one. Requires `rows` in chronological
    order (oldest first) -- see this module's docstring."""
    if not rows:
        return 0.0
    weights = _recency_weights(len(rows))
    wins = [1.0 if (r.result or "").strip().upper() == "W" else 0.0 for r in rows]
    total_weight = sum(weights)
    if not total_weight:
        return 0.0
    return round(sum(w * x for w, x in zip(weights, wins)) / total_weight, 3)


def average_points_earned(rows: list[PlayerHeadToHead]) -> Optional[float]:
    """None (not 0.0) when no row carries a points value -- a real 0 must
    stay distinguishable from "we don't know"."""
    points = [r.points_earned for r in rows if r.points_earned is not None]
    return round(sum(points) / len(points), 2) if points else None


def average_opponent_skill_level(rows: list[PlayerHeadToHead]) -> Optional[float]:
    """Descriptive context, shown next to the score -- see
    opponent_skill_modifier() for how (a subset of) this same information
    also feeds into the score itself."""
    levels = [r.opponent_skill_level for r in rows if r.opponent_skill_level is not None]
    return round(sum(levels) / len(levels), 2) if levels else None


def opponent_skill_modifier(rows: list[PlayerHeadToHead]) -> float:
    """Bonus for wins that came against higher-skill-level opponents (and a
    matching penalty for wins that came against lower-skill-level
    opponents), averaged over WON games only -- a loss's skill context
    isn't weighted here; there's no evidence base yet for how a loss to a
    much stronger opponent should compare to one against an even opponent,
    so this stays scoped to what was actually asked for. 2 points per
    skill-level of average gap on wins, capped at +/-10 so one lopsided
    pairing can't dominate the score on its own.

    This was deliberately left OUT of the original version: APA's own
    point-per-skill-level handicap already compensates for a gap in the
    scoring itself, and folding it in a second time risks double-counting
    that correction. It's included now on explicit direction -- that
    tradeoff is a product decision about how a captain wants the tool
    weighted, not a data question, and real per-opponent skill level data
    was already being collected either way.
    """
    win_gaps = [
        r.opponent_skill_level - r.own_skill_level
        for r in rows
        if (r.result or "").strip().upper() == "W"
        and r.opponent_skill_level is not None
        and r.own_skill_level is not None
    ]
    if not win_gaps:
        return 0.0
    avg_gap = sum(win_gaps) / len(win_gaps)
    return max(-10.0, min(10.0, avg_gap * 2))


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


def sample_size_weight(n: int) -> float:
    """0.0 for no games, ramping linearly to 1.0 at FULL_CONFIDENCE_GAMES
    -- how much of the win-rate/opponent-skill swing to actually apply to
    matchup_score. This is what stops a 1-0 record scoring the same as a
    10-0 one: at n=1 only 1/FULL_CONFIDENCE_GAMES of that swing counts."""
    return min(n / FULL_CONFIDENCE_GAMES, 1.0)


def confidence_score(rows: list[PlayerHeadToHead], trend: str, volatility: int) -> int:
    """0-100: how much to trust matchup_score, from three independently
    documented components, averaged:

    - sample size: sample_size_weight(n) * 100 -- 0 games is 0 confidence,
      FULL_CONFIDENCE_GAMES+ games is full confidence.
    - volatility: 100 minus 15 per real skill-level change (the same per-
      change cost volatility_penalty charges the score itself), floored at 0.
    - trend stability: "stable" is trusted most (100); a trend actively
      moving -- "up" or "down" -- means the player's true current level is
      a moving target, not a settled one (70); "no data" is a genuine
      unknown, not a settled-and-trusted state, so it lands in between (50).
    """
    n = len(rows)
    sample_component = sample_size_weight(n) * 100
    volatility_component = max(0, 100 - volatility * 15)
    stability_component = _TREND_STABILITY.get(trend, 50)
    return int(round((sample_component + volatility_component + stability_component) / 3))


def matchup_score(rows: list[PlayerHeadToHead], trend: str, volatility: int) -> int:
    """0-100. The win-rate/opponent-skill swing (recency-weighted, per
    weighted_win_rate() and opponent_skill_modifier()) is scaled by
    sample_size_weight() before being added to the 50-point baseline --
    a small sample pulls the score toward neutral rather than swinging it
    fully. The player's own current trend and volatility are NOT scaled by
    this pairing's sample size: they describe the player's present form in
    general, not something this specific opponent's game count should
    dilute.

    50 (neutral, not a guess at "good" or "bad") for a pair with no head-
    to-head history at all -- there's nothing yet to score. See
    confidence_score() for how much to trust the result, and
    docs/matchups.md for the full formula and its limitations.
    """
    if not rows:
        return 50
    weight = sample_size_weight(len(rows))
    win_rate_swing = (weighted_win_rate(rows) - 0.5) * 80
    skill_swing = opponent_skill_modifier(rows)
    score = 50 + weight * (win_rate_swing + skill_swing) + trend_modifier(trend) - volatility_penalty(volatility)
    return int(round(max(0, min(100, score))))
