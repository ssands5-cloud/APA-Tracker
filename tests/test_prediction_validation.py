"""Tests for the win-probability model validation (analytics.prediction_validation).

Fixtures are built from real detached PlayerHeadToHead ORM objects, same
convention as tests/test_head_to_head.py's `game()` helper -- a column
rename breaks these rather than silently emptying a field.
"""

from __future__ import annotations

import math

import pytest

from analytics.head_to_head import MAX_WIN_PROBABILITY, MIN_WIN_PROBABILITY, win_probability
from analytics.prediction_validation import (
    ScoredPrediction,
    accuracy,
    brier_score,
    calibration_curve,
    format_label,
    group_summaries,
    log_loss,
    mean_calibration_error,
    naive_baseline,
    prior_games_label,
    score_all_pairings,
    score_skill_only,
    score_walk_forward,
    skill_direction_label,
    skill_only_probability,
    summarize,
)
from database.models import PlayerHeadToHead


def h2h(player_id=1, opponent_id=2, own=5, opp=5, result="W", fmt="8-Ball Open", session="S"):
    """One head-to-head game, detached from any session."""
    return PlayerHeadToHead(
        player_id=player_id, opponent_id=opponent_id,
        own_skill_level=own, opponent_skill_level=opp, result=result,
        format=fmt, session_name=session,
    )


def pred(probability, win, skill=None, prior=None, fmt="8-Ball Open"):
    """One already-scored prediction, for testing the grading functions in
    isolation from anything that produces them."""
    return ScoredPrediction(
        player_id=1, opponent_id=2, format=fmt, session_name="S",
        predicted_probability=probability, actual_win=win,
        skill_advantage=skill, prior_games=prior,
    )


class TestBrierScore:
    def test_hand_computed_value(self):
        preds = [pred(0.8, True), pred(0.3, False), pred(0.5, True)]
        expected = ((0.8 - 1) ** 2 + (0.3 - 0) ** 2 + (0.5 - 1) ** 2) / 3
        assert brier_score(preds) == round(expected, 4)

    def test_empty_is_none_not_zero(self):
        """No predictions is not a perfect score -- it's nothing to grade."""
        assert brier_score([]) is None

    def test_perfect_confident_predictions_score_zero(self):
        assert brier_score([pred(1.0, True), pred(0.0, False)]) == 0.0

    def test_always_50_50_scores_a_quarter(self):
        assert brier_score([pred(0.5, True), pred(0.5, False)]) == 0.25


class TestLogLoss:
    def test_always_50_50_scores_ln2(self):
        preds = [pred(0.5, True), pred(0.5, False)]
        assert log_loss(preds) == round(math.log(2), 4)

    def test_empty_is_none(self):
        assert log_loss([]) is None

    def test_clamps_an_extreme_wrong_prediction_instead_of_exploding(self):
        result = log_loss([pred(1.0, False)])
        assert result is not None
        assert math.isfinite(result)


class TestAccuracy:
    def test_counts_only_the_favoured_side_winning(self):
        preds = [pred(0.7, True), pred(0.3, False), pred(0.6, False)]
        assert accuracy(preds) == round(2 / 3, 4)

    def test_empty_is_none_not_zero(self):
        assert accuracy([]) is None


class TestMeanCalibrationError:
    def test_positive_means_overconfident(self):
        preds = [pred(0.9, False), pred(0.9, False)]
        assert mean_calibration_error(preds) == 0.9

    def test_negative_means_underconfident(self):
        preds = [pred(0.1, True), pred(0.1, True)]
        assert mean_calibration_error(preds) == pytest.approx(-0.9)

    def test_empty_is_none(self):
        assert mean_calibration_error([]) is None


class TestCalibrationCurve:
    def test_bucket_count_matches_bins(self):
        assert len(calibration_curve([pred(0.5, True)], bins=5)) == 5

    def test_a_prediction_lands_in_its_probability_bucket(self):
        buckets = calibration_curve([pred(0.05, False), pred(0.55, True)], bins=5)
        assert buckets[0].count == 1
        assert buckets[0].mean_predicted == 0.05
        assert buckets[0].actual_win_rate == 0.0

    def test_probability_of_exactly_one_lands_in_the_last_bucket(self):
        buckets = calibration_curve([pred(1.0, True)], bins=5)
        assert buckets[-1].count == 1
        assert buckets[-1].actual_win_rate == 1.0

    def test_an_empty_bucket_reports_none_not_zero(self):
        buckets = calibration_curve([pred(0.05, True)], bins=5)
        empty = buckets[-1]
        assert empty.count == 0
        assert empty.mean_predicted is None
        assert empty.actual_win_rate is None


class TestNaiveBaseline:
    def test_replaces_probability_but_keeps_everything_else(self):
        [baseline] = naive_baseline([pred(0.9, True, skill=1.5, prior=3)], probability=0.5)
        assert baseline.predicted_probability == 0.5
        assert baseline.actual_win is True
        assert baseline.skill_advantage == 1.5
        assert baseline.prior_games == 3


