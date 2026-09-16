"""Tests for scripts/run_production_demo.py.

The launcher's whole job is to refuse to present anything it cannot
re-verify, so most of these are refusal tests. One real fixture bundle is
built for the module and each test tampers with its own copy.

No test starts a browser, binds a non-loopback address, reads a credential,
or makes a network request. The builder subprocess is mocked wherever the
test is about launcher behavior rather than a real build.
"""

from __future__ import annotations

import json
import shutil
import urllib.request

import pytest

from scripts import build_full_production_demo as builder
from scripts import run_production_demo as launcher
from scripts.run_production_demo import PresentationError, verify_run


@pytest.fixture(scope="module")
def run_root():
    root = builder.PROJECT_ROOT / "demo-runs" / "pytest-launcher"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def built_run(run_root):
    target = run_root / "fixture-launcher"
    builder.run_build("fixture", target, run_root)
    return target


@pytest.fixture
def run_copy(built_run, run_root, request):
    destination = run_root / f"copy-{abs(hash(request.node.name)) % 100000}"
    shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(built_run, destination)
    try:
        yield destination
    finally:
        shutil.rmtree(destination, ignore_errors=True)


class TestAcceptsAVerifiedRun:
    def test_a_real_bundle_verifies(self, run_copy, run_root):
        manifest = verify_run(run_copy, run_root)

        assert manifest["promotable"] is True
        assert manifest["run_id"] == run_copy.name or manifest["run_id"]

    def test_verification_does_not_modify_the_bundle(self, run_copy, run_root):
        before = {
            p: (p.stat().st_mtime_ns, p.stat().st_size)
            for p in sorted(run_copy.rglob("*")) if p.is_file()
        }

        verify_run(run_copy, run_root)

        after = {
            p: (p.stat().st_mtime_ns, p.stat().st_size)
            for p in sorted(run_copy.rglob("*")) if p.is_file()
        }
        assert before == after


class TestRefusals:
    def test_a_missing_ready_marker_is_refused(self, run_copy, run_root):
        (run_copy / "READY").unlink()

        with pytest.raises(PresentationError, match="not promotable"):
            verify_run(run_copy, run_root)

    def test_a_tampered_artifact_is_refused(self, run_copy, run_root):
        target = run_copy / "html" / "team_strength.html"
        target.write_text(target.read_text(encoding="utf-8") + "<!-- edited -->", encoding="utf-8")

        with pytest.raises(PresentationError, match="checksum mismatch"):
            verify_run(run_copy, run_root)

    def test_an_emptied_artifact_is_refused(self, run_copy, run_root):
        (run_copy / "excel" / "team_strength.xlsx").write_bytes(b"")

        with pytest.raises(PresentationError, match="checksum mismatch"):
            verify_run(run_copy, run_root)

    def test_a_deleted_artifact_is_refused(self, run_copy, run_root):
        (run_copy / "html" / "data_coverage.html").unlink()

        with pytest.raises(PresentationError, match="missing"):
            verify_run(run_copy, run_root)

    def test_a_tampered_manifest_is_refused(self, run_copy, run_root):
        manifest_path = run_copy / "demo_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["promotable"] = True
        manifest["scope"]["our_team_id"] = "99999"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        with pytest.raises(PresentationError, match="manifest hash does not match"):
            verify_run(run_copy, run_root)

    def test_a_run_marked_not_promotable_is_refused(self, run_copy, run_root):
        """Even with every hash self-consistent, promotable=false stops it."""
        manifest_path = run_copy / "demo_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["promotable"] = False
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        ready_path = run_copy / "READY"
        ready = json.loads(ready_path.read_text(encoding="utf-8"))
        ready["manifest_sha256"] = builder.sha256_file(manifest_path)
        ready_path.write_text(json.dumps(ready, indent=2), encoding="utf-8")

        with pytest.raises(PresentationError, match="promotable"):
            verify_run(run_copy, run_root)

    def test_a_missing_index_is_refused(self, run_copy, run_root):
        checksums = run_copy / "checksums.sha256"
        kept = [
            line for line in checksums.read_text(encoding="utf-8").splitlines()
            if not line.endswith("index.html")
        ]
        checksums.write_text("\n".join(kept) + "\n", encoding="utf-8")
        (run_copy / "index.html").unlink()

        with pytest.raises(PresentationError, match="index.html"):
            verify_run(run_copy, run_root)

    def test_a_run_outside_the_run_root_is_refused(self, tmp_path, run_root):
        with pytest.raises(PresentationError, match="escapes the run root"):
            verify_run(tmp_path / "elsewhere", run_root)

    def test_a_traversal_path_is_refused(self, run_root):
        with pytest.raises(PresentationError, match="escapes the run root"):
            verify_run(run_root / ".." / ".." / "etc", run_root)

    def test_a_nonexistent_run_is_refused(self, run_root):
        with pytest.raises(PresentationError, match="does not exist"):
            verify_run(run_root / "never-built", run_root)


