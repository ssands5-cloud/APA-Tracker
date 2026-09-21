"""Guard the steady-state maintenance path against accidental full-history crawls.

The league-wide Ultimate Coach history build is a one-time / explicit recovery
operation. Normal daily and game-night maintenance must stay scoped to Paul's
current teams and their current divisions.
"""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
MAINTENANCE_ENTRYPOINTS = (
    "scheduler/daily_sync.py",
    "scheduler/graphql_sync.py",
    "scripts/build_full_production_demo.py",
    "scripts/run_game_night.py",
)
HISTORICAL_PIPELINE_MARKERS = (
    "run_ultimate_coach_browser",
    "expand_ultimate_coach_history",
    "build_ultimate_coach_archive",
    "enrich_ultimate_coach_players",
    "scraper.historical_graph",
    "scraper.historical_archive",
)


@pytest.mark.parametrize("relative_path", MAINTENANCE_ENTRYPOINTS)
def test_steady_state_entrypoints_never_invoke_full_history_pipeline(relative_path):
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    found = [marker for marker in HISTORICAL_PIPELINE_MARKERS if marker in text]
    assert found == [], (
        f"{relative_path} references full-history acquisition marker(s) {found}; "
        "steady-state maintenance must remain current-team/current-division only"
    )


def test_live_production_refresh_uses_current_division_sync():
    text = (ROOT / "scripts/build_full_production_demo.py").read_text(encoding="utf-8")
    assert "from scheduler.graphql_sync import run_division_wide" in text
    assert "result = run_division_wide(" in text


def test_daily_sync_delegates_only_to_narrow_live_sync():
    text = (ROOT / "scheduler/daily_sync.py").read_text(encoding="utf-8")
    assert "from scheduler.graphql_sync import run as run_live" in text
    assert "run_live(config_path, export=True)" in text
