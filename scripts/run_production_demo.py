"""Unified Demo Launcher: docs/demo_launcher.md.

The operator-facing wrapper around scripts/build_full_production_demo.py. It
selects the mode, runs the builder as a child process with an argument array
(never an interpolated shell string), re-verifies the finished run, and only
then optionally serves and opens it.

It contains no scraper, SQL, analytics, or rendering logic, and imports none
of those modules. Everything it knows about a run comes from that run's own
manifest, checksums, and READY marker.

Verification before anything is presented, in this order:

    READY exists and parses
    manifest SHA-256 recomputed and matched against READY
    every checksum in checksums.sha256 recomputed and matched
    manifest promotable is true
    index.html resolves beneath the run root

The run directory comes from the builder's versioned JSONL completion
event, never from a directory listing -- the launcher will not present a
run merely because it is the newest one on disk. An unknown event schema
version fails closed.

Serving binds 127.0.0.1 only, sends nosniff/CSP/referrer headers, and
refuses any request that escapes the run root. Default behavior builds and
verifies without serving or opening, which is the shape CI uses.

Usage:
    python scripts/run_production_demo.py --mode fixture
    python scripts/run_production_demo.py --mode fixture --serve --open
    python scripts/run_production_demo.py --verified-run demo-runs/<id> --no-build --serve
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import tempfile
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOUNDARY_FILE = PROJECT_ROOT / ".repo-boundary-id"
BOUNDARY_ID = "apa-tracker"
DEFAULT_RUN_ROOT = PROJECT_ROOT / "demo-runs"
BUILDER = PROJECT_ROOT / "scripts" / "build_full_production_demo.py"

EVENT_SCHEMA_VERSION = "demo-event-v1"
MANIFEST_NAME = "demo_manifest.json"
CHECKSUMS_NAME = "checksums.sha256"
READY_NAME = "READY"
INDEX_NAME = "index.html"

EXIT_OK = 0
EXIT_PRESENTATION = 13
EXIT_INTERRUPT = 130

logger = logging.getLogger("run_production_demo")


class PresentationError(RuntimeError):
    """The run cannot be trusted, so nothing is served or opened."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_contained(path: Path, root: Path) -> Path:
    resolved = Path(path).resolve()
    root_resolved = Path(root).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise PresentationError(f"path escapes the run root: {path}")
    return resolved


