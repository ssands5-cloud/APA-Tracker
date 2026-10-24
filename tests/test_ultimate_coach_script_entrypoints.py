"""Regression tests for direct-file Ultimate Coach builder entry points."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "script",
    [
        "scripts/build_ultimate_coach_production.py",
        "scripts/build_ultimate_coach_excel.py",
        "scripts/build_ultimate_coach_html.py",
    ],
)
def test_ultimate_coach_builders_support_direct_file_invocation(script: str):
    completed = subprocess.run(
        [sys.executable, script, "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.lower()
