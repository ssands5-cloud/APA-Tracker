"""Direct tests for the Ultimate Coach browser runner refresh loop."""

from __future__ import annotations

import ast
import inspect

import pytest

from scraper.graphql_scraper import AccessTokenExpired
from tools import run_ultimate_coach_browser as runner

playwright_sync_api = pytest.importorskip("playwright.sync_api")


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


# --- --persistent-auth CLI wiring (main()-level, capture function mocked) ---


def test_persistent_auth_flag_uses_persistent_capture_never_manual(monkeypatch):
    tokens = iter(["token-1", "token-2"])
    persistent_calls = []
    manual_calls = {"count": 0}

    def fake_persistent_capture(**kwargs):
        persistent_calls.append(kwargs)
        return next(tokens)

    def fake_manual_capture():
        manual_calls["count"] += 1
        return next(tokens)

    monkeypatch.setattr(runner, "capture_access_token_persistent", fake_persistent_capture)
    monkeypatch.setattr(runner, "capture_access_token", fake_manual_capture)

    pipeline_calls = []

    def fake_pipeline(token, *, resume):
        pipeline_calls.append((token, resume))
        if token == "token-1":
            raise AccessTokenExpired("expired")
        return 0

    monkeypatch.setattr(runner, "run_pipeline", fake_pipeline)

    assert runner.main(["--persistent-auth"]) == 0
    assert manual_calls["count"] == 0, "manual capture must never run in persistent-auth mode"
    assert len(persistent_calls) == 2, "persistent capture must be retried on confirmed auth expiry"
    assert pipeline_calls == [("token-1", False), ("token-2", True)]


def test_persistent_auth_no_token_reports_failure_without_pipeline(monkeypatch, capsys):
    called = {"pipeline": 0}

    monkeypatch.setattr(runner, "capture_access_token_persistent", lambda **kwargs: None)

    def should_not_run(*args, **kwargs):
        called["pipeline"] += 1
        return 0

    monkeypatch.setattr(runner, "run_pipeline", should_not_run)

    assert runner.main(["--persistent-auth", "--resume"]) == 1
    assert called["pipeline"] == 0


def test_manual_and_persistent_auth_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        runner.main(["--manual-auth", "--persistent-auth"])


def test_manual_auth_flag_preserves_default_behavior(monkeypatch):
    """--manual-auth is an explicit alias, not a new code path."""
    monkeypatch.setattr(runner, "capture_access_token", lambda: "token-1")
    monkeypatch.setattr(runner, "capture_access_token_persistent", lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("persistent capture must not run for --manual-auth")
    ))

    def fake_pipeline(token, *, resume):
        return 0

    monkeypatch.setattr(runner, "run_pipeline", fake_pipeline)

    assert runner.main(["--manual-auth"]) == 0


# --- capture_access_token_persistent() itself (Playwright fully faked) ---


class _FakeLocator:
    def __init__(self, count=0, visible=True):
        self._count = count
        self._visible = visible
        self.click_calls = 0

    def count(self):
        return self._count

    @property
    def first(self):
        return self

    def is_visible(self):
        return self._visible

    def click(self, timeout=None):
        self.click_calls += 1


class _FakeRequest:
    def __init__(self, headers):
        self.headers = headers


class _FakeResponse:
    def __init__(self, url, headers):
        self.url = url
        self.request = _FakeRequest(headers)


class _FakePage:
    def __init__(self, *, continue_locator=None, on_tick=None):
        self.goto_url = None
        self._continue_locator = continue_locator or _FakeLocator(count=0)
        self._on_tick = on_tick
        self.tick_count = 0

    def goto(self, url):
        self.goto_url = url

    def wait_for_timeout(self, ms):
        self.tick_count += 1
        if self._on_tick:
            self._on_tick(self.tick_count)

    def get_by_text(self, text, exact=False):
        assert text == "Continue to Member Services"
        return self._continue_locator


class _FakeContext:
    def __init__(self, page):
        self.pages = [page]
        self._page = page
        self.handlers: dict[str, object] = {}
        self.closed = False

    def on(self, event, handler):
        self.handlers[event] = handler

    def new_page(self):
        return self._page

    def close(self):
        self.closed = True

    def emit_response(self, response):
        self.handlers["response"](response)


class _FakeChromium:
    def __init__(self, context):
        self._context = context
        self.launch_persistent_context_calls = []

    def launch_persistent_context(self, user_data_dir, headless=False, **kwargs):
        self.launch_persistent_context_calls.append(
            {"user_data_dir": user_data_dir, "headless": headless, **kwargs}
        )
        return self._context


class _FakePlaywright:
    def __init__(self, context):
        self.chromium = _FakeChromium(context)


