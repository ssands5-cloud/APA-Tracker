"""Shared repository-boundary checks (scripts/repo_boundary.py), used by the Match Night publisher and the
UAT build's output folder (GPT audit #84: a junctioned DestinationRoot passed a string-prefix check).
Throwaway repositories with a FAKE origin only; junctions on Windows, symlinks elsewhere; every outside
target is a sentinel that must survive."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts.repo_boundary import CANONICAL_ROOT, BoundaryRefused, check_output_root, main

ORIGIN = "https://example.invalid/fake/boundary-test.git"


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


def _link(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


@pytest.fixture()
def canon(tmp_path):
    root = tmp_path / "canon"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", ORIGIN)
    return root


def test_an_inside_output_folder_is_allowed_even_before_it_exists(canon):
    assert check_output_root(canon / "tmp" / "uat", canon, canon, ORIGIN) == canon / "tmp" / "uat"
    (canon / "tmp" / "uat").mkdir(parents=True)
    assert check_output_root(canon / "tmp" / "uat" / "build-abc", canon, canon, ORIGIN)


def test_an_outside_output_folder_is_refused(canon, tmp_path):
    with pytest.raises(BoundaryRefused, match="is not inside"):
        check_output_root(tmp_path / "Desktop" / "Ultimate Coach FINAL UAT", canon, canon, ORIGIN)


@pytest.mark.parametrize("linked", ["tmp", "tmp/uat"])
def test_a_junction_anywhere_on_the_way_is_refused_and_the_outside_target_untouched(canon, tmp_path, linked):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside sentinel", encoding="utf-8")
    link = canon / linked
    link.parent.mkdir(parents=True, exist_ok=True)
    _link(link, outside)
    with pytest.raises(BoundaryRefused, match="link/junction"):
        check_output_root(canon / "tmp" / "uat" / "build-abc", canon, canon, ORIGIN)
    assert sentinel.read_text(encoding="utf-8") == "outside sentinel"
    assert sorted(p.name for p in outside.iterdir()) == ["sentinel.txt"]   # nothing was created there


def test_a_wrong_origin_or_foreign_repository_is_refused(canon, tmp_path):
    with pytest.raises(BoundaryRefused, match="origin is"):
        check_output_root(canon / "tmp" / "uat", canon, canon, "https://example.invalid/other.git")
    other = canon / "nested-other"
    other.mkdir()
    git(other, "init", "-q")
    git(other, "remote", "add", "origin", ORIGIN)
    with pytest.raises(BoundaryRefused, match="git common dir"):
        check_output_root(canon / "tmp" / "uat", other, canon, ORIGIN)


def test_the_cli_refuses_with_exit_2_and_creates_nothing(capsys):
    target = CANONICAL_ROOT.parent / "UC-boundary-cli-probe-must-not-exist"     # beside the canonical folder
    code = main(["check-output", "--repo", str(Path.cwd()), "--dest", str(target)])
    assert code == 2 and "Refused:" in capsys.readouterr().out
    assert not target.exists()


def test_the_uat_build_checks_the_boundary_before_the_fetch_and_every_write():
    """tools/build_ultimate_coach_final_uat.ps1 must call the shared check (not a string-prefix test) before
    git fetch, and immediately before each New-Item/Remove-Item/Move-Item/Copy-Item/Set-Content."""
    lines = (Path(__file__).resolve().parent.parent / "tools" / "build_ultimate_coach_final_uat.ps1").read_text(
        encoding="utf-8").splitlines()
    code = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    assert not any("StartsWith(" in l for l in code)
    last_check = None
    writes = 0
    for i, line in enumerate(code):
        if line.startswith("Assert-OutputInsideCanonical"):
            last_check = i
        elif line.startswith("git -C $RepoRoot fetch"):
            assert last_check is not None, "fetch before the boundary check"
        elif any(w in line for w in ("New-Item", "Remove-Item", "Move-Item", "Copy-Item", "Set-Content")) or (
                line.startswith("python scripts/build_")):
            writes += 1
            assert last_check is not None and i - last_check <= 8, f"write without a check just before it: {line}"
    assert writes >= 8
    default = next(l for l in code if l.startswith("[string]$DestinationRoot"))
    assert "tmp\\uat" in default and "Desktop" not in default
