"""Repository boundary checks shared by the Match Night publisher and the UAT build (GPT audit #84).

Paul's rule (2026-10-07/08): all work, scratch files, workbook copies, screenshots and build outputs stay
inside the canonical APA-Tracker folder, whose common git dir is <canonical>/.git and whose origin is the
APA-Tracker URL. Comparing resolved path strings is not enough: a junction (or symlink, or other reparse
point) on the way makes an inside-looking path land outside, while both sides still resolve "equal".

So every check here walks the path component by component from the trusted root and refuses any
component that is a link, then also requires the final resolved path to stay inside the resolved root.
Callers run these checks BEFORE any fetch, create, delete, build or copy, and again right before use.

CLI (used by tools/build_ultimate_coach_final_uat.ps1):
    python scripts/repo_boundary.py check-output --repo <worktree> --dest <folder> [--dest <folder> ...]
exit 0 = allowed; exit 2 = refused (reason printed); nothing is created or deleted by the check itself.
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

CANONICAL_ROOT = Path(r"C:\Users\ssand\Desktop\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker")
CANONICAL_ORIGIN = "https://github.com/ssands5-cloud/APA-Tracker.git"


class BoundaryRefused(RuntimeError):
    pass


def run_git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise BoundaryRefused(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def same(a: Path, b: Path) -> bool:
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


def inside(child: Path, parent: Path) -> bool:
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def is_link(path: Path) -> bool:
    """Symlink, Windows junction or any other reparse point."""
    try:
        st = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def check_no_links(path: Path, root: Path, what: str) -> Path:
    """Every existing component from root down to path is a real directory/file (no symlink, junction or
    reparse point), and the final resolved path stays inside the resolved root. Returns the logical path."""
    root = Path(os.path.abspath(root))
    path = Path(os.path.abspath(path))
    try:
        rel = path.relative_to(root)
    except ValueError:
        raise BoundaryRefused(f"{what} {path} is not inside {root}") from None
    current = root
    if is_link(current):
        raise BoundaryRefused(f"{what}: {current} is a link/junction; refusing")
    for part in rel.parts:
        current = current / part
        if is_link(current):
            raise BoundaryRefused(f"{what}: {current} is a link/junction; refusing")
    if not inside(path, root):
        raise BoundaryRefused(f"{what} {path} resolves outside {root.resolve()}")
    return path


def check_repository(repo: Path, canonical: Path = CANONICAL_ROOT, origin: str = CANONICAL_ORIGIN) -> Path:
    """The checkout is the canonical repository (or a linked worktree of it) with the expected origin."""
    if not inside(repo, canonical):
        raise BoundaryRefused(f"{Path(repo).resolve()} is not inside the canonical repository {canonical}")
    check_no_links(repo, canonical, "repository checkout")
    repo = Path(repo).resolve()
    common = Path(run_git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    if not same(common, Path(canonical) / ".git"):
        raise BoundaryRefused(f"git common dir {common} is not {Path(canonical) / '.git'}")
    actual_origin = run_git(repo, "remote", "get-url", "origin")
    if actual_origin != origin:
        raise BoundaryRefused(f"origin is {actual_origin}, expected {origin}")
    return repo


def check_output_root(dest: Path, repo: Path, canonical: Path = CANONICAL_ROOT,
                      origin: str = CANONICAL_ORIGIN) -> Path:
    """A build output folder (existing or not yet created) that may be written: the repository is canonical
    (common dir + origin) and the folder is inside the canonical root with no link/junction on the way."""
    check_repository(repo, canonical, origin)
    dest = Path(os.path.abspath(dest))
    check_no_links(dest, canonical, "output folder")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    out = sub.add_parser("check-output")
    out.add_argument("--repo", type=Path, required=True)
    out.add_argument("--dest", type=Path, action="append", required=True)
    args = parser.parse_args(argv)
    try:
        for dest in args.dest:
            check_output_root(dest, args.repo)
    except BoundaryRefused as exc:
        print(f"Refused: {exc}")
        return 2
    print("Output folders are inside the canonical repository with no links on the way.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
