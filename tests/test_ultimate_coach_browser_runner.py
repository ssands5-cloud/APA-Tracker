"""Direct tests for the Ultimate Coach browser runner refresh loop."""

from __future__ import annotations

from scraper.graphql_scraper import AccessTokenExpired
from tools import run_ultimate_coach_browser as runner


def test_fresh_run_switches_to_resume_after_confirmed_auth_expiry(monkeypatch):
    tokens = iter(["token-1", "token-2"])
    calls = []

    monkeypatch.setattr(runner, "capture_access_token", lambda: next(tokens))

    def fake_pipeline(token, *, resume):
        calls.append((token, resume))
        if token == "token-1":
            raise AccessTokenExpired("expired")
        return 0

    monkeypatch.setattr(runner, "run_pipeline", fake_pipeline)

    assert runner.main([]) == 0
    assert calls == [
        ("token-1", False),
        ("token-2", True),
    ]


def test_resume_stays_resume_across_multiple_auth_refreshes(monkeypatch):
    tokens = iter(["token-1", "token-2", "token-3"])
    calls = []

    monkeypatch.setattr(runner, "capture_access_token", lambda: next(tokens))

    def fake_pipeline(token, *, resume):
        calls.append((token, resume))
        if token != "token-3":
            raise AccessTokenExpired("expired")
        return 0

    monkeypatch.setattr(runner, "run_pipeline", fake_pipeline)

    assert runner.main(["--resume"]) == 0
    assert calls == [
        ("token-1", True),
        ("token-2", True),
        ("token-3", True),
    ]


def test_no_captured_token_exits_without_running_pipeline(monkeypatch):
    called = {"pipeline": 0}

    monkeypatch.setattr(runner, "capture_access_token", lambda: None)

    def should_not_run(*args, **kwargs):
        called["pipeline"] += 1
        return 0

    monkeypatch.setattr(runner, "run_pipeline", should_not_run)

    assert runner.main(["--resume"]) == 1
    assert called["pipeline"] == 0


def test_non_auth_pipeline_failure_is_not_retried(monkeypatch):
    capture_calls = {"count": 0}
    pipeline_calls = []

    def capture():
        capture_calls["count"] += 1
        return "token-1"

    monkeypatch.setattr(runner, "capture_access_token", capture)

    def fake_pipeline(token, *, resume):
        pipeline_calls.append((token, resume))
        return 1

    monkeypatch.setattr(runner, "run_pipeline", fake_pipeline)

    assert runner.main(["--resume"]) == 1
    assert capture_calls["count"] == 1
    assert pipeline_calls == [("token-1", True)]


def test_auth_failure_detail_never_requires_token_introspection():
    exc = AccessTokenExpired("server rejected authentication")
    assert runner._auth_failure_detail(exc) == "server rejected authentication"
