"""Calibration metrics for historical matchup probability backtests."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_prediction: float | None
    observed_rate: float | None


def _validate(predictions: list[float], outcomes: list[int]) -> None:
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have the same length")
    if not predictions:
        raise ValueError("at least one prediction is required")
    if any(not 0.0 <= float(p) <= 1.0 for p in predictions):
        raise ValueError("every prediction must be between 0 and 1")
    if any(int(y) not in (0, 1) for y in outcomes):
        raise ValueError("every outcome must be 0 or 1")


def brier_score(predictions: list[float], outcomes: list[int]) -> float:
    _validate(predictions, outcomes)
    return round(
        sum((float(p) - int(y)) ** 2 for p, y in zip(predictions, outcomes))
        / len(predictions),
        6,
    )


def log_loss(predictions: list[float], outcomes: list[int], eps: float = 1e-12) -> float:
    _validate(predictions, outcomes)
    losses = []
    for p, y in zip(predictions, outcomes):
        clipped = min(1.0 - eps, max(eps, float(p)))
        losses.append(-(int(y) * math.log(clipped) + (1 - int(y)) * math.log(1 - clipped)))
    return round(sum(losses) / len(losses), 6)


def calibration_bins(
    predictions: list[float],
    outcomes: list[int],
    *,
    bins: int = 10,
) -> list[CalibrationBin]:
    _validate(predictions, outcomes)
    if bins < 2:
        raise ValueError("bins must be at least 2")

    grouped: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in zip(predictions, outcomes):
        index = min(int(float(p) * bins), bins - 1)
        grouped[index].append((float(p), int(y)))

    result = []
    for index, rows in enumerate(grouped):
        lower = index / bins
        upper = (index + 1) / bins
        if rows:
            mean_prediction = round(sum(p for p, _ in rows) / len(rows), 6)
            observed_rate = round(sum(y for _, y in rows) / len(rows), 6)
        else:
            mean_prediction = None
            observed_rate = None
        result.append(
            CalibrationBin(
                lower=lower,
                upper=upper,
                count=len(rows),
                mean_prediction=mean_prediction,
                observed_rate=observed_rate,
            )
        )
    return result


def expected_calibration_error(
    predictions: list[float],
    outcomes: list[int],
    *,
    bins: int = 10,
) -> float:
    rows = calibration_bins(predictions, outcomes, bins=bins)
    total = len(predictions)
    return round(
        sum(
            (row.count / total) * abs(row.mean_prediction - row.observed_rate)
            for row in rows
            if row.count and row.mean_prediction is not None and row.observed_rate is not None
        ),
        6,
    )
