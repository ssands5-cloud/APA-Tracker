"""scripts/refresh_ultimate_coach_current_session.py: a current-session refresh into a COPY, never the source.

No network: sync_division_wide is replaced by a fake that writes what a real sync would (a newly scored
match with its scoresheet, a brand-new fixture), and the denial path is exercised by a fake retry wrapper.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine

from database.models import Base
from scripts import refresh_ultimate_coach_current_session as refresh

VIEWER = "9001"


def _db(path):
    Base.metadata.create_all(create_engine(f"sqlite:///{path}"))
    con = sqlite3.connect(path)
    con.execute("INSERT INTO teams (id, external_id, name) VALUES (1, 'T1', 'Ours'), (2, 'T2', 'Theirs')")
    con.execute("INSERT INTO players (id, external_id, name) VALUES (1, ?, 'Viewer'), (2, '9002', 'Opp')", (VIEWER,))
    con.execute("INSERT INTO player_team_history (player_id, is_current, team_external_id, team_name, session_name)"
                " VALUES (1, 0, 'T1', 'Ours', 'Fall 2026')")
    for mid, ext, date, scored in ((1, "M1", "2026-09-28T19:00:00-06:00", 1), (2, "M2", "2026-10-05T19:00:00-06:00", 0)):
        con.execute("INSERT INTO matches (id, external_id, home_team_id, away_team_id, match_date, status, format,"
                    " session_name, home_score, away_score, is_scored) VALUES (?, ?, 'T1', 'T2', ?, ?, '8-Ball Open',"
                    " 'Fall 2026', ?, ?, ?)", (mid, ext, date, "COMPLETED" if scored else "UNPLAYED",
                                               9 if scored else None, 6 if scored else None, scored))
    con.execute("INSERT INTO matches (id, external_id, home_team_id, away_team_id, match_date, status, format,"
                " session_name, is_scored) VALUES (3, 'OLD', 'T1', 'T2', '2025-01-05T19:00:00-06:00', 'COMPLETED',"
                " '8-Ball Open', 'Spring 2025', 1)")
    con.execute("INSERT INTO player_matches (player_id, match_id, match_date, result) VALUES (1, 1, '2026-09-28', 'W')")
    con.commit()
    con.close()


def _catalog(path):
    rows = [{"division_id": d, "catalog_session_id": "s26", "catalog_session_name": "Fall 2026", "format": "EIGHT",
             "current_session_id": "s26", "is_mine": d == "D1"} for d in ("D1", "D2")]
    rows.append({"division_id": "D0", "catalog_session_id": "s25", "catalog_session_name": "Spring 2025",
                 "format": "EIGHT", "current_session_id": "s26", "is_mine": True})
    path.write_text(json.dumps({"schema": "ultimate-coach-historical-catalog-v1", "divisions": rows}), encoding="utf-8")


def _fake_sync(calls):
    def sync(config, db, division_id, division_format, session_name, resume=False, **kw):
        calls.append((division_id, resume, kw))
        if division_id == "D1":                       # Monday's match was scored: status, score and scoresheet
            con = sqlite3.connect(config["database"]["path"])
            con.execute("UPDATE matches SET status='COMPLETED', is_scored=1, home_score=10, away_score=5 WHERE id=2")
            con.execute("INSERT INTO player_matches (player_id, match_id, match_date, result) VALUES (1, 2, '2026-10-05', 'W'),"
                        " (2, 2, '2026-10-05', 'L')")
            con.execute("INSERT INTO matches (external_id, home_team_id, away_team_id, match_date, status, format,"
                        " session_name, is_scored) VALUES ('M4', 'T2', 'T1', '2026-10-12T19:00:00-06:00', 'UNPLAYED',"
                        " '8-Ball Open', 'Fall 2026', 0)")
            con.commit()
            con.close()
        return {k: 0 for k in ("teams_discovered", "teams_ingested", "roster_players_discovered",
                               "roster_players_ingested", "matches_discovered", "matches_ingested",
                               "scored_matches_discovered", "scored_matches_with_scoresheet")}
    return sync


@pytest.fixture()
def setup(tmp_path):
    source, catalog = tmp_path / "live" / "ultimate_coach_staging.db", tmp_path / "live" / "catalog.json"
    source.parent.mkdir()
    _db(source)
    _catalog(catalog)
    return source, catalog, tmp_path / "out"


def _run(setup, monkeypatch, *, mine_only=False, retry=None):
    source, catalog, out = setup
    calls = []
    monkeypatch.setattr("scraper.auth_classification.call_with_confirmed_denial_retry",
                        retry or (lambda config, fetch: fetch()))
    report = refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=out,
                                 mine_only=mine_only, verify_member=VIEWER, verify_date="2026-10-05",
                                 sync=_fake_sync(calls), rebuild_matchups=lambda db: [],
                                 now=lambda: datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc))
    return report, calls


def test_refresh_writes_a_copy_and_reports_monday(setup, monkeypatch):
    source, _, out = setup
    before = refresh.sha256_file(source)
    report, calls = _run(setup, monkeypatch)
    assert refresh.sha256_file(source) == before                       # the original is never written
    assert report["provenance"]["source_db_sha256"] == report["provenance"]["source_db_sha256_after"] == before
    assert (out / "ultimate_coach_staging.db").is_file() and report["provenance"]["refreshed_db_sha256"] != before
    # current-session divisions only, through the audited incremental sync (resume=True)
    assert [c[0] for c in calls] == ["D1", "D2"] and all(c[1] and c[2]["roster_is_current"] for c in calls)
    c = report["changes"]
    assert c["matches_newly_scored"] == ["M2"] and c["matches_added"] == ["M4"] and c["matches_score_changed"] == []
    assert c["scoresheet_rows_added"] == 2 and c["latest_scored_date_before"] == "2026-09-28"
    assert c["latest_scored_date_after"] == "2026-10-05" and c["date_range_checked"] == ["2026-09-28", "2026-10-12"]
    assert c["totals_after"]["matches"] == 4                         # the Spring 2025 history is kept
    assert report["verify"]["viewer_fixtures"] == [{"match_id": "M2", "format": "8-Ball Open", "status": "COMPLETED",
                                                    "is_scored": True, "home_score": 10.0, "away_score": 5.0,
                                                    "scoresheet_rows": 2, "viewer_rows": 1}]
    assert report["gaps"] == []
    saved = json.loads((out / "refresh_report.json").read_text(encoding="utf-8"))
    assert saved["changes"] == c and "Viewer" not in json.dumps(saved)   # ids and counts only, no names


def test_mine_only_and_unscored_monday_is_a_reported_gap(setup, monkeypatch):
    report, calls = _run(setup, monkeypatch, mine_only=True, retry=None)
    assert [c[0] for c in calls] == ["D1"]
    source, catalog, _ = setup
    report2 = refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=setup[2].parent / "out2",
                                  mine_only=True, verify_member=VIEWER, verify_date="2026-10-05",
                                  sync=lambda *a, **k: _fake_sync([])(*a[:2], "D9", *a[3:], **k),
                                  rebuild_matchups=lambda db: [])
    assert "viewer fixture M2 on 2026-10-05 is still not scored in APA's data" in report2["gaps"]


def test_a_confirmed_denial_is_a_gap_not_a_crash(setup, monkeypatch):
    from scraper.auth_classification import ConfirmedScopeDenial

    def retry(config, fetch):
        if len(seen) == 1:
            raise ConfirmedScopeDenial("denied")
        seen.append(1)
        return fetch()
    seen = []
    report, _ = _run(setup, monkeypatch, retry=retry)
    assert any("D2" in g and "denied" in g for g in report["gaps"])
    assert [d.get("confirmed_denial") for d in report["divisions"]] == [None, True]


def test_refuses_to_overwrite_an_existing_copy(setup, monkeypatch):
    _run(setup, monkeypatch)
    with pytest.raises(refresh.RefreshError, match="overwrite"):
        _run(setup, monkeypatch)
