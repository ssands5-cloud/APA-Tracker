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


def test_confirmed_division_denial_is_checkpointed_and_crawl_continues(monkeypatch, tmp_path):
    """Stage 3's own auth-classification gap: a division discovered through
    another roster member's cross-league history can be genuinely,
    permanently inaccessible to THIS viewer even though the viewer's own
    token is otherwise valid. Without this fix, sync_division_wide's own
    bare AccessTokenExpired re-raise (shared, unmodified code) would make
    the whole runner treat this as a full auth expiry forever. This test
    proves: (1) the call is retried once after confirming the SAME token
    is still viewer-valid, (2) after BOTH attempts fail with a confirmed-
    valid viewer, the division is tracked as PERMANENTLY DENIED -- never
    as completed -- and (3) the crawl continues to the NEXT division
    instead of stopping."""
    from scraper import auth_classification
    from scraper.graphql_scraper import AccessTokenExpired

    catalog_path = tmp_path / "catalog.json"
    staging = tmp_path / "ultimate.db"
    report = tmp_path / "report.json"
    denied = _division(division_id="501", session_id="134")
    healthy = _division(division_id="502", session_id="134")
    catalog_path.write_text(json.dumps(_catalog([denied, healthy])), encoding="utf-8")

    sync_calls = []

    def fake_sync(config, db, division_id, format_name, session_name, resume, **kwargs):
        sync_calls.append(division_id)
        if division_id == "501":
            raise AccessTokenExpired("division forbidden")
        return {
            "teams_discovered": 1, "teams_ingested": 1,
            "roster_players_discovered": 1, "roster_players_ingested": 1,
            "matches_discovered": 0, "matches_ingested": 0,
            "scored_matches_discovered": 0, "scored_matches_with_scoresheet": 0,
            "head_to_head_rows": 0, "identity_resolved": 0, "identity_unresolved": 0,
        }

    viewer_calls = {"count": 0}

    def always_valid_viewer(config):
        viewer_calls["count"] += 1
        return {"id": 999}

    monkeypatch.setattr(archive, "sync_division_wide", fake_sync)
    monkeypatch.setattr(archive, "build_matchups", lambda db: [])
    monkeypatch.setattr(auth_classification, "fetch_dashboard_teams", always_valid_viewer)

    result = archive.run_archive(
        {},
        catalog_path=catalog_path,
        staging_db=staging,
        report_path=report,
        seed_db=None,
        resume=False,
    )

    assert sync_calls.count("501") == 2, "must retry the denied division exactly once"
    assert sync_calls.count("502") == 1, "the crawl must continue to the next division"
    assert viewer_calls["count"] == 2, "viewer validity must be checked before AND after the retry"
    assert result["status"] == "crawl_complete"

    denied_key = ":134:501"
    assert denied_key in result["permanently_denied_division_keys"]
    assert denied_key not in result["completed_division_keys"], (
        "a confirmed denial must NEVER be counted as completed -- "
        "sync_division_wide's own ingest helpers commit internally, so "
        "partial rows may already be durable even though the division "
        "itself never finished"
    )
    assert result["divisions_crawled"] == 1
    assert result["divisions_permanently_denied"] == 1

    denied_result = next(r for r in result["division_results"] if r["division_id"] == "501")
    assert denied_result["confirmed_denial"] is True
    assert denied_result["data_completeness"] == "partial_or_none_unreliable"
    assert any(
        "confirmed-valid viewer token" in obs
        for obs in denied_result["coverage_observations"]
    )
    healthy_result = next(r for r in result["division_results"] if r["division_id"] == "502")
    assert healthy_result.get("teams_ingested") == 1


