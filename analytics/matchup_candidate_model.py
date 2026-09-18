"""Research-only calibrated matchup candidate for Ultimate Coach.

This module deliberately trains ONLY on BacktestExample fields that were built
from information available before each historical match. Current lifetime
career aggregates, current roster snapshots, player names/ids, and any future
outcomes are forbidden from the feature vector.

The trained artifact is research evidence, never a production activation flag.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import numpy as np

from analytics.backtest_dataset import BacktestExample
from analytics.calibration_metrics import (
    brier_score,
    calibration_bins,
    expected_calibration_error,
    log_loss,
)
from analytics.head_to_head import skill_only_win_probability

FEATURE_NAMES = (
    "skill_delta",
    "skill_available",
    "direct_edge",
    "direct_available",
    "log1p_direct_games",
    "overall_rate_delta",
    "overall_available",
    "log1p_player_games",
    "log1p_opponent_games",
    "recent_rate_delta",
    "recent_available",
    "shared_rate_delta",
    "shared_available",
    "log1p_shared_games_min",
    "log1p_shared_opponents",
)

DEFAULT_MIN_TRAIN = 200
DEFAULT_MIN_CALIBRATION = 75
DEFAULT_MIN_TEST = 75


@dataclass(frozen=True)
class ChronologicalSplit:
    train: tuple[BacktestExample, ...]
    calibration: tuple[BacktestExample, ...]
    test: tuple[BacktestExample, ...]
    train_end: str | None
    calibration_end: str | None
    test_end: str | None


@dataclass(frozen=True)
class LogisticArtifact:
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    intercept: float
    coefficients: tuple[float, ...]
    l2: float
    iterations: int


@dataclass(frozen=True)
class CalibratorArtifact:
    mean_logit: float
    scale_logit: float
    intercept: float
    slope: float
    l2: float
    iterations: int


def _parse_aware_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"backtest match date is not timezone-aware: {value!r}")
    return parsed


def _pair_delta(left: float | None, right: float | None) -> tuple[float, float]:
    if left is None or right is None:
        return 0.0, 0.0
    return float(left) - float(right), 1.0


def feature_vector(row: BacktestExample) -> tuple[float, ...]:
    """Directional pre-match features plus explicit availability indicators.

    Missing evidence is represented as delta=0 AND availability=0. A genuinely
    equal observed pair has delta=0 AND availability=1, so absence is never
    silently treated as a neutral/equal fact.
    """
    skill_delta = float(row.skill_delta or 0.0)
    skill_available = 1.0 if row.skill_delta is not None else 0.0

    direct_edge = (
        float(row.direct_win_rate_before) - 0.5
        if row.direct_win_rate_before is not None
        else 0.0
    )
    direct_available = 1.0 if row.direct_win_rate_before is not None else 0.0

    overall_delta, overall_available = _pair_delta(
        row.player_win_rate_before, row.opponent_win_rate_before
    )
    recent_delta, recent_available = _pair_delta(
        row.player_recent5_win_rate, row.opponent_recent5_win_rate
    )
    shared_delta, shared_available = _pair_delta(
        row.player_shared_win_rate_before, row.opponent_shared_win_rate_before
    )

    return (
        skill_delta,
        skill_available,
        direct_edge,
        direct_available,
        math.log1p(max(0, int(row.direct_games_before))),
        overall_delta,
        overall_available,
        math.log1p(max(0, int(row.player_games_before))),
        math.log1p(max(0, int(row.opponent_games_before))),
        recent_delta,
        recent_available,
        shared_delta,
        shared_available,
        math.log1p(
            max(
                0,
                min(
                    int(row.player_shared_games_before),
                    int(row.opponent_shared_games_before),
                ),
            )
        ),
        math.log1p(max(0, int(row.shared_opponent_count_before))),
    )


def feature_matrix(rows: list[BacktestExample] | tuple[BacktestExample, ...]) -> np.ndarray:
    if not rows:
        return np.empty((0, len(FEATURE_NAMES)), dtype=float)
    return np.asarray([feature_vector(row) for row in rows], dtype=float)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    clipped = np.clip(z, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _fit_logistic(
    x: np.ndarray,
    y: np.ndarray,
    *,
    l2: float = 1.0,
    max_iter: int = 100,
    tol: float = 1e-8,
) -> LogisticArtifact:
    if x.ndim != 2 or x.shape[0] != y.shape[0] or not len(y):
        raise ValueError("x/y shapes are invalid for logistic fitting")
    if len(np.unique(y)) < 2:
        raise ValueError("logistic fitting requires both outcome classes")

    means = x.mean(axis=0)
    scales = x.std(axis=0)
    scales = np.where(scales < 1e-12, 1.0, scales)
    z = (x - means) / scales
    design = np.column_stack([np.ones(len(z)), z])
    beta = np.zeros(design.shape[1], dtype=float)
    regularizer = np.eye(design.shape[1], dtype=float) * float(l2)
    regularizer[0, 0] = 0.0

    iterations = 0
    for iterations in range(1, max_iter + 1):
        p = _sigmoid(design @ beta)
        weights = np.clip(p * (1.0 - p), 1e-6, None)
        gradient = design.T @ (y - p) - regularizer @ beta
        information = design.T @ (design * weights[:, None]) + regularizer
        try:
            step = np.linalg.solve(information, gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.pinv(information) @ gradient
        beta = beta + step
        if float(np.max(np.abs(step))) < tol:
            break

    return LogisticArtifact(
        feature_names=FEATURE_NAMES,
        means=tuple(float(v) for v in means),
        scales=tuple(float(v) for v in scales),
        intercept=float(beta[0]),
        coefficients=tuple(float(v) for v in beta[1:]),
        l2=float(l2),
        iterations=iterations,
    )


def _raw_logits(model: LogisticArtifact, x: np.ndarray) -> np.ndarray:
    means = np.asarray(model.means, dtype=float)
    scales = np.asarray(model.scales, dtype=float)
    coefficients = np.asarray(model.coefficients, dtype=float)
    return model.intercept + ((x - means) / scales) @ coefficients


def _predict_raw(model: LogisticArtifact, x: np.ndarray) -> np.ndarray:
    return _sigmoid(_raw_logits(model, x))


def _fit_calibrator(
    raw_probabilities: np.ndarray,
    y: np.ndarray,
    *,
    l2: float = 0.05,
    max_iter: int = 100,
    tol: float = 1e-8,
) -> CalibratorArtifact:
    """Fit Platt scaling directly on one normalized raw-model logit.

    The saved intercept/slope are the exact parameters used by
    _apply_calibrator. No hidden second scaler exists between training and
    inference.
    """
    if len(raw_probabilities) != len(y) or not len(y):
        raise ValueError("calibration arrays are invalid")
    if len(np.unique(y)) < 2:
        raise ValueError("calibration requires both outcome classes")

    p = np.clip(raw_probabilities, 1e-6, 1.0 - 1e-6)
    logits = np.log(p / (1.0 - p))
    mean = float(logits.mean())
    scale = float(logits.std())
    if scale < 1e-12:
        scale = 1.0
    x = (logits - mean) / scale
    design = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(2, dtype=float)
    regularizer = np.diag([0.0, float(l2)])

    iterations = 0
    for iterations in range(1, max_iter + 1):
        predicted = _sigmoid(design @ beta)
        weights = np.clip(predicted * (1.0 - predicted), 1e-6, None)
        gradient = design.T @ (y - predicted) - regularizer @ beta
        information = design.T @ (design * weights[:, None]) + regularizer
        try:
            step = np.linalg.solve(information, gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.pinv(information) @ gradient
        beta = beta + step
        if float(np.max(np.abs(step))) < tol:
            break

    return CalibratorArtifact(
        mean_logit=mean,
        scale_logit=scale,
        intercept=float(beta[0]),
        slope=float(beta[1]),
        l2=float(l2),
        iterations=iterations,
    )


def _apply_calibrator(
    calibrator: CalibratorArtifact,
    raw_probabilities: np.ndarray,
) -> np.ndarray:
    p = np.clip(raw_probabilities, 1e-6, 1.0 - 1e-6)
    logits = np.log(p / (1.0 - p))
    x = (logits - calibrator.mean_logit) / calibrator.scale_logit
    return _sigmoid(calibrator.intercept + calibrator.slope * x)


def chronological_split(
    rows: list[BacktestExample],
    *,
    train_fraction: float = 0.60,
    calibration_fraction: float = 0.20,
) -> ChronologicalSplit:
    """Split by whole timestamps so one match-time cannot cross boundaries."""
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError("calibration_fraction must be between 0 and 1")
    if train_fraction + calibration_fraction >= 1.0:
        raise ValueError("train + calibration fractions must leave a test window")

    buckets: dict[datetime, list[BacktestExample]] = {}
    for row in rows:
        when = _parse_aware_iso(row.match_date)
        buckets.setdefault(when, []).append(row)
    times = sorted(buckets)
    if len(times) < 3:
        return ChronologicalSplit((), (), (), None, None, None)

    train_count = max(1, int(len(times) * train_fraction))
    calibration_count = max(1, int(len(times) * calibration_fraction))
    if train_count + calibration_count >= len(times):
        calibration_count = max(1, len(times) - train_count - 1)
    if train_count + calibration_count >= len(times):
        train_count = max(1, len(times) - 2)
        calibration_count = 1

    train_times = times[:train_count]
    calibration_times = times[train_count : train_count + calibration_count]
    test_times = times[train_count + calibration_count :]

    def gather(selected: list[datetime]) -> tuple[BacktestExample, ...]:
        return tuple(
            row
            for when in selected
            for row in sorted(
                buckets[when],
                key=lambda item: (item.match_id, item.player_id, item.opponent_id),
            )
        )

    train = gather(train_times)
    calibration = gather(calibration_times)
    test = gather(test_times)
    return ChronologicalSplit(
        train=train,
        calibration=calibration,
        test=test,
        train_end=train_times[-1].isoformat() if train_times else None,
        calibration_end=calibration_times[-1].isoformat() if calibration_times else None,
        test_end=test_times[-1].isoformat() if test_times else None,
    )


def _metrics(predictions: np.ndarray, outcomes: np.ndarray) -> dict[str, Any]:
    if not len(predictions):
        return {
            "count": 0,
            "brier_score": None,
            "log_loss": None,
            "expected_calibration_error": None,
            "calibration_bins": [],
        }
    p = [float(v) for v in predictions]
    y = [int(v) for v in outcomes]
    return {
        "count": len(p),
        "brier_score": brier_score(p, y),
        "log_loss": log_loss(p, y),
        "expected_calibration_error": expected_calibration_error(p, y, bins=10),
        "calibration_bins": [asdict(row) for row in calibration_bins(p, y, bins=10)],
        "mean_prediction": round(sum(p) / len(p), 6),
        "observed_win_rate": round(sum(y) / len(y), 6),
    }


def _baseline_predictions(rows: tuple[BacktestExample, ...]) -> tuple[np.ndarray, np.ndarray, list[int]]:
    probabilities: list[float] = []
    outcomes: list[int] = []
    indices: list[int] = []
    for index, row in enumerate(rows):
        probability = skill_only_win_probability(
            row.own_skill_level, row.opponent_skill_level
        )
        if probability is None:
            continue
        probabilities.append(float(probability))
        outcomes.append(int(row.outcome_win))
        indices.append(index)
    return (
        np.asarray(probabilities, dtype=float),
        np.asarray(outcomes, dtype=int),
        indices,
    )


def train_format_candidate(
    rows: list[BacktestExample],
    *,
    format_name: str,
    min_train: int = DEFAULT_MIN_TRAIN,
    min_calibration: int = DEFAULT_MIN_CALIBRATION,
    min_test: int = DEFAULT_MIN_TEST,
    l2: float = 1.0,
) -> dict[str, Any]:
    format_name = str(format_name).upper()
    selected = [row for row in rows if row.format == format_name]
    split = chronological_split(selected)

    report: dict[str, Any] = {
        "format": format_name,
        "status": "INSUFFICIENT_DATA",
        "feature_policy": (
            "pre-match backtest fields only; current lifetime/career aggregates, "
            "names, ids and future outcomes forbidden"
        ),
        "feature_names": list(FEATURE_NAMES),
        "split": {
            "train": len(split.train),
            "calibration": len(split.calibration),
            "test": len(split.test),
            "train_end": split.train_end,
            "calibration_end": split.calibration_end,
            "test_end": split.test_end,
        },
        "minimums": {
            "train": min_train,
            "calibration": min_calibration,
            "test": min_test,
        },
    }

    if (
        len(split.train) < min_train
        or len(split.calibration) < min_calibration
        or len(split.test) < min_test
    ):
        report["reason"] = "chronological split does not meet minimum sample requirements"
        return report

    y_train = np.asarray([row.outcome_win for row in split.train], dtype=int)
    y_cal = np.asarray([row.outcome_win for row in split.calibration], dtype=int)
    y_test = np.asarray([row.outcome_win for row in split.test], dtype=int)
    if any(len(np.unique(y)) < 2 for y in (y_train, y_cal, y_test)):
        report["reason"] = "one chronological window lacks both outcome classes"
        return report

    model = _fit_logistic(feature_matrix(split.train), y_train, l2=l2)
    raw_cal = _predict_raw(model, feature_matrix(split.calibration))
    calibrator = _fit_calibrator(raw_cal, y_cal)
    raw_test = _predict_raw(model, feature_matrix(split.test))
    calibrated_test = _apply_calibrator(calibrator, raw_test)

    baseline_p, baseline_y, comparable_indices = _baseline_predictions(split.test)
    candidate_comparable = calibrated_test[np.asarray(comparable_indices, dtype=int)]

    candidate_all_metrics = _metrics(calibrated_test, y_test)
    candidate_comparable_metrics = _metrics(candidate_comparable, baseline_y)
    baseline_metrics = _metrics(baseline_p, baseline_y)

    thresholds = {
        "minimum_comparable_test_examples": min_test,
        "minimum_brier_improvement": 0.001,
        "minimum_log_loss_improvement": 0.001,
        "maximum_ece_regression": 0.02,
    }

    reasons: list[str] = []
    if len(baseline_y) < min_test:
        reasons.append("too few skill-baseline-comparable final-test examples")
    if baseline_metrics["brier_score"] is not None:
        improvement = baseline_metrics["brier_score"] - candidate_comparable_metrics["brier_score"]
        if improvement < thresholds["minimum_brier_improvement"]:
            reasons.append("candidate did not improve Brier score by the research threshold")
    if baseline_metrics["log_loss"] is not None:
        improvement = baseline_metrics["log_loss"] - candidate_comparable_metrics["log_loss"]
        if improvement < thresholds["minimum_log_loss_improvement"]:
            reasons.append("candidate did not improve log loss by the research threshold")
    if (
        baseline_metrics["expected_calibration_error"] is not None
        and candidate_comparable_metrics["expected_calibration_error"] is not None
        and candidate_comparable_metrics["expected_calibration_error"]
        > baseline_metrics["expected_calibration_error"] + thresholds["maximum_ece_regression"]
    ):
        reasons.append("candidate calibration error regressed beyond the research tolerance")

    report.update(
        {
            "status": "RESEARCH_GATE_PASS" if not reasons else "RESEARCH_GATE_FAIL",
            "research_gate_reasons": reasons,
            "research_gate_thresholds": thresholds,
            "model": asdict(model),
            "calibrator": asdict(calibrator),
            "metrics": {
                "candidate_all_test": candidate_all_metrics,
                "candidate_baseline_comparable_test": candidate_comparable_metrics,
                "skill_only_baseline_test": baseline_metrics,
            },
            "activation": "FORBIDDEN_PENDING_LIVE_REVIEW_AND_INDEPENDENT_AUDIT",
        }
    )
    return report


def train_candidate_models(
    rows: list[BacktestExample],
    **kwargs,
) -> dict[str, Any]:
    return {
        "schema": "ultimate-coach-candidate-model-v1",
        "activation": "FORBIDDEN_PENDING_LIVE_REVIEW_AND_INDEPENDENT_AUDIT",
        "formats": {
            format_name: train_format_candidate(
                rows, format_name=format_name, **kwargs
            )
            for format_name in ("EIGHT", "NINE")
        },
    }
