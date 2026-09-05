"""Player Trend Analyzer.

How a player has been performing lately, per format: average points, how
much those points swing, which direction they are heading, how settled their
skill level is, and a documented heuristic for how likely the league is to
re-rate them.

Every input is real captured data -- ``PlayerMatch.points_earned`` and
``.skill_level``, with format from the joined ``Match``. Nothing is
synthesised. There are no innings and no defensive-shot figures anywhere in
this project (APA does not expose them; see docs/data-fields.md), and none
are invented here either.

The honest-gap rule applies throughout: a figure that needs more evidence
than exists returns ``None`` rather than a default. A single match has no
spread, which is a different fact from zero spread, and a "trend" through
two points is a line through noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

# The rolling window. Matches beyond the most recent 20 in a format do not
# influence "lately" -- a player who was cold in the spring and hot since
# should read hot.
WINDOW_SIZE = 20

# A slope needs at least three points to distinguish a trend from a pair of
# results. Two points always fit a line perfectly, which would report a
# confident trend from a single win followed by a single loss.
MIN_MATCHES_FOR_TREND = 3

# Two readings is the minimum for any spread at all.
MIN_MATCHES_FOR_SPREAD = 2

# Full-scale for trend_strength, PER FORMAT. The two formats score on
# completely different scales -- 8-ball match points run 0-3, 9-ball 0-20 --
# so a single constant cannot serve both. Calibrated at roughly a third of
# each format's range per match: a climb that steep cannot continue for long,
# which makes it a sensible ceiling rather than an arbitrary one.
#
# Getting this wrong is not cosmetic. With a flat 1.0, every 9-ball slope
# above one point per match clamped to 1.0, so a +1.4 and a +10.0 both read
# "maximally strong" and the column lost all discrimination in that format.
TREND_SLOPE_FULL_SCALE = {
    "8-ball": 1.0,
    "9-ball": 6.0,
}
DEFAULT_SLOPE_FULL_SCALE = 1.0


def slope_full_scale(format_: Optional[str]) -> float:
    """The full-scale slope for a format, matched case-insensitively on the
    format name. Falls back to the 8-ball scale for an unrecognised format --
    the conservative choice, since it saturates sooner and so understates
    rather than overstates a trend."""
    name = (format_ or "").lower()
    for marker, scale in TREND_SLOPE_FULL_SCALE.items():
        if marker in name:
            return scale
    return DEFAULT_SLOPE_FULL_SCALE

# Hot/cold needs enough history to mean something. Below this the player is
# left unflagged rather than sorted into a quartile on one result.
MIN_MATCHES_FOR_FLAG = 3

# --- projected SL change heuristic -------------------------------------------
# Both weights apply to real, observed quantities: how often this player's
# skill level has ALREADY moved, and how hard their current form is pushing.
# Neither is a league projection and neither is fitted -- see
# docs/player_trends.md.
SL_HISTORY_WEIGHT = 0.7
FORM_PRESSURE_WEIGHT = 0.3


@dataclass
class PlayerTrendResult:
    """One (player, format) window, fully evaluated."""

    player_id: str
    format: Optional[str]
    matches_considered: int
    avg_points_last_20: Optional[float]
    volatility_last_20: Optional[float]
    trend_slope: Optional[float]
    trend_strength: Optional[float]
    sl_stability: Optional[float]
    hot_cold_flag: Optional[str]
    projected_sl_change_probability: Optional[float]


def rolling_window(values: Sequence, size: int = WINDOW_SIZE) -> list:
    """The most recent `size` entries, oldest first.

    `values` must already be in chronological order; this slices, it does not
    sort, so an unordered caller gets an unordered window.
    """
    return list(values[-size:]) if size else list(values)


def average(values: Sequence[float]) -> Optional[float]:
    """Mean, or None for an empty series."""
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 3) if clean else None


def volatility(values: Sequence[float]) -> Optional[float]:
    """Population standard deviation of the series.

    Population rather than sample: this describes the window actually played,
    not an estimate of some wider distribution the player is drawn from.

    None below two readings -- one match has no spread, and reporting 0.0
    would claim perfect consistency from a single data point.
    """
    clean = [v for v in values if v is not None]
    if len(clean) < MIN_MATCHES_FOR_SPREAD:
        return None
    mean = sum(clean) / len(clean)
    return round(math.sqrt(sum((v - mean) ** 2 for v in clean) / len(clean)), 3)


def trend_slope(values: Sequence[float]) -> Optional[float]:
    """Least-squares slope of `values` against match order, in points per
    match. Positive means improving.

    Ordinary least squares over x = 0, 1, 2 ... n-1:

        slope = Σ((x - x̄)(y - ȳ)) / Σ((x - x̄)²)

    None below MIN_MATCHES_FOR_TREND, and None when every x is identical
    (a zero denominator), which cannot happen for a real window but would
    otherwise be a divide-by-zero waiting for a caller to find.
    """
    clean = [v for v in values if v is not None]
    if len(clean) < MIN_MATCHES_FOR_TREND:
        return None

    n = len(clean)
    mean_x = (n - 1) / 2
    mean_y = sum(clean) / n
    denominator = sum((x - mean_x) ** 2 for x in range(n))
    if denominator == 0:
        return None
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in enumerate(clean))
    return round(numerator / denominator, 4)


def trend_strength(slope: Optional[float],
                   format_: Optional[str] = None) -> Optional[float]:
    """|slope| normalised to 0.0-1.0 against the FORMAT's full scale.

    Direction is already carried by the slope's sign; strength answers only
    "how steeply", so a steep decline and a steep climb both read 1.0.
    Clamped, so an implausible slope cannot report above full scale.

    `format_` selects the scale -- see slope_full_scale. Omitting it uses the
    8-ball scale, which saturates sooner and therefore understates a 9-ball
    trend rather than overstating it.
    """
    if slope is None:
        return None
    return round(min(1.0, abs(slope) / slope_full_scale(format_)), 4)


def sl_stability(levels: Sequence[Optional[int]]) -> Optional[float]:
    """VARIANCE of skill level across the window.

    0.0 means the level never moved; higher means less settled. Stored as the
    raw variance rather than inverted into a 0-1 "stability score" so the
    number keeps its units and can be reasoned about directly.

    None below two readings, for the same reason as `volatility`.
    """
    clean = [level for level in levels if level is not None]
    if len(clean) < MIN_MATCHES_FOR_SPREAD:
        return None
    mean = sum(clean) / len(clean)
    return round(sum((level - mean) ** 2 for level in clean) / len(clean), 4)


def skill_level_changes(levels: Sequence[Optional[int]]) -> int:
    """How many times the skill level actually moved between readings."""
    clean = [level for level in levels if level is not None]
    return sum(1 for a, b in zip(clean, clean[1:]) if a != b)


def projected_sl_change_probability(levels: Sequence[Optional[int]],
                                    slope: Optional[float],
                                    format_: Optional[str] = None) -> Optional[float]:
    """Heuristic 0.0-1.0: how likely this player's skill level is to move.

    Two real, observed terms -- no league model, no fitted coefficients, and
    no claim to predict APA's actual re-rating decisions:

        p = SL_HISTORY_WEIGHT * observed_change_rate
          + FORM_PRESSURE_WEIGHT * trend_strength(slope)

    * ``observed_change_rate`` is how often this player's level HAS already
      moved: changes divided by the transitions available (readings - 1). A
      player re-rated twice in four matches is visibly in motion; one who has
      sat at the same level all season is not.
    * ``trend_strength(slope)`` is current form pressure. APA re-rates on
      performance, so a player climbing steeply is under more pressure to
      move than one holding steady -- but form is the weaker signal, because
      plenty of hot streaks end without a re-rate.

    Returns None when there are fewer than two skill-level readings: with no
    transition to observe, the first term does not exist, and reporting form
    alone would dress one number up as two.

    This is a documented heuristic, deliberately simple and stated in full so
    it can be argued with. It is not a fitted model, and it must not be
    presented as APA's own projection.
    """
    clean = [level for level in levels if level is not None]
    transitions = len(clean) - 1
    if transitions < 1:
        return None

    observed_change_rate = skill_level_changes(clean) / transitions
    form_pressure = trend_strength(slope, format_) or 0.0

    probability = (SL_HISTORY_WEIGHT * observed_change_rate
                   + FORM_PRESSURE_WEIGHT * form_pressure)
    return round(min(1.0, max(0.0, probability)), 4)


def hot_cold_flag(slope: Optional[float], matches: int,
                  hot_threshold: Optional[float],
                  cold_threshold: Optional[float]) -> Optional[str]:
    """"hot" / "cold" / "steady" against population quartiles.

    The thresholds are the upper and lower quartile of every player's slope
    IN THE SAME FORMAT, computed by the builder -- "hot" is relative to the
    league, not to an absolute number that would mean different things in
    8-ball and 9-ball scoring.

    None below MIN_MATCHES_FOR_FLAG, or when the population was too small to
    produce thresholds: sorting a player into a quartile on one result would
    be a label the evidence cannot carry.
    """
    if slope is None or matches < MIN_MATCHES_FOR_FLAG:
        return None
    if hot_threshold is None or cold_threshold is None:
        return None
    if slope >= hot_threshold:
        return "hot"
    if slope <= cold_threshold:
        return "cold"
    return "steady"


def quartile_thresholds(slopes: Sequence[float]) -> tuple[Optional[float], Optional[float]]:
    """(upper quartile, lower quartile) of a population of slopes.

    Uses the nearest-rank method on the sorted series -- no interpolation, no
    numpy dependency for a handful of values. Returns (None, None) for a
    population too small to have quartiles, which keeps every player in it
    unflagged rather than arbitrarily labelled.
    """
    clean = sorted(s for s in slopes if s is not None)
    if len(clean) < 4:
        return None, None
    lower = clean[max(0, math.ceil(0.25 * len(clean)) - 1)]
    upper = clean[max(0, math.ceil(0.75 * len(clean)) - 1)]
    return upper, lower


def evaluate(points: Sequence[Optional[float]], levels: Sequence[Optional[int]],
             player_id: str, format_: Optional[str] = None,
             hot_threshold: Optional[float] = None,
             cold_threshold: Optional[float] = None) -> PlayerTrendResult:
    """Everything the analyzer knows about one (player, format) window.

    `points` and `levels` must be the player's matches in that format, in
    chronological order and index-aligned. The window is applied here.
    """
    window_points = rolling_window(points)
    window_levels = rolling_window(levels)
    slope = trend_slope(window_points)
    considered = len([p for p in window_points if p is not None])

    return PlayerTrendResult(
        player_id=player_id,
        format=format_,
        matches_considered=considered,
        avg_points_last_20=average(window_points),
        volatility_last_20=volatility(window_points),
        trend_slope=slope,
        trend_strength=trend_strength(slope, format_),
        sl_stability=sl_stability(window_levels),
        hot_cold_flag=hot_cold_flag(slope, considered, hot_threshold, cold_threshold),
        projected_sl_change_probability=projected_sl_change_probability(
            window_levels, slope, format_
        ),
    )
