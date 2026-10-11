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
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:                                    # imported as scripts.publish_match_night (tests)
    from scripts.repo_boundary import (CANONICAL_ORIGIN, CANONICAL_ROOT, BoundaryRefused, check_no_links,
                                       check_repository, inside as _inside, is_link as _is_link, same as _same)
except ImportError:                     # run as python scripts/publish_match_night.py
    from repo_boundary import (CANONICAL_ORIGIN, CANONICAL_ROOT, BoundaryRefused, check_no_links,  # type: ignore
                               check_repository, inside as _inside, is_link as _is_link, same as _same)

PAGES_BRANCH = "gh-pages"
PUBLISHED = (".nojekyll", ".repo-boundary-id", "index.html", "sw.js", "manifest.webmanifest", "package.json",
             "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png")
FOOTER = "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"

PublishRefused = BoundaryRefused        # one refusal type for every boundary and publisher guard


def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise PublishRefused(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def check_site_dir(site: Path, repo: Path) -> Path:
    expected = Path(os.path.abspath(repo / "tmp" / "match_night_site"))
    if os.path.normcase(os.path.abspath(site)) != os.path.normcase(str(expected)):
        raise PublishRefused(f"build folder must be {expected}, got {os.path.abspath(site)}")
    check_no_links(expected, repo, "build folder")
    if (expected / "icons").exists():
        check_no_links(expected / "icons", repo, "build folder")
    return expected


def check_pages_worktree(pages: Path, canonical: Path = CANONICAL_ROOT) -> str:
    """Return 'missing' (safe to create) or 'ready'. Refuses anything unexpected."""
    expected = Path(os.path.abspath(canonical / ".worktrees" / "gh-pages"))
    if os.path.normcase(os.path.abspath(pages)) != os.path.normcase(str(expected)):
        raise PublishRefused(f"Pages checkout must be {expected}, got {os.path.abspath(pages)}")
    check_no_links(expected, canonical, "Pages checkout")
    if not pages.exists():
        return "missing"
    if (pages / "icons").exists():
        check_no_links(pages / "icons", canonical, "Pages checkout")
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


def preflight_paths(site: Path, pages: Path, repo: Path, canonical: Path = CANONICAL_ROOT) -> None:
    """Every path this publish may delete, read or write -- all allowlisted build files (cleanup targets and
    copy sources), the boundary marker, and every Pages destination -- is checked TOGETHER, so a link found
    on the last path refuses before the first file is touched (GPT audit #84: a junctioned package.json was
    refused only after index.html had already been deleted)."""
    check_no_links(site, repo, "build folder")
    check_no_links(site / "icons", repo, "build folder")
    check_no_links(pages / "icons", canonical, "Pages checkout")
    for name in PUBLISHED:
        check_no_links(site / name, repo, "build folder")
        if name == ".repo-boundary-id":
            check_no_links(repo / name, repo, "published source")
        check_no_links(pages / name, canonical, "published destination")


def sync_allowlisted(site: Path, pages: Path, repo: Path, canonical: Path = CANONICAL_ROOT) -> None:
    """Copy exactly the allowlisted files (nothing is deleted except files of the same names). Every source
    and destination is checked for links/junctions immediately before it is used."""
    (pages / "icons").mkdir(exist_ok=True)
    for name in PUBLISHED:
        source = repo / name if name == ".repo-boundary-id" else site / name
        check_no_links(source, repo, "published source")
        check_no_links(pages / name, canonical, "published destination")
        shutil.copyfile(source, pages / name)


def publish(repo: Path, *, demo: bool, match_id: str | None, db: Path | None, push: bool = True,
            canonical: Path = CANONICAL_ROOT, origin: str = CANONICAL_ORIGIN, builder=None) -> str:
    repo = check_repository(repo, canonical, origin)
    site = check_site_dir(repo / "tmp" / "match_night_site", repo)
    pages = canonical / ".worktrees" / "gh-pages"
    state = check_pages_worktree(pages, canonical)
    # Publish only committed source, and say which (GPT audit #84: never label working changes as HEAD).
    changed = git(repo, "status", "--porcelain", "--untracked-files=no")
    if changed:
        raise PublishRefused(f"the source checkout has uncommitted changes; commit them first:\n{changed}")
    source = git(repo, "rev-parse", "HEAD")
    if push and not git(repo, "branch", "-r", "--contains", source):
        raise PublishRefused(f"source commit {source[:7]} is not on origin yet; push it first")

    preflight_paths(site, pages, repo, canonical)   # ALL paths, before anything is deleted or built
    if site.exists():
        for name in PUBLISHED:                      # remove only previously generated files (links refused)
            target = site / name
            check_no_links(target, repo, "build folder")
            if target.is_file():
                target.unlink()
        icons = site / "icons"
        if icons.is_dir() and not _is_link(icons) and not any(icons.iterdir()):
            icons.rmdir()
    check_site_dir(site, repo)                      # re-check right before writing
    if builder is not None:                         # tests: build in-process
        builder(site)
    else:
        build = [sys.executable, str(repo / "scripts" / "build_match_night_package.py"), "--out", str(site)]
        build += ["--demo"] if demo else ["--db", str(db)]
        if match_id:
            build += ["--match-id", match_id]
        if subprocess.run(build, cwd=repo).returncode != 0:
            raise PublishRefused("the Match Night package was not built; nothing was published")
    check_site_dir(site, repo)
    preflight_paths(site, pages, repo, canonical)   # a link made during the build: refuse before Pages is touched
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

    preflight_paths(site, pages, repo, canonical)   # immediately before copying
    sync_allowlisted(site, pages, repo, canonical)
    git(pages, "add", "--", *PUBLISHED)
    if not git(pages, "status", "--porcelain", "--", *PUBLISHED):
        return "unchanged"
    label = "DEMO (synthetic players)" if demo else "private encrypted package"
    git(pages, "commit", "-m", f"Publish Match Night {label}\n\nSource: {source}\n\n{FOOTER}", "--", *PUBLISHED)
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