class _FakeSyncPlaywrightCM:
    def __init__(self, context):
        self.playwright = _FakePlaywright(context)

    def __enter__(self):
        return self.playwright

    def __exit__(self, *exc_info):
        return False


def test_persistent_capture_profile_path_is_under_gitignored_session_cache():
    gitignore = (runner._REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".session_cache/" in gitignore
    assert runner.SESSION_PROFILE_DIR.is_relative_to(runner._REPO_ROOT / ".session_cache")


def test_persistent_capture_returns_token_with_no_input_call(monkeypatch):
    page = _FakePage()
    context = _FakeContext(page)

    def on_tick(n):
        if n == 2:
            context.emit_response(_FakeResponse(
                f"https://{runner.GRAPHQL_HOST}/graphql", {"authorization": "real-token-abc"}
            ))

    page._on_tick = on_tick

    monkeypatch.setattr(
        playwright_sync_api, "sync_playwright", lambda: _FakeSyncPlaywrightCM(context)
    )

    def _forbidden_input(*args, **kwargs):
        raise AssertionError("persistent auth must never call input()")

    monkeypatch.setattr("builtins.input", _forbidden_input)

    token = runner.capture_access_token_persistent(timeout_s=5)

    assert token == "real-token-abc"
    assert context.closed is True
    assert page.goto_url == runner.LEAGUE_URL


def test_persistent_capture_clicks_continue_to_member_services(monkeypatch):
    continue_button = _FakeLocator(count=1, visible=True)
    page = _FakePage(continue_locator=continue_button)
    context = _FakeContext(page)

    def on_tick(n):
        if n == 2:
            context.emit_response(_FakeResponse(
                f"https://{runner.GRAPHQL_HOST}/graphql", {"authorization": "real-token-abc"}
            ))

    page._on_tick = on_tick

    monkeypatch.setattr(
        playwright_sync_api, "sync_playwright", lambda: _FakeSyncPlaywrightCM(context)
    )
    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must not call input()")
    ))

    token = runner.capture_access_token_persistent(timeout_s=5)

    assert token == "real-token-abc"
    assert continue_button.click_calls >= 1


def test_persistent_capture_times_out_without_any_credential_handling(monkeypatch, capsys):
    page = _FakePage()
    context = _FakeContext(page)

    monkeypatch.setattr(
        playwright_sync_api, "sync_playwright", lambda: _FakeSyncPlaywrightCM(context)
    )
    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must not call input()")
    ))

    token = runner.capture_access_token_persistent(timeout_s=1)

    assert token is None
    assert context.closed is True
    out = capsys.readouterr().out
    assert "MANUAL APA LOGIN REQUIRED" in out


def test_persistent_capture_source_has_no_password_or_env_credential_code():
    """AST-based proof -- not a bare substring scan, which would also flag
    this module's own explanatory comments/docstrings about NOT handling
    credentials -- that no actual credential-handling CODE exists anywhere
    in the module: no dotenv/getpass import, no APA_USERNAME/APA_PASSWORD
    string literal, no password-selector string, no .fill(/.type( calls
    (the Playwright APIs used to populate form fields)."""
    tree = ast.parse(inspect.getsource(runner))

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            names = [alias.name for alias in node.names]
            for candidate in [module, *names]:
                lowered = candidate.lower()
                assert "dotenv" not in lowered and "getpass" not in lowered, (
                    f"forbidden credential-related import: {candidate!r}"
                )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in ("APA_USERNAME", "APA_PASSWORD"), (
                f"forbidden credential env-var literal: {node.value!r}"
            )
            lowered_value = node.value.lower()
            assert 'type="password"' not in lowered_value, (
                f"forbidden password-selector string literal: {node.value!r}"
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in ("fill", "type"), (
                f"forbidden form-filling call .{node.func.attr}(...) found -- "
                "this module must never populate a login form field"
            )


def test_persistent_capture_never_enables_recording():
    """AST-based proof that no screenshot/video/HAR/trace capture (which
    could persist session material to disk) is ever enabled -- checks
    actual keyword arguments and call targets, not comment text (this
    function's own comment explains, in prose, that these are absent)."""
    tree = ast.parse(inspect.getsource(runner.capture_access_token_persistent))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                assert keyword.arg not in ("record_video_dir", "record_har_path"), (
                    f"forbidden recording option passed: {keyword.arg}"
                )
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr != "screenshot", "forbidden .screenshot(...) call"
                if node.func.attr == "start":
                    value = node.func.value
                    target = getattr(value, "attr", getattr(value, "id", ""))
                    assert target != "tracing", "forbidden tracing.start(...) call"
