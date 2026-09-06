"""Tests for pipeline_run_all.py -- the end-to-end orchestrator (scrape ->
`python -m pipeline` -> test suite) that had zero coverage of its own.

Every real step is a subprocess.run() call -- driving a browser, running the
real ingest, running pytest recursively -- so these tests mock subprocess.run
rather than actually invoking any of that. What's under test here is the
ORCHESTRATION: which commands run, in what order, with which cwd, how
--skip-scrape / --skip-tests change that, and that a failing step stops the
chain instead of silently continuing to the next one.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import pipeline_run_all


def completed(returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode)


@pytest.fixture
def recorded_calls(monkeypatch):
    """Replace subprocess.run with a recorder that always succeeds, and
    hand back the list of (cmd, cwd) it was called with."""
    calls: list[tuple[list[str], object]] = []

    def fake_run(cmd, cwd=None, **kwargs):
        calls.append((cmd, cwd))
        return completed(0)

    monkeypatch.setattr(pipeline_run_all.subprocess, "run", fake_run)
    return calls


class TestDefaultRun:
    def test_runs_scrape_then_pipeline_then_tests_in_order(self, recorded_calls):
        exit_code = pipeline_run_all.main([])
        assert exit_code == 0
        assert len(recorded_calls) == 3

        scrape_cmd, scrape_cwd = recorded_calls[0]
        assert scrape_cmd[0] == sys.executable
        assert scrape_cmd[1].endswith("full_auto_scrape.py")
        assert scrape_cwd == pipeline_run_all.ROOT

        pipeline_cmd, pipeline_cwd = recorded_calls[1]
        assert pipeline_cmd == [sys.executable, "-m", "pipeline"]
        assert pipeline_cwd == pipeline_run_all.ROOT

        tests_cmd, tests_cwd = recorded_calls[2]
        assert tests_cmd == [sys.executable, "-m", "pytest", "-q"]
        assert tests_cwd == pipeline_run_all.ROOT


class TestSkipFlags:
    def test_skip_scrape_omits_only_the_scrape_step(self, recorded_calls):
        exit_code = pipeline_run_all.main(["--skip-scrape"])
        assert exit_code == 0
        assert len(recorded_calls) == 2
        assert recorded_calls[0][0] == [sys.executable, "-m", "pipeline"]
        assert recorded_calls[1][0] == [sys.executable, "-m", "pytest", "-q"]

    def test_skip_tests_omits_only_the_test_step(self, recorded_calls):
        exit_code = pipeline_run_all.main(["--skip-tests"])
        assert exit_code == 0
        assert len(recorded_calls) == 2
        assert recorded_calls[0][0][1].endswith("full_auto_scrape.py")
        assert recorded_calls[1][0] == [sys.executable, "-m", "pipeline"]

    def test_both_skip_flags_leave_only_the_pipeline_step(self, recorded_calls):
        exit_code = pipeline_run_all.main(["--skip-scrape", "--skip-tests"])
        assert exit_code == 0
        assert len(recorded_calls) == 1
        assert recorded_calls[0][0] == [sys.executable, "-m", "pipeline"]


class TestFailurePropagation:
    def test_a_failing_step_stops_the_chain_and_exits_with_its_code(self, monkeypatch):
        """If ingest/export fails, the test suite must never run against a
        half-written database -- and the process's own exit code must say
        which step failed, not just "something failed"."""
        calls: list[list[str]] = []

        def fake_run(cmd, cwd=None, **kwargs):
            calls.append(cmd)
            if cmd == [sys.executable, "-m", "pipeline"]:
                return completed(2)
            return completed(0)

        monkeypatch.setattr(pipeline_run_all.subprocess, "run", fake_run)

        with pytest.raises(SystemExit) as excinfo:
            pipeline_run_all.main(["--skip-scrape"])

        assert excinfo.value.code == 2
        # The pipeline step ran and failed; the test-suite step must never
        # have been reached.
        assert calls == [[sys.executable, "-m", "pipeline"]]

    def test_a_failing_scrape_step_never_reaches_pipeline_or_tests(self, monkeypatch):
        calls: list[list[str]] = []

        def fake_run(cmd, cwd=None, **kwargs):
            calls.append(cmd)
            return completed(1)

        monkeypatch.setattr(pipeline_run_all.subprocess, "run", fake_run)

        with pytest.raises(SystemExit) as excinfo:
            pipeline_run_all.main([])

        assert excinfo.value.code == 1
        assert len(calls) == 1
        assert calls[0][1].endswith("full_auto_scrape.py")


class TestRootIsTheScriptsOwnDirectory:
    def test_root_is_not_the_parent_of_the_repo(self):
        """Regression guard for the exact bug pipeline_run_all.py's own
        docstring describes: an earlier version used .parent.parent, which
        resolved one level ABOVE the repo, so every command it built pointed
        outside the project."""
        assert (pipeline_run_all.ROOT / "pipeline_run_all.py").is_file()
        assert (pipeline_run_all.ROOT / "scraper" / "full_auto_scrape.py").is_file()
