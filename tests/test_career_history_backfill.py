"""Offline tests for scripts.backfill_career_history.

No test in this file calls APA. The live GraphQL boundary is monkeypatched,
so CI proves pagination, deduplication, staging preservation, and fail-closed
resume behavior without credentials.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import backfill_career_history as career


def _team_entry(
    team_id: int,
    division_id: int,
    session_name: str,
    *,
    current: bool = False,
) -> dict:
    return {
        "id": team_id * 10,
        "__typename": "EightBallPlayer",
        "isActive": True,
        "matchesPlayed": 12,
        "matchesWon": 7,
        "skillLevel": 5,
        "rank": 2,
        "nickName": "",
        "session": {"id": team_id, "name": session_name},
        "team": {
            "id": team_id,
            "name": f"Team {team_id}",
            "division": {"id": division_id, "isTournament": False},
        },
    }


def test_complete_team_history_paginates_past_teams_and_adds_current_once(monkeypatch):
    calls = []

    def fake_fetch(config, alias_id, limit=50, offset=0):
        calls.append((alias_id, limit, offset))
        current = [_team_entry(900, 90, "Fall 2026", current=True)]
        if offset == 0:
            past = [
                _team_entry(100, 10, "Spring 2025"),
                _team_entry(200, 20, "Summer 2025"),
            ]
        elif offset == 2:
            past = [_team_entry(300, 30, "Fall 2025")]
        else:
            raise AssertionError(f"unexpected offset {offset}")
        return {"pastTeams": past, "currentTeams": current}

    monkeypatch.setattr(career, "fetch_team_stat", fake_fetch)

    rows = career.fetch_complete_team_history({}, 700001, page_size=2)

    assert calls == [(700001, 2, 0), (700001, 2, 2)]
    assert {(r["team_id"], r["session_name"]) for r in rows} == {
        ("100", "Spring 2025"),
        ("200", "Summer 2025"),
        ("300", "Fall 2025"),
        ("900", "Fall 2026"),
    }
    assert sum(1 for r in rows if r["is_current"]) == 1


def test_complete_team_history_deduplicates_repeated_rows(monkeypatch):
    repeated = _team_entry(100, 10, "Spring 2025")

    monkeypatch.setattr(
        career,
        "fetch_team_stat",
        lambda config, alias_id, limit=50, offset=0: {
            "pastTeams": [repeated, repeated],
            "currentTeams": [],
        },
    )

    rows = career.fetch_complete_team_history({}, 700001, page_size=50)

    assert len(rows) == 1
    assert rows[0]["team_id"] == "100"


def test_prepare_staging_seeds_from_production(tmp_path):
    production = tmp_path / "production.db"
    production.write_bytes(b"career-complete")
    staging = tmp_path / "staging.db"
    staging.write_bytes(b"stale-partial")

    detail = career.prepare_staging(
        staging,
        resume=False,
        production_db=production,
    )

    assert staging.read_bytes() == b"career-complete"
    assert "seeded" in detail


def test_prepare_staging_resume_requires_existing_file(tmp_path):
    with pytest.raises(career.CareerBackfillError, match="does not exist"):
        career.prepare_staging(
            tmp_path / "missing.db",
            resume=True,
            production_db=tmp_path / "production.db",
        )


def test_division_groups_keeps_current_and_historical_sessions_separate_by_division():
    rows = [
        {"team_id": "100", "division_id": "10", "session_name": "Spring 2025", "is_current": False},
        {"team_id": "200", "division_id": "20", "session_name": "Fall 2026", "is_current": True},
    ]

    groups = career._division_groups(rows)

    assert set(groups) == {"10", "20"}
    assert groups["10"][0]["is_current"] is False
    assert groups["20"][0]["is_current"] is True
