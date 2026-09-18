"""Tests for the research-only Ultimate Coach candidate model."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from analytics.backtest_dataset import BacktestExample
from analytics.matchup_candidate_model import (
    FEATURE_NAMES,
    _apply_calibrator,
    _fit_calibrator,
    _fit_logistic,
    _predict_raw,
    chronological_split,
    feature_vector,
    train_format_candidate,
)


def _row(
    index: int,
    *,
    fmt: str = "EIGHT",
    outcome: int = 1,
    skill_delta: int | None = 1,
    overall_delta: float | None = 0.2,
    recent_delta: float | None = 0.2,
    shared_delta: float | None = 0.2,
) -> BacktestExample:
    day = index + 1
    month = 1 + (day - 1) // 28
    day_in_month = 1 + (day - 1) % 28
    own_sl = 5 if skill_delta is not None else None
    opp_sl = (5 - skill_delta) if skill_delta is not None else None

    def rates(delta):
        if delta is None:
            return None, None
        return 0.5 + delta / 2, 0.5 - delta / 2

    player_rate, opponent_rate = rates(overall_delta)
    player_recent, opponent_recent = rates(recent_delta)
    player_shared, opponent_shared = rates(shared_delta)
    return BacktestExample(
        match_id=index,
        match_external_id=str(1000 + index),
        match_date=f"2024-{month:02d}-{day_in_month:02d}T19:00:00-07:00",
        format=fmt,
        session_name="S",
        player_id=1,
        opponent_id=2,
        outcome_win=outcome,
        own_skill_level=own_sl,
        opponent_skill_level=opp_sl,
        skill_delta=skill_delta,
        direct_games_before=3,
        direct_win_rate_before=0.67 if outcome else 0.33,
        player_games_before=10,
        player_win_rate_before=player_rate,
        opponent_games_before=10,
        opponent_win_rate_before=opponent_rate,
        player_recent5_win_rate=player_recent,
        opponent_recent5_win_rate=opponent_recent,
        shared_opponent_count_before=4,
        player_shared_games_before=6,
        player_shared_win_rate_before=player_shared,
        opponent_shared_games_before=6,
        opponent_shared_win_rate_before=opponent_shared,
    )


def test_missing_is_distinct_from_observed_equal_value():
    missing = _row(
        1,
        skill_delta=None,
        overall_delta=None,
        recent_delta=None,
        shared_delta=None,
    )
    equal = _row(
        2,
        skill_delta=0,
        overall_delta=0.0,
        recent_delta=0.0,
        shared_delta=0.0,
    )

    a = feature_vector(missing)
    b = feature_vector(equal)

    assert len(a) == len(FEATURE_NAMES)
    assert a[FEATURE_NAMES.index("skill_delta")] == 0.0
    assert b[FEATURE_NAMES.index("skill_delta")] == 0.0
    assert a[FEATURE_NAMES.index("skill_available")] == 0.0
    assert b[FEATURE_NAMES.index("skill_available")] == 1.0
    assert a[FEATURE_NAMES.index("overall_available")] == 0.0
    assert b[FEATURE_NAMES.index("overall_available")] == 1.0


def test_chronological_split_never_splits_same_timestamp():
    rows = [_row(i, outcome=i % 2) for i in range(1, 11)]
    duplicate = replace(rows[5], match_id=999, player_id=3, opponent_id=4)
    rows.append(duplicate)

    split = chronological_split(rows)

    train_dates = {r.match_date for r in split.train}
    cal_dates = {r.match_date for r in split.calibration}
    test_dates = {r.match_date for r in split.test}
    assert not (train_dates & cal_dates)
    assert not (train_dates & test_dates)
    assert not (cal_dates & test_dates)


def test_logistic_fitter_learns_simple_direction():
    x = np.asarray([[-3.0], [-2.0], [-1.0], [1.0], [2.0], [3.0]])
    y = np.asarray([0, 0, 0, 1, 1, 1])
    model = _fit_logistic(x, y, l2=0.5)
    p = _predict_raw(model, np.asarray([[-2.0], [2.0]]))
    assert p[0] < 0.5
    assert p[1] > 0.5


def test_platt_calibrator_returns_bounded_probabilities():
    raw = np.asarray([0.1, 0.2, 0.7, 0.8, 0.9])
    y = np.asarray([0, 0, 1, 1, 1])
    calibrator = _fit_calibrator(raw, y)
    calibrated = _apply_calibrator(calibrator, raw)
    assert np.all(calibrated > 0.0)
    assert np.all(calibrated < 1.0)
    assert calibrated[-1] > calibrated[0]


def test_insufficient_sample_never_produces_model_artifact():
    rows = [_row(i, outcome=i % 2) for i in range(1, 30)]
    report = train_format_candidate(
        rows,
        format_name="EIGHT",
        min_train=20,
        min_calibration=10,
        min_test=10,
    )
    assert report["status"] == "INSUFFICIENT_DATA"
    assert "model" not in report
    assert "calibrator" not in report


def test_research_artifact_never_claims_production_activation():
    rows = []
    # Strong, deterministic feature/outcome relation across enough dates for
    # all three windows. Alternating order keeps both classes in each window.
    for i in range(1, 181):
        favorable = i % 2 == 0
        rows.append(
            _row(
                i,
                outcome=1 if favorable else 0,
                skill_delta=2 if favorable else -2,
                overall_delta=0.4 if favorable else -0.4,
                recent_delta=0.4 if favorable else -0.4,
                shared_delta=0.4 if favorable else -0.4,
            )
        )

    report = train_format_candidate(
        rows,
        format_name="EIGHT",
        min_train=80,
        min_calibration=25,
        min_test=25,
        l2=1.0,
    )

    assert report["status"] in {"RESEARCH_GATE_PASS", "RESEARCH_GATE_FAIL"}
    assert report["activation"] == "FORBIDDEN_PENDING_LIVE_REVIEW_AND_INDEPENDENT_AUDIT"
    assert report["metrics"]["candidate_all_test"]["count"] >= 25


def test_feature_schema_contains_no_identity_or_current_lifetime_fields():
    forbidden_tokens = ("player_id", "name", "career", "lifetime", "current")
    for feature in FEATURE_NAMES:
        assert not any(token in feature.lower() for token in forbidden_tokens)
