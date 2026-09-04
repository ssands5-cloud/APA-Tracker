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


def _is_win(result) -> Optional[bool]:
    """True for a recognized win, False for a recognized loss, None for
    anything else -- a missing value, a blank string, "UNKNOWN", or any
    other value the API might return that isn't W/L. An unrecognized
    result must not silently count as a loss, and must not count as a
    game at all for win-rate or sample-size purposes -- see
    recognized_results().

    PlayerMatch.result / PlayerHeadToHead.result are already normalized to
    exactly "W", "L", or None at ingestion (database.ingest._normalize_result),
    so in practice this only ever sees clean input from real rows -- the
    case-insensitive/whitespace handling here is defense in depth for
    anything constructed directly (tests, a future caller), not a second
    real-world data path.
    """
    normalized = str(result or "").strip().upper()
    if normalized == "W":
        return True
    if normalized == "L":
        return False
    return None


def recognized_results(rows: list[PlayerHeadToHead]) -> list[PlayerHeadToHead]:
    """Rows with a recognized W/L result only. A row with a missing or
    malformed result still exists -- its points_earned or skill-level
    context can still be real -- it just doesn't count as a known outcome,
    so it's excluded here rather than silently read as a loss."""
    return [r for r in rows if _is_win(r.result) is not None]


def head_to_head_win_rate(rows: list[PlayerHeadToHead]) -> float:
    """Fraction of RECOGNIZED-result games won against this specific
    opponent, unweighted -- the real, simple record (this is what the
    exported "Win Rate" column shows). 0.0 when there's no recognized
    result to go on -- either no rows at all, or rows whose result
    couldn't be read -- not None, since an empty record is a real,
    reportable 0-0, not a missing value. See weighted_win_rate() for the
    recency-weighted version matchup_score actually uses.
    """
    recognized = recognized_results(rows)
    if not recognized:
        return 0.0
    wins = sum(1 for r in recognized if _is_win(r.result))
    return round(wins / len(recognized), 3)


_RECENT_WINDOW = 3
_RECENT_BOOST = 1.1  # +10%

def _recency_weights(n: int) -> list[float]:
    """P2 recency bias: a flat baseline weight of 1.0 for every game
    except the most recent 3, which get a flat +10% (1.1x) boost. Replaces
    the earlier linear 0.7x-1.3x ramp across the WHOLE history -- this is
    a smaller, more literal "recent games count slightly more", not a
    scaling effect across every game ever played.

    With 3 or fewer games, every game is within the last 3, so all of
    them get the boost equally -- there's no "older" game left to serve
    as a baseline, so weighting has no differentiating effect until a 4th
    game exists. `rows` must already be in chronological order, oldest
    first, same as before.
    """
    return [_RECENT_BOOST if i >= n - _RECENT_WINDOW else 1.0 for i in range(n)]


def weighted_win_rate(rows: list[PlayerHeadToHead]) -> float:
    """Recency-weighted win rate over RECOGNIZED-result games only: a
    win/loss from a more recent game counts slightly more than an older
    one. A row with an unrecognized result is dropped before weighting --
    it doesn't consume a "recent" slot it has no real outcome to justify.
    Requires `rows` in chronological order (oldest first) -- see this
    module's docstring.
    """
    recognized = recognized_results(rows)
    if not recognized:
        return 0.0
    weights = _recency_weights(len(recognized))
    wins = [1.0 if _is_win(r.result) else 0.0 for r in recognized]
    total_weight = sum(weights)
    if not total_weight:
        return 0.0
    return round(sum(w * x for w, x in zip(weights, wins)) / total_weight, 3)


def average_points_earned(rows: list[PlayerHeadToHead]) -> Optional[float]:
    """None (not 0.0) when no row carries a points value -- a real 0 must
    stay distinguishable from "we don't know"."""
    points = [r.points_earned for r in rows if r.points_earned is not None]
    return round(sum(points) / len(points), 2) if points else None


def average_own_skill_level(rows: list[PlayerHeadToHead]) -> Optional[float]:
    """P2 SL delta context (avg_own_sl): the player's own average skill
    level across ALL games in the pairing, wins and losses alike --
    purely descriptive, alongside average_opponent_skill_level() and
    average_skill_level_delta() below, never folded into matchup_score.
    """
    levels = [r.own_skill_level for r in rows if r.own_skill_level is not None]
    return round(sum(levels) / len(levels), 2) if levels else None


def average_opponent_skill_level(rows: list[PlayerHeadToHead]) -> Optional[float]:
    """Descriptive context, shown next to the score -- see
    opponent_skill_modifier() for how (a subset of) this same information
    also feeds into the score itself.

    This is the P2 directive's "avg_opponent_sl" -- already existed under
    this name from the original engine, so it wasn't renamed; see
    average_own_skill_level() above and average_skill_level_delta() below
    for the sibling P2 fields.
    """
    levels = [r.opponent_skill_level for r in rows if r.opponent_skill_level is not None]
    return round(sum(levels) / len(levels), 2) if levels else None


