"""Player Trend Analyzer.

Implements the governing spec exactly. Every formula, threshold and
minimum-evidence rule below comes from that spec -- none is chosen here, and
nothing is left to be inferred.

The subject of every metric is the player's **skill level**. Points earned
are not an input.

Two spans differ deliberately and conflating them would break one:

  * regression_slope -- ALL SL observations in the session, uncapped
  * volatility       -- the LAST 20 observations only

Every input is real captured data (``PlayerMatch.skill_level``, with format
and session from the joined ``Match``). NULL means insufficient evidence and
is never replaced by a fabricated zero.

Full write-up: docs/player_trends.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

# --- windows and minimum evidence -------------------------------------------
VOLATILITY_WINDOW = 20
VOLATILITY_DDOF = 1

MIN_OBSERVATIONS_SLOPE = 2
MIN_OBSERVATIONS_VOLATILITY = 2
MIN_SAMPLE_SIZE_CLASSIFICATION = 5

# --- hot / cold thresholds ---------------------------------------------------
HOT_SLOPE_MIN = 0.05          # SL per match
COLD_SLOPE_MAX = -0.05        # SL per match
STABLE_VOLATILITY_MAX = 0.40  # SL sample stddev

HOT = "HOT"
COLD = "COLD"
NEUTRAL = "NEUTRAL"

# --- projected SL-change probability ----------------------------------------
# p = clamp(0.5 * tanh(4 * slope) * (1 - sigma) * n/20, 0, 1)
PROBABILITY_SCALE = 0.5
PROBABILITY_SLOPE_GAIN = 4.0
PROBABILITY_SAMPLE_CAP = 20

# --- format normalisation ----------------------------------------------------
# The spec stores '8-ball' / '9-ball'. The captured data says '8-Ball Open' /
# '9-Ball Open'.
FORMAT_EIGHT_BALL = "8-ball"
FORMAT_NINE_BALL = "9-ball"


def normalize_format(raw: Optional[str]) -> Optional[str]:
    """Map a captured format name onto the spec's '8-ball' / '9-ball'.

    An unrecognised format is returned unchanged rather than forced into a
    bucket it may not belong in -- a silent mis-bucketing would put a
    tournament or masters division's numbers under a label that promises
    something else.
    """
    if raw is None:
        return None
    name = raw.strip().lower()
    if "8-ball" in name or "8 ball" in name or "eight" in name:
        return FORMAT_EIGHT_BALL
    if "9-ball" in name or "9 ball" in name or "nine" in name:
        return FORMAT_NINE_BALL
    return raw


@dataclass
class PlayerTrendResult:
    """One (player, format, session) evaluation."""

    player_id: str
    format: Optional[str]
    session_name: Optional[str]
    sample_size: int
    current_skill_level: Optional[int]
    regression_slope: Optional[float]
    volatility: Optional[float]
    sl_stability: Optional[float]
    hot_cold_flag: Optional[str]
    projected_sl_change_probability: Optional[float]


def _valid(values: Sequence) -> list:
    """Only observations that exist. A missing skill level is not a zero."""
    return [v for v in values if v is not None]


def rolling_window(values: Sequence, size: int = VOLATILITY_WINDOW) -> list:
    """The most recent `size` entries, oldest first.

    Slices; does not sort. Callers must supply chronological order -- the
    regression reads against match order and would be meaningless otherwise.
    """
    return list(values[-size:]) if size else list(values)


def regression_slope(skill_levels: Sequence[Optional[int]]) -> Optional[float]:
    """Least-squares slope of skill level against match order, SL per match.

        slope = (n Σxᵢyᵢ - Σxᵢ Σyᵢ) / (n Σxᵢ² - (Σxᵢ)²)

    with xᵢ = i, 1-indexed chronologically.

    Uses every observation supplied, uncapped -- unlike volatility, which is
    windowed. Callers must not pre-slice.

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


def volatility(skill_levels: Sequence[Optional[int]]) -> Optional[float]:
    """Sample standard deviation (ddof=1) of skill level over the last 20
    observations.

        ȳ = (1/n) Σ yᵢ
        σ  = sqrt( (1/(n-1)) Σ (yᵢ - ȳ)² )

    Windows internally, so callers pass the full history.

    Sample rather than population: this estimates how variable the player's
    skill level *is* from a finite set of observations rather than describing
    a closed population.

    None below MIN_OBSERVATIONS_VOLATILITY. One observation has no spread,
    which is a different fact from zero spread.
    """
    clean = _valid(rolling_window(skill_levels))
    if len(clean) < MIN_OBSERVATIONS_VOLATILITY:
        return None
    mean = sum(clean) / len(clean)
    variance = sum((y - mean) ** 2 for y in clean) / (len(clean) - VOLATILITY_DDOF)
    return round(math.sqrt(variance), 6)


