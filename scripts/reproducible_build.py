"""Recreate the entire tested environment from scratch, on any machine.

    python scripts/reproducible_build.py
    python scripts/reproducible_build.py --venv-dir .build-venv --out-dir dist
    python scripts/reproducible_build.py --keep-venv   # skip deleting it afterward
    python scripts/reproducible_build.py --fixtures path/to/repository-local/fixtures

What "works on my machine" vs. "works on any machine, forever" actually
means here: this script does not trust the interpreter it happens to be
invoked with. It creates a brand-new virtual environment, installs ONLY
what `requirements-dev.txt` (the pip-compile lock -- see
docs/reproducible_builds.md) pins, and does everything else -- verifying
those are really the versions that got installed, running the full test
suite (which includes the determinism check,
tests/test_full_pipeline_integration.py::TestFullPipelineDeterminism),
running the real pipeline, and writing a build manifest -- through THAT
interpreter, never the one running this script.

Steps:
    1. Create a fresh venv
    2. Install pinned dependencies (requirements-dev.txt)
    3. Verify the installed versions match the lockfile exactly
    4. Run the full test suite
    5. Run the real pipeline against the committed CI sample tree in a clean
       scratch directory and confirm every expected artifact was written
    6. Write BUILD_INFO.json -- the artifact this whole thing is FOR: proof
       of exactly what commit, what interpreter, and what dependency
       versions produced a given set of exports (see docs/reproducible_builds.md,
       "Step 5: versioning artifacts").

Any step failing stops the build immediately with a non-zero exit code --
a build that "mostly" reproduced is not a reproducible build.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import venv
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
LOCKFILE = ROOT / "requirements-dev.txt"
DEFAULT_VENV_DIR = ROOT / ".build-venv"
DEFAULT_OUT_DIR = ROOT / "dist"
SAMPLE_FIXTURES = ROOT / "tests" / "fixtures" / "sample_pipeline"
CI_CONFIG = ROOT / "tests" / "fixtures" / "ci_pipeline_config.yaml"
CI_BUILD_DIR = ROOT / "ci-build"

SUPPORTED_PYTHON = {(3, 12), (3, 13)}
EXPECTED_ARTIFACTS = {
    "analysis_tabs.html",
    "apa_data.json",
    "apa_stats.xlsx",
    "captains_edge.html",
    "captains_edge.json",
    "captains_edge.xlsx",
    "lineups.json",
}
BUILD_VENV_MARKER = ".apa-reproducible-build-venv"


def step(label: str) -> None:
    print(f"\n=== {label} ===")


def fail(message: str) -> None:
    print(f"\nBUILD FAILED: {message}\n")
    sys.exit(1)


def venv_python(venv_dir: Path) -> Path:
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return venv_dir / bin_dir / exe


def project_child_path(raw_path: str, option: str) -> Path:
    """Resolve a CLI path and require it to be a child of this repository.

    The build deletes its virtual-environment directory before and after a
    run.  Rejecting the repository root and every path outside it turns a
    mistyped ``--venv-dir`` into a clear error instead of a recursive delete
    aimed at unrelated work.
    """
    path = Path(raw_path)
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    root = ROOT.resolve()
    if resolved == root:
        raise ValueError(
            f"{option} must be a child directory of {root}, "
            "not the repository root"
        )
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{option} must stay inside the repository: {resolved}") from exc
    return resolved


def python_is_supported(version: Sequence[int] = sys.version_info) -> bool:
    """Whether ``version`` belongs to the project's supported build matrix."""
    return tuple(version[:2]) in SUPPORTED_PYTHON


def paths_overlap(left: Path, right: Path) -> bool:
    """True when either path contains the other (including equality)."""
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents


def is_replaceable_build_venv(path: Path) -> bool:
    """Whether an existing directory is safe for this script to replace.

    The marker covers environments made by this version.  The structural
    fallback admits only the documented default ``.build-venv`` from before
    the marker existed; a normal developer venv passed by mistake fails
    closed instead of being deleted.
    """
    if not path.is_dir():
        return False
    if (path / BUILD_VENV_MARKER).is_file():
        return True
    return (
        path.resolve() == DEFAULT_VENV_DIR.resolve()
        and (path / "pyvenv.cfg").is_file()
        and venv_python(path).is_file()
    )