def average_skill_level_delta(rows: list[PlayerHeadToHead]) -> Optional[float]:
    """P2 SL delta context ("avg_sl_delta" in the directive -- already
    existed under this name from the prior P2 pass): average
    (opponent_skill_level - own_skill_level) across ALL games, wins and
    losses alike -- purely descriptive context, reported alongside
    matchup_score but NOT folded into it.

    Different from opponent_skill_modifier() below: that one only looks at
    WINS (it's rewarding upsets) and IS weighted into matchup_score. This
    answers a different question -- "how has the skill gap looked overall
    in this pairing" -- regardless of who won each game.
    """
    deltas = [
        r.opponent_skill_level - r.own_skill_level
        for r in rows
        if r.opponent_skill_level is not None and r.own_skill_level is not None
    ]
    return round(sum(deltas) / len(deltas), 2) if deltas else None


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
        if _is_win(r.result) is True
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
    -- how much of the opponent-skill swing to actually apply to
    matchup_score, and confidence_score's own sample-size component. This
    is what stops a 1-0 record's skill-swing bonus scoring the same as a
    10-0 one's: at n=1 only 1/FULL_CONFIDENCE_GAMES of that swing counts.

    P2 scoped a separate reliability_weight() (below) to the win-rate
    swing specifically, leaving this one governing the skill swing and
    confidence_score exactly as before -- see reliability_weight's own
    docstring for why the two aren't the same function.
    """
    return min(n / FULL_CONFIDENCE_GAMES, 1.0)


def reliability_weight(n: int) -> float:
    """P2 sample-size weighting: n / (n + 3), applied ONLY to the H2H
    win-rate swing in matchup_score -- a reliability/shrinkage factor
    (the same shape as a Bayesian estimate with a 3-game virtual prior),
    distinct from sample_size_weight() above, which still governs the
    opponent-skill swing and confidence_score's sample component.

    Never reaches 1.0, unlike sample_size_weight's hard cap at
    FULL_CONFIDENCE_GAMES: a win-rate swing is never treated as fully
    certain, however long the record gets, whereas the skill-swing/
    confidence weighting deliberately settles to full trust past a fixed
    threshold. 0.0 for n=0 (no evidence, no swing).
    """
    return n / (n + 3)


def confidence_score(rows: list[PlayerHeadToHead], trend: str, volatility: int) -> int:
    """0-100: how much to trust matchup_score, from three independently
    documented components, averaged:

    - sample size: sample_size_weight(n) * 100 -- 0 RECOGNIZED-result games
      is 0 confidence, FULL_CONFIDENCE_GAMES+ is full confidence. A row
      with a malformed result doesn't count toward n -- it's not evidence
      either way.
    - volatility: 100 minus 15 per real skill-level change (the same per-
      change cost volatility_penalty charges the score itself), floored at 0.
    - trend stability: "stable" is trusted most (100); a trend actively
      moving -- "up" or "down" -- means the player's true current level is
      a moving target, not a settled one (70); "no data" is a genuine
      unknown, not a settled-and-trusted state, so it lands in between (50).
    """
    n = len(recognized_results(rows))
    sample_component = sample_size_weight(n) * 100
    volatility_component = max(0, 100 - volatility * 15)
    stability_component = _TREND_STABILITY.get(trend, 50)
    return int(round((sample_component + volatility_component + stability_component) / 3))


def matchup_score(rows: list[PlayerHeadToHead], trend: str, volatility: int) -> int:
    """0-100. The win-rate swing (recency-weighted, per weighted_win_rate())
    is scaled by reliability_weight() -- P2 -- and the opponent-skill swing
    (per opponent_skill_modifier()) is scaled by sample_size_weight(), each
    before being added to the 50-point baseline: a small sample pulls both
    toward neutral rather than swinging the score fully, but via two
    separately documented factors rather than one shared one (see each
    function's own docstring for why they differ). The player's own
    current trend and volatility are NOT scaled by either factor: they
    describe the player's present form in general, not something this
    specific opponent's game count should dilute.

    50 (neutral, not a guess at "good" or "bad") for a pair with no
    RECOGNIZED-result head-to-head history at all -- either no rows, or
    rows whose result couldn't be read -- there's nothing yet to score.
    See confidence_score() for how much to trust the result, and
    docs/matchups.md for the full formula and its limitations.
    """
    recognized = recognized_results(rows)
    if not recognized:
        return 50
    n = len(recognized)
    reliability = reliability_weight(n)
    weight = sample_size_weight(n)
    win_rate_swing = (weighted_win_rate(rows) - 0.5) * 80
    skill_swing = opponent_skill_modifier(rows)
    score = (
        50
        + reliability * win_rate_swing
        + weight * skill_swing
        + trend_modifier(trend)
        - volatility_penalty(volatility)
    )
    return int(round(max(0, min(100, score))))