def sl_stability(sigma: Optional[float]) -> Optional[float]:
    """Normalised stability from volatility:

        stability = 1 / (1 + σ)

    1.0 is perfectly stable; approaches 0.0 as the level swings. No
    thresholds are baked in -- those live only in the classification below.

    None when volatility is None: stability derived from no observed spread
    would assert steadiness that was never measured.
    """
    if sigma is None:
        return None
    return round(1.0 / (1.0 + sigma), 6)


def hot_cold_flag(slope: Optional[float], sigma: Optional[float],
                  sample_size: int) -> Optional[str]:
    """'HOT' / 'COLD' / 'NEUTRAL', against absolute spec thresholds.

    HOT needs slope >= +0.05, volatility <= 0.40 and sample_size >= 5; COLD
    mirrors it. Every condition is required: a steep slope through an erratic
    skill level is noise, not a trend.

    None -- not 'NEUTRAL' -- when sample_size is below the minimum or
    volatility is missing. Insufficient evidence is a different fact from an
    observed absence of movement.
    """
    if sample_size < MIN_SAMPLE_SIZE_CLASSIFICATION or sigma is None:
        return None
    if slope is None:
        return NEUTRAL
    if sigma <= STABLE_VOLATILITY_MAX:
        if slope >= HOT_SLOPE_MIN:
            return HOT
        if slope <= COLD_SLOPE_MAX:
            return COLD
    return NEUTRAL


def projected_sl_change_probability(slope: Optional[float], sigma: Optional[float],
                                    sample_size: int) -> Optional[float]:
    """Transparent heuristic, not a learned model:

        p = clamp( 0.5 * tanh(4 * slope) * (1 - σ) * n/20,  0, 1 )

    with n capped at 20.

    * ``tanh(4 * slope)`` turns SL-per-match pressure into a bounded signal.
    * ``(1 - σ)`` damps an erratic level; a σ above 1.0 drives the product
      negative and the clamp takes it to 0.0 -- no confidence at all, not a
      hidden negative.
    * ``n/20`` damps a thin sample.

    The clamp floors at 0, so a DOWNWARD trend yields 0.0. The heuristic
    describes upward SL pressure only; direction lives in regression_slope,
    stored alongside it.

    None when slope or volatility is missing, or sample_size is below the
    minimum. Every constant is named above and documented -- there are no
    opaque numbers here, and this must not be presented as APA's own
    re-rating projection.
    """
    if slope is None or sigma is None:
        return None
    if sample_size < MIN_SAMPLE_SIZE_CLASSIFICATION:
        return None

    capped = min(sample_size, PROBABILITY_SAMPLE_CAP)
    raw = (PROBABILITY_SCALE
           * math.tanh(PROBABILITY_SLOPE_GAIN * slope)
           * (1.0 - sigma)
           * (capped / PROBABILITY_SAMPLE_CAP))
    return round(min(1.0, max(0.0, raw)), 6)


def evaluate(skill_levels: Sequence[Optional[int]], player_id: str,
             format_: Optional[str] = None,
             session_name: Optional[str] = None) -> PlayerTrendResult:
    """Evaluate one (player, format, session) history.

    `skill_levels` is the player's full chronological history in that group;
    windowing happens here, since the two spans differ.

    `sample_size` counts the observations in the volatility window -- the
    span the classification gates are stated over, and the n the probability
    caps at 20.
    """
    window = _valid(rolling_window(skill_levels))
    sample_size = len(window)

    sigma = volatility(skill_levels)
    slope = regression_slope(skill_levels)
    all_levels = _valid(skill_levels)

    return PlayerTrendResult(
        player_id=player_id,
        format=normalize_format(format_),
        session_name=session_name,
        sample_size=sample_size,
        # Most recent reading in this group -- the level the player is on now.
        current_skill_level=all_levels[-1] if all_levels else None,
        regression_slope=slope,
        volatility=sigma,
        sl_stability=sl_stability(sigma),
        hot_cold_flag=hot_cold_flag(slope, sigma, sample_size),
        projected_sl_change_probability=projected_sl_change_probability(
            slope, sigma, sample_size
        ),
    )