def test_genuine_expiry_during_stage3_retry_still_raises_for_reauth(monkeypatch, tmp_path):
    """The narrower race form: the token can genuinely, globally expire in
    the window between the first viewer revalidation and the retry call
    itself. That must still raise for normal reauth/resume, never be
    converted into a permanent per-division limitation."""
    from scraper import auth_classification
    from scraper.graphql_scraper import AccessTokenExpired

    catalog_path = tmp_path / "catalog.json"
    staging = tmp_path / "ultimate.db"
    report = tmp_path / "report.json"
    catalog_path.write_text(json.dumps(_catalog([_division()])), encoding="utf-8")

    def fails_twice(config, db, division_id, format_name, session_name, resume, **kwargs):
        raise AccessTokenExpired("expired")

    viewer_calls = {"count": 0}

    def viewer_valid_once_then_dead(config):
        viewer_calls["count"] += 1
        if viewer_calls["count"] == 1:
            return {"id": 999}
        raise AccessTokenExpired("viewer session is dead now")

    monkeypatch.setattr(archive, "sync_division_wide", fails_twice)
    monkeypatch.setattr(archive, "build_matchups", lambda db: [])
    monkeypatch.setattr(auth_classification, "fetch_dashboard_teams", viewer_valid_once_then_dead)

    with pytest.raises(AccessTokenExpired, match="expired"):
        archive.run_archive(
            {},
            catalog_path=catalog_path,
            staging_db=staging,
            report_path=report,
            seed_db=None,
            resume=False,
        )

    assert viewer_calls["count"] == 2
    if report.is_file():
        saved = json.loads(report.read_text())
        assert not saved.get("completed_division_keys")
        assert not saved.get("permanently_denied_division_keys"), (
            "a genuine expiry must never be recorded as a confirmed denial"
        )


def test_confirmed_denial_partway_through_real_ingestion_leaves_only_partial_durable_rows(
    monkeypatch, tmp_path
):
    """GPT independent-review finding on the first version of this fix:
    sync_division_wide's own ingest helpers (upsert_team, upsert_player,
    ingest_match, ...) COMMIT INTERNALLY as they run -- a db.rollback()
    after the fact cannot undo them. This test exercises the REAL
    sync_division_wide function (only the fetch_*() GraphQL calls are
    mocked, exactly like tests/test_division_wide_sync.py's own pattern)
    so a roster and a scored match's schedule row are genuinely committed
    to the real staging database before fetch_match_detail (the scoresheet
    call) is denied twice. Proves: (1) the team/player/match rows really
    are present and durable afterward -- the partial-commit claim is real,
    not hypothetical -- and (2) the division is correctly tracked as
    permanently denied, never as completed, so that real partial data is
    never mistaken for complete coverage."""
    from scraper import auth_classification
    from scraper.graphql_scraper import AccessTokenExpired

    catalog_path = tmp_path / "catalog.json"
    staging = tmp_path / "ultimate.db"
    report = tmp_path / "report.json"
    division = _division(division_id="501", session_id="134")
    catalog_path.write_text(json.dumps(_catalog([division])), encoding="utf-8")

    rosters_payload = {
        "teams": [
            {"isBye": False, "id": 301, "name": "Fixture Sharks", "roster": [
                {"id": 1, "displayName": "Ann Fixture", "matchesWon": 6, "matchesPlayed": 9,
                 "skillLevel": 6, "member": {"id": 9001}},
            ]},
            {"isBye": False, "id": 302, "name": "Fixture Renegades", "roster": [
                {"id": 2, "displayName": "Uma Sample", "matchesWon": 4, "matchesPlayed": 9,
                 "skillLevel": 5, "member": {"id": 9002}},
            ]},
        ],
    }
    schedule_payload = {
        "schedule": [
            {"weekOfPlay": 1, "matches": [
                {
                    "id": 90401, "isBye": False, "status": "COMPLETED", "startTime": "2026-01-15",
                    "isScored": True, "isFinalized": True,
                    "results": [{"homeAway": "HOME", "points": {"total": 18}},
                                {"homeAway": "AWAY", "points": {"total": 12}}],
                    "home": {"id": 301, "name": "Fixture Sharks"},
                    "away": {"id": 302, "name": "Fixture Renegades"},
                },
            ]},
        ],
    }

    import scheduler.graphql_sync as sync_module

    def denied_match_detail(config, match_id):
        raise AccessTokenExpired("scoresheet forbidden")

    viewer_calls = {"count": 0}

    def always_valid_viewer(config):
        viewer_calls["count"] += 1
        return {"id": 999}

    monkeypatch.setattr(sync_module, "fetch_division_rosters", lambda config, division_id: rosters_payload)
    monkeypatch.setattr(sync_module, "fetch_division_schedule", lambda config, division_id: schedule_payload)
    monkeypatch.setattr(sync_module, "fetch_match_detail", denied_match_detail)
    monkeypatch.setattr(archive, "build_matchups", lambda db: [])
    monkeypatch.setattr(auth_classification, "fetch_dashboard_teams", always_valid_viewer)

    result = archive.run_archive(
        {},
        catalog_path=catalog_path,
        staging_db=staging,
        report_path=report,
        seed_db=None,
        resume=False,
    )

    denied_key = ":134:501"
    assert denied_key in result["permanently_denied_division_keys"]
    assert denied_key not in result["completed_division_keys"]

    from database.engine import create_db_engine
    from database.models import Match, Player, Team
    from sqlalchemy.orm import Session as ORMSession

    engine = create_db_engine({"database": {"path": str(staging)}})
    try:
        with ORMSession(engine) as db:
            teams = db.query(Team).all()
            players = db.query(Player).all()
            matches = db.query(Match).all()

            # The real, exact partial-commit scenario GPT identified: roster
            # and schedule ingestion (upsert_team/upsert_player/ingest_match)
            # DID commit before the scoresheet fetch was denied.
            assert len(teams) == 2, "roster ingestion's team commits are real and durable"
            assert len(players) == 2, "roster ingestion's player commits are real and durable"
            assert len(matches) == 1, "schedule ingestion's match commit is real and durable"

            # But the scoresheet-level detail (the thing that was actually
            # denied) never arrived -- no PlayerMatch/head-to-head rows.
            from database.models import PlayerHeadToHead, PlayerMatch

            assert db.query(PlayerMatch).count() == 0
            assert db.query(PlayerHeadToHead).count() == 0
    finally:
        engine.dispose()


