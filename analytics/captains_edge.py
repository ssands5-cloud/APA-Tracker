"""Captain's Decision Engine.

Turns the outputs of the existing engines into one ranked lineup answer:
which of my players should take which opponent, in what order, and how much
to trust each call.

Purely derived. It invents no metric and writes to no table. Every input is
already computed and stored by something else:

    win_probability, expected_points, expected_balls
        -> player_h2h_advantage   (analytics.head_to_head)
    volatility, sl_stability, regression_slope, hot_cold_flag
        -> player_trends          (analytics.player_trends)

Note on sourcing: the specification names ``analytics.matchups`` as the
source of the first three. They are not there -- ``player_matchups`` carries
win_rate and matchup_score, while expected_points, expected_balls and
win_probability are the Head-to-Head Advantage Engine's columns. This module
reads them from where they actually live rather than from where the spec
expected them.

NULL means insufficient evidence throughout and is never a fabricated zero.

Full write-up: docs/captains_edge.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

# --- composite matchup score -------------------------------------------------
# Weights are the spec's. Win probability dominates because it is the only
# component that already answers "will this player win"; the expected-output
# terms describe HOW MUCH they win by, which breaks ties rather than deciding.
WEIGHT_WIN_PROBABILITY = 0.6
WEIGHT_EXPECTED_POINTS = 0.3
WEIGHT_EXPECTED_BALLS = 0.1

# --- confidence --------------------------------------------------------------
# A player's form flag sets the base, and the slope nudges it. The bases are
# the spec's.
CONFIDENCE_BASE = {
    "HOT": 0.75,
    "NEUTRAL": 0.50,
    "COLD": 0.25,
}

NO_DATA = None


@dataclass(frozen=True)
class Bounds:
    """Min/max of one component across the whole population, for min-max
    normalisation. `low is None` means the component was never present."""

    low: Optional[float] = None
    high: Optional[float] = None

    @property
    def usable(self) -> bool:
        return self.low is not None and self.high is not None


@dataclass(frozen=True)
class ScoreBounds:
    """Population bounds for every normalised component."""

    expected_points: Bounds = Bounds()
    expected_balls: Bounds = Bounds()


@dataclass
class LineupEntry:
    """One player's recommended assignment."""

    player_id: str
    player_name: str
    opponent_id: Optional[str]
    opponent_name: Optional[str]
    matchup_score: Optional[float]
    risk_factor: Optional[float]
    confidence: Optional[float]
    recommended_order: Optional[int]
    rationale: str


def _bounds_of(values: Iterable[Optional[float]]) -> Bounds:
    present = [v for v in values if v is not None]
    if not present:
        return Bounds()
    return Bounds(low=min(present), high=max(present))


def compute_bounds(pairings: Sequence[dict]) -> ScoreBounds:
    """Min/max for each normalised component, across every pairing.

    Normalisation is population-relative by design: an "expected 3 points"
    means nothing until you know whether 3 is the best or the worst on the
    board.
    """
    return ScoreBounds(
        expected_points=_bounds_of(p.get("expected_points") for p in pairings),
        expected_balls=_bounds_of(p.get("expected_balls") for p in pairings),
    )


def normalize(value: Optional[float], bounds: Bounds) -> Optional[float]:
    """Min-max a value into 0..1 against population bounds.

    None when the value is missing or the population had no usable range.

    A degenerate range (every value identical) returns 1.0 rather than
    dividing by zero: if every candidate expects the same output, none is
    disadvantaged by that component. Returning 0.0 would penalise all of
    them equally, which is the same ranking but a misleading number.
    """
    if value is None or not bounds.usable:
        return None
    if bounds.high == bounds.low:
        return 1.0
    return (value - bounds.low) / (bounds.high - bounds.low)


def matchup_score(win_probability: Optional[float],
                  expected_points: Optional[float],
                  expected_balls: Optional[float],
                  bounds: ScoreBounds) -> Optional[float]:
    """Composite 0..1 score for one pairing.

        score = 0.6*win_probability + 0.3*points_norm + 0.1*balls_norm

    A NULL component is **skipped and the remaining weights are
    renormalised**, so the score stays on a 0..1 scale.

    That renormalisation is an interpretation the spec does not state, and
    it is deliberate: without it, a 9-ball pairing (which has no
    expected_points by construction) would score up to 0.3 lower than an
    identical 8-ball one purely for having a field that does not apply to
    it. Penalising a row for a structural absence would make the two formats
    incomparable -- see docs/captains_edge.md.

    None when every component is missing: a pairing with no evidence has no
    score, which is different from a score of zero.
    """
    components = (
        (win_probability, WEIGHT_WIN_PROBABILITY),
        (normalize(expected_points, bounds.expected_points), WEIGHT_EXPECTED_POINTS),
        (normalize(expected_balls, bounds.expected_balls), WEIGHT_EXPECTED_BALLS),
    )
    present = [(value, weight) for value, weight in components if value is not None]
    if not present:
        return NO_DATA

    total_weight = sum(weight for _, weight in present)
    if total_weight == 0:
        return NO_DATA
    return round(sum(value * weight for value, weight in present) / total_weight, 6)