def run_in_venv(venv_dir: Path, args: list[str], label: str, cwd: Optional[Path] = None) -> None:
    step(label)
    result = subprocess.run([str(venv_python(venv_dir)), *args], cwd=str(cwd or ROOT))
    if result.returncode != 0:
        fail(f"{label} exited {result.returncode}")


def parse_lockfile_pins(lockfile: Path) -> dict[str, str]:
    """{normalized package name: version} for every `name==version` line."""
    pins: dict[str, str] = {}
    for line in lockfile.read_text(encoding="utf-8").splitlines():
        line = line.split(" #", 1)[0].strip()  # drop the "# via ..." trailer
        if not line or line.startswith("#") or line.startswith("-r "):
            continue
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        pins[name.strip().lower().replace("_", "-")] = version.strip()
    return pins


def installed_versions(venv_dir: Path) -> dict[str, str]:
    result = subprocess.run(
        [str(venv_python(venv_dir)), "-m", "pip", "freeze"],
        cwd=str(ROOT), capture_output=True, text=True, check=True,
    )
    versions: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        versions[name.strip().lower().replace("_", "-")] = version.strip()
    return versions


def git_info() -> dict[str, object]:
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else ""

    commit = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain"))
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    return {"commit": commit or None, "dirty": dirty, "branch": branch or None}


