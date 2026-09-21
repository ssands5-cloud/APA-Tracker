"""Tests for probability calibration metrics."""

from analytics.calibration_metrics import (
    brier_score,
    calibration_bins,
    expected_calibration_error,
    log_loss,
)


def test_perfect_predictions_have_zero_brier_and_near_zero_logloss():
    predictions = [0.0, 1.0]
    outcomes = [0, 1]
    assert brier_score(predictions, outcomes) == 0.0
    assert log_loss(predictions, outcomes) < 1e-6


def test_half_predictions_have_quarter_brier():
    assert brier_score([0.5, 0.5], [0, 1]) == 0.25


def test_calibration_bins_report_prediction_vs_observed_rate():
    bins = calibration_bins([0.1, 0.2, 0.8, 0.9], [0, 1, 1, 1], bins=2)
    assert bins[0].count == 2
    assert bins[0].mean_prediction == 0.15
    assert bins[0].observed_rate == 0.5
    assert bins[1].count == 2
    assert bins[1].mean_prediction == 0.85
    assert bins[1].observed_rate == 1.0


def test_expected_calibration_error_is_weighted_gap():
    value = expected_calibration_error([0.1, 0.2, 0.8, 0.9], [0, 1, 1, 1], bins=2)
    assert value == 0.25
