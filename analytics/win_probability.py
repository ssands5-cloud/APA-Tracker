"""Opponent-specific win probability -- a hand-rolled, transparent logistic
model over real, already-computed signals.

Purely derived and purely computational, the same split
analytics.lineup_optimizer already uses: this module queries no database
and reads no config. scripts/build_lineups.py resolves the real inputs
(skill levels, win rates, volatility) from the database and calls
compute_win_probability; apa_config.yaml's own `win_probability` section
supplies real, overridable weights via
scripts.build_lineups.load_win_probability_weights_from_config.

Every input concept is real:

    sl_delta     -> Player.skill_level (player's) minus Player.skill_level
                    (opponent's) -- both real, current roster values.
    wr_sl        -> this player's real win rate, from player_head_to_head,
                    against every real opponent who shares the SAME
                    opponent_skill_level as this pairing's opponent.
    wr_h2h       -> this player's real win rate against THIS SPECIFIC
                    opponent -- the same real, already-validated
                    player_h2h_advantage.win_probability the existing
                    Lineup Optimizer already uses (see
                    docs/lineup_optimizer.md). Reused, not recomputed.
    volatility   -> player_trends.volatility, the same real Player Trend
                    Analyzer signal analytics.captains_edge.risk_factor
                    already uses (docs/player_trends.md).

Full write-up, including what was checked against this project's own real
data before picking the default weights below, and the race-chart gap:
docs/win_probability.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# --- objective weights -------------------------------------------------
# Checked for real DIRECTION against this project's own H2H outcomes
# before shipping (docs/win_probability.md's "Verification against real
# data" section) -- not fit by any ML library (none is used anywhere in
# this module), and explicitly NOT claimed as precisely optimal: the real
# sample available (106 decided H2H games) is too small to fit five free
# parameters with confidence, the same caveat
# analytics.close_match_performance.CLOSE_MATCH_MARGIN's own docstring
# gives for its 14-match sample. Provisional, real-direction-checked
# defaults -- expected to be revisited as more real data accumulates.
WEIGHT_SL_DELTA = 0.15
WEIGHT_WR_SL = 0.20
WEIGHT_WR_H2H = 0.30
WEIGHT_VOLATILITY = 0.05
LOGISTIC_SCALE = 1.0
CLAMP_MIN = 0.02
CLAMP_MAX = 0.98

# math.exp overflows for a large positive argument; z is a weighted sum of
# real, bounded-ish inputs so this is not expected to bind in practice, but
# clamping it is cheap insurance against a genuinely pathological input
# (e.g. a config with an extreme weight) turning into an unhandled
# OverflowError instead of a real, if extreme, clamped probability.
_MAX_EXP_ARGUMENT = 700.0


@dataclass(frozen=True)
class WinProbabilityWeights:
    """The logistic model's real, overridable coefficients -- see the
    module docstring for what was checked against real data, and
    docs/win_probability.md for the full verification writeup.

    No `race_difficulty` weight: see race_difficulty()'s own docstring for
    why that term is a documented v1 gap, not an oversight.
    """

    sl_delta: float = WEIGHT_SL_DELTA
    wr_sl: float = WEIGHT_WR_SL
    wr_h2h: float = WEIGHT_WR_H2H
    volatility: float = WEIGHT_VOLATILITY
    logistic_scale: float = LOGISTIC_SCALE
    clamp_min: float = CLAMP_MIN
    clamp_max: float = CLAMP_MAX


DEFAULT_WIN_PROBABILITY_WEIGHTS = WinProbabilityWeights()


def sl_delta(player_skill_level: Optional[int], opponent_skill_level: Optional[int]) -> float:
    """SLDelta = the player's real skill level minus the opponent's.

    Treats either missing skill level as 0 -- NOT excluded, and NOT the
    neutral 0.5 analytics.lineup_optimizer.NEUTRAL_DEFAULT uses elsewhere
    in this project. This module's own spec calls for a literal 0 default
    specifically: a missing skill level contributes nothing to z, rather
    than being treated as an average opponent (which 0.5 would imply for
    a 0..1-scaled signal -- SLDelta isn't one, so a different convention
    for "missing" is appropriate here, not an inconsistency).
    """
    if player_skill_level is None or opponent_skill_level is None:
        return 0.0
    return float(player_skill_level - opponent_skill_level)


def race_difficulty(player_skill_level: Optional[int] = None,
                    opponent_skill_level: Optional[int] = None,
                    format_name: Optional[str] = None) -> float:
    """PENDING -- always returns 0.0. Not implemented in v1.

    APA's real "Games Must Win" race charts (the source that would make
    this real) were located and verified for both 8-Ball and 9-Ball
    Team/Singles play (rules.poolplayers.com -- see
    docs/win_probability.md's "Race chart verification" section for the
    full transcribed tables and citation). They were NOT wired in here:
    a race-length-derived signal plausibly overlaps with sl_delta above
    (how much longer/shorter your required race is, versus your
    opponent's, is itself mostly determined by the same skill-level
    pairing sl_delta already captures), and whether that overlap would
    double-count the same real signal was not checked against real data
    before this module shipped. Returning a fixed 0.0 keeps this an
    honest, documented gap -- explicitly not a fabricated value standing
    in for a real one -- rather than guessing at a coefficient for an
    unverified interaction. Accepts the same arguments a real
    implementation would need, so a future implementation is a body
    change here, not a signature change at every call site.
    """
    return 0.0


def compute_win_probability(
    sl_delta: Optional[float],
    wr_sl: Optional[float],
    wr_h2h: Optional[float],
    volatility: Optional[float],
    weights: WinProbabilityWeights = DEFAULT_WIN_PROBABILITY_WEIGHTS,
) -> float:
    """P(win), a hand-rolled logistic model over four real signals.

        z = weights.sl_delta*SLDelta + weights.wr_sl*WR_SL
            + weights.wr_h2h*WR_H2H - weights.volatility*Volatility
        P(win) = 1 / (1 + e^(-weights.logistic_scale * z))

    Every missing input is treated as 0 -- NOT excluded; a pairing is
    never dropped for lacking data, per this module's own spec. This is a
    deliberately different convention from
    analytics.lineup_optimizer.pairing_score's neutral-0.5 default: that
    module treats "unknown" as "assume average," this one treats it as
    "this factor contributes nothing," which is the right reading for a
    difference-from-zero term like sl_delta and a from-zero rate like
    wr_sl/wr_h2h/volatility.

    Always returns a real float in [weights.clamp_min, weights.clamp_max]
    (0.02..0.98 by default) -- clamped so a real upset always stays
    possible and a real result is never predicted as an absolute
    certainty either way.
    """
    sld = sl_delta if sl_delta is not None else 0.0
    wsl = wr_sl if wr_sl is not None else 0.0
    wh2h = wr_h2h if wr_h2h is not None else 0.0
    vol = volatility if volatility is not None else 0.0

    z = (
        weights.sl_delta * sld
        + weights.wr_sl * wsl
        + weights.wr_h2h * wh2h
        - weights.volatility * vol
    )
    exponent = max(-_MAX_EXP_ARGUMENT, min(_MAX_EXP_ARGUMENT, -weights.logistic_scale * z))
    p = 1.0 / (1.0 + math.exp(exponent))
    return round(min(weights.clamp_max, max(weights.clamp_min, p)), 6)
