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
from typing import Any, Optional


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
    """One real remaining match's real projection."""

    match_id: str
    opponent_team_id: Optional[str]
    opponent_team_name: Optional[str]
    week: Optional[int]
    win_probability: Optional[float]
    upset_likelihood: Optional[float]


@dataclass(frozen=True)
class SeasonProjection:
    """The real remaining schedule's aggregate projection."""

    matches: list[RemainingMatchProjection]
    expected_wins: float
    expected_losses: float
    high_upset_risk_matches: list[RemainingMatchProjection]


def project_remaining_schedule(
    remaining_matches: list[dict[str, Any]],
    our_win_rate: Optional[float],
    opponent_win_rates: dict[str, float],
    upset_risk_threshold: float = 0.40,
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
    `expected_losses` and is never flagged as high upset risk -- absence
    of evidence is not evidence of anything.
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
        ))

    decided = [p for p in projections if p.win_probability is not None]
    expected_wins = round(sum(p.win_probability for p in decided), 6)
    expected_losses = round(sum(1.0 - p.win_probability for p in decided), 6)
    high_upset_risk = [
        p for p in decided if p.upset_likelihood is not None and p.upset_likelihood >= upset_risk_threshold
    ]

    return SeasonProjection(
        matches=projections,
        expected_wins=expected_wins,
        expected_losses=expected_losses,
        high_upset_risk_matches=high_upset_risk,
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
