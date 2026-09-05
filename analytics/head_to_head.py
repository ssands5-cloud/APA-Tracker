"""Head-to-Head Advantage Engine.

Turns a player's real games against ONE opponent into a record, a
trend-adjusted score, and three forward-looking estimates: the probability
of winning, the expected 8-ball match points, and the expected 9-ball ball
count.

Built entirely on ``PlayerHeadToHead`` rows -- the same rows
``analytics.matchups`` aggregates -- so this engine and the Matchup
Advantage Engine can never disagree about which games happened. Where a
weighting already exists there (``reliability_weight``, ``trend_modifier``,
``matchup_score``) it is reused rather than re-derived: two definitions of
"how much does a 2-game sample count" would drift apart within a session.

**Nothing here is fabricated.** Every input is a real captured field. Two
metrics the original ask wanted are absent because APA does not expose them
at all -- per-opponent innings, and per-opponent defensive shots (only a
lifetime average exists). See docs/head_to_head.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from analytics.matchups import (
    matchup_score,
    recognized_results,
    reliability_weight,
    trend_modifier,
)
from database.models import PlayerHeadToHead

# --- model constants ---------------------------------------------------------

# Log-odds granted per skill level of advantage. APA skill levels run 2-7 and
# the handicap system is explicitly designed so a higher SL must win MORE
# games to earn the same match points -- so a one-level edge is a real but
# moderate advantage, not a rout. 0.40 puts a +1 SL edge at ~60% and a +3 edge
# at ~77% before any head-to-head history is considered.
SL_LOG_ODDS_PER_LEVEL = 0.40

# Laplace smoothing on the observed record, so a 1-0 pairing reads as 67%
# rather than a certainty and a 0-1 reads as 33% rather than impossible.
SMOOTHING_WINS = 1.0
SMOOTHING_GAMES = 2.0

# Probabilities are clamped away from the asymptotes: pool has upsets, and a
# stated 0% or 100% would be a claim the data cannot support.
MIN_WIN_PROBABILITY = 0.02
MAX_WIN_PROBABILITY = 0.98

EIGHT_BALL = "8-Ball"
NINE_BALL = "9-Ball"


@dataclass
class HeadToHeadAdvantage:
    """One (player, opponent, format, session) pairing, fully evaluated."""

    player_id: str
    opponent_id: str
    total_matches: int
    wins: int
    losses: int
    sl_delta: Optional[float]
    trend_modifier: int
    matchup_score: int
    win_probability: Optional[float]
    expected_points: Optional[float]
    expected_balls: Optional[float]
    format: Optional[str]
    session_name: Optional[str]


# --- primitives --------------------------------------------------------------

def win_loss(rows: Sequence[PlayerHeadToHead]) -> tuple[int, int]:
    """(wins, losses) over games with a RECOGNISED result.

    A malformed or missing result is evidence of nothing and is excluded from
    both counts -- the same rule ``analytics.matchups`` applies, so wins +
    losses always equals ``total_matches``.
    """
    recognised = recognized_results(rows)
    wins = sum(1 for row in recognised if (row.result or "").strip().upper() == "W")
    return wins, len(recognised) - wins


def average_skill_level_delta(rows: Sequence[PlayerHeadToHead]) -> Optional[float]:
    """Mean (opponent SL - own SL). Positive means the player has been
    giving up skill level in this pairing.

    None when no game carries both levels -- a pairing with no skill data is
    not a pairing with a zero gap.
    """
    deltas = [
        row.opponent_skill_level - row.own_skill_level
        for row in rows
        if row.own_skill_level is not None and row.opponent_skill_level is not None
    ]
    return round(sum(deltas) / len(deltas), 3) if deltas else None


def skill_level_trend(rows: Sequence[PlayerHeadToHead]) -> str:
    """"up" / "down" / "stable" / "no data" from the player's own skill level
    across this pairing, first reading versus last.

    Mirrors ``analytics.skill_level_trends.skill_level_trend`` -- same
    first-vs-last rule, so a dip that fully recovers reads "stable" -- but
    operates on head-to-head rows, which carry ``own_skill_level`` rather
    than the ``skill_level`` attribute that function expects.
    """
    levels = [row.own_skill_level for row in rows if row.own_skill_level is not None]
    if not levels:
        return "no data"
    if levels[-1] > levels[0]:
        return "up"
    if levels[-1] < levels[0]:
        return "down"
    return "stable"


def _format_of(rows: Sequence[PlayerHeadToHead]) -> Optional[str]:
    for row in rows:
        if row.format:
            return row.format
    return None


def _is_format(rows: Sequence[PlayerHeadToHead], marker: str) -> bool:
    fmt = _format_of(rows) or ""
    return marker.lower() in fmt.lower()


# --- the probabilistic layer -------------------------------------------------

def win_probability(rows: Sequence[PlayerHeadToHead]) -> Optional[float]:
    """Probability the player wins the next game against this opponent.

    A logistic model in log-odds space with two real terms:

        logit(p) = SL_LOG_ODDS_PER_LEVEL * skill_advantage
                 + reliability(n) * logit(smoothed_win_rate)

    * ``skill_advantage`` is the player's mean SL minus the opponent's --
      the negation of ``sl_delta``, which is stored opponent-minus-own.
    * ``smoothed_win_rate`` is Laplace-smoothed, so one game cannot assert
      certainty.
    * ``reliability(n)`` is ``analytics.matchups.reliability_weight`` -- the
      SAME n/(n+3) damping the matchup score already uses. A 1-game record
      contributes a quarter of its log-odds; a 10-game record nearly all of
      it.

    This is a transparent, documented model, **not a fitted one**: no
    training pipeline exists, and pretending otherwise would misrepresent
    where the numbers come from. Its constants are stated above and its
    behaviour is pinned by tests.

    Returns None when there is nothing to go on -- no recognised games and
    no skill levels. A pairing with no evidence has no probability, which is
    different from a 50/50 one.
    """
    recognised = recognized_results(rows)
    delta = average_skill_level_delta(rows)
    if not recognised and delta is None:
        return None

    log_odds = 0.0
    if delta is not None:
        # sl_delta is opponent-minus-own, so the player's advantage is its
        # negation. Getting this backwards would invert every prediction.
        log_odds += SL_LOG_ODDS_PER_LEVEL * (-delta)

    n = len(recognised)
    if n:
        wins, _ = win_loss(rows)
        smoothed = (wins + SMOOTHING_WINS) / (n + SMOOTHING_GAMES)
        log_odds += reliability_weight(n) * math.log(smoothed / (1 - smoothed))

    probability = 1 / (1 + math.exp(-log_odds))
    return round(min(MAX_WIN_PROBABILITY, max(MIN_WIN_PROBABILITY, probability)), 4)


def _expected_value(values: list[float], baseline: Optional[float] = None) -> Optional[float]:
    """Mean of `values`, shrunk toward `baseline` by how little evidence
    there is.

    Without a baseline this is the plain observed mean -- shrinking a value
    toward itself would be arithmetic theatre, so the damping is only applied
    when the caller can supply a genuinely different anchor (the player's own
    average across ALL opponents in this format; see
    scripts/build_head_to_head.py). With one game the estimate sits a quarter
    of the way from the baseline to the observed value, and by ten games it
    is almost entirely the observed value -- the same n/(n+3) reliability
    curve the rest of the engine uses.
    """
    if not values:
        return None
    observed = sum(values) / len(values)
    if baseline is None:
        return round(observed, 3)
    weight = reliability_weight(len(values))
    return round(weight * observed + (1 - weight) * baseline, 3)


def expected_points(rows: Sequence[PlayerHeadToHead],
                    baseline: Optional[float] = None) -> Optional[float]:
    """Expected 8-ball MATCH POINTS. None for a 9-ball pairing -- that
    format has no match-point figure here, and 0.0 would read as "expect
    nothing" rather than "not applicable"."""
    if not _is_format(rows, EIGHT_BALL):
        return None
    values = [row.points_earned for row in rows if row.points_earned is not None]
    return _expected_value(values, baseline)


