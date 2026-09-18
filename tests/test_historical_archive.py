"""Offline safety tests for the Ultimate Coach archive runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scraper import historical_archive as archive


def _catalog(divisions):
    return {
        "schema": archive.CATALOG_SCHEMA,
        "member_id": "123",
        "aliases": [],
        "sessions": [],
        "divisions": divisions,
        "source_limitations": [],
        "counts": {"aliases": 0, "sessions": 1, "divisions": len(divisions)},
    }


def _division(division_id="501", session_id="134", current_session_id="200"):
    return {
        "division_id": division_id,
        "division_name": "Monday 8",
        "format": "EIGHT",
        "session_id": session_id,
        "session_name": "Summer 2024",
        "catalog_session_id": session_id,
        "catalog_session_name": "Summer 2024",
        "current_session_id": current_session_id,
    }


def test_prepare_staging_copies_seed_without_mutating_it(tmp_path):
    seed = tmp_path / "career.db"
    seed.write_bytes(b"verified-career")
    staging = tmp_path / "ultimate.db"

    detail = archive.prepare_staging(staging, resume=False, seed_db=seed)

    assert "seeded" in detail
    assert staging.read_bytes() == b"verified-career"
    staging.write_bytes(b"changed")
    assert seed.read_bytes() == b"verified-career"


def test_prepare_staging_resume_requires_existing_db(tmp_path):
    with pytest.raises(archive.ArchiveError, match="does not exist"):
        archive.prepare_staging(tmp_path / "missing.db", resume=True, seed_db=None)


def test_division_plan_deduplicates_and_rejects_incomplete_rows():
    good = _division()
    duplicate = dict(good)
    incomplete = {"division_id": "999", "session_id": "134", "session_name": "Summer 2024"}

    plan = archive.division_plan(_catalog([good, duplicate, incomplete]))

    assert len(plan) == 1
    assert plan[0]["division_id"] == "501"


def test_resume_refuses_catalog_drift(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    staging = tmp_path / "ultimate.db"
    report = tmp_path / "report.json"
    catalog_path.write_text(json.dumps(_catalog([_division()])), encoding="utf-8")
    staging.write_bytes(b"db")
    report.write_text(
        json.dumps({"catalog_sha256": "not-the-current-sha", "completed_division_keys": []}),
        encoding="utf-8",
    )

    with pytest.raises(archive.ArchiveError, match="catalog changed"):
        archive.run_archive(
            {},
            catalog_path=catalog_path,
            staging_db=staging,
            report_path=report,
            seed_db=None,
            resume=True,
        )


def test_runner_uses_historical_identity_mode_and_checkpoints(monkeypatch, tmp_path):
    catalog_path = tmp_path / "catalog.json"
    staging = tmp_path / "ultimate.db"
    report = tmp_path / "report.json"
    catalog_path.write_text(json.dumps(_catalog([_division()])), encoding="utf-8")

    calls = []

    def fake_sync(config, db, division_id, format_name, session_name, resume, **kwargs):
        calls.append((division_id, format_name, session_name, resume, kwargs))
        return {
            "teams_discovered": 2,
            "teams_ingested": 2,
            "roster_players_discovered": 10,
            "roster_players_ingested": 10,
            "matches_discovered": 5,
            "matches_ingested": 5,
            "scored_matches_discovered": 4,
            "scored_matches_with_scoresheet": 3,
            "head_to_head_rows": 6,
            "identity_resolved": 8,
            "identity_unresolved": 0,
        }

    monkeypatch.setattr(archive, "sync_division_wide", fake_sync)
    monkeypatch.setattr(archive, "build_matchups", lambda db: [])

    result = archive.run_archive(
        {},
        catalog_path=catalog_path,
        staging_db=staging,
        report_path=report,
        seed_db=None,
        resume=False,
    )

    assert calls[0][0:4] == ("501", "EIGHT", "Summer 2024", True)
    assert calls[0][4]["roster_is_current"] is False
    assert calls[0][4]["identity_current_only"] is False
    assert result["status"] == "crawl_complete"
    assert result["divisions_crawled"] == 1
    assert result["coverage_observations"]
    assert "1 completed match(es) have no scoresheet" in result["coverage_observations"][0]["observations"]


def test_runner_marks_current_session_current(monkeypatch, tmp_path):
    catalog_path = tmp_path / "catalog.json"
    staging = tmp_path / "ultimate.db"
    report = tmp_path / "report.json"
    catalog_path.write_text(
        json.dumps(_catalog([_division(session_id="200", current_session_id="200")])),
        encoding="utf-8",
    )

    seen = {}

    def fake_sync(config, db, division_id, format_name, session_name, resume, **kwargs):
        seen.update(kwargs)
        return {
            "teams_discovered": 0,
            "teams_ingested": 0,
            "roster_players_discovered": 0,
            "roster_players_ingested": 0,
            "matches_discovered": 0,
            "matches_ingested": 0,
            "scored_matches_discovered": 0,
            "scored_matches_with_scoresheet": 0,
            "head_to_head_rows": 0,
            "identity_resolved": 0,
            "identity_unresolved": 0,
        }

    monkeypatch.setattr(archive, "sync_division_wide", fake_sync)
    monkeypatch.setattr(archive, "build_matchups", lambda db: [])

    archive.run_archive(
        {},
        catalog_path=catalog_path,
        staging_db=staging,
        report_path=report,
        seed_db=None,
        resume=False,
    )

    assert seen["roster_is_current"] is True
    assert seen["identity_current_only"] is True


def test_load_catalog_accepts_recursive_v2_schema(tmp_path):
    path = tmp_path / "catalog.json"
    payload = _catalog([_division()])
    payload["schema"] = "ultimate-coach-historical-catalog-v2"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = archive.load_catalog(path)

    assert loaded["schema"] == "ultimate-coach-historical-catalog-v2"


def test_division_plan_keeps_same_numeric_ids_from_different_leagues():
    left = _division()
    left["league_id"] = "12"
    left["league_slug"] = "league-a"
    right = dict(left)
    right["league_id"] = "99"
    right["league_slug"] = "league-b"

    plan = archive.division_plan(_catalog([left, right]))

    assert len(plan) == 2
    assert {row["league_slug"] for row in plan} == {"league-a", "league-b"}
