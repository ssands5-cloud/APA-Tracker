"""scripts/refresh_ultimate_coach_current_session.py: a current-session refresh into a COPY, never the source.

No network: sync_division_wide is replaced by a fake that writes what a real sync would (a newly scored match
with its scoresheet, a brand-new fixture); the division schedule and each match's authoritative scoresheet come
from a small fake API; the denial path is exercised by a fake retry wrapper / a raising fetch.

GPT audit 4874e4b / e6ea86a: resume=True alone skips every match that already has scoresheet rows, so corrected
or partial player results were never reconciled. The default "reconcile" mode re-fetches those; the regressions
below cover a correction with unchanged team totals, a partial existing sheet, repeat runs, earlier-session
history, authoritative removal, and denied / empty / unresolved answers staying visible as gaps.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine

from database.models import Base
from scripts import refresh_ultimate_coach_current_session as refresh

VIEWER, OPP = "9001", "9002"


def _db(path):
    Base.metadata.create_all(create_engine(f"sqlite:///{path}"))
    con = sqlite3.connect(path)
    con.execute("INSERT INTO teams (id, external_id, name) VALUES (1, 'T1', 'Ours'), (2, 'T2', 'Theirs')")
    con.execute("INSERT INTO players (id, external_id, name) VALUES (1, ?, 'Viewer'), (2, ?, 'Opp')", (VIEWER, OPP))
    con.execute("INSERT INTO player_team_history (player_id, is_current, team_external_id, team_name, session_name)"
                " VALUES (1, 0, 'T1', 'Ours', 'Fall 2026')")
    for mid, ext, date, scored in ((1, "M1", "2026-09-28T19:00:00-06:00", 1), (2, "M2", "2026-10-05T19:00:00-06:00", 0)):
        con.execute("INSERT INTO matches (id, external_id, home_team_id, away_team_id, home_team_name, away_team_name,"
                    " match_date, status, format, session_name, home_score, away_score, is_scored) VALUES"
                    " (?, ?, 'T1', 'T2', 'Ours', 'Theirs', ?, ?, '8-Ball Open', 'Fall 2026', ?, ?, ?)",
                    (mid, ext, date, "COMPLETED" if scored else "UNPLAYED", 9 if scored else None,
                     6 if scored else None, scored))
    con.execute("INSERT INTO matches (id, external_id, home_team_id, away_team_id, match_date, status, format,"
                " session_name, home_score, away_score, is_scored) VALUES (3, 'OLD', 'T1', 'T2',"
                " '2025-01-05T19:00:00-06:00', 'COMPLETED', '8-Ball Open', 'Spring 2025', 3, 2, 1)")
    # M1's captured sheet: both players; OLD (an earlier session) has its own history row.
    con.execute("INSERT INTO player_matches (player_id, match_id, match_date, team_id, result) VALUES"
                " (1, 1, '2026-09-28', 'T1', 'W'), (2, 1, '2026-09-28', 'T2', 'L'), (1, 3, '2025-01-05', 'T1', 'L')")
    con.commit()
    con.close()


def _catalog(path):
    rows = [{"division_id": d, "catalog_session_id": "s26", "catalog_session_name": "Fall 2026", "format": "EIGHT",
             "current_session_id": "s26", "is_mine": d == "D1"} for d in ("D1", "D2")]
    rows.append({"division_id": "D0", "catalog_session_id": "s25", "catalog_session_name": "Spring 2025",
                 "format": "EIGHT", "current_session_id": "s26", "is_mine": True})
    path.write_text(json.dumps({"schema": "ultimate-coach-historical-catalog-v1", "divisions": rows}), encoding="utf-8")


def _row(pid, result, team):
    return {"player_id": pid, "player_name": "Viewer" if pid == VIEWER else "Opp", "team_id": team,
            "team_name": "Ours" if team == "T1" else "Theirs", "result": result}


AUTHORITATIVE_M1 = [_row(VIEWER, "W", "T1"), _row(OPP, "L", "T2")]       # identical to what the copy holds


def _fake_sync(calls):
    def sync(config, db, division_id, division_format, session_name, resume=False, **kw):
        calls.append((division_id, resume, kw))
        if division_id == "D1":                       # Monday's match was scored: status, score and scoresheet
            con = sqlite3.connect(config["database"]["path"])
            con.execute("UPDATE matches SET status='COMPLETED', is_scored=1, home_score=10, away_score=5 WHERE id=2")
            # Idempotent like the real sync (resume=True fetches only a sheet the copy lacks; upserts the rest).
            if not con.execute("SELECT 1 FROM player_matches WHERE match_id = 2").fetchone():
                con.execute("INSERT INTO player_matches (player_id, match_id, match_date, team_id, result) VALUES"
                            " (1, 2, '2026-10-05', 'T1', 'W'), (2, 2, '2026-10-05', 'T2', 'L')")
            con.execute("INSERT OR IGNORE INTO matches (external_id, home_team_id, away_team_id, match_date, status, format,"
                        " session_name, is_scored) VALUES ('M4', 'T2', 'T1', '2026-10-12T19:00:00-06:00', 'UNPLAYED',"
                        " '8-Ball Open', 'Fall 2026', 0)")
            con.commit()
            con.close()
        return {k: 0 for k in ("teams_discovered", "teams_ingested", "roster_players_discovered",
                               "roster_players_ingested", "matches_discovered", "matches_ingested",
                               "scored_matches_discovered", "scored_matches_with_scoresheet")}
    return sync


def _schedule(cfg, division_id):
    return {"D1": [{"match_id": "M1", "is_scored": True, "is_bye": False},
                   {"match_id": "M2", "is_scored": True, "is_bye": False},
                   {"match_id": "M4", "is_scored": False, "is_bye": False}], "D2": []}[division_id]


def _sheets(m1=None, fetched=None):
    def scoresheet(config, match_id):
        if fetched is not None:
            fetched.append(match_id)
        if match_id != "M1":                       # Monday's M2, exactly as the sync captured it
            return [_row(VIEWER, "W", "T1"), _row(OPP, "L", "T2")], []
        rows = AUTHORITATIVE_M1 if m1 is None else m1
        if isinstance(rows, Exception):
            raise rows
        return [dict(r) for r in rows], []
    return scoresheet


RESOLVED = lambda db, session, scores, current_only=True: ({}, len(scores), 0)      # noqa: E731


@pytest.fixture()
def setup(tmp_path):
    source, catalog = tmp_path / "live" / "ultimate_coach_staging.db", tmp_path / "live" / "catalog.json"
    source.parent.mkdir()
    _db(source)
    _catalog(catalog)
    return source, catalog, tmp_path / "out"


def _run(setup, monkeypatch, *, mine_only=False, retry=None, mode="reconcile", m1=None, resolve=RESOLVED,
         source=None, out=None, fetched=None):
    src, catalog, default_out = setup
    calls = []
    monkeypatch.setattr("scraper.auth_classification.call_with_confirmed_denial_retry",
                        retry or (lambda config, fetch: fetch()))
    report = refresh.run_refresh({"database": {}}, source_db=source or src, catalog_path=catalog,
                                 out_dir=out or default_out, mine_only=mine_only, verify_member=VIEWER,
                                 verify_date="2026-10-05", sync=_fake_sync(calls), rebuild_matchups=lambda db: [],
                                 mode=mode, schedule=_schedule, scoresheet=_sheets(m1, fetched), resolve=resolve,
                                 now=lambda: datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc))
    return report, calls


def _rows(db, match_ext):
    con = sqlite3.connect(db)
    try:
        return sorted(con.execute("SELECT p.external_id, pm.result, pm.team_id FROM player_matches pm JOIN players p"
                                  " ON p.id = pm.player_id JOIN matches m ON m.id = pm.match_id WHERE m.external_id = ?",
                                  (match_ext,)).fetchall())
    finally:
        con.close()


def test_refresh_writes_a_copy_and_reports_monday(setup, monkeypatch):
    source, _, out = setup
    before = refresh.sha256_file(source)
    fetched = []
    report, calls = _run(setup, monkeypatch, fetched=fetched)
    assert refresh.sha256_file(source) == before                       # the original is never written
    assert report["provenance"]["source_db_sha256"] == report["provenance"]["source_db_sha256_after"] == before
    assert (out / "ultimate_coach_staging.db").is_file() and report["provenance"]["refreshed_db_sha256"] != before
    # current-session divisions only, through the audited incremental sync (resume=True) ...
    assert [c[0] for c in calls] == ["D1", "D2"] and all(c[1] and c[2]["roster_is_current"] for c in calls)
    # ... and then the already-captured scored match (M1) re-fetched; M2 was fetched fresh by the sync itself.
    assert fetched == ["M1"] and report["reconciliation"]["matches_checked"] == ["M1"]
    outcome = report["reconciliation"]["outcomes"][0]
    assert outcome["status"] == "unchanged" and outcome["scoresheet_rows_received"] == 2
    # Provenance of what was applied: fetch time and a digest of the authoritative rows as received.
    assert outcome["fetched_utc"].endswith(" UTC") and len(outcome["scoresheet_sha256"]) == 64
    c = report["changes"]
    assert c["matches_newly_scored"] == ["M2"] and c["matches_added"] == ["M4"] and c["matches_score_changed"] == []
    assert c["scoresheet_rows_added"] == 2 and c["latest_scored_date_before"] == "2026-09-28"
    assert c["latest_scored_date_after"] == "2026-10-05" and c["date_range_checked"] == ["2026-09-28", "2026-10-12"]
    assert c["totals_after"]["matches"] == 4                         # the Spring 2025 history is kept
    assert report["verify"]["viewer_fixtures"] == [{"match_id": "M2", "format": "8-Ball Open", "status": "COMPLETED",
                                                    "is_scored": True, "home_score": 10.0, "away_score": 5.0,
                                                    "scoresheet_rows": 2, "viewer_rows": 1}]
    assert report["gaps"] == [] and report["coverage"] == "complete"
    saved = json.loads((out / "refresh_report.json").read_text(encoding="utf-8"))
    assert saved["changes"] == c and "Viewer" not in json.dumps(saved)   # ids and counts only, no names


def test_player_result_correction_with_unchanged_team_totals_is_reconciled(setup, monkeypatch):
    # APA corrected who won each game; the team score (9-6) did not change, so a team-total diff sees nothing.
    report, _ = _run(setup, monkeypatch, m1=[_row(VIEWER, "L", "T1"), _row(OPP, "W", "T2")])
    assert report["changes"]["matches_score_changed"] == []
    assert sorted((x["player"], x["changes"]["result"][1]) for x in report["reconciliation"]["player_results_changed"]) \
        == [(VIEWER, "L"), (OPP, "W")]
    assert _rows(setup[2] / "ultimate_coach_staging.db", "M1") == [(VIEWER, "L", "T1"), (OPP, "W", "T2")]


def test_partial_existing_scoresheet_is_completed(setup, monkeypatch):
    con = sqlite3.connect(setup[0])
    con.execute("DELETE FROM player_matches WHERE player_id = 2 AND match_id = 1")   # only half the sheet captured
    con.commit()
    con.close()
    report, _ = _run(setup, monkeypatch)
    assert report["reconciliation"]["player_results_added"] == [{"match_id": "M1", "player": OPP}]
    assert _rows(setup[2] / "ultimate_coach_staging.db", "M1") == [(VIEWER, "W", "T1"), (OPP, "L", "T2")]


def test_authoritative_removal_and_earlier_session_history_preserved(setup, monkeypatch):
    report, _ = _run(setup, monkeypatch, m1=[_row(VIEWER, "W", "T1")])   # the corrected sheet no longer has OPP
    assert report["reconciliation"]["player_results_removed"] == [{"match_id": "M1", "player": OPP}]
    db = setup[2] / "ultimate_coach_staging.db"
    assert _rows(db, "M1") == [(VIEWER, "W", "T1")]
    assert _rows(db, "OLD") == [(VIEWER, "L", "T1")]                    # an earlier session is never touched
    assert _rows(db, "M2") == [(VIEWER, "W", "T1"), (OPP, "L", "T2")]   # nor another match of this session


def test_repeating_the_refresh_adds_nothing_twice(setup, monkeypatch):
    correction = [_row(VIEWER, "L", "T1"), _row(OPP, "W", "T2")]
    first, _ = _run(setup, monkeypatch, m1=correction)
    again, _ = _run(setup, monkeypatch, m1=correction, source=setup[2] / "ultimate_coach_staging.db",
                    out=setup[2].parent / "out-again")
    db = setup[2].parent / "out-again" / "ultimate_coach_staging.db"
    assert first["reconciliation"]["player_results_changed"] and not again["reconciliation"]["player_results_changed"]
    assert not again["reconciliation"]["player_results_added"] and not again["reconciliation"]["player_results_removed"]
    assert sorted(again["reconciliation"]["matches_checked"]) == ["M1", "M2"]   # M2 now has rows, so it is re-checked
    assert _rows(db, "M1") == [(VIEWER, "L", "T1"), (OPP, "W", "T2")]
    assert again["changes"]["totals_after"]["player_matches"] == first["changes"]["totals_after"]["player_matches"]


def test_denied_empty_and_unresolved_answers_stay_visible_as_gaps(setup, monkeypatch):
    from scraper.auth_classification import ConfirmedScopeDenial

    db = setup[2] / "ultimate_coach_staging.db"
    denied, _ = _run(setup, monkeypatch, m1=ConfirmedScopeDenial("denied"))
    assert denied["reconciliation"]["matches_failed"] == ["M1"] and denied["coverage"] == "partial"
    assert any(g.startswith("match M1: scoresheet denied") for g in denied["gaps"])
    assert _rows(db, "M1") == [(VIEWER, "W", "T1"), (OPP, "L", "T2")]          # kept, and reported unverified

    empty, _ = _run(setup, monkeypatch, m1=[], out=setup[2].parent / "out-empty")
    assert "match M1: APA returned no player rows; 2 existing row(s) kept unverified" in empty["gaps"]
    assert _rows(setup[2].parent / "out-empty" / "ultimate_coach_staging.db", "M1") == [(VIEWER, "W", "T1"),
                                                                                         (OPP, "L", "T2")]
    unresolved, _ = _run(setup, monkeypatch, m1=[_row(VIEWER, "W", "T1")], out=setup[2].parent / "out-unres",
                         resolve=lambda db, session, scores, current_only=True: ({}, 0, 1))
    assert any("identity(ies) unresolved" in g for g in unresolved["gaps"]) and unresolved["coverage"] == "partial"
    assert not unresolved["reconciliation"]["player_results_removed"]          # nothing removed on a guess
    failed, _ = _run(setup, monkeypatch, m1=RuntimeError("boom"), out=setup[2].parent / "out-failed")
    assert failed["reconciliation"]["matches_failed"] == ["M1"] and failed["coverage"] == "partial"


def test_missing_only_mode_never_claims_complete_coverage(setup, monkeypatch):
    fetched = []
    report, _ = _run(setup, monkeypatch, mode="missing-only", fetched=fetched)
    assert fetched == [] and report["reconciliation"]["matches_checked"] == []
    assert report["coverage"] == "partial" and report["provenance"]["mode"] == "missing-only"


def test_mine_only_and_unscored_monday_is_a_reported_gap(setup, monkeypatch):
    report, calls = _run(setup, monkeypatch, mine_only=True)
    assert [c[0] for c in calls] == ["D1"]
    source, catalog, out = setup
    report2 = refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=out.parent / "out2",
                                  mine_only=True, verify_member=VIEWER, verify_date="2026-10-05",
                                  sync=lambda *a, **k: _fake_sync([])(*a[:2], "D9", *a[3:], **k),
                                  rebuild_matchups=lambda db: [], schedule=_schedule, scoresheet=_sheets(),
                                  resolve=RESOLVED)
    assert "viewer fixture M2 on 2026-10-05 is still not scored in APA's data" in report2["gaps"]


def test_a_confirmed_division_denial_is_a_gap_not_a_crash(setup, monkeypatch):
    from scraper.auth_classification import ConfirmedScopeDenial

    def retry(config, fetch):
        if len(seen) == 1:
            raise ConfirmedScopeDenial("denied")
        seen.append(1)
        return fetch()
    seen = []
    report, _ = _run(setup, monkeypatch, retry=retry, mode="missing-only")
    assert any("D2" in g and "denied" in g for g in report["gaps"])
    assert [d.get("confirmed_denial") for d in report["divisions"]] == [None, True]


def test_refuses_to_overwrite_an_existing_copy(setup, monkeypatch):
    _run(setup, monkeypatch)
    with pytest.raises(refresh.RefreshError, match="overwrite"):
        _run(setup, monkeypatch)


def test_verify_member_defaults_to_the_configured_viewer(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(refresh, "run_refresh", lambda config, **kw: seen.update(kw) or {
        "changes": {"date_range_checked": None, "latest_scored_date_before": None, "latest_scored_date_after": None,
                    "matches_added": [], "matches_newly_scored": [], "matches_score_changed": [],
                    "scoresheet_rows_added": 0},
        "provenance": {"refreshed_db": "x", "refreshed_db_sha256": "y", "source_db_sha256": "z"}, "gaps": [],
        "reconciliation": {"matches_checked": [], "matches_failed": [], "player_results_changed": [],
                           "player_results_added": [], "player_results_removed": []}, "coverage": "partial",
        "scope": {"divisions": 0}})
    monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda dest, repo: dest)
    config = tmp_path / "apa_config.yaml"
    config.write_text("ultimate_coach:\n  viewer_member_external_id: \"9001\"\n", encoding="utf-8")
    assert refresh.main(["--config", str(config), "--verify-date", "2026-10-05"]) == 0
    assert seen["verify_member"] == "9001" and seen["verify_date"] == "2026-10-05" and seen["mode"] == "reconcile"
    config.write_text("ultimate_coach:\n  viewer_member_external_id: \"CHANGE_ME\"\n", encoding="utf-8")
    assert refresh.main(["--config", str(config), "--verify-date", "2026-10-05"]) == 2   # never guessed


def test_describe_source_never_lets_a_partial_or_altered_refresh_pass_as_current(setup, monkeypatch, capsys):
    # GPT 056dae6: partial reports must not become accepted current data. A build records this verdict.
    source, _, out = setup
    assert refresh.describe_source(source) == {
        "refreshed": False, "accepted_current_data": False,
        "note": "no refresh_report.json beside the source DB: data as originally archived, not refreshed"}
    _run(setup, monkeypatch)                                   # complete reconcile refresh
    copy = out / "ultimate_coach_staging.db"
    complete = refresh.describe_source(copy)
    assert complete["refreshed"] and complete["report_matches_db"] and complete["coverage"] == "complete"
    assert complete["accepted_current_data"] and complete["gaps"] == 0 and complete["mode"] == "reconcile"
    assert refresh.main(["--describe-source", str(copy)]) == 0
    assert json.loads(capsys.readouterr().out) == complete     # the build script reads this JSON
    partial, _ = _run(setup, monkeypatch, mode="missing-only", out=out.parent / "out-partial")
    assert not refresh.describe_source(out.parent / "out-partial" / "ultimate_coach_staging.db")["accepted_current_data"]
    con = sqlite3.connect(copy)                                # edited after its refresh: the report no longer
    con.execute("UPDATE player_matches SET result = 'L' WHERE id = 1")   # describes this file
    con.commit()
    con.close()
    altered = refresh.describe_source(copy)
    assert not altered["report_matches_db"] and not altered["accepted_current_data"]