def expected_balls(rows: Sequence[PlayerHeadToHead],
                   baseline: Optional[float] = None) -> Optional[float]:
    """Expected 9-ball BALL COUNT, from the real ``nineBallPoints`` capture.

    Distinct from ``points_earned``, which on a 9-ball row carries match
    points, not balls. None for an 8-ball pairing, and None when the ball
    count was never captured -- older rows predate that column.
    """
    if not _is_format(rows, NINE_BALL):
        return None
    values = [row.nine_ball_points for row in rows if row.nine_ball_points is not None]
    return _expected_value(values, baseline)


# --- assembly ----------------------------------------------------------------

def evaluate(rows: Sequence[PlayerHeadToHead], player_id: str, opponent_id: str,
             points_baseline: Optional[float] = None,
             balls_baseline: Optional[float] = None) -> HeadToHeadAdvantage:
    """Everything the engine knows about one pairing.

    `rows` must already be one (player, opponent, format, session) group in
    chronological order -- the trend reads first-versus-last and would be
    nonsense on an unordered list.

    The two baselines are the player's own averages across ALL opponents in
    this format; when supplied, a thin pairing is pulled toward the player's
    normal output instead of trusting one night. The builder computes them.
    """
    wins, losses = win_loss(rows)
    trend = skill_level_trend(rows)
    modifier = trend_modifier(trend)

    # Reuse the existing 0-100 score outright. Volatility is passed as 0
    # here: it is a property of a player's whole season, which this
    # pairing-scoped view does not have, and analytics.matchups already
    # treats 0 as "no volatility penalty" rather than as missing data.
    score = matchup_score(list(rows), trend, 0)

    return HeadToHeadAdvantage(
        player_id=player_id,
        opponent_id=opponent_id,
        total_matches=wins + losses,
        wins=wins,
        losses=losses,
        sl_delta=average_skill_level_delta(rows),
        trend_modifier=modifier,
        matchup_score=score,
        win_probability=win_probability(rows),
        expected_points=expected_points(rows, points_baseline),
        expected_balls=expected_balls(rows, balls_baseline),
        format=_format_of(rows),
        session_name=next((r.session_name for r in rows if r.session_name), None),
    )
