"""Offline tests for pipeline.league_catchup_import (no network, no real data)."""
from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from database.engine import create_db_engine
from pipeline import league_catchup_import as imp
from scheduler import graphql_sync as sync
from tests.test_division_wide_sync import (
    DIVISION_ID, FORMAT_NAME, MATCH_DETAIL_PAYLOAD, ROSTERS_PAYLOAD, SCHEDULE_PAYLOAD, SESSION_NAME,
)

TODAY = "2026-02-01"


def _new_match(match_id: int, start: str) -> tuple[dict, dict]:
    row = copy.deepcopy(SCHEDULE_PAYLOAD["schedule"][0]["matches"][0])
    row.update(id=match_id, startTime=start)
    detail = copy.deepcopy(MATCH_DETAIL_PAYLOAD)
    detail.update(id=match_id, startTime=start, isFinalized=True)
    return row, detail


def _schedule_with(extra_rows: list[dict]) -> dict:
    schedule = copy.deepcopy(SCHEDULE_PAYLOAD)
    schedule["schedule"].append({"weekOfPlay": 3, "matches": extra_rows})
    return schedule


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sync_live(db_path: Path, monkeypatch, schedule: dict, details: dict[str, dict]) -> None:
    """Build a DB with the real sync and fixture payloads (the 'archive as crawled')."""
    monkeypatch.setattr(sync, "fetch_division_rosters", lambda config, did: ROSTERS_PAYLOAD)
    monkeypatch.setattr(sync, "fetch_division_schedule", lambda config, did: schedule)
    monkeypatch.setattr(sync, "fetch_match_detail", lambda config, mid: details[str(mid)])
    engine = create_db_engine({"database": {"path": str(db_path)}})
    try:
        with Session(engine) as db:
            sync.sync_division_wide({}, db, DIVISION_ID, FORMAT_NAME, SESSION_NAME, resume=True)
            db.commit()
    finally:
        engine.dispose()
    monkeypatch.undo()


def _h2h(db_path: Path) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return sorted(con.execute(
            "select m.external_id, p.external_id, o.external_id, h.result, h.own_skill_level, "
            "h.opponent_skill_level, h.format, h.session_name from player_head_to_head h "
            "join matches m on m.id = h.match_id join players p on p.id = h.player_id "
            "join players o on o.id = h.opponent_id").fetchall())
    finally:
        con.close()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Archive holds match 90401 with games; catch-up also captured new match 90403."""
    archive = tmp_path / "archive.db"
    first = copy.deepcopy(MATCH_DETAIL_PAYLOAD)
    _sync_live(archive, monkeypatch, SCHEDULE_PAYLOAD, {"90401": first})

    new_row, new_detail = _new_match(90403, "2026-01-29")
    store = tmp_path / "league-catchup"
    _write(store / "rosters" / f"{DIVISION_ID}.json", ROSTERS_PAYLOAD)
    _write(store / "divisions" / f"{DIVISION_ID}.json", _schedule_with([new_row]))
    _write(store / "matches" / "90403.json", {"tag": "division_schedule", "match": new_detail})

    catalog = tmp_path / "catalog.json"
    _write(catalog, {"divisions": [{"division_id": DIVISION_ID, "session_id": "1", "session_name": SESSION_NAME,
                                    "format": FORMAT_NAME, "current_session_id": "1"}]})
    return {"archive": archive, "store": store, "catalog": catalog, "tmp": tmp_path,
            "new_row": new_row, "new_detail": new_detail, "first": first}


def _run(setup, **kw):
    return imp.run_import(source_db=setup["archive"], out_db=setup["tmp"] / "out.db",
                          catalog_path=setup["catalog"], stores=[setup["store"]], since="2024-01-01",
                          today=TODAY, **kw)


def test_dry_run_counts_pending_and_writes_nothing(setup):
    report = _run(setup, dry_run=True)
    assert report["status"] == "dry_run"
    assert report["pending_before"]["matches"] == 1
    assert report["pending_before"]["games"] == 1
    assert not (setup["tmp"] / "out.db").exists()
    assert report["source_sha256_before"] == report["source_sha256_after"]


def test_import_matches_live_sync_and_leaves_source_untouched(setup, monkeypatch):
    sha_before = imp.sha256_file(setup["archive"])
    report = _run(setup)
    assert report["status"] == "verified", report["problems"]
    assert report["source_unchanged"] and imp.sha256_file(setup["archive"]) == sha_before
    assert report["existing_games_unchanged"]
    assert report["pending_after"]["matches"] == 0
    assert report["counts_delta"]["player_head_to_head"] == 2

    # The same data fetched "live" from APA must produce identical rows.
    live = setup["tmp"] / "live.db"
    _sync_live(live, monkeypatch, _schedule_with([setup["new_row"]]),
               {"90401": setup["first"], "90403": setup["new_detail"]})
    assert _h2h(setup["tmp"] / "out.db") == _h2h(live)


def test_refuses_to_overwrite_existing_output(setup):
    (setup["tmp"] / "out.db").write_bytes(b"keep me")
    with pytest.raises(imp.CatchupImportError, match="refusing to overwrite"):
        _run(setup)
    assert (setup["tmp"] / "out.db").read_bytes() == b"keep me"


def test_refuses_output_equal_to_source(setup):
    with pytest.raises(imp.CatchupImportError):
        imp.run_import(source_db=setup["archive"], out_db=setup["archive"], catalog_path=setup["catalog"],
                       stores=[setup["store"]], today=TODAY)


def test_missing_capture_is_recorded_not_guessed(setup):
    source = imp.OfflineCatchupSource([setup["store"]])
    with pytest.raises(imp.MissingCapture):
        source.match_detail({}, 99999)
    assert source.misses == [("matches", "99999")]


def test_division_missing_from_catalog_stops_the_import(setup):
    _write(setup["catalog"], {"divisions": []})
    with pytest.raises(imp.CatchupImportError, match="not in catalog"):
        _run(setup)
    assert not (setup["tmp"] / "out.db").exists()


def test_offline_fetches_restores_the_real_functions(setup):
    real = (sync.fetch_division_rosters, sync.fetch_division_schedule, sync.fetch_match_detail)
    with imp.offline_fetches(imp.OfflineCatchupSource([setup["store"]])):
        assert sync.fetch_match_detail is not real[2]
    assert (sync.fetch_division_rosters, sync.fetch_division_schedule, sync.fetch_match_detail) == real
