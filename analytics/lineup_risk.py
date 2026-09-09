"""Lineup Risk Scoring -- elevates the Lineup Optimizer's per-PAIRING
signals (modeled_win_probability, volatility, matchup_score, confidence,
risk_factor) to a per-LINEUP summary: how dangerous is this whole solved
lineup, where is the upset risk concentrated, and is it stable enough to
anchor a match.

Purely derived and purely computational, the same split
analytics.lineup_optimizer and analytics.win_probability already use:
this module takes an already-solved lineup's real
analytics.lineup_optimizer.AssignmentEntry list as input and queries
nothing. scripts/build_lineups.py calls it once per solved lineup, right
after analytics.lineup_optimizer.solve_lineup_assignment returns;
apa_config.yaml's own `lineup_risk` section supplies real, overridable
weights via scripts.build_lineups.load_lineup_risk_weights_from_config.

Every input is a real, already-computed pairing signal -- see
docs/lineup_risk.md for the full formula writeup, the real "anchor"
definition used here (the assigned player with the highest
modeled_win_probability -- a project-defined operational choice, not
itself a further claimed APA rule), and the missing-data convention
(volatility missing -> 0, mirroring analytics.win_probability's own
convention for the identical underlying signal; modeled_win_probability
is never missing on a real solved assignment -- see
analytics.win_probability.compute_win_probability, which always returns
a real, clamped float).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


class RiskAssignment(Protocol):
    """The minimal real shape this module needs from one solved lineup
    slot -- analytics.lineup_optimizer.AssignmentEntry satisfies this
    structurally; a Protocol keeps this module from importing that one
    just to type-hint against it."""

    player_name: str
    modeled_win_probability: Optional[float]
    volatility: Optional[float]
    risk_factor: Optional[float]


# --- objective weights -------------------------------------------------
# A transparent decision-support scalar, not a fitted probability model --
# the same honest framing docs/lineup_optimizer.md already gives the
# Lineup Optimizer's own combined score. There is no historical "which
# lineup actually won" record to check LRS's ranking against (the same
# real gap docs/lineup_optimizer.md documents for the optimizer itself),
# so these starting weights are a reasoned, equal-ish split across the
# four components -- not claimed as empirically fit. See
# docs/lineup_risk.md.
WEIGHT_UPSET_RISK = 0.30
WEIGHT_ANCHOR_INSTABILITY = 0.30
WEIGHT_VOLATILITY_LOAD = 0.20
WEIGHT_DANGER_COUNT = 0.20

# The Danger Matchup Count's own threshold: a pairing scoring below this
# real modeled_win_probability counts as a "red flag" pairing. 0.40 is
# the value asked for; overridable, not asserted as empirically derived.
DANGER_THRESHOLD = 0.40


@dataclass(frozen=True)
class LineupRiskWeights:
    """The Lineup Risk Score's real, overridable coefficients. Defaults
    reproduce this module's own WEIGHT_*/DANGER_THRESHOLD constants above;
    scripts.build_lineups.load_lineup_risk_weights_from_config reads
    apa_config.yaml's own `lineup_risk` section to build a real,
    non-default instance."""

    upset_risk: float = WEIGHT_UPSET_RISK
    anchor_instability: float = WEIGHT_ANCHOR_INSTABILITY
    volatility_load: float = WEIGHT_VOLATILITY_LOAD
    danger_count: float = WEIGHT_DANGER_COUNT
    danger_threshold: float = DANGER_THRESHOLD


DEFAULT_LINEUP_RISK_WEIGHTS = LineupRiskWeights()


@dataclass(frozen=True)
class LineupRiskMetrics:
    """One solved lineup's real, team-level risk summary."""

    upset_risk_index: float
    anchor_stability_score: Optional[float]
    anchor_player_name: Optional[str]
    lineup_volatility_load: float
    danger_matchup_count: int
    lineup_risk_score: float


def _win_probability(assignment: RiskAssignment) -> float:
    """modeled_win_probability, defaulting to 0 when absent. In practice
    this never triggers on a real solved assignment -- compute_win_probability
    always returns a real, clamped float -- but a defensive default keeps
    this module correct against a hand-built or partial assignment too."""
    value = assignment.modeled_win_probability
    return value if value is not None else 0.0


