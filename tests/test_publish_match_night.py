"""Fail-closed publisher (GPT audit #84 P1): every guard runs before anything is built, deleted or copied.
Uses a throwaway repository with a FAKE origin (never a copy of APA-Tracker), so the machine-level
repository-boundary hook is neither triggered nor bypassed."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts.publish_match_night import (
    PUBLISHED,
    PublishRefused,
    check_pages_worktree,
    check_repository,
    check_site_dir,
    publish,
)

ORIGIN = "https://example.invalid/fake/publisher-test.git"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=ENV).stdout.strip()


@pytest.fixture()
def canon(tmp_path):
    root = tmp_path / "canon"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", ORIGIN)
    (root / ".repo-boundary-id").write_text("fake\n", encoding="utf-8")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    git(root, "add", "--", ".repo-boundary-id", "README.md")
    git(root, "commit", "-q", "-m", "init")
    return root


def _demo_builder(site: Path):
    from tests.test_excel_war_room_formulas import _payload
    from ui.match_night import build_site
    build_site(_payload(), viewer_external_id="1001", passphrase="correct horse battery staple",
               built_at="2026-10-07 18:00 UTC", out=site, demo=True)


def _pages(canon):
    return canon / ".worktrees" / "gh-pages"


def test_wrong_root_or_origin_is_refused_before_anything_happens(canon, tmp_path):
    outsider = tmp_path / "other"
    outsider.mkdir()
    git(outsider, "init", "-q")
    with pytest.raises(PublishRefused, match="not inside the canonical"):
        check_repository(outsider, canon, ORIGIN)
    with pytest.raises(PublishRefused, match="origin is"):
        check_repository(canon, canon, "https://example.invalid/somewhere-else.git")
    assert check_repository(canon, canon, ORIGIN) == canon.resolve()
    with pytest.raises(PublishRefused, match="build folder must be"):
        check_site_dir(tmp_path / "elsewhere", canon)


def test_first_publish_creates_the_worktree_and_commits_only_the_allowlist(canon):
    keep = canon / "tmp" / "match_night_site" / "keep-me.txt"     # not generated: must survive a rebuild
    keep.parent.mkdir(parents=True)
    keep.write_text("mine", encoding="utf-8")
    commit = publish(canon, demo=True, match_id=None, db=None, push=False, canonical=canon, origin=ORIGIN,
                     builder=_demo_builder)
    pages = _pages(canon)
    assert git(pages, "branch", "--show-current") == "gh-pages"
    assert sorted(git(pages, "ls-files").splitlines()) == sorted(PUBLISHED)
    message = git(pages, "log", "-1", "--format=%B")
    assert "Publish Match Night DEMO (synthetic players)" in message and "Claude Sonnet 5" in message
    assert commit == git(pages, "rev-parse", "--short", "HEAD")
    assert keep.read_text(encoding="utf-8") == "mine"
    assert check_pages_worktree(pages, canon) == "ready"


def test_uncommitted_work_wrong_branch_or_extra_files_in_pages_are_refused_untouched(canon):
    publish(canon, demo=True, match_id=None, db=None, push=False, canonical=canon, origin=ORIGIN, builder=_demo_builder)
    pages = _pages(canon)
    wip = pages / "notes.txt"
    wip.write_text("captain's WIP", encoding="utf-8")
    with pytest.raises(PublishRefused, match="uncommitted work"):
        publish(canon, demo=True, match_id=None, db=None, push=False, canonical=canon, origin=ORIGIN, builder=_demo_builder)
    assert wip.read_text(encoding="utf-8") == "captain's WIP"          # nothing was touched
    wip.unlink()
    (pages / "index.html").write_text("edited", encoding="utf-8")
    with pytest.raises(PublishRefused, match="uncommitted work"):
        check_pages_worktree(pages, canon)
    git(pages, "checkout", "-q", "--", "index.html")
    (pages / "extra.html").write_text("x", encoding="utf-8")
    git(pages, "add", "--", "extra.html")
    git(pages, "commit", "-q", "-m", "extra")
    with pytest.raises(PublishRefused, match="outside the published allowlist"):
        check_pages_worktree(pages, canon)
    git(pages, "checkout", "-q", "-b", "other")
    with pytest.raises(PublishRefused, match="expected gh-pages"):
        check_pages_worktree(pages, canon)
    with pytest.raises(PublishRefused, match="Pages checkout must be"):
        check_pages_worktree(canon / "somewhere", canon)


def test_failed_build_publishes_nothing(canon):
    def broken(site):
        raise PublishRefused("the Match Night package was not built; nothing was published")
    with pytest.raises(PublishRefused, match="not built"):
        publish(canon, demo=True, match_id=None, db=None, push=False, canonical=canon, origin=ORIGIN, builder=broken)
    assert not _pages(canon).exists()
