"""Regression coverage for the live-capture dispatch-timing bug fixed 2026-10-09.

Root cause: tools/capture_apa_graphql.py used Playwright's SYNC API, whose
context.on("response", ...) callbacks are dispatched back onto the main
thread's greenlet -- and that handoff only happens when the main thread makes
its own next Playwright call. The old code blocked the main thread in a bare
input() while the user logged in and browsed, so every real response queued
up unprocessed until browser.close() finally forced it to flush -- by which
point the browser was already closing, and every response body failed with
TargetClosedError. Confirmed live: a real login produced a token and dozens
of real operations (dashboard, MatchPage, DivisionContacts, ...), every one
of them lost.

These tests exercise the fix's building blocks without Playwright or a live
login: input() now runs on a background thread while the main thread keeps
calling page.wait_for_timeout() (a real Playwright call) in a loop, which is
what actually lets context.on(...) keep firing live while the user browses.
"""

from __future__ import annotations

import builtins
import threading
import time

from tools.capture_apa_graphql import _extract_auth_and_captures, _pump_until, _read_line_in_background


class FakePage:
    """Stands in for a Playwright Page: wait_for_timeout is the one call the
    fix relies on to keep returning control to Playwright's dispatcher."""

    def __init__(self) -> None:
        self.pump_count = 0

    def wait_for_timeout(self, _ms: int) -> None:
        self.pump_count += 1


class TestReadLineInBackground:
    def test_input_runs_off_the_main_thread_so_it_never_blocks_the_caller(self, monkeypatch):
        """This is the actual bug: a bare input() call blocks the main thread,
        which is the one thread Playwright's sync API needs free to dispatch
        events. Proving input() now runs elsewhere is the core of the fix."""
        release = threading.Event()

        def slow_input(prompt):
            release.wait(timeout=2)
            return ""

        monkeypatch.setattr(builtins, "input", slow_input)

        started = time.monotonic()
        ready = _read_line_in_background("prompt> ")
        elapsed = time.monotonic() - started

        assert elapsed < 0.5, "input() blocked the calling thread instead of running in the background"
        assert not ready.is_set()
        release.set()
        assert ready.wait(timeout=2), "the Event was never set once input() returned"

    def test_an_interrupted_or_closed_stdin_still_signals_ready(self, monkeypatch):
        """EOF/Ctrl+C inside the background thread must not hang the caller forever."""

        def raising_input(prompt):
            raise EOFError

        monkeypatch.setattr(builtins, "input", raising_input)
        ready = _read_line_in_background("prompt> ")
        assert ready.wait(timeout=2)


class TestPumpUntil:
    def test_it_keeps_calling_wait_for_timeout_until_ready_is_set(self):
        """This IS the fix: looping on a real Playwright call instead of a
        bare input() is what keeps context.on("response", ...) dispatching
        while the main thread waits for the user."""
        page = FakePage()
        ready = threading.Event()

        def set_ready_after_a_few_pumps():
            while page.pump_count < 3:
                time.sleep(0.01)
            ready.set()

        threading.Thread(target=set_ready_after_a_few_pumps, daemon=True).start()
        _pump_until(page, ready, poll_ms=1)

        assert ready.is_set()
        assert page.pump_count >= 3

    def test_a_token_that_arrives_mid_wait_is_visible_as_soon_as_the_wait_ends(self):
        """Simulates the real scenario: context.on("response", ...) updates
        token_holder on its own thread while _pump_until is still looping --
        exactly what the old blocking input() call could never observe."""
        page = FakePage()
        token_holder: dict[str, str] = {}
        ready = threading.Event()

        def background_login_then_press_enter():
            time.sleep(0.02)
            token_holder["token"] = "Bearer real-session-token"
            time.sleep(0.02)
            ready.set()

        threading.Thread(target=background_login_then_press_enter, daemon=True).start()
        _pump_until(page, ready, poll_ms=1)

        assert token_holder.get("token") == "Bearer real-session-token"


class TestExtractAuthAndCaptures:
    """_extract_auth_and_captures replaces the old on_response body: these
    prove the token is captured independently of operation names and of
    whether the response body can be parsed -- exactly what was asked of
    this fix, and exactly what the old code got wrong (auth capture sat
    behind an `if not body: return`, and the loop that followed it skipped
    anything without an operationName before ever touching the token)."""

    def test_token_is_captured_even_when_the_request_has_no_body(self):
        token_holder: dict = {}
        _extract_auth_and_captures(
            "https://gql.poolplayers.com/graphql",
            {"authorization": "Bearer abc123"},
            None,
            lambda: (_ for _ in ()).throw(AssertionError("fetch_json should never be called")),
            {},
            token_holder,
        )
        assert token_holder["token"] == "Bearer abc123"

    def test_token_is_captured_even_when_response_json_raises(self):
        """The exact failure mode seen live: TargetClosedError from a closing
        browser must not cost us the token we already have the header for."""
        token_holder: dict = {}
        captures: dict = {}

        def failing_fetch_json():
            raise RuntimeError("Response.json: Target page, context or browser has been closed")

        _extract_auth_and_captures(
            "https://gql.poolplayers.com/graphql",
            {"authorization": "Bearer abc123"},
            [{"operationName": "dashboard", "variables": {}, "query": "query dashboard { x }"}],
            failing_fetch_json,
            captures,
            token_holder,
        )
        assert token_holder["token"] == "Bearer abc123"
        assert captures == {}

    def test_token_is_captured_even_when_no_operation_name_is_present(self):
        token_holder: dict = {}
        _extract_auth_and_captures(
            "https://gql.poolplayers.com/graphql",
            {"authorization": "Bearer abc123"},
            [{"variables": {}, "query": "query { x }"}],
            lambda: {},
            {},
            token_holder,
        )
        assert token_holder["token"] == "Bearer abc123"

    def test_non_graphql_host_is_ignored_entirely(self):
        token_holder: dict = {}
        _extract_auth_and_captures(
            "https://example.com/other",
            {"authorization": "Bearer should-not-be-captured"},
            [{"operationName": "x"}],
            lambda: {},
            {},
            token_holder,
        )
        assert token_holder == {}

    def test_a_real_operation_with_a_parseable_body_is_still_captured_normally(self):
        token_holder: dict = {}
        captures: dict = {}
        _extract_auth_and_captures(
            "https://gql.poolplayers.com/graphql",
            {"authorization": "Bearer abc123"},
            [{"operationName": "dashboard", "variables": {"x": 1}, "query": "query dashboard { x }"}],
            lambda: {"data": {"x": 1}},
            captures,
            token_holder,
        )
        assert token_holder["token"] == "Bearer abc123"
        assert captures["dashboard"]["response"] == {"data": {"x": 1}}