def test_resume_complete_archive_with_matching_hash_returns_without_rebuilding(monkeypatch, tmp_path):
    catalog_path = tmp_path / "catalog.json"
    staging = tmp_path / "ultimate.db"
    report = tmp_path / "report.json"
    division = _division()
    catalog_path.write_text(json.dumps(_catalog([division])), encoding="utf-8")
    staging.write_bytes(b"stable-final-archive")

    key = archive._division_key(archive.division_plan(_catalog([division]))[0])
    previous = {
        "schema": archive.REPORT_SCHEMA,
        "status": "crawl_complete",
        "catalog_sha256": archive.sha256_file(catalog_path),
        "staging_sha256": archive.sha256_file(staging),
        "completed_division_keys": [key],
        "permanently_denied_division_keys": [],
        "divisions_crawled": 1,
        "division_results": [],
        "catalog_source_limitations": [],
        "coverage_observations": [],
        "matchups_rebuilt": 42,
    }
    report.write_text(json.dumps(previous), encoding="utf-8")

    monkeypatch.setattr(
        archive,
        "create_db_engine",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("verified-complete resume must not open the staging DB")
        ),
    )
    monkeypatch.setattr(
        archive,
        "build_matchups",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("verified-complete resume must not rebuild matchups")
        ),
    )

    result = archive.run_archive(
        {},
        catalog_path=catalog_path,
        staging_db=staging,
        report_path=report,
        seed_db=None,
        resume=True,
    )

    assert result == previous


