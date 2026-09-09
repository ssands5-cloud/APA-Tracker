"""Captain's Edge rationale strings -- real, transparent, plain-language
explanations of already-computed real numbers. Never a fabricated
judgment presented as if it were statistically derived.

**Per-pairing rationale already exists and is intentionally NOT
duplicated here.** Two real, tested, already-shipped implementations
cover it:

    analytics.captains_edge.build_rationale   -- the Captain's Decision Engine
    analytics.lineup_optimizer.build_rationale -- the Lineup Optimizer

Both are wired into their own JSON/Excel outputs today. Adding a third,
centralized "per-pairing rationale" here would fragment one real concept
across three files with no behavioral gain -- exactly the kind of
duplication this project's own history has already caught and reverted
once (see the Lineup Optimizer's own git log: an earlier request for a
duplicate Hungarian-algorithm module was redirected into extending the
existing one instead). If per-pairing rationale ever needs a genuinely
new capability, it belongs next to the score it explains, matching that
established pattern -- not centralized here.

**What IS new, and lives here**: PER-LINEUP rationale -- "why this whole
lineup," as opposed to "why this one pairing." This only became possible
once analytics.lineup_risk existed to summarize a solved lineup's signals
at the team level; there was nothing to build a lineup-level sentence out
of before that.
"""

from __future__ import annotations

from dataclasses import dataclass

from analytics.lineup_risk import LineupRiskMetrics, LineupRiskWeights


@dataclass(frozen=True)
class RationaleToggles:
    """Whether to compute/include real rationale strings at all --
    apa_config.yaml's own `rationale` section
    (scripts.build_lineups.load_rationale_toggles_from_config). Defaults
    to including it; a captain who finds the extra text noisy can turn it
    off without anything else in the pipeline changing."""

    include_lineup_rationale: bool = True


DEFAULT_RATIONALE_TOGGLES = RationaleToggles()

# Descriptive cutoffs for "high"/"low" overall volatility load, in the
# same spirit as analytics.matchups.MATCHUPS_WIN_RATE_HIGH/LOW and
# analytics.captains_edge.EDGE_HIGH_CONFIDENCE/EDGE_HIGH_RISK: picked for
# readable, real-number-grounded language, not fit to data. A typical
# real per-player volatility reading in this project's own captured data
# runs roughly 0.05-0.9 (see docs/win_probability.md's real-data
# verification); a 5-player lineup's LVL (a plain sum) crossing 2.0
# means an average per-player volatility above 0.4, and dropping below
# 0.5 means an average below 0.1 -- both real, checkable thresholds
# against that same range, not arbitrary round numbers.
LINEUP_VOLATILITY_LOAD_HIGH = 2.0
LINEUP_VOLATILITY_LOAD_LOW = 0.5

# Descriptive cutoffs for the anchor's own stability -- ASS = P(win) -
# Volatility, so a real anchor with a real win probability comfortably
# above their real volatility reading (ASS >= 0.5) reads as genuinely
# reliable; a real anchor whose volatility reading meets or exceeds their
# own win probability (ASS <= 0) reads as a real liability, not just a
# weak favorite.
ANCHOR_STABLE_AT = 0.5
ANCHOR_SHAKY_AT = 0.0


def lineup_risk_rationale(
    metrics: LineupRiskMetrics,
    weights: LineupRiskWeights,
) -> str:
    """One real, factual sentence describing a solved lineup's actual risk
    numbers -- states what IS true about `metrics`, never a fabricated
    categorical verdict dressed up as a statistical one.

    An empty lineup (no real anchor) gets an explicit, honest sentence
    saying so, never a guessed risk description.
    """
    if metrics.anchor_player_name is None:
        return "No real assignments in this lineup -- no risk profile to describe."

    parts: list[str] = [f"Anchor: {metrics.anchor_player_name}"]

    if metrics.anchor_stability_score is not None:
        if metrics.anchor_stability_score >= ANCHOR_STABLE_AT:
            parts.append(f"stable at {metrics.anchor_stability_score:+.2f}")
        elif metrics.anchor_stability_score <= ANCHOR_SHAKY_AT:
            parts.append(f"shaky at {metrics.anchor_stability_score:+.2f}")
        else:
            parts.append(f"stability {metrics.anchor_stability_score:+.2f}")

    if metrics.danger_matchup_count > 0:
        plural = "es" if metrics.danger_matchup_count != 1 else ""
        parts.append(
            f"{metrics.danger_matchup_count} danger matchup{plural} below the "
            f"{weights.danger_threshold:.0%} win-probability threshold"
        )
    else:
        parts.append("no danger matchups")

    if metrics.lineup_volatility_load >= LINEUP_VOLATILITY_LOAD_HIGH:
        parts.append("high overall volatility")
    elif metrics.lineup_volatility_load <= LINEUP_VOLATILITY_LOAD_LOW:
        parts.append("low overall volatility")

    # Deliberately NOT .capitalize() on the joined string -- that lowercases
    # every character but the first, corrupting a real player's name
    # (e.g. "Anchor: Bob" -> "anchor: bob") anywhere but the very start.
    # "Anchor: ..." already starts capitalized, so nothing else is needed.
    return ", ".join(parts) + f". Lineup Risk Score: {metrics.lineup_risk_score:.2f}."