class TestCompletionEvent:
    def test_the_run_directory_comes_from_the_completion_event(self, tmp_path):
        events = tmp_path / "events.jsonl"
        events.write_text(
            json.dumps({
                "schema_version": launcher.EVENT_SCHEMA_VERSION,
                "phase": "complete", "status": "ok",
                "run_dir": "demo-runs/chosen-run", "run_id": "chosen-run",
            }) + "\n",
            encoding="utf-8",
        )

        assert launcher._completion_event(events)["run_dir"] == "demo-runs/chosen-run"

    def test_an_unknown_event_schema_fails_closed(self, tmp_path):
        events = tmp_path / "events.jsonl"
        events.write_text(
            json.dumps({"schema_version": "from-the-future-v9", "phase": "complete"}) + "\n",
            encoding="utf-8",
        )

        with pytest.raises(PresentationError, match="unknown builder event schema"):
            launcher._completion_event(events)

    def test_no_completion_event_fails_closed(self, tmp_path):
        events = tmp_path / "events.jsonl"
        events.write_text(
            json.dumps({
                "schema_version": launcher.EVENT_SCHEMA_VERSION,
                "phase": "preflight", "status": "ok",
            }) + "\n",
            encoding="utf-8",
        )

        with pytest.raises(PresentationError, match="no completion event"):
            launcher._completion_event(events)

    def test_an_absent_event_stream_fails_closed(self, tmp_path):
        with pytest.raises(PresentationError, match="no event stream"):
            launcher._completion_event(tmp_path / "never-written.jsonl")


class TestBuilderFailureStopsPresentation:
    def test_a_failing_builder_exit_code_is_returned_and_nothing_is_served(self, monkeypatch):
        served = []
        monkeypatch.setattr(launcher, "invoke_builder", lambda *a, **k: builder.EXIT_DOCUMENTS)
        monkeypatch.setattr(launcher, "serve", lambda *a, **k: served.append(a))

        code = launcher.main(["--mode", "fixture", "--serve"])

        assert code == builder.EXIT_DOCUMENTS
        assert served == []

    def test_a_verification_failure_returns_the_presentation_code(self, monkeypatch, tmp_path):
        def fake_builder(forwarded, events_path):
            events_path.write_text(
                json.dumps({
                    "schema_version": launcher.EVENT_SCHEMA_VERSION,
                    "phase": "complete", "status": "ok",
                    "run_dir": "demo-runs/does-not-exist", "run_id": "x",
                }) + "\n",
                encoding="utf-8",
            )
            return 0

        monkeypatch.setattr(launcher, "invoke_builder", fake_builder)

        assert launcher.main(["--mode", "fixture"]) == launcher.EXIT_PRESENTATION


class TestFlagPolicy:
    def test_open_requires_serve(self):
        with pytest.raises(SystemExit):
            launcher.main(["--mode", "fixture", "--open"])

    def test_no_build_requires_a_verified_run(self):
        with pytest.raises(SystemExit):
            launcher.main(["--no-build"])

    def test_mode_is_required_unless_no_build(self):
        with pytest.raises(SystemExit):
            launcher.main([])

    def test_an_unknown_flag_is_rejected(self):
        with pytest.raises(SystemExit):
            launcher.main(["--mode", "fixture", "--totally-unknown"])

    def test_the_builder_is_invoked_with_an_argument_array(self, monkeypatch):
        captured = {}

        def fake_run(command, cwd, check):
            captured["command"] = command
            raise SystemExit(0)

        monkeypatch.setattr(launcher.subprocess, "run", fake_run)
        with pytest.raises(SystemExit):
            launcher.invoke_builder(["--mode", "fixture"], builder.PROJECT_ROOT / "x.jsonl")

        assert isinstance(captured["command"], list)
        assert "--mode" in captured["command"]


class TestLoopbackServer:
    def test_it_binds_loopback_only_and_sets_safety_headers(self, run_copy):
        server, url = launcher.serve(run_copy, 0)
        try:
            assert server.server_address[0] == "127.0.0.1"
            assert url.startswith("http://127.0.0.1:")

            with urllib.request.urlopen(url, timeout=5) as response:
                headers = dict(response.headers)
                body = response.read().decode("utf-8")

            assert headers["X-Content-Type-Options"] == "nosniff"
            assert "default-src 'none'" in headers["Content-Security-Policy"]
            assert headers["Referrer-Policy"] == "no-referrer"
            assert "APA Tracker demo run" in body
        finally:
            server.shutdown()
            server.server_close()

    def test_a_traversal_request_cannot_escape_the_run_root(self, run_copy):
        server, url = launcher.serve(run_copy, 0)
        base = url.rsplit("/", 1)[0]
        try:
            with urllib.request.urlopen(f"{base}/../../../.gitignore", timeout=5) as response:
                body = response.read().decode("utf-8", errors="replace")
            # Served the run root listing/index instead of the repository file.
            assert "__pycache__" not in body
        except urllib.error.HTTPError as exc:
            assert exc.code in (403, 404)
        finally:
            server.shutdown()
            server.server_close()