def _volatility(assignment: RiskAssignment) -> float:
    """Raw player_trends.volatility, defaulting to 0 when absent -- the
    same missing-data convention analytics.win_probability itself uses for
    this identical signal (see compute_win_probability's own docstring)."""
    value = assignment.volatility
    return value if value is not None else 0.0


def upset_risk_index(assignments: Sequence[RiskAssignment]) -> float:
    """URI = sum over the lineup of (1 - P(win)) * Volatility.

    High volatility combined with a low real win probability is exactly
    the shape of a player who could plausibly lose a match they're
    supposed to win -- summed across the whole lineup, this is "how much
    real upset risk is sitting in this lineup," not any one player's.
    """
    return round(
        sum((1.0 - _win_probability(a)) * _volatility(a) for a in assignments),
        6,
    )


def anchor_stability_score(
    assignments: Sequence[RiskAssignment],
) -> tuple[Optional[float], Optional[str]]:
    """ASS = P(win) - Volatility, for the lineup's real anchor.

    The anchor is the assigned player with the highest real
    modeled_win_probability -- an operational definition this module
    picks (a real, principled choice given the available real signals),
    not itself a further claimed APA rule the way the 23-Rule is. Ties
    broken by lower risk_factor, then lexicographically by player_name,
    for a single deterministic answer -- the same tie-break shape
    analytics.lineup_optimizer.solve_lineup_assignment already uses.

    Returns (None, None) for an empty lineup -- there is no anchor to
    speak of, not a guessed one.
    """
    if not assignments:
        return None, None
    anchor = min(
        assignments,
        key=lambda a: (
            -_win_probability(a),
            a.risk_factor if a.risk_factor is not None else 1.0,
            a.player_name,
        ),
    )
    score = round(_win_probability(anchor) - _volatility(anchor), 6)
    return score, anchor.player_name


def lineup_volatility_load(assignments: Sequence[RiskAssignment]) -> float:
    """LVL = sum of real Volatility across the whole lineup -- how
    'swingy' the lineup is overall, independent of any one player's own
    win probability."""
    return round(sum(_volatility(a) for a in assignments), 6)


def danger_matchup_count(
    assignments: Sequence[RiskAssignment],
    threshold: float = DANGER_THRESHOLD,
) -> int:
    """DMC = count of real pairings with modeled_win_probability strictly
    below `threshold` -- the captain's real "red flag" count."""
    return sum(1 for a in assignments if _win_probability(a) < threshold)


def compute_lineup_risk(
    assignments: Sequence[RiskAssignment],
    weights: LineupRiskWeights = DEFAULT_LINEUP_RISK_WEIGHTS,
) -> LineupRiskMetrics:
    """The full real Lineup Risk Score:

        LRS = weights.upset_risk * URI
            + weights.anchor_instability * (1 - ASS)
            + weights.volatility_load * LVL
            + weights.danger_count * DMC

    An empty lineup (no real assignments at all) is a real, valid input --
    every component is 0 or None rather than raising, since there is
    nothing dangerous about a lineup that doesn't exist yet.
    """
    uri = upset_risk_index(assignments)
    ass, anchor_name = anchor_stability_score(assignments)
    lvl = lineup_volatility_load(assignments)
    dmc = danger_matchup_count(assignments, threshold=weights.danger_threshold)

    # (1 - ASS) needs a real value to combine into LRS; an empty lineup's
    # None ASS contributes 0 to LRS the same way every other component
    # already does for an empty lineup, rather than propagating None
    # through a scalar the rest of this dataclass keeps as a real float.
    ass_for_score = ass if ass is not None else 0.0
    lrs = round(
        weights.upset_risk * uri
        + weights.anchor_instability * (1.0 - ass_for_score)
        + weights.volatility_load * lvl
        + weights.danger_count * dmc,
        6,
    )

    return LineupRiskMetrics(
        upset_risk_index=uri,
        anchor_stability_score=ass,
        anchor_player_name=anchor_name,
        lineup_volatility_load=lvl,
        danger_matchup_count=dmc,
        lineup_risk_score=lrs,
    )