def risk_factor(volatility: Optional[float],
                sl_stability: Optional[float]) -> Optional[float]:
    """How unpredictable this player currently is, 0..1.

        risk = clamp(volatility * (1 - sl_stability), 0, 1)

    Both terms come from the Player Trend Analyzer. They are related --
    stability is 1/(1+volatility) -- so this is effectively
    volatility²/(1+volatility): risk climbs faster than volatility alone,
    which is the intent. A player whose skill level swings is a gamble twice
    over, once for the swing and once for not knowing which way.

    None when either input is missing.
    """
    if volatility is None or sl_stability is None:
        return NO_DATA
    return round(min(1.0, max(0.0, volatility * (1.0 - sl_stability))), 6)


def confidence(regression_slope: Optional[float],
               hot_cold_flag: Optional[str]) -> Optional[float]:
    """How much to trust this player's current form, 0..1.

        HOT     -> 0.75 + slope
        NEUTRAL -> 0.50 + slope
        COLD    -> 0.25 + slope

    clamped to 0..1.

    The flag sets the base and the slope nudges it, so a COLD player who has
    started climbing is not written off entirely and a HOT player who has
    begun to slide loses ground before the flag catches up.

    None when either input is missing, or when the flag is not one the
    Player Trend Analyzer produces -- an unrecognised flag is a bug
    upstream, and guessing a base for it would hide that.
    """
    if regression_slope is None or hot_cold_flag is None:
        return NO_DATA
    base = CONFIDENCE_BASE.get(str(hot_cold_flag).upper())
    if base is None:
        return NO_DATA
    return round(min(1.0, max(0.0, base + regression_slope)), 6)


def build_rationale(entry_score: Optional[float], risk: Optional[float],
                    conf: Optional[float], opponent_name: Optional[str]) -> str:
    """One short sentence explaining the ranking.

    Says which signal drove the call, and says so plainly when the answer
    rests on thin evidence -- a recommendation a captain cannot interrogate
    is one they should not follow.
    """
    if entry_score is None:
        return "No scored pairing yet - not enough history to recommend."

    against = f"vs {opponent_name}" if opponent_name else "unassigned"
    parts = [f"{against}: score {entry_score:.2f}"]

    if conf is None:
        parts.append("form unknown (needs 5+ matches)")
    elif conf >= 0.7:
        parts.append("strong recent form")
    elif conf <= 0.35:
        parts.append("poor recent form")

    if risk is None:
        parts.append("stability unknown")
    elif risk >= 0.5:
        parts.append("high skill-level volatility")
    elif risk <= 0.1:
        parts.append("settled skill level")

    return "; ".join(parts) + "."


def lineup_recommendation(pairings: Sequence[dict],
                          trends: dict[str, dict],
                          bounds: Optional[ScoreBounds] = None) -> list[LineupEntry]:
    """Rank a team's players into a recommended playing order.

    `pairings` are that team's players' rows against the opponent's players
    (from player_h2h_advantage); `trends` maps player_id -> that player's
    player_trends row.

    One entry per PLAYER, not per pairing: a player has many possible
    opponents and the lineup answers "who should they play", so each player
    keeps their single best-scoring pairing.

    Ranked by matchup_score descending. Players with no score sort last and
    receive no `recommended_order` at all -- ordering them would imply a
    judgement the evidence does not support.

    `recommended_order` runs 1..N over the scored players. It is NOT padded
    to 5: a team with three scored players has three recommendations, and
    inventing two more would be fabrication.
    """
    bounds = bounds if bounds is not None else compute_bounds(pairings)

    best: dict[str, tuple[float, dict]] = {}
    unscored: dict[str, dict] = {}
    for pairing in pairings:
        player_id = pairing.get("player_id")
        if not player_id:
            continue
        score = matchup_score(
            pairing.get("win_probability"),
            pairing.get("expected_points"),
            pairing.get("expected_balls"),
            bounds,
        )
        if score is None:
            unscored.setdefault(player_id, pairing)
            continue
        current = best.get(player_id)
        if current is None or score > current[0]:
            best[player_id] = (score, pairing)

    entries: list[LineupEntry] = []
    for player_id, (score, pairing) in best.items():
        trend = trends.get(player_id) or {}
        risk = risk_factor(trend.get("volatility"), trend.get("sl_stability"))
        conf = confidence(trend.get("regression_slope"), trend.get("hot_cold_flag"))
        entries.append(LineupEntry(
            player_id=player_id,
            player_name=pairing.get("player_name") or "",
            opponent_id=pairing.get("opponent_id"),
            opponent_name=pairing.get("opponent_name"),
            matchup_score=score,
            risk_factor=risk,
            confidence=conf,
            recommended_order=None,
            rationale=build_rationale(score, risk, conf, pairing.get("opponent_name")),
        ))

    entries.sort(key=lambda e: -(e.matchup_score or 0))
    for order, entry in enumerate(entries, start=1):
        entry.recommended_order = order

    # Players whose every pairing was unscored: listed, explicitly unranked.
    for player_id, pairing in unscored.items():
        if player_id in best:
            continue
        trend = trends.get(player_id) or {}
        entries.append(LineupEntry(
            player_id=player_id,
            player_name=pairing.get("player_name") or "",
            opponent_id=pairing.get("opponent_id"),
            opponent_name=pairing.get("opponent_name"),
            matchup_score=None,
            risk_factor=risk_factor(trend.get("volatility"), trend.get("sl_stability")),
            confidence=confidence(trend.get("regression_slope"), trend.get("hot_cold_flag")),
            recommended_order=None,
            rationale=build_rationale(None, None, None, pairing.get("opponent_name")),
        ))

    return entries
