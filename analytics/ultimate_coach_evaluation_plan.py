"""Deterministic chronological evaluation plan for Ultimate Coach research.

This module plans expanding-window train/holdout folds only. It never fits a
model, scores a probability, chooses coefficients, or unlocks publication.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from analytics.ultimate_coach_backtest_readiness import build_backtest_readiness
from analytics.ultimate_coach_prequential_features import build_prequential_feature_rows


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("prequential target_time must be timezone-aware")
    return parsed


def build_evaluation_plan(
    all_games: list[dict[str, Any]],
    fmt: str,
    *,
    min_train_targets: int = 20,
    holdout_instants: int = 5,
    readiness_kwargs: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Plan expanding-window folds without splitting simultaneous games.

    A fold is admitted only when every training target is strictly earlier than
    every holdout target. ``holdout_instants`` counts unique chronological
    instants, not rows, so doubleheaders/same-time batches are never divided
    between train and holdout.
    """
    if not isinstance(min_train_targets, int) or min_train_targets < 1:
        raise ValueError("min_train_targets must be a positive integer")
    if not isinstance(holdout_instants, int) or holdout_instants < 1:
        raise ValueError("holdout_instants must be a positive integer")

    readiness = build_backtest_readiness(
        all_games, fmt, **(readiness_kwargs or {})
    )
    prequential = build_prequential_feature_rows(all_games, fmt)
    rows = prequential["feature_rows"]

    by_time: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_time[_instant(row["target_time"])].append(row)
    instants = sorted(by_time)

    folds: list[dict[str, Any]] = []
    skipped = defaultdict(int)
    for holdout_start in range(1, len(instants), holdout_instants):
        holdout_times = instants[holdout_start:holdout_start + holdout_instants]
        if not holdout_times:
            continue
        first_holdout = holdout_times[0]
        train = [row for when in instants if when < first_holdout for row in by_time[when]]
        holdout = [row for when in holdout_times for row in by_time[when]]
        if len(train) < min_train_targets:
            skipped["INSUFFICIENT_TRAIN_TARGETS"] += 1
            continue

        train_keys = [row["target_game_key"] for row in train]
        holdout_keys = [row["target_game_key"] for row in holdout]
        overlap = sorted(set(train_keys) & set(holdout_keys))
        if overlap:
            raise ValueError("train/holdout provenance overlap")

        folds.append({
            "fold_number": len(folds) + 1,
            "format": prequential["format"],
            "train_target_count": len(train),
            "holdout_target_count": len(holdout),
            "train_game_keys": train_keys,
            "holdout_game_keys": holdout_keys,
            "train_end_time": max(_instant(row["target_time"]) for row in train).isoformat(),
            "holdout_start_time": first_holdout.isoformat(),
            "holdout_end_time": holdout_times[-1].isoformat(),
            "chronology_rule": "MAX_TRAIN_TIME_STRICTLY_BEFORE_MIN_HOLDOUT_TIME",
        })

    failures: list[str] = []
    if readiness["status"] != "READY_FOR_EVALUATION_DESIGN":
        failures.append("BACKTEST_READINESS_NOT_MET")
    if not folds:
        failures.append("NO_VALID_EVALUATION_FOLDS")

    return {
        "schema": "ultimate-coach-evaluation-plan-v1",
        "format": prequential["format"],
        "status": "PLAN_READY" if not failures else "PLAN_NOT_READY",
        "probability_publication": "FORBIDDEN",
        "model_training_performed": False,
        "calibration_performed": False,
        "evaluation_executed": False,
        "readiness_status": readiness["status"],
        "min_train_targets": min_train_targets,
        "holdout_instants": holdout_instants,
        "folds": folds,
        "skipped_candidate_folds": dict(sorted(skipped.items())),
        "failures": failures,
        "interpretation": (
            "PLAN_READY means only that deterministic chronological folds exist; "
            "no model quality or calibration claim has been evaluated."
        ),
    }