class TestSkillOnlyProbability:
    def test_matches_the_production_logistic_shape(self):
        from analytics.head_to_head import SL_LOG_ODDS_PER_LEVEL
        expected = 1 / (1 + math.exp(-SL_LOG_ODDS_PER_LEVEL * 2))
        assert skill_only_probability(6, 4) == pytest.approx(expected)

    def test_even_skill_level_is_a_coin_flip(self):
        assert skill_only_probability(5, 5) == pytest.approx(0.5)

    def test_stays_within_the_production_clamp(self):
        assert skill_only_probability(7, 2) <= MAX_WIN_PROBABILITY
        assert skill_only_probability(2, 7) >= MIN_WIN_PROBABILITY


class TestScoreSkillOnly:
    def test_skips_a_row_missing_either_skill_level(self):
        assert score_skill_only([h2h(own=None), h2h(opp=None)]) == []

    def test_skips_an_unrecognized_result(self):
        assert score_skill_only([h2h(result="?")]) == []

    def test_scores_every_eligible_row_regardless_of_order(self):
        rows = [h2h(own=6, opp=4, result="W"), h2h(own=4, opp=6, result="L")]
        scored = score_skill_only(rows)
        assert len(scored) == 2
        assert scored[0].skill_advantage == 2
        assert scored[1].skill_advantage == -2

    def test_predicted_probability_matches_the_shared_formula(self):
        [scored] = score_skill_only([h2h(own=6, opp=4, result="W")])
        assert scored.predicted_probability == skill_only_probability(6, 4)


class TestScoreWalkForward:
    def test_a_pairings_first_ever_meeting_is_never_scored(self):
        """Nothing precedes it, so there is nothing to predict from."""
        assert score_walk_forward([h2h(result="W")]) == []

    def test_second_meeting_predicts_from_only_the_first_games_data(self):
        rows = [h2h(own=6, opp=4, result="W"), h2h(own=6, opp=4, result="L")]
        [scored] = score_walk_forward(rows)
        assert scored.predicted_probability == win_probability(rows[:1])
        assert scored.actual_win is False
        assert scored.prior_games == 1

    def test_a_later_games_outcome_never_leaks_into_an_earlier_prediction(self):
        shared_prefix = [h2h(result="W"), h2h(result="L")]
        longer = shared_prefix + [h2h(result="W")]
        short_prediction = score_walk_forward(shared_prefix)[0]
        long_prediction = score_walk_forward(longer)[0]
        assert short_prediction.predicted_probability == long_prediction.predicted_probability

    def test_skips_a_held_out_game_with_an_unrecognized_result(self):
        """There's a real prediction to make, but nothing to grade it against."""
        assert score_walk_forward([h2h(result="W"), h2h(result="?")]) == []

    def test_prior_games_counts_recognized_results_only(self):
        rows = [h2h(result="?"), h2h(result="W"), h2h(result="L")]
        scored = score_walk_forward(rows)
        assert [s.prior_games for s in scored] == [0, 1]


class TestScoreAllPairings:
    def test_each_pairing_is_walked_forward_using_only_its_own_history(self):
        groups = {
            (1, 2, "8-Ball Open", "S"): [
                h2h(player_id=1, opponent_id=2, result="W"),
                h2h(player_id=1, opponent_id=2, result="L"),
            ],
            (3, 4, "8-Ball Open", "S"): [
                h2h(player_id=3, opponent_id=4, result="L"),
            ],
        }
        scored = score_all_pairings(groups)
        # (3, 4) has only one meeting -> nothing to score.
        # (1, 2) has two -> exactly one held-out prediction.
        assert len(scored) == 1
        assert (scored[0].player_id, scored[0].opponent_id) == (1, 2)


class TestLabels:
    def test_format_label_falls_back_when_missing(self):
        assert format_label(pred(0.5, True, fmt=None)) == "unknown format"

    def test_skill_direction_buckets(self):
        assert skill_direction_label(pred(0.5, True, skill=1.0)) == "favored (higher SL)"
        assert skill_direction_label(pred(0.5, True, skill=-1.0)) == "underdog (lower SL)"
        assert skill_direction_label(pred(0.5, True, skill=0.0)) == "even SL"
        assert skill_direction_label(pred(0.5, True, skill=None)) == "unknown skill gap"

    def test_prior_games_bucket_boundaries(self):
        assert prior_games_label(pred(0.5, True, prior=1)) == "1 prior game"
        assert prior_games_label(pred(0.5, True, prior=3)) == "2-3 prior games"
        assert prior_games_label(pred(0.5, True, prior=6)) == "4-6 prior games"
        assert prior_games_label(pred(0.5, True, prior=7)) == "7+ prior games"
        assert prior_games_label(pred(0.5, True, prior=None)) == "unknown"


class TestGroupSummaries:
    def test_splits_and_summarizes_each_bucket_independently(self):
        preds = [pred(0.9, True, fmt="8-Ball Open"), pred(0.1, False, fmt="9-Ball Open")]
        result = group_summaries(preds, format_label)
        assert set(result) == {"8-Ball Open", "9-Ball Open"}
        assert result["8-Ball Open"].n == 1
        assert result["9-Ball Open"].n == 1


class TestSummarize:
    def test_empty_predictions_report_none_not_zero(self):
        summary = summarize("empty", [])
        assert summary.n == 0
        assert summary.brier is None
        assert summary.log_loss is None
        assert summary.accuracy is None
        assert summary.mean_calibration_error is None
