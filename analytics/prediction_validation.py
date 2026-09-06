"""Win-Probability Model Validation.

Checks ``analytics.head_to_head.win_probability`` against real recorded
match outcomes -- the model the Lineup Optimizer's ``Wij`` input comes from
(see ``analytics/lineup_optimizer.py``, spec section 1.1: Wij carries 30% of
Fij's weight). Every input here is a real ``PlayerHeadToHead`` row; nothing
is simulated or synthesized.

Two INDEPENDENT checks, kept separate because they exercise different parts
of the model and have different data requirements:

Analysis A -- the SKILL-LEVEL term in isolation. A player's
``own_skill_level`` and the opponent's ``opponent_skill_level`` are both
posted before a given match is played (APA's handicap system rates players
from history outside that specific match), so grading the skill-only
prediction against that SAME match's own W/L result is a legitimate,
non-circular test: it needs no held-out split and no walk-forward, because
the predictor (posted skill level) already existed independently of the
outcome being predicted. Runs on every row that carries both skill levels
and a recognised result.

Analysis B -- the HISTORICAL-RECORD term, which the real ``win_probability``
blends in via ``reliability_weight(n)``. This term is about a PAIRING's past
meetings, so validating it correctly requires a genuine walk-forward: for
the k-th meeting between one player and one opponent, predict using ONLY
``rows[:k]`` (strictly earlier games) and grade against game k's real
result. Scoring it against ``rows[:k+1]`` instead -- i.e. letting the
prediction see the very outcome it is being graded on -- would be circular,
not a validation. A pairing's first-ever meeting (k=0) is never scored:
``rows[:0]`` is empty, and ``win_probability(())`` correctly returns
``None`` for it (nothing prior to predict from).

Both analyses reuse the exact constants and formulas already in
``analytics.head_to_head`` / ``analytics.matchups`` -- the skill-only
ablation is not a second, possibly-drifting reimplementation of the model,
it is the same log-odds arithmetic with the record term left out.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Callable, Optional, Sequence

from analytics.head_to_head import (
    MAX_WIN_PROBABILITY,
    MIN_WIN_PROBABILITY,
    SL_LOG_ODDS_PER_LEVEL,
    win_probability,
)
from database.models import PlayerHeadToHead

LOG_LOSS_EPSILON = 1e-6
"""Clamp away from exactly 0/1 before taking a log -- a single miss on an
unclamped prediction would otherwise score +inf. win_probability() already
clamps to [0.02, 0.98] in production, so this guard exists for the
skill-only ablation below, which does not carry that clamp's rationale (it
is not the deployed model) but should not blow up on an extreme skill gap.
"""


def _actual_win(result) -> Optional[bool]:
    """True/False for a recognised W/L result, None otherwise. Same rule as
    analytics.matchups._is_win, restated locally rather than importing a
    function whose leading underscore marks it module-private."""
    normalized = str(result or "").strip().upper()
    if normalized == "W":
        return True
    if normalized == "L":
        return False
    return None


@dataclass(frozen=True)
class ScoredPrediction:
    """One real game, one model prediction, ready to grade.

    `skill_advantage` (own - opponent) and `prior_games` are descriptive
    context for the bias breakdowns below, not inputs the grading functions
    need -- either may be None where not applicable to the analysis that
    produced this row.
    """

    player_id: int
    opponent_id: int
    format: Optional[str]
    session_name: Optional[str]
    predicted_probability: float
    actual_win: bool
    skill_advantage: Optional[float] = None
    prior_games: Optional[int] = None


# --- shared grading (both analyses land here) --------------------------------

def brier_score(predictions: Sequence[ScoredPrediction]) -> Optional[float]:
    """Mean squared error between predicted probability and the 0/1 outcome.
    0 is perfect, 0.25 is what guessing 50/50 every time scores, 1 is
    perfectly and confidently wrong. None (not 0) when there is nothing to
    grade -- an empty score is not a perfect one."""
    if not predictions:
        return None
    total = sum(
        (p.predicted_probability - (1.0 if p.actual_win else 0.0)) ** 2
        for p in predictions
    )
    return round(total / len(predictions), 4)


def log_loss(predictions: Sequence[ScoredPrediction]) -> Optional[float]:
    """Mean negative log-likelihood of the real outcome under the predicted
    probability. Lower is better; guessing 50/50 every time scores ln(2)
    ~= 0.6931."""
    if not predictions:
        return None
    total = 0.0
    for p in predictions:
        prob = min(max(p.predicted_probability, LOG_LOSS_EPSILON), 1 - LOG_LOSS_EPSILON)
        y = 1.0 if p.actual_win else 0.0
        total += -(y * math.log(prob) + (1 - y) * math.log(1 - prob))
    return round(total / len(predictions), 4)


def accuracy(predictions: Sequence[ScoredPrediction]) -> Optional[float]:
    """Fraction of games where the favoured side (predicted probability
    >= 0.5) actually won. A coarser, more readable companion to Brier/log
    loss -- it throws away HOW confident the model was, which is exactly
    why it is reported alongside them rather than instead of them."""
    if not predictions:
        return None
    correct = sum(1 for p in predictions if (p.predicted_probability >= 0.5) == p.actual_win)
    return round(correct / len(predictions), 4)


def mean_calibration_error(predictions: Sequence[ScoredPrediction]) -> Optional[float]:
    """Mean(predicted - actual). Positive means the model is systematically
    OVER-confident about winning; negative means UNDER-confident. This can
    read as ~0 even for a badly miscalibrated model if over- and
    under-confident errors cancel out -- that is exactly why
    calibration_curve() below exists alongside it rather than in place of
    it."""
    if not predictions:
        return None
    total = sum(p.predicted_probability - (1.0 if p.actual_win else 0.0) for p in predictions)
    return round(total / len(predictions), 4)


@dataclass(frozen=True)
class CalibrationBucket:
    label: str
    lower: float
    upper: float
    count: int
    mean_predicted: Optional[float]
    actual_win_rate: Optional[float]


def calibration_curve(predictions: Sequence[ScoredPrediction], bins: int = 5) -> list[CalibrationBucket]:
    """Bucket predictions by predicted probability and compare each
    bucket's average prediction to its real win rate -- a well-calibrated
    model has the two columns track each other in every bucket with enough
    count to judge. 5 bins, not 10: this dataset is real and currently
    small, and finer bins would mostly report "1 game, 100% or 0%" -- noise
    dressed up as a systematic bias rather than an actual one.
    """
    edges = [i / bins for i in range(bins + 1)]
    buckets = []
    for lo, hi in zip(edges, edges[1:]):
        is_last_bin = math.isclose(hi, 1.0)
        in_bin = [
            p for p in predictions
            if lo <= p.predicted_probability < hi
            or (is_last_bin and math.isclose(p.predicted_probability, 1.0))
        ]
        if in_bin:
            mean_pred = round(sum(p.predicted_probability for p in in_bin) / len(in_bin), 4)
            win_rate = round(sum(1 for p in in_bin if p.actual_win) / len(in_bin), 4)
        else:
            mean_pred = None
            win_rate = None
        buckets.append(CalibrationBucket(f"[{lo:.1f}-{hi:.1f})", lo, hi, len(in_bin), mean_pred, win_rate))
    return buckets


@dataclass(frozen=True)
class ValidationSummary:
    label: str
    n: int
    brier: Optional[float]
    log_loss: Optional[float]
    accuracy: Optional[float]
    mean_calibration_error: Optional[float]
    calibration: list[CalibrationBucket]


def summarize(label: str, predictions: Sequence[ScoredPrediction], bins: int = 5) -> ValidationSummary:
    return ValidationSummary(
        label=label,
        n=len(predictions),
        brier=brier_score(predictions),
        log_loss=log_loss(predictions),
        accuracy=accuracy(predictions),
        mean_calibration_error=mean_calibration_error(predictions),
        calibration=calibration_curve(predictions, bins=bins),
    )


def naive_baseline(predictions: Sequence[ScoredPrediction], probability: float = 0.5) -> list[ScoredPrediction]:
    """The same real outcomes, re-scored as though the model had predicted
    a constant `probability` every time -- the "always guess 50/50" floor
    any real model needs to beat to be worth using."""
    return [replace(p, predicted_probability=probability) for p in predictions]


def group_summaries(
    predictions: Sequence[ScoredPrediction],
    key: Callable[[ScoredPrediction], str],
    bins: int = 5,
) -> dict[str, ValidationSummary]:
    """Split predictions by `key` and summarize each bucket independently --
    the mechanism behind every bias breakdown below (by format, by skill
    direction, by sample depth)."""
    buckets: dict[str, list[ScoredPrediction]] = defaultdict(list)
    for prediction in predictions:
        buckets[key(prediction)].append(prediction)
    return {label: summarize(label, preds, bins=bins) for label, preds in buckets.items()}


def format_label(prediction: ScoredPrediction) -> str:
    return prediction.format or "unknown format"


def skill_direction_label(prediction: ScoredPrediction) -> str:
    """Descriptive bucket for the SAME game's own skill gap, regardless of
    which analysis produced the prediction -- lets a bias check ask "is the
    model worse for underdogs?" independently of which term made the call.
    """
    advantage = prediction.skill_advantage
    if advantage is None:
        return "unknown skill gap"
    if advantage > 0:
        return "favored (higher SL)"
    if advantage < 0:
        return "underdog (lower SL)"
    return "even SL"


def prior_games_label(prediction: ScoredPrediction) -> str:
    """Descriptive bucket for how much pairing history existed before this
    prediction -- Analysis B only; a small bucket count here does not mean
    a rare event, it means walk-forward evidence is still thin overall."""
    n = prediction.prior_games
    if n is None:
        return "unknown"
    if n <= 1:
        return "1 prior game"
    if n <= 3:
        return "2-3 prior games"
    if n <= 6:
        return "4-6 prior games"
    return "7+ prior games"


# --- Analysis A: skill-level term, cross-sectional ---------------------------

def skill_only_probability(own_skill_level: float, opponent_skill_level: float) -> float:
    """The same logistic-in-log-odds shape analytics.head_to_head.win_probability
    uses, with the historical-record term dropped entirely -- isolates what
    the posted skill-level gap ALONE would have predicted for this game.
    Reuses SL_LOG_ODDS_PER_LEVEL from the real model so this can never
    quietly drift from the constant actually in production.
    """
    advantage = own_skill_level - opponent_skill_level
    log_odds = SL_LOG_ODDS_PER_LEVEL * advantage
    probability = 1 / (1 + math.exp(-log_odds))
    return min(MAX_WIN_PROBABILITY, max(MIN_WIN_PROBABILITY, probability))


def score_skill_only(rows: Sequence[PlayerHeadToHead]) -> list[ScoredPrediction]:
    """Analysis A over every row that carries both skill levels and a
    recognised result. Row order does not matter here -- each row is
    scored against its OWN game using facts (posted skill levels) that
    exist independently of that game's own outcome, so there is no
    walk-forward and no lookahead concern to manage.
    """
    scored = []
    for row in rows:
        actual = _actual_win(row.result)
        if actual is None:
            continue
        if row.own_skill_level is None or row.opponent_skill_level is None:
            continue
        predicted = skill_only_probability(row.own_skill_level, row.opponent_skill_level)
        scored.append(ScoredPrediction(
            player_id=row.player_id,
            opponent_id=row.opponent_id,
            format=row.format,
            session_name=row.session_name,
            predicted_probability=predicted,
            actual_win=actual,
            skill_advantage=row.own_skill_level - row.opponent_skill_level,
        ))
    return scored


# --- Analysis B: historical-record term, walk-forward per pairing -----------

def score_walk_forward(rows: Sequence[PlayerHeadToHead]) -> list[ScoredPrediction]:
    """Analysis B over one already-ordered (player, opponent, format,
    session) pairing group -- oldest first, exactly as
    scripts.build_head_to_head.ordered_rows / group_by_pairing deliver.

    For the k-th meeting, predicts using ``win_probability(rows[:k])`` --
    strictly earlier games only -- and grades it against that meeting's own
    result. The first meeting (k=0) is skipped: ``rows[:0]`` is empty, and
    ``win_probability`` correctly returns None for it -- there is no prior
    evidence to predict from, and treating a first meeting as predictable
    would misrepresent the model.
    """
    scored = []
    for k in range(1, len(rows)):
        game = rows[k]
        actual = _actual_win(game.result)
        if actual is None:
            continue
        prior = rows[:k]
        predicted = win_probability(prior)
        if predicted is None:
            continue
        prior_recognized = [r for r in prior if _actual_win(r.result) is not None]
        skill_advantage = None
        if game.own_skill_level is not None and game.opponent_skill_level is not None:
            skill_advantage = game.own_skill_level - game.opponent_skill_level
        scored.append(ScoredPrediction(
            player_id=game.player_id,
            opponent_id=game.opponent_id,
            format=game.format,
            session_name=game.session_name,
            predicted_probability=predicted,
            actual_win=actual,
            skill_advantage=skill_advantage,
            prior_games=len(prior_recognized),
        ))
    return scored


def score_all_pairings(groups: dict[tuple, list[PlayerHeadToHead]]) -> list[ScoredPrediction]:
    """score_walk_forward() applied across every pairing group, flattened
    into one list. `groups` is expected in the shape
    scripts.build_head_to_head.group_by_pairing produces."""
    scored: list[ScoredPrediction] = []
    for pair_rows in groups.values():
        scored.extend(score_walk_forward(pair_rows))
    return scored