def test_resume_complete_archive_hash_mismatch_does_not_take_fast_path(monkeypatch, tmp_path):
    catalog_path = tmp_path / "catalog.json"
    staging = tmp_path / "ultimate.db"
    report = tmp_path / "report.json"
    division = _division()
    catalog_path.write_text(json.dumps(_catalog([division])), encoding="utf-8")
    staging.write_bytes(b"changed-after-report")

    key = archive._division_key(archive.division_plan(_catalog([division]))[0])
    previous = {
        "schema": archive.REPORT_SCHEMA,
        "status": "crawl_complete",
        "catalog_sha256": archive.sha256_file(catalog_path),
        "staging_sha256": "not-the-current-staging-hash",
        "completed_division_keys": [key],
        "permanently_denied_division_keys": [],
        "matchups_rebuilt": 42,
    }
    report.write_text(json.dumps(previous), encoding="utf-8")

    monkeypatch.setattr(
        archive,
        "create_db_engine",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("normal-resume-path-entered")
        ),
    )

    with pytest.raises(RuntimeError, match="normal-resume-path-entered"):
        archive.run_archive(
            {},
            catalog_path=catalog_path,
            staging_db=staging,
            report_path=report,
            seed_db=None,
            resume=True,
        )


def test_resume_in_progress_report_does_not_take_complete_fast_path(monkeypatch, tmp_path):
    catalog_path = tmp_path / "catalog.json"
    staging = tmp_path / "ultimate.db"
    report = tmp_path / "report.json"
    division = _division()
    catalog_payload = _catalog([division])
    catalog_path.write_text(json.dumps(catalog_payload), encoding="utf-8")
    staging.write_bytes(b"stable-final-archive")

    key = archive._division_key(archive.division_plan(catalog_payload)[0])
    previous = {
        "schema": archive.REPORT_SCHEMA,
        "status": "crawl_in_progress",
        "catalog_sha256": archive.sha256_file(catalog_path),
        "staging_sha256": archive.sha256_file(staging),
        "completed_division_keys": [key],
        "permanently_denied_division_keys": [],
        "matchups_rebuilt": 42,
    }
    report.write_text(json.dumps(previous), encoding="utf-8")

    monkeypatch.setattr(
        archive,
        "create_db_engine",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("normal-resume-path-entered")
        ),
    )

    with pytest.raises(RuntimeError, match="normal-resume-path-entered"):
        archive.run_archive(
            {},
            catalog_path=catalog_path,
            staging_db=staging,
            report_path=report,
            seed_db=None,
            resume=True,
        )


def test_resume_complete_report_with_unaccounted_division_does_not_take_fast_path(
    monkeypatch, tmp_path
):
    catalog_path = tmp_path / "catalog.json"
    staging = tmp_path / "ultimate.db"
    report = tmp_path / "report.json"
    first = _division(division_id="501")
    second = _division(division_id="502")
    catalog_payload = _catalog([first, second])
    catalog_path.write_text(json.dumps(catalog_payload), encoding="utf-8")
    staging.write_bytes(b"stable-final-archive")

    planned = archive.division_plan(catalog_payload)
    first_key = archive._division_key(planned[0])
    assert len(planned) == 2

    previous = {
        "schema": archive.REPORT_SCHEMA,
        "status": "crawl_complete",
        "catalog_sha256": archive.sha256_file(catalog_path),
        "staging_sha256": archive.sha256_file(staging),
        "completed_division_keys": [first_key],
        "permanently_denied_division_keys": [],
        "matchups_rebuilt": 42,
    }
    report.write_text(json.dumps(previous), encoding="utf-8")

    monkeypatch.setattr(
        archive,
        "create_db_engine",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("normal-resume-path-entered")
        ),
    )

    with pytest.raises(RuntimeError, match="normal-resume-path-entered"):
        archive.run_archive(
            {},
            catalog_path=catalog_path,
            staging_db=staging,
            report_path=report,
            seed_db=None,
            resume=True,
        )
