"""Tests for transparent skill-only baseline evaluation."""

from analytics.backtest_dataset import BacktestExample
from analytics.baseline_evaluation import evaluate_skill_only_baseline


def _example(*, fmt="EIGHT", outcome=1, own=4, opponent=5):
    return BacktestExample(
        match_id=1,
        match_external_id="101",
        match_date="2024-01-01",
        format=fmt,
        session_name="S",
        player_id=1,
        opponent_id=2,
        outcome_win=outcome,
        own_skill_level=own,
        opponent_skill_level=opponent,
        skill_delta=(own - opponent) if own is not None and opponent is not None else None,
        direct_games_before=0,
        direct_win_rate_before=None,
        player_games_before=0,
        player_win_rate_before=None,
        opponent_games_before=0,
        opponent_win_rate_before=None,
        player_recent5_win_rate=None,
        opponent_recent5_win_rate=None,
        shared_opponent_count_before=0,
        player_shared_games_before=0,
        player_shared_win_rate_before=None,
        opponent_shared_games_before=0,
        opponent_shared_win_rate_before=None,
    )


def test_missing_skill_is_excluded_not_filled_with_neutral_probability():
    report = evaluate_skill_only_baseline(
        [_example(own=None, opponent=5), _example(outcome=0, own=4, opponent=4)]
    )
    assert report["overall"]["examples_total"] == 2
    assert report["overall"]["examples_evaluated"] == 1
    assert report["overall"]["excluded_missing_skill"] == 1


def test_formats_are_reported_separately():
    report = evaluate_skill_only_baseline(
        [_example(fmt="EIGHT"), _example(fmt="NINE", outcome=0)]
    )
    assert report["by_format"]["EIGHT"]["examples_total"] == 1
    assert report["by_format"]["NINE"]["examples_total"] == 1


def test_empty_group_has_null_metrics_not_fake_zeroes():
    report = evaluate_skill_only_baseline([_example(fmt="EIGHT")])
    nine = report["by_format"]["NINE"]
    assert nine["examples_total"] == 0
    assert nine["brier_score"] is None
    assert nine["log_loss"] is None
    assert nine["calibration_bins"] == []