def verify_run(run_dir: Path, run_root: Path) -> dict:
    """Re-verify a finished run from disk. Returns its manifest."""
    run_dir = resolve_contained(run_dir, run_root)
    if not run_dir.is_dir():
        raise PresentationError(f"run directory does not exist: {run_dir}")

    ready_path = run_dir / READY_NAME
    if not ready_path.is_file():
        raise PresentationError(f"no {READY_NAME} marker: the run is not promotable")
    try:
        ready = json.loads(ready_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise PresentationError(f"{READY_NAME} is not valid JSON: {exc}") from None

    manifest_path = run_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise PresentationError(f"missing {MANIFEST_NAME}")
    actual_manifest_hash = sha256_file(manifest_path)
    if ready.get("manifest_sha256") != actual_manifest_hash:
        raise PresentationError(
            "manifest hash does not match the READY marker: the bundle changed after finalization"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("run_id") != ready.get("run_id"):
        raise PresentationError("READY run id does not match the manifest run id")
    if not manifest.get("promotable"):
        raise PresentationError("manifest does not mark this run promotable")

    checksums_path = run_dir / CHECKSUMS_NAME
    if not checksums_path.is_file():
        raise PresentationError(f"missing {CHECKSUMS_NAME}")
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split("  ", 1)
        target = resolve_contained(run_dir / relative, run_dir)
        if not target.is_file():
            raise PresentationError(f"checksummed artifact is missing: {relative}")
        if sha256_file(target) != digest:
            raise PresentationError(f"checksum mismatch: {relative}")

    index_path = resolve_contained(run_dir / INDEX_NAME, run_dir)
    if not index_path.is_file():
        raise PresentationError(f"missing {INDEX_NAME}")

    return manifest


def _completion_event(events_path: Path) -> dict:
    """The builder's own versioned completion event."""
    if not events_path.is_file():
        raise PresentationError("builder produced no event stream")
    completion = None
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("schema_version") != EVENT_SCHEMA_VERSION:
            raise PresentationError(
                f"unknown builder event schema {event.get('schema_version')!r}"
            )
        if event.get("phase") == "complete":
            completion = event
    if completion is None:
        raise PresentationError("builder emitted no completion event")
    return completion


def invoke_builder(forwarded: list[str], events_path: Path) -> int:
    """Start the builder as a child process with an argument array."""
    command = [sys.executable, str(BUILDER), *forwarded, "--events", str(events_path)]
    logger.info("Building: %s", " ".join(forwarded))
    completed = subprocess.run(command, cwd=str(PROJECT_ROOT), check=False)
    return completed.returncode


class _RunHandler(SimpleHTTPRequestHandler):
    """Serves exactly one verified run root, with conservative headers."""

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'",
        )
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def translate_path(self, path):
        resolved = Path(super().translate_path(path)).resolve()
        root = Path(self.directory).resolve()
        if resolved != root and root not in resolved.parents:
            return str(root)  # refuse to escape the run root
        return str(resolved)

    def log_message(self, format, *args):  # noqa: A002 - base class signature
        logger.debug("http %s", format % args)


def serve(run_dir: Path, port: int) -> tuple[ThreadingHTTPServer, str]:
    handler = partial(_RunHandler, directory=str(run_dir))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/{INDEX_NAME}"


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Build, verify, and present a demo run.")
    parser.add_argument("--mode", choices=("fixture", "live"))
    parser.add_argument("--verified-run", help="an existing run directory")
    parser.add_argument("--no-build", action="store_true", help="requires --verified-run")
    parser.add_argument("--serve", action="store_true", help="serve on loopback only")
    parser.add_argument("--port", type=int, default=0, help="loopback port; default ephemeral")
    parser.add_argument("--open", dest="open_browser", action="store_true", help="requires --serve")
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--promote", action="store_true", help="forwarded to the builder")
    parser.add_argument(
        "--resume", action="store_true",
        help="live mode only, forwarded to the builder: resume an interrupted acquisition",
    )
    parser.add_argument(
        "--source-db",
        help=(
            "live mode only, forwarded to the builder: build from this already-"
            "acquired database instead of a fresh scrape -- never rescrapes"
        ),
    )
    parser.add_argument(
        "--opponent-team-id",
        help="live mode only, forwarded to the builder: pin the scope's opponent team",
    )
    parser.add_argument(
        "--session",
        help="live mode only, forwarded to the builder: pin the scope's session name",
    )
    parser.add_argument(
        "--format",
        dest="format_name",
        help="live mode only, forwarded to the builder: pin the scope's format",
    )
    args = parser.parse_args(argv)

    if BOUNDARY_FILE.read_text(encoding="utf-8").strip() != BOUNDARY_ID if BOUNDARY_FILE.is_file() else True:
        logger.error("not the canonical APA-Tracker repository")
        return EXIT_PRESENTATION
    if args.open_browser and not args.serve:
        parser.error("--open requires --serve")
    if args.no_build and not args.verified_run:
        parser.error("--no-build requires --verified-run")
    if not args.no_build and not args.mode:
        parser.error("--mode is required unless --no-build is used")
    if args.resume and args.mode != "live":
        parser.error("--resume is only meaningful with --mode live")
    if args.source_db and args.mode != "live":
        parser.error("--source-db is only meaningful with --mode live")
    scope_overrides = (args.opponent_team_id, args.session, args.format_name)
    if any(scope_overrides) and args.mode != "live":
        parser.error("--opponent-team-id/--session/--format are only meaningful with --mode live")
    if any(scope_overrides) and not all(scope_overrides):
        parser.error("--opponent-team-id, --session and --format must be given together, or not at all")

    run_root = Path(args.run_root)

    try:
        if args.no_build:
            run_dir = Path(args.verified_run)
        else:
            forwarded = ["--mode", args.mode, "--run-root", str(run_root)]
            if args.promote:
                forwarded.append("--promote")
            if args.resume:
                forwarded.append("--resume")
            if args.source_db:
                forwarded.extend(["--source-db", args.source_db])
            if args.opponent_team_id:
                forwarded.extend(["--opponent-team-id", args.opponent_team_id])
            if args.session:
                forwarded.extend(["--session", args.session])
            if args.format_name:
                forwarded.extend(["--format", args.format_name])
            with tempfile.TemporaryDirectory(prefix="launcher-") as tmp:
                events_path = Path(tmp) / "events.jsonl"
                code = invoke_builder(forwarded, events_path)
                if code != EXIT_OK:
                    logger.error("Builder failed with exit code %d; nothing will be opened.", code)
                    return code
                completion = _completion_event(events_path)
                run_dir = PROJECT_ROOT / completion["run_dir"]

        manifest = verify_run(run_dir, run_root)
    except PresentationError as exc:
        logger.error("VERIFICATION FAILED: %s", exc)
        return EXIT_PRESENTATION
    except KeyboardInterrupt:
        return EXIT_INTERRUPT

    logger.info(
        "Verified run %s (%d artifacts, database %s)",
        manifest["run_id"], len(manifest["artifacts"]), manifest["database_sha256"][:12],
    )
    index_path = Path(run_dir).resolve() / INDEX_NAME
    if not args.serve:
        logger.info("Open: %s", index_path)
        return EXIT_OK

    server, url = serve(Path(run_dir).resolve(), args.port)
    logger.info("Serving on %s (loopback only). Ctrl+C to stop.", url)
    try:
        if args.open_browser:
            webbrowser.open(url)
        threading.Event().wait()
    except KeyboardInterrupt:
        logger.info("Stopping server.")
        return EXIT_INTERRUPT
    finally:
        server.shutdown()
        server.server_close()
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
