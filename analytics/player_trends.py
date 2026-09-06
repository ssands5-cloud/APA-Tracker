"""Player Trend Analyzer.

Implements the finalized governing spec exactly. Every formula, threshold,
constant and minimum-evidence rule below comes from that spec -- none is
chosen here. Where the spec is silent, that is called out in a comment
rather than filled in silently.

The subject of every trend metric is the player's **skill level**, not their
points earned: volatility is the sample standard deviation of SL, and the
regression slope is in SL units per match. `avg_points_last_20` is the one
points-based figure, kept as descriptive context.

Two different spans are used on purpose, per spec:

  * regression slope  -- ALL matches in the session, uncapped
  * volatility        -- the LAST 20 matches only

Every input is real captured data (``PlayerMatch.skill_level`` and
``.points_earned``, format from the joined ``Match``). Nothing is
synthesised, and a metric without enough evidence is NULL, never a
fabricated zero.

Full write-up: docs/player_trends.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

# --- spec §1: volatility -----------------------------------------------------
# The volatility window. The slope deliberately does NOT use this -- see §5.
VOLATILITY_WINDOW = 20
# Sample standard deviation: ddof=1, the correct choice when estimating
# variability from a finite sample rather than describing a whole population.
VOLATILITY_DDOF = 1

# --- spec §3: hot / cold thresholds ------------------------------------------
# Tuned for APA skill-level behaviour. Both conditions must hold: a steep
# slope with erratic skill levels is noise, not a trend.
HOT_SLOPE_MIN = 0.05          # SL per match
COLD_SLOPE_MAX = -0.05        # SL per match
STABLE_VOLATILITY_MAX = 0.40  # SL sample stddev

# --- spec §4: projected SL-change probability --------------------------------
# p = clamp(0.5 * tanh(PROBABILITY_SLOPE_GAIN * slope) * (1 - sigma) * n/CAP, 0, 1)
PROBABILITY_SCALE = 0.5
PROBABILITY_SLOPE_GAIN = 4.0
PROBABILITY_SAMPLE_CAP = 20

# --- spec §6: minimum evidence ----------------------------------------------
MIN_OBSERVATIONS_SLOPE = 2
MIN_OBSERVATIONS_VOLATILITY = 2
MIN_OBSERVATIONS_FLAG = 5
MIN_OBSERVATIONS_PROBABILITY = 5


@dataclass
class PlayerTrendResult:
    """One (player, format) evaluation. Any field may be None -- see §6."""

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


def _valid(values: Sequence) -> list:
    """Only observations that actually exist. A missing skill level is not a
    zero skill level."""
    return [v for v in values if v is not None]


def rolling_window(values: Sequence, size: int = VOLATILITY_WINDOW) -> list:
    """The most recent `size` entries, oldest first.

    Slices; does not sort. Callers must supply chronological order -- the
    slope reads against match order and would be meaningless otherwise.
    """
    return list(values[-size:]) if size else list(values)


def average(values: Sequence[Optional[float]]) -> Optional[float]:
    """Mean of the present values, or None when there are none."""
    clean = _valid(values)
    return round(sum(clean) / len(clean), 3) if clean else None


# --- spec §1 -----------------------------------------------------------------

def volatility(skill_levels: Sequence[Optional[int]]) -> Optional[float]:
    """Sample standard deviation (ddof=1) of skill level over the window.

        ȳ = (1/n) Σ yᵢ
        σ  = sqrt( (1/(n-1)) Σ (yᵢ - ȳ)² )

    Sample rather than population: this estimates how variable the player's
    skill level *is* from a finite set of observations, rather than
    describing a closed population.

    None below MIN_OBSERVATIONS_VOLATILITY. One reading has no spread, which
    is a different fact from zero spread -- the spec is explicit that zeros
    must not be fabricated here.

    Callers pass the last-20 window; this does not slice.
    """
    clean = _valid(skill_levels)
    if len(clean) < MIN_OBSERVATIONS_VOLATILITY:
        return None
    mean = sum(clean) / len(clean)
    variance = sum((y - mean) ** 2 for y in clean) / (len(clean) - VOLATILITY_DDOF)
    return round(math.sqrt(variance), 4)


# --- spec §2 -----------------------------------------------------------------

def sl_stability(sigma: Optional[float]) -> Optional[float]:
    """Normalised stability from volatility:

        stability = 1 / (1 + σ)

    1.0 is perfectly stable; approaches 0.0 as the skill level swings. No
    thresholds are baked in -- those live only in the hot/cold
    classification (§3).

    None when volatility is None; a stability figure derived from no spread
    would assert stability that was never observed.
    """
    if sigma is None:
        return None
    return round(1.0 / (1.0 + sigma), 4)


# --- spec §5 -----------------------------------------------------------------

def trend_slope(skill_levels: Sequence[Optional[int]]) -> Optional[float]:
    """Least-squares slope of skill level against match order, in SL units
    per match.

        slope = (n Σxᵢyᵢ - Σxᵢ Σyᵢ) / (n Σxᵢ² - (Σxᵢ)²)

    with xᵢ = i, 1-indexed in chronological order.

    Uses ALL matches supplied, uncapped -- unlike volatility, which is
    windowed to the last 20. Callers must not pre-slice.

    None below MIN_OBSERVATIONS_SLOPE, and None on a zero denominator (every
    x identical), which cannot arise from real match ordering but would
    otherwise be an unguarded division.
    """
    clean = _valid(skill_levels)
    n = len(clean)
    if n < MIN_OBSERVATIONS_SLOPE:
        return None

    xs = range(1, n + 1)
    sum_x = sum(xs)
    sum_y = sum(clean)
    sum_xy = sum(x * y for x, y in zip(xs, clean))
    sum_x_squared = sum(x * x for x in xs)

    denominator = n * sum_x_squared - sum_x * sum_x
    if denominator == 0:
        return None
    return round((n * sum_xy - sum_x * sum_y) / denominator, 6)


def trend_strength(slope: Optional[float]) -> Optional[float]:
    """|slope| mapped to 0.0-1.0.

    NOT DEFINED BY THE GOVERNING SPEC. The table requires the column and the
    spec does not give a normalisation, so rather than introduce a new
    constant this reuses the spec's own slope transform from §4:

        strength = |tanh(PROBABILITY_SLOPE_GAIN * slope)|

    That keeps every constant in this module traceable to the spec. It is
    flagged here and in docs/player_trends.md as the one derived-not-
    specified metric, so it can be replaced the moment a definition exists.
    """
    if slope is None:
        return None
    return round(abs(math.tanh(PROBABILITY_SLOPE_GAIN * slope)), 4)


# --- spec §3 -----------------------------------------------------------------

def hot_cold_flag(slope: Optional[float], sigma: Optional[float],
                  sample_size: int) -> Optional[str]:
    """"hot" / "cold" / "neutral", against absolute spec thresholds.

    Hot needs slope >= +0.05 AND volatility <= 0.40; cold needs slope <=
    -0.05 AND the same volatility ceiling. Both conditions are required: a
    steep slope through erratic skill levels is noise, not a trend.

    None -- not "neutral" -- when there are fewer than
    MIN_OBSERVATIONS_FLAG observations or no volatility. Insufficient
    evidence is a different fact from an observed absence of movement.
    """
    if sample_size < MIN_OBSERVATIONS_FLAG or slope is None or sigma is None:
        return None
    if sigma <= STABLE_VOLATILITY_MAX:
        if slope >= HOT_SLOPE_MIN:
            return "hot"
        if slope <= COLD_SLOPE_MAX:
            return "cold"
    return "neutral"


# --- spec §4 -----------------------------------------------------------------

def projected_sl_change_probability(slope: Optional[float], sigma: Optional[float],
                                    sample_size: int) -> Optional[float]:
    """Transparent heuristic, not a learned model:

        p = clamp( 0.5 * tanh(4 * slope) * (1 - σ) * n/20,  0, 1 )

    * ``tanh(4 * slope)`` turns SL-per-match pressure into a bounded signal.
    * ``(1 - σ)`` damps an erratic skill level; a σ above 1.0 drives the
      product negative and the clamp takes it to 0.0, which is the intended
      reading -- no confidence at all, not a hidden negative.
    * ``n/20`` damps a thin sample, with n capped at 20.

    The clamp floors at 0, so a DOWNWARD trend yields 0.0. The heuristic
    describes upward SL pressure only; direction lives in ``trend_slope``,
    which is stored alongside it.

    None below MIN_OBSERVATIONS_PROBABILITY or without volatility. Every
    constant is named above and documented in docs/player_trends.md -- there
    are no opaque numbers here, and this must not be presented as APA's own
    re-rating projection.
    """
    if sample_size < MIN_OBSERVATIONS_PROBABILITY or slope is None or sigma is None:
        return None

    capped = min(sample_size, PROBABILITY_SAMPLE_CAP)
    raw = (PROBABILITY_SCALE
           * math.tanh(PROBABILITY_SLOPE_GAIN * slope)
           * (1.0 - sigma)
           * (capped / PROBABILITY_SAMPLE_CAP))
    return round(min(1.0, max(0.0, raw)), 4)


# --- assembly ----------------------------------------------------------------

def evaluate(points: Sequence[Optional[float]], skill_levels: Sequence[Optional[int]],
             player_id: str, format_: Optional[str] = None) -> PlayerTrendResult:
    """Evaluate one (player, format) history.

    `points` and `skill_levels` are the player's full match history in that
    format, chronological and index-aligned. Windowing happens here, and the
    two spans differ by design: the slope sees everything, volatility sees
    the last 20.
    """
    window_levels = rolling_window(skill_levels)
    window_points = rolling_window(points)

    sigma = volatility(window_levels)
    # Slope over the FULL history, per §5 -- deliberately not the window.
    slope = trend_slope(skill_levels)
    # Sample size governs the evidence gates and the probability's n/20 term.
    # It counts the volatility window, the span those gates are stated over.
    sample_size = len(_valid(window_levels))

    return PlayerTrendResult(
        player_id=player_id,
        format=format_,
        matches_considered=sample_size,
        avg_points_last_20=average(window_points),
        volatility_last_20=sigma,
        trend_slope=slope,
        trend_strength=trend_strength(slope),
        sl_stability=sl_stability(sigma),
        hot_cold_flag=hot_cold_flag(slope, sigma, sample_size),
        projected_sl_change_probability=projected_sl_change_probability(
            slope, sigma, sample_size
        ),
    )