def read_version() -> Optional[str]:
    """The project's own release version from the repo-root VERSION file
    (e.g. "1.0.0-rc1"), or None if that file doesn't exist yet -- release
    metadata the manifest reports when available, not something this
    script requires to build. See docs/versioning.md."""
    if not VERSION_FILE.is_file():
        return None
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    return version or None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--venv-dir", default=str(DEFAULT_VENV_DIR),
                         help=f"where to create the fresh venv (default: {DEFAULT_VENV_DIR})")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                         help=f"where to write BUILD_INFO.json (default: {DEFAULT_OUT_DIR})")
    parser.add_argument("--keep-venv", action="store_true",
                         help="do not delete the venv when the build finishes")
    parser.add_argument(
        "--fixtures",
        default=str(SAMPLE_FIXTURES),
        help="fixture tree to ingest (default: the committed CI sample tree)",
    )
    args = parser.parse_args(argv)

    if not python_is_supported():
        fail(
            f"Python {sys.version_info.major}.{sys.version_info.minor} is unsupported; "
            "run this build with Python 3.12 or 3.13"
        )

    try:
        venv_dir = project_child_path(args.venv_dir, "--venv-dir")
        out_dir = project_child_path(args.out_dir, "--out-dir")
        fixtures_dir = project_child_path(args.fixtures, "--fixtures")
        ci_build_dir = project_child_path(str(CI_BUILD_DIR), "CI build directory")
    except ValueError as exc:
        parser.error(str(exc))

    if paths_overlap(venv_dir, out_dir):
        parser.error("--venv-dir and --out-dir must not overlap")
    if paths_overlap(venv_dir, fixtures_dir):
        parser.error("--venv-dir must not overlap --fixtures")
    if paths_overlap(out_dir, fixtures_dir):
        parser.error("--out-dir must not overlap --fixtures")
    if paths_overlap(venv_dir, ci_build_dir):
        parser.error("--venv-dir must not overlap the CI build directory")
    if paths_overlap(out_dir, ci_build_dir):
        parser.error("--out-dir must not overlap the CI build directory")
    if paths_overlap(fixtures_dir, ci_build_dir):
        parser.error("--fixtures must not overlap the CI build directory")

    if not LOCKFILE.is_file():
        fail(f"{LOCKFILE} does not exist -- run pip-compile first (see docs/reproducible_builds.md)")
    if not fixtures_dir.is_dir() or not any(fixtures_dir.rglob("*.json")):
        fail(f"fixture tree has no JSON fixtures: {fixtures_dir}")

    # 1. Fresh venv -- deleted first if a stale one is left over from a
    #    previous run, so "fresh" is not aspirational.
    step("1. Create a fresh virtual environment")
    if venv_dir.exists():
        if not is_replaceable_build_venv(venv_dir):
            fail(
                f"refusing to delete {venv_dir}: it is not a recognized "
                "reproducible-build virtual environment"
            )
        shutil.rmtree(venv_dir)
    print(f"Creating venv at {venv_dir}")
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    (venv_dir / BUILD_VENV_MARKER).write_text(
        "Created by scripts/reproducible_build.py\n", encoding="utf-8"
    )

    # 2. Install pinned dependencies -- the lockfile only, nothing implied
    #    by whatever happens to already be on this machine.
    run_in_venv(venv_dir, ["-m", "pip", "install", "--upgrade", "pip"], "2a. Upgrade pip in the venv")
    run_in_venv(venv_dir, ["-m", "pip", "install", "-r", str(LOCKFILE)],
                "2b. Install pinned dependencies (requirements-dev.txt)")

    # 3. Verify versions -- what got installed must be EXACTLY what the
    #    lockfile pinned, not "close enough".
    step("3. Verify installed versions match the lockfile")
    pinned = parse_lockfile_pins(LOCKFILE)
    installed = installed_versions(venv_dir)
    mismatches = {
        name: (version, installed.get(name))
        for name, version in pinned.items()
        if installed.get(name) != version
    }
    if mismatches:
        for name, (wanted, got) in mismatches.items():
            print(f"  MISMATCH {name}: lockfile wants {wanted}, venv has {got or 'MISSING'}")
        fail("installed versions do not match requirements-dev.txt")
    print(f"All {len(pinned)} pinned package(s) match exactly.")

    # 4. Full test suite, through the fresh venv's own interpreter -- this
    #    already includes tests/test_full_pipeline_integration.py's
    #    determinism check (step "6" in the roadmap request is folded in
    #    here rather than duplicated as a separate ad hoc comparison).
    run_in_venv(venv_dir, ["-m", "pytest", "tests/", "-q"], "4. Run the full test suite")

    # 5. Run the real pipeline against an explicitly selected fixture tree.
    #    The committed sample is the default on every machine; ignored local
    #    scrape state is never selected merely because it happens to exist.
    #    Clear the documented scratch directory first so a stale artifact
    #    cannot make an incomplete run look successful.
    step("5. Run the full pipeline and confirm every artifact is produced")
    if ci_build_dir.exists():
        shutil.rmtree(ci_build_dir)
    print(f"Using fixtures at {fixtures_dir}")
    pipeline_args = [
        "-m", "pipeline", "--fixtures", str(fixtures_dir),
        "--config", str(CI_CONFIG),
    ]
    exports_dir = ci_build_dir / "exports"
    result = subprocess.run([str(venv_python(venv_dir)), *pipeline_args], cwd=str(ROOT))
    if result.returncode != 0:
        fail(f"pipeline run exited {result.returncode}")
    produced = sorted(p.name for p in exports_dir.glob("*")) if exports_dir.is_dir() else []
    missing = sorted(EXPECTED_ARTIFACTS.difference(produced))
    if missing:
        fail(
            "pipeline run reported success but did not produce: "
            + ", ".join(missing)
        )
    print(f"Artifacts in {exports_dir}: {', '.join(produced)}")

    # 6. Build manifest: what commit, what interpreter, what exact
    #    dependency versions produced this. See docs/reproducible_builds.md.
    step("6. Write the build manifest")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "apa_tracker_version": read_version(),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "git": git_info(),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "dependencies": pinned,
        "lockfile": str(LOCKFILE.relative_to(ROOT)),
        "fixtures_used": str(fixtures_dir.relative_to(ROOT)),
        "exports_dir": str(exports_dir),
        "artifacts": produced,
    }
    manifest_path = out_dir / "BUILD_INFO.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path}")
    if manifest["git"]["dirty"]:
        print(
            "NOTE: the working tree has uncommitted changes -- this build "
            "does not correspond to a pushed commit. Commit first for a "
            "manifest someone else can actually reproduce."
        )

    if not args.keep_venv:
        step("Clean up")
        shutil.rmtree(venv_dir)
        print(f"Removed {venv_dir} (pass --keep-venv to keep it)")

    print("\n=== Reproducible build completed successfully ===")
    print(f"Version: {manifest['apa_tracker_version'] or '(no VERSION file)'}")
    print(f"Commit:  {manifest['git']['commit']}")
    print(f"Python:  {manifest['python']['version']}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
