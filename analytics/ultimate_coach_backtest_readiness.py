"""Fail-closed readiness report for future Ultimate Coach calibration/backtests.

This module does not train or score a model. It inspects leakage-safe
prequential feature rows and reports whether the real historical archive has
enough auditable support to begin a later evaluation stage.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from analytics.ultimate_coach_prequential_features import build_prequential_feature_rows


DEFAULT_MIN_TARGETS = 30
DEFAULT_MIN_PLAYERS = 8
DEFAULT_MIN_PRIOR_SUPPORTED = 15
DEFAULT_MIN_DIRECT_SUPPORTED = 5


def _distinct_players(rows: list[dict[str, Any]]) -> set[int]:
    ids: set[int] = set()
    for row in rows:
        for key in ("participant_a_id", "participant_b_id"):
            value = row.get(key)
            if isinstance(value, int):
                ids.add(value)
    return ids


def build_backtest_readiness(
    all_games: list[dict[str, Any]],
    fmt: str,
    *,
    min_targets: int = DEFAULT_MIN_TARGETS,
    min_players: int = DEFAULT_MIN_PLAYERS,
    min_prior_supported: int = DEFAULT_MIN_PRIOR_SUPPORTED,
    min_direct_supported: int = DEFAULT_MIN_DIRECT_SUPPORTED,
) -> dict[str, Any]:
    """Summarize whether one format has enough safe history for later testing.

    Thresholds are readiness policy, not statistical validation. Meeting them
    means only that a future model/backtest may be attempted. Probability
    publication remains forbidden until an independently audited chronological
    evaluation and calibration gate passes on real archive data.
    """
    thresholds = {
        "min_targets": min_targets,
        "min_players": min_players,
        "min_prior_supported": min_prior_supported,
        "min_direct_supported": min_direct_supported,
    }
    if any(not isinstance(value, int) or value < 1 for value in thresholds.values()):
        raise ValueError("all readiness thresholds must be positive integers")

    prequential = build_prequential_feature_rows(all_games, fmt)
    rows = prequential["feature_rows"]
    target_count = len(rows)
    player_count = len(_distinct_players(rows))
    prior_supported = sum(bool(row.get("prior_game_keys")) for row in rows)
    direct_supported = sum(bool(row.get("direct_prior_game_keys")) for row in rows)
    shared_supported = sum(int(row.get("shared_opponent_count") or 0) > 0 for row in rows)

    failures: list[str] = []
    if target_count < min_targets:
        failures.append("INSUFFICIENT_TARGET_GAMES")
    if player_count < min_players:
        failures.append("INSUFFICIENT_DISTINCT_PLAYERS")
    if prior_supported < min_prior_supported:
        failures.append("INSUFFICIENT_PRIOR_SUPPORTED_TARGETS")
    if direct_supported < min_direct_supported:
        failures.append("INSUFFICIENT_DIRECT_HISTORY_TARGETS")

    provenance_keys = [row["target_game_key"] for row in rows]
    duplicate_targets = sorted(key for key, count in Counter(provenance_keys).items() if count > 1)
    if duplicate_targets:
        failures.append("DUPLICATE_TARGET_PROVENANCE")

    return {
        "schema": "ultimate-coach-backtest-readiness-v1",
        "format": prequential["format"],
        "status": "READY_FOR_EVALUATION_DESIGN" if not failures else "NOT_READY",
        "probability_publication": "FORBIDDEN",
        "model_training_performed": False,
        "calibration_performed": False,
        "thresholds": thresholds,
        "counts": {
            "eligible_targets": target_count,
            "distinct_players": player_count,
            "targets_with_any_prior_history": prior_supported,
            "targets_with_direct_prior_history": direct_supported,
            "targets_with_shared_opponent_history": shared_supported,
        },
        "excluded_source_rows": dict(prequential.get("excluded", {})),
        "failures": failures,
        "target_game_keys": provenance_keys,
        "duplicate_target_game_keys": duplicate_targets,
        "interpretation": (
            "Readiness only permits design/execution of a future held-out evaluation; "
            "it is not evidence of predictive validity or calibration."
        ),
    }
