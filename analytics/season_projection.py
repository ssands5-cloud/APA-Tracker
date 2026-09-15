"""Season Projection -- projects the real REMAINING schedule using each
team's real season-to-date record, and reports the real historical
standings trend. Never simulates a future lineup or invents a player
being on a future roster: the Lineup Simulator's own real gap
(docs/future_sheets_upstream_gaps.md -- there is no real "selected
upcoming lineup" concept anywhere in this project's captured data) means
projection here stays at the TEAM level, using only real, already-scraped
standings and schedule data.

Purely derived and purely computational, the same split every other
analytics module in this project uses: this module takes already-fetched
real rows as input and queries nothing itself.

Every input is real:

    remaining matches   -> Match rows where is_scored is False (the real,
                            already-scraped schedule -- see ui.export_json._schedule)
    win rates           -> StandingsSnapshot.wins/losses, real per-team
                            season-to-date totals
    standings history   -> every real StandingsSnapshot capture for one
                            team, across real sync runs over real time

The win-probability estimate for one remaining match, given both teams'
real season win rates, uses the "log5" formula (Bill James): a real,
established sabermetrics method for estimating one team's win
probability against another from each team's own overall win rate, not
an invented formula:

    P(A beats B) = (pA - pA*pB) / (pA + pB - 2*pA*pB)

When only one side's real win rate is known (a new opponent never faced,
or a season with no decided games yet), that side's own win rate is used
directly as the match's win probability rather than guessing the
opponent's strength.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ProbabilitySource(str, Enum):
    """Which real rate(s) a match's win_probability actually came from --
    posted to Issue #14's own audit finding against this module ("the
    one-side fallback mathematically assumes the missing side is exactly
    0.5"): the fallback is a documented, disclosed behavior, never an
    imputed opponent rate silently blended in. Every RemainingMatchProjection
    carries this so a renderer/reader can tell "both real records used"
    from "only one side had a real record" from "no real record at all"."""

    BOTH_RATES = "BOTH_RATES"
    OUR_RATE_ONLY = "OUR_RATE_ONLY"
    OPPONENT_RATE_ONLY = "OPPONENT_RATE_ONLY"
    NO_RATE = "NO_RATE"


def win_rate(wins: Optional[int], losses: Optional[int]) -> Optional[float]:
    """A real team's season-to-date win rate. None when there are no real
    decided games yet -- never a guessed 0 or 0.5."""
    if wins is None or losses is None:
        return None
    decided = wins + losses
    if decided <= 0:
        return None
    return round(wins / decided, 6)


def log5_win_probability(
    our_win_rate: Optional[float],
    opponent_win_rate: Optional[float],
) -> Optional[float]:
    """P(we win), from the real log5 formula, given both teams' real
    season win rates. Falls back to whichever single real rate IS known
    when the other side has none -- never a guessed opponent strength.
    None only when NEITHER side has a real decided-game record yet.
    """
    if our_win_rate is None and opponent_win_rate is None:
        return None
    if opponent_win_rate is None:
        return our_win_rate
    if our_win_rate is None:
        return 1.0 - opponent_win_rate

    denominator = our_win_rate + opponent_win_rate - 2 * our_win_rate * opponent_win_rate
    if denominator == 0:
        # Only possible at the degenerate pA=pB=0 or pA=pB=1 extremes --
        # a real 0.5 is the honest answer for "both undefeated" or "both
        # winless", not a division-by-zero guess either way.
        return 0.5
    return round((our_win_rate - our_win_rate * opponent_win_rate) / denominator, 6)


def upset_likelihood(win_probability: Optional[float]) -> Optional[float]:
    """How surprising a result would be either way: the probability of
    the LESS-favored side winning this specific match. 0.5 at an even
    match (no real upset either way), approaching 0 as one side becomes
    the heavy real favorite. None when there's no real win probability to
    derive it from."""
    if win_probability is None:
        return None
    return round(min(win_probability, 1.0 - win_probability), 6)


@dataclass(frozen=True)
class RemainingMatchProjection:
    """One real remaining match's real projection.

    ``probability_source`` names exactly which real rate(s) produced
    ``win_probability`` -- see ProbabilitySource. A renderer showing
    OUR_RATE_ONLY/OPPONENT_RATE_ONLY next to the number is the documented
    fix for the audit finding that a bare fallback number reads as if
    both sides' real records were used.
    """

    match_id: str
    opponent_team_id: Optional[str]
    opponent_team_name: Optional[str]
    week: Optional[int]
    win_probability: Optional[float]
    upset_likelihood: Optional[float]
    probability_source: ProbabilitySource


@dataclass(frozen=True)
class SeasonProjection:
    """The real remaining schedule's aggregate projection.

    ``coverage`` is the fraction of ``matches`` that received a real
    ``win_probability`` (a match with no decided-game record on either
    side does not count) -- ``None`` when there is no remaining schedule
    at all, never a division by zero.

    No categorical "high upset risk" bucket is produced here: Issue #14's
    audit found the caller-supplied 0.40 cutoff unfitted to any real APA
    outcome, and docs/season_projection.md's own design says the demo
    presents the raw numeric ``upset_likelihood`` per match, not a
    categorical warning built from an arbitrary threshold. Each
    RemainingMatchProjection already carries its own real
    ``upset_likelihood``; a caller wanting a "worst matchups" view sorts
    on that real number directly rather than this module producing an
    invented bucket.
    """

    matches: list[RemainingMatchProjection]
    expected_wins: float
    expected_losses: float
    coverage: Optional[float]


def _probability_source(
    our_win_rate: Optional[float], opponent_win_rate: Optional[float]
) -> ProbabilitySource:
    if our_win_rate is not None and opponent_win_rate is not None:
        return ProbabilitySource.BOTH_RATES
    if our_win_rate is not None:
        return ProbabilitySource.OUR_RATE_ONLY
    if opponent_win_rate is not None:
        return ProbabilitySource.OPPONENT_RATE_ONLY
    return ProbabilitySource.NO_RATE


def project_remaining_schedule(
    remaining_matches: list[dict[str, Any]],
    our_win_rate: Optional[float],
    opponent_win_rates: dict[str, float],
) -> SeasonProjection:
    """Project the real remaining schedule.

    `remaining_matches` is a list of real dicts, each needing
    `match_id`/`opponent_team_id`/`opponent_team_name`/`week` -- the same
    real shape ui.export_json._schedule already produces for unplayed
    matches (is_scored is False). `opponent_win_rates` keys on real
    opponent team_id -> that opponent's own real season win rate, when
    known; a missing key means "no real record for this specific
    opponent yet", handled by log5_win_probability's own fallback, not by
    this function guessing one.

    A remaining match with no real win_probability at all (neither side
    has any decided games) is still included in `matches` (for real
    schedule visibility) but contributes nothing to `expected_wins`/
    `expected_losses` and does not count toward `coverage` -- absence of
    evidence is not evidence of anything.
    """
    projections = []
    for match in remaining_matches:
        opponent_id = match.get("opponent_team_id")
        opponent_rate = opponent_win_rates.get(opponent_id) if opponent_id else None
        probability = log5_win_probability(our_win_rate, opponent_rate)
        projections.append(RemainingMatchProjection(
            match_id=match.get("match_id", ""),
            opponent_team_id=opponent_id,
            opponent_team_name=match.get("opponent_team_name"),
            week=match.get("week"),
            win_probability=probability,
            upset_likelihood=upset_likelihood(probability),
            probability_source=_probability_source(our_win_rate, opponent_rate),
        ))

    decided = [p for p in projections if p.win_probability is not None]
    expected_wins = round(sum(p.win_probability for p in decided), 6)
    expected_losses = round(sum(1.0 - p.win_probability for p in decided), 6)
    coverage = round(len(decided) / len(projections), 6) if projections else None

    return SeasonProjection(
        matches=projections,
        expected_wins=expected_wins,
        expected_losses=expected_losses,
        coverage=coverage,
    )


@dataclass(frozen=True)
class StandingsPoint:
    """One real point on the team volatility curve."""

    captured_at: str
    wins: Optional[int]
    losses: Optional[int]
    win_rate: Optional[float]


def team_volatility_curve(standings_history: list[dict[str, Any]]) -> list[StandingsPoint]:
    """The real, historical win-rate trend for one team, from every real
    StandingsSnapshot capture -- deduplicated to only the captures where
    the real (wins, losses) record actually CHANGED.

    `standings_history` must already be sorted by real `captured_at`
    ascending (the same order database.queries.standings_history already
    returns). Without deduplication, a team synced dozens of times a day
    with no new real result would show a "curve" that is really just
    noise from how often the pipeline happened to run -- collapsing
    repeated identical records to their first real occurrence shows only
    real, meaningful changes.

    Genuinely flat: a real team with no decided games change across every
    real capture yields a single point, honestly reflecting that no real
    volatility exists yet to show -- not synthesized to look more
    interesting than the real data is.
    """
    points: list[StandingsPoint] = []
    last_record: Optional[tuple[Optional[int], Optional[int]]] = None
    for row in standings_history:
        wins, losses = row.get("wins"), row.get("losses")
        record = (wins, losses)
        if record == last_record:
            continue
        points.append(StandingsPoint(
            captured_at=row.get("captured_at", ""),
            wins=wins,
            losses=losses,
            win_rate=win_rate(wins, losses),
        ))
        last_record = record
    return points
