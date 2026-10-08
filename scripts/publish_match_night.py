"""Publish the Match Night site to the gh-pages branch -- fail-closed (GPT audit #84 P1).

Every check runs BEFORE anything is built, deleted, copied, fetched or checked out:
- the repository is the canonical APA-Tracker checkout (exact common git dir and origin URL);
- the build output folder resolves inside <repo>/tmp/ and is exactly the expected folder;
- the Pages checkout is the linked worktree <canonical>/.worktrees/gh-pages, on branch gh-pages, of the
  same repository, with no uncommitted work and no files outside the published allowlist.
Only allowlisted generated files are ever removed, copied or staged; staging and committing name those
paths explicitly. Any git failure stops the run. Hooks are never bypassed; history is never rewritten.
The passphrase is handled only by scripts/build_match_night_package.py (hidden prompt / env var).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

CANONICAL_ROOT = Path(r"C:\Users\ssand\Desktop\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker")
CANONICAL_ORIGIN = "https://github.com/ssands5-cloud/APA-Tracker.git"
PAGES_BRANCH = "gh-pages"
PUBLISHED = (".nojekyll", ".repo-boundary-id", "index.html", "sw.js", "manifest.webmanifest", "package.json",
             "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png")
FOOTER = "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"


class PublishRefused(RuntimeError):
    pass


def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise PublishRefused(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def _same(a: Path, b: Path) -> bool:
    return str(a.resolve()).lower() == str(b.resolve()).lower()


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def check_repository(repo: Path, canonical: Path = CANONICAL_ROOT, origin: str = CANONICAL_ORIGIN) -> Path:
    """The checkout is the canonical repository (or a linked worktree of it) with the expected origin."""
    repo = repo.resolve()
    if not _inside(repo, canonical):
        raise PublishRefused(f"{repo} is not inside the canonical repository {canonical}")
    common = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    if not _same(common, canonical / ".git"):
        raise PublishRefused(f"git common dir {common} is not {canonical / '.git'}")
    actual_origin = git(repo, "remote", "get-url", "origin")
    if actual_origin != origin:
        raise PublishRefused(f"origin is {actual_origin}, expected {origin}")
    return repo


def check_site_dir(site: Path, repo: Path) -> Path:
    site = site.resolve()
    expected = (repo / "tmp" / "match_night_site").resolve()
    if not _same(site, expected):
        raise PublishRefused(f"build folder must be {expected}, got {site}")
    return site


def check_pages_worktree(pages: Path, canonical: Path = CANONICAL_ROOT) -> str:
    """Return 'missing' (safe to create) or 'ready'. Refuses anything unexpected."""
    expected = (canonical / ".worktrees" / "gh-pages").resolve()
    if not _same(pages, expected):
        raise PublishRefused(f"Pages checkout must be {expected}, got {pages.resolve()}")
    if not pages.exists():
        return "missing"
    common = Path(git(pages, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    if not _same(common, canonical / ".git"):
        raise PublishRefused(f"{pages} is not a worktree of {canonical}")
    top = Path(git(pages, "rev-parse", "--show-toplevel"))
    if not _same(top, pages):
        raise PublishRefused(f"{pages} is not the top of a worktree (top is {top})")
    branch = git(pages, "branch", "--show-current")
    if branch != PAGES_BRANCH:
        raise PublishRefused(f"{pages} is on branch {branch!r}, expected {PAGES_BRANCH}")
    dirty = git(pages, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise PublishRefused(f"{pages} has uncommitted work; refusing to touch it:\n{dirty}")
    tracked = set(git(pages, "ls-files").splitlines())
    unexpected = sorted(tracked - set(PUBLISHED))
    if unexpected:
        raise PublishRefused(f"{pages} tracks files outside the published allowlist: {unexpected}")
    return "ready"


def check_site_contents(site: Path) -> None:
    missing = [name for name in PUBLISHED if name != ".repo-boundary-id" and not (site / name).is_file()]
    if missing:
        raise PublishRefused(f"the built site is missing {missing}")


def sync_allowlisted(site: Path, pages: Path, repo: Path) -> None:
    """Copy exactly the allowlisted files (nothing is deleted except files of the same names)."""
    (pages / "icons").mkdir(exist_ok=True)
    for name in PUBLISHED:
        source = repo / name if name == ".repo-boundary-id" else site / name
        shutil.copyfile(source, pages / name)


def publish(repo: Path, *, demo: bool, match_id: str | None, db: Path | None, push: bool = True,
            canonical: Path = CANONICAL_ROOT, origin: str = CANONICAL_ORIGIN, builder=None) -> str:
    repo = check_repository(repo, canonical, origin)
    site = check_site_dir(repo / "tmp" / "match_night_site", repo)
    pages = canonical / ".worktrees" / "gh-pages"
    state = check_pages_worktree(pages, canonical)

    if site.exists():
        for name in PUBLISHED:                      # remove only previously generated files, then the empty dirs
            target = site / name
            if target.is_file():
                target.unlink()
        for leftover in sorted(site.rglob("*"), reverse=True):
            if leftover.is_dir() and not any(leftover.iterdir()):
                leftover.rmdir()
    if builder is not None:                         # tests: build in-process
        builder(site)
    else:
        build = [sys.executable, str(repo / "scripts" / "build_match_night_package.py"), "--out", str(site)]
        build += ["--demo"] if demo else ["--db", str(db)]
        if match_id:
            build += ["--match-id", match_id]
        if subprocess.run(build, cwd=repo).returncode != 0:
            raise PublishRefused("the Match Night package was not built; nothing was published")
    check_site_contents(site)

    if state == "missing":
        remote = git(repo, "ls-remote", "--heads", "origin", PAGES_BRANCH) if push else ""
        if remote:
            git(repo, "fetch", "origin", PAGES_BRANCH)
            git(repo, "worktree", "add", str(pages), PAGES_BRANCH)
        else:
            git(repo, "worktree", "add", "--orphan", "-b", PAGES_BRANCH, str(pages))
        check_pages_worktree(pages, canonical)
    elif push:
        git(pages, "pull", "--ff-only", "origin", PAGES_BRANCH)
        check_pages_worktree(pages, canonical)

    sync_allowlisted(site, pages, repo)
    git(pages, "add", "--", *PUBLISHED)
    if not git(pages, "status", "--porcelain", "--", *PUBLISHED):
        return "unchanged"
    label = "DEMO (synthetic players)" if demo else "private encrypted package"
    git(pages, "commit", "-m", f"Publish Match Night {label}\n\n{FOOTER}", "--", *PUBLISHED)
    if push:
        git(pages, "push", "origin", PAGES_BRANCH)
    return git(pages, "rev-parse", "--short", "HEAD")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--match-id", default=None)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.demo and (args.db is None or not args.db.is_file()):
        print("Refused: --db <staging.db> is required for a real package (or use --demo).")
        return 2
    repo = Path(__file__).resolve().parent.parent
    try:
        commit = publish(repo, demo=args.demo, match_id=args.match_id, db=args.db)
    except PublishRefused as exc:
        print(f"Refused, nothing published: {exc}")
        return 2
    print(f"Published gh-pages {commit}. Open https://ssands5-cloud.github.io/APA-Tracker/ (Pages updates in about a minute).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
