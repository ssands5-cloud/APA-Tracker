"""Scheduler routing contracts."""

from __future__ import annotations

import scheduler.daily_sync as daily_sync
import scheduler.graphql_sync as graphql_sync


def test_token_backed_daily_job_uses_complete_all_team_live_sync(monkeypatch):
    calls = []
    monkeypatch.setattr(
        daily_sync,
        "load_config",
        lambda _path: {"apa": {"access_token": "ephemeral-test-token"}},
    )

    def all_teams(path, export=True):
        calls.append((path, export))

    def single_team(*_args, **_kwargs):  # pragma: no cover - assertion is the test
        raise AssertionError("the scheduled production job must not use single-team sync")

    monkeypatch.setattr(graphql_sync, "run_all_teams", all_teams)
    monkeypatch.setattr(graphql_sync, "run", single_team)

    daily_sync.run("scheduled.yaml")

    assert calls == [("scheduled.yaml", True)]
