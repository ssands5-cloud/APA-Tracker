"""Smoke test for scripts/build_matchups.py.

Mirrors tests/test_build_demo.py's approach: run the real script as a
subprocess against a real (temp) database and check its real output,
rather than unit-testing pieces of it in isolation (that's
tests/test_matchups.py and tests/test_match_detail_fixture.py's
TestHeadToHeadRows/TestIngestHeadToHead).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_build_matchups_computes_real_rows_from_the_demo_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # scripts/build_demo.py now ingests head-to-head rows and computes
    # matchups itself (see its own docstring) -- run it first so there's a
    # real database to point build_matchups.py at, exactly the order a real
    # user would follow.
    demo_result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "build_demo.py")],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert demo_result.returncode == 0, demo_result.stderr

    config_path = tmp_path / "matchups_config.yaml"
    config_path.write_text(yaml.dump({"database": {"path": "data/demo_apa_tracker.db"}}))

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "build_matchups.py"),
         "--config", str(config_path)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Strongest matchups" in result.stdout
    assert "Weakest matchups" in result.stdout

    import sqlite3

    conn = sqlite3.connect(tmp_path / "data" / "demo_apa_tracker.db")
    count = conn.execute("SELECT COUNT(*) FROM player_matchups").fetchone()[0]
    conn.close()
    assert count > 0, "build_matchups.py ran but wrote no rows"


def test_build_matchups_on_an_empty_database_reports_no_history_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "empty_config.yaml"
    config_path.write_text(yaml.dump({"database": {"path": "data/empty.db"}}))

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "build_matchups.py"),
         "--config", str(config_path)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "No head-to-head history ingested yet" in result.stdout
