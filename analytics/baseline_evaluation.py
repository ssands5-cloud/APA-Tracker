"""Evaluate transparent pre-match probability baselines on historical examples.

This is not model fitting. It measures the already-existing skill-gap-only
probability against leakage-safe examples and reports only examples where both
real historical skill levels are available.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from analytics.backtest_dataset import BacktestExample
from analytics.calibration_metrics import (
    brier_score,
    calibration_bins,
    expected_calibration_error,
    log_loss,
)
from analytics.head_to_head import skill_only_win_probability


def _evaluate_group(examples: list[BacktestExample]) -> dict[str, Any]:
    predictions: list[float] = []
    outcomes: list[int] = []
    excluded_missing_skill = 0

    for row in examples:
        probability = skill_only_win_probability(
            row.own_skill_level,
            row.opponent_skill_level,
        )
        if probability is None:
            excluded_missing_skill += 1
            continue
        predictions.append(float(probability))
        outcomes.append(int(row.outcome_win))

    result: dict[str, Any] = {
        "examples_total": len(examples),
        "examples_evaluated": len(predictions),
        "excluded_missing_skill": excluded_missing_skill,
    }
    if not predictions:
        result.update(
            {
                "brier_score": None,
                "log_loss": None,
                "expected_calibration_error": None,
                "calibration_bins": [],
            }
        )
        return result

    result.update(
        {
            "brier_score": brier_score(predictions, outcomes),
            "log_loss": log_loss(predictions, outcomes),
            "expected_calibration_error": expected_calibration_error(
                predictions, outcomes, bins=10
            ),
            "calibration_bins": [
                asdict(row)
                for row in calibration_bins(predictions, outcomes, bins=10)
            ],
            "mean_prediction": round(sum(predictions) / len(predictions), 6),
            "observed_win_rate": round(sum(outcomes) / len(outcomes), 6),
        }
    )
    return result


def evaluate_skill_only_baseline(
    examples: list[BacktestExample],
) -> dict[str, Any]:
    """Evaluate all eligible examples plus EIGHT/NINE separately."""
    by_format = {
        "EIGHT": [row for row in examples if row.format == "EIGHT"],
        "NINE": [row for row in examples if row.format == "NINE"],
    }
    return {
        "baseline": "analytics.head_to_head:skill_only_win_probability",
        "scope": "leakage-safe historical pre-match examples with both real SLs",
        "overall": _evaluate_group(examples),
        "by_format": {
            format_name: _evaluate_group(rows)
            for format_name, rows in by_format.items()
        },
    }
