"""Smoke test for scripts/build_demo.py.

Not a unit test of ingestion logic -- that's covered elsewhere (see
test_viewer_sync_fixture.py, test_division_standings_fixture.py,
test_match_detail_fixture.py). This just proves the demo script still wires
those pieces together correctly end to end and produces a real workbook,
so a signature change in any of them fails loudly here instead of only
being noticed the next time someone runs the demo by hand.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_build_demo_produces_a_readable_workbook(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "build_demo.py")],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr

    workbook_path = tmp_path / "exports" / "demo_apa_stats.xlsx"
    assert workbook_path.exists()

    wb = openpyxl.load_workbook(workbook_path)
    assert set(wb.sheetnames) == {
        "Standings", "Player Stats", "Career Stats", "Team History",
        "Skill Level History", "Matchups",
    }

    standings = wb["Standings"]
    assert standings.max_row > 1, "Standings sheet has no data rows"

    player_stats = wb["Player Stats"]
    assert player_stats.max_row > 1, "Player Stats sheet has no data rows"
