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


class TestLatestScoredDateRequiresRealEvidence:
    """GPT audit 7a4f8b5: a live refresh (refresh-20261009-035923Z) reported
    latest_scored_date_after=2026-10-12, but that date's only "scored" match
    (51775357) was flagged COMPLETED/is_scored=1 by APA with null team
    scores and zero player/head-to-head rows -- a scheduling-system
    artifact, not a real result. diff() computed the headline freshness
    date from the raw is_scored flag alone, so it advertised a date with no
    actual evidence behind it. The real latest evidence that night was
    2026-10-07. The match still surfaces as its own disclosed gap via
    scored_matches_without_scoresheet either way -- this only fixes the
    headline date, not that existing gap mechanism."""

    def test_a_completed_flag_with_null_scores_does_not_inflate_the_latest_date(self):
        before = {"matches": {}, "totals": {}}
        after = {"matches": {
            "M1": {"date": "2026-10-07", "status": "COMPLETED", "is_scored": True, "home_score": 9.0,
                   "away_score": 6.0, "scoresheet_rows": 10},
            "M2": {"date": "2026-10-12", "status": "COMPLETED", "is_scored": True, "home_score": None,
                   "away_score": None, "scoresheet_rows": 0},
        }, "totals": {}}

        result = refresh.diff(before, after)

        assert result["latest_scored_date_after"] == "2026-10-07"
        assert "M2" in result["scored_matches_without_scoresheet"]   # still disclosed as its own gap

    def test_the_before_side_gets_the_same_protection(self):
        before = {"matches": {
            "M1": {"date": "2026-09-20", "status": "COMPLETED", "is_scored": True, "home_score": 9.0,
                   "away_score": 6.0, "scoresheet_rows": 10},
            "M2": {"date": "2026-10-01", "status": "COMPLETED", "is_scored": True, "home_score": None,
                   "away_score": None, "scoresheet_rows": 0},
        }, "totals": {}}
        after = {"matches": {}, "totals": {}}

        result = refresh.diff(before, after)

        assert result["latest_scored_date_before"] == "2026-09-20"

    def test_a_real_score_of_zero_still_counts_as_evidence(self):
        """0-0 and similar low real scores must not be mistaken for the
        None/None no-evidence case -- only an actual missing score should
        be excluded, never a legitimately low one."""
        before = {"matches": {}, "totals": {}}
        after = {"matches": {
            "M1": {"date": "2026-10-10", "status": "COMPLETED", "is_scored": True, "home_score": 0.0,
                   "away_score": 0.0, "scoresheet_rows": 0},
        }, "totals": {}}

        result = refresh.diff(before, after)

        assert result["latest_scored_date_after"] == "2026-10-10"


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
                                                    "is_bye": False, "scoresheet_rows": 2, "viewer_rows": 1}]
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
    """Runs under tmp_path because it used to run in the REPO.

    Without --out-root this called main() with the default out-root, so every
    full-suite run created a real timestamped directory in tmp/refresh/ holding
    an empty log and nothing else -- the stub it patches over run_refresh
    returns a dict without doing any work.

    Those directories are indistinguishable from an aborted live login, and I
    spent a long investigation diagnosing them as the owner's failed attempts
    before the call-site identity marker named this lambda as the callee. A
    test that writes into the working tree does not just risk flaky state; it
    manufactures false evidence about production.
    """
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
    out_root = str(tmp_path / "refresh")        # never the repo's own tmp/refresh -- see below
    assert refresh.main(["--config", str(config), "--out-root", out_root, "--verify-date", "2026-10-05"]) == 0
    assert seen["verify_member"] == "9001" and seen["verify_date"] == "2026-10-05" and seen["mode"] == "reconcile"
    config.write_text("ultimate_coach:\n  viewer_member_external_id: \"CHANGE_ME\"\n", encoding="utf-8")
    assert refresh.main(["--config", str(config), "--out-root", out_root,
                         "--verify-date", "2026-10-05"]) == 2   # never guessed


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


def test_an_unexpected_failure_is_recorded_on_disk_and_scrubbed(tmp_path, monkeypatch, capsys):
    # The first real run (2026-10-08 15:43 UTC) died after copying with only a console traceback.
    secret = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"

    def boom(config, **kw):
        logging.getLogger("scheduler.graphql_sync").warning("calling with Bearer %s", secret)
        raise ValueError(f"unexpected answer while using Bearer {secret}")
    import logging

    monkeypatch.setattr(refresh, "run_refresh", boom)
    monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda dest, repo: dest)
    config = tmp_path / "apa_config.yaml"
    config.write_text("ultimate_coach: {}\n", encoding="utf-8")
    assert refresh.main(["--config", str(config), "--out-root", str(tmp_path / "r")]) == 5
    run = next((tmp_path / "r").iterdir())
    error = json.loads((run / "refresh_error.json").read_text(encoding="utf-8"))
    log = (run / "refresh.log").read_text(encoding="utf-8")
    assert error["error_type"] == "ValueError" and "NOT a refreshed database" in error["note"]
    assert "unexpected answer" in error["message"] and "[redacted]" in error["message"]
    for text in (json.dumps(error), log, capsys.readouterr().out):
        assert secret not in text and "eyJ" not in text
    assert "calling with [redacted]" in log
    assert refresh.describe_source(run / "ultimate_coach_staging.db")["accepted_current_data"] is False


def test_describe_source_fails_closed_on_inconsistent_or_malformed_reports(setup, monkeypatch):
    # GPT audit 9244b5e: a matching hash + coverage "complete" was accepted even with mode missing-only and a gap.
    _run(setup, monkeypatch)
    copy = setup[2] / "ultimate_coach_staging.db"
    path = copy.with_name("refresh_report.json")
    good = json.loads(path.read_text(encoding="utf-8"))
    assert refresh.describe_source(copy)["accepted_current_data"] is True

    def verdict(mutate=None, raw=None):
        if raw is not None:
            path.write_text(raw, encoding="utf-8")
        else:
            report = json.loads(json.dumps(good))
            mutate(report)
            path.write_text(json.dumps(report), encoding="utf-8")
        out = refresh.describe_source(copy)
        assert out["accepted_current_data"] is False and out["rejected_because"], out
        return " | ".join(out["rejected_because"])

    def inconsistent(r):                       # GPT's exact probe: hash matches, "complete", but missing-only + a gap
        r["provenance"]["mode"] = "missing-only"
        r["gaps"] = ["match M9: scoresheet denied; existing rows kept unverified"]
    assert "mode is 'missing-only'" in verdict(inconsistent) and "1 gap(s)" in verdict(inconsistent)
    assert "mode is None" in verdict(lambda r: r["provenance"].pop("mode"))
    assert "schema is None" in verdict(lambda r: r.pop("schema"))
    assert "schema is 'other-v9'" in verdict(lambda r: r.update(schema="other-v9"))
    assert "gap(s)" in verdict(lambda r: r.update(gaps="none"))                       # wrong type
    assert "coverage is None" in verdict(lambda r: r.pop("coverage"))
    assert "denied or incomplete" in verdict(lambda r: r["divisions"][1].update(confirmed_denial=True))
    assert "denied or incomplete" in verdict(lambda r: r["divisions"][0].update(coverage_observations=["1 team not ingested"]))
    assert "matches failed" in verdict(lambda r: r["reconciliation"]["matches_failed"].append("M1"))
    assert "reconciliation results are missing" in verdict(lambda r: r.pop("reconciliation"))
    assert "source changed" in verdict(lambda r: r["provenance"].update(source_db_sha256_after="0" * 64))
    assert "catalog provenance" in verdict(lambda r: r["provenance"].pop("catalog_sha256"))
    assert "scope does not match" in verdict(lambda r: r["scope"].update(divisions=31))
    assert "does not match this file" in verdict(lambda r: r["provenance"].update(refreshed_db_sha256="0" * 64))
    assert "not valid JSON" in verdict(raw="{not json")
    assert "not a JSON object" in verdict(raw="[1, 2]")
    path.write_text(json.dumps(good), encoding="utf-8")
    assert refresh.describe_source(copy)["accepted_current_data"] is True                # the untouched report


def test_a_token_that_expires_mid_run_is_resumed_on_the_same_copy(setup, monkeypatch):
    # Live run 2026-10-08: APA rejected the token after ~14 min of a >1 h scope. Progress must survive a re-login.
    from scraper.graphql_scraper import AccessTokenExpired

    source, catalog, out = setup
    single, _ = _run(setup, monkeypatch, out=out.parent / "single")              # the reference: one segment
    with pytest.raises(AccessTokenExpired):
        _run(setup, monkeypatch, m1=AccessTokenExpired("expired"))               # dies inside D1's reconcile
    progress = json.loads((out / "refresh_progress.json").read_text(encoding="utf-8"))
    assert progress["completed_divisions"] == [] and progress["segments"][-1]["ended_by"] == "AccessTokenExpired"
    assert not (out / "refresh_report.json").exists()
    unfinished = refresh.describe_source(out / "ultimate_coach_staging.db")
    assert unfinished["accepted_current_data"] is False and "UNFINISHED" in unfinished["note"]

    monkeypatch.setattr("scraper.auth_classification.call_with_confirmed_denial_retry", lambda config, fetch: fetch())
    resumed = refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=out, resume=True,
                                  verify_member=VIEWER, verify_date="2026-10-05", sync=_fake_sync([]),
                                  rebuild_matchups=lambda db: [], schedule=_schedule, scoresheet=_sheets(),
                                  resolve=RESOLVED)
    assert [s["ended_by"] for s in resumed["segments"]] == ["AccessTokenExpired", "completed"]
    # Judged against the ORIGINAL before-snapshot: the same changes as the one-shot run, nothing counted twice.
    for key in ("matches_newly_scored", "matches_added", "scoresheet_rows_added", "latest_scored_date_before"):
        assert resumed["changes"][key] == single["changes"][key], key
    assert resumed["reconciliation"]["matches_checked"] == ["M1"] and resumed["coverage"] == "complete"
    assert refresh.describe_source(out / "ultimate_coach_staging.db")["accepted_current_data"] is True
    with pytest.raises(refresh.RefreshError, match="already has a refresh report"):
        refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=out, resume=True,
                            sync=_fake_sync([]), rebuild_matchups=lambda db: [], schedule=_schedule,
                            scoresheet=_sheets(), resolve=RESOLVED)


def test_resume_refuses_a_changed_source_and_runs_the_viewers_divisions_first(setup, monkeypatch):
    from scraper.graphql_scraper import AccessTokenExpired

    source, catalog, out = setup
    rows = json.loads(catalog.read_text(encoding="utf-8"))
    for r in rows["divisions"]:
        r["is_mine"] = r["division_id"] == "D2"                                   # the viewer's division sorts later
    catalog.write_text(json.dumps(rows), encoding="utf-8")
    report, calls = _run(setup, monkeypatch, out=out.parent / "order")
    assert [c[0] for c in calls] == ["D2", "D1"]                                  # viewer's own division first
    with pytest.raises(AccessTokenExpired):
        _run(setup, monkeypatch, m1=AccessTokenExpired("expired"))
    con = sqlite3.connect(source)
    con.execute("UPDATE matches SET week = 99 WHERE id = 3")                      # the source moved on meanwhile
    con.commit()
    con.close()
    with pytest.raises(refresh.RefreshError, match="source_db_sha256"):
        refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=out, resume=True,
                            sync=_fake_sync([]), rebuild_matchups=lambda db: [], schedule=_schedule,
                            scoresheet=_sheets(), resolve=RESOLVED)


def test_resume_refuses_an_older_incompatible_checkpoint_instead_of_crashing(setup, monkeypatch):
    # GPT audit 1633b34: ed139fe changed progress["results"] from a list to a dict keyed by division, but never
    # bumped PROGRESS_SCHEMA -- so a preserved v1 checkpoint (same schema string, results still a list) passed
    # the version check and only failed later with AttributeError at results.items(). A clean, explicit refusal
    # is required instead.
    from scraper.graphql_scraper import AccessTokenExpired

    source, catalog, out = setup
    with pytest.raises(AccessTokenExpired):
        _run(setup, monkeypatch, m1=AccessTokenExpired("expired"))
    progress = json.loads((out / "refresh_progress.json").read_text(encoding="utf-8"))
    progress["schema"] = "ultimate-coach-current-session-refresh-progress-v1"   # the pre-ed139fe shape
    progress["results"] = []                                                    # its results were a list, not a dict
    (out / "refresh_progress.json").write_text(json.dumps(progress), encoding="utf-8")

    monkeypatch.setattr("scraper.auth_classification.call_with_confirmed_denial_retry", lambda config, fetch: fetch())
    with pytest.raises(refresh.RefreshError, match="older, incompatible progress format"):
        refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=out, resume=True,
                            verify_member=VIEWER, verify_date="2026-10-05", sync=_fake_sync([]),
                            rebuild_matchups=lambda db: [], schedule=_schedule, scoresheet=_sheets(), resolve=RESOLVED)
    # Refused before anything was touched: the stale checkpoint and copy are exactly as this test left them.
    assert json.loads((out / "refresh_progress.json").read_text(encoding="utf-8"))["results"] == []
    assert not (out / "refresh_report.json").exists()


def test_capture_tool_renews_an_expired_token_from_the_open_browser_and_resumes(tmp_path, monkeypatch):
    import os

    from tools import capture_apa_graphql as capture

    folder = tmp_path / "refresh-x"
    folder.mkdir()
    (folder / "refresh_progress.json").write_text("{}", encoding="utf-8")
    calls, codes = [], iter([3, 3, 0])                      # expires twice, then completes

    def fake_main(args):
        calls.append((list(args), os.environ.get("APA_ACCESS_TOKEN")))
        refresh.LAST_OUT_DIR = folder
        return next(codes)
    monkeypatch.setattr(refresh, "main", fake_main)
    tokens = iter(["t2", "t3"])
    capture._run_uc_refresh("t1", ["--verify-date", "2026-10-05"], renew=lambda old: next(tokens))
    assert [c[1] for c in calls] == ["t1", "t2", "t3"]     # each segment used the then-current token
    assert calls[0][0] == ["--verify-date", "2026-10-05"]
    assert calls[1][0] == calls[2][0] == ["--verify-date", "2026-10-05", "--resume", str(folder)]   # never doubled
    assert "APA_ACCESS_TOKEN" not in os.environ             # never left behind

    codes2 = iter([3])
    monkeypatch.setattr(refresh, "main", lambda args: (setattr(refresh, "LAST_OUT_DIR", folder), next(codes2))[1])
    with pytest.raises(SystemExit) as stop:                  # the browser gave no NEW token: stop, keep progress
        capture._run_uc_refresh("t1", [], renew=lambda old: old)
    assert stop.value.code == 3 and "APA_ACCESS_TOKEN" not in os.environ
    monkeypatch.setattr(refresh, "main", lambda args: 4)      # any other failure is not retried
    with pytest.raises(SystemExit) as other:
        capture._run_uc_refresh("t1", [], renew=lambda old: "never")
    assert other.value.code == 4


def test_resume_reopens_a_division_whose_match_failed_before_a_later_division_expired(setup, monkeypatch):
    # GPT audit 77e99da: D1 finishes with a failed match (not fatal, the loop continues); D2 then raises
    # AccessTokenExpired (fatal). THE BUG: D1 got marked completed anyway, so on resume its failed outcome was
    # stripped and retried but D1 itself was skipped -- the gap vanished and coverage could read "complete".
    from scraper.graphql_scraper import AccessTokenExpired

    source, catalog, out = setup
    con = sqlite3.connect(source)
    con.execute("INSERT INTO matches (id, external_id, home_team_id, away_team_id, home_team_name, away_team_name,"
                " match_date, status, format, session_name, home_score, away_score, is_scored) VALUES"
                " (4, 'M3', 'T1', 'T2', 'Ours', 'Theirs', '2026-09-20T19:00:00-06:00', 'COMPLETED', '8-Ball Open',"
                " 'Fall 2026', 9, 6, 1)")
    con.execute("INSERT INTO player_matches (player_id, match_id, match_date, team_id, result) VALUES"
                " (1, 4, '2026-09-20', 'T1', 'W'), (2, 4, '2026-09-20', 'T2', 'L')")
    con.commit()
    con.close()

    def schedule2(cfg, division_id):
        return {"D1": [{"match_id": "M1", "is_scored": True, "is_bye": False}],
                "D2": [{"match_id": "M3", "is_scored": True, "is_bye": False}]}[division_id]

    state = {"m1_attempts": 0, "m3_ok": False}

    def scoresheet2(config, match_id):
        if match_id == "M1":
            state["m1_attempts"] += 1
            if state["m1_attempts"] == 1:
                raise RuntimeError("APA returned a malformed scoresheet")
            return [_row(VIEWER, "W", "T1"), _row(OPP, "L", "T2")], []
        if match_id == "M3":
            if not state["m3_ok"]:
                raise AccessTokenExpired("expired")
            return [_row(VIEWER, "W", "T1"), _row(OPP, "L", "T2")], []
        raise AssertionError(match_id)

    with pytest.raises(AccessTokenExpired):
        refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=out,
                            sync=_fake_sync([]), rebuild_matchups=lambda db: [], schedule=schedule2,
                            scoresheet=scoresheet2, resolve=RESOLVED)
    progress = json.loads((out / "refresh_progress.json").read_text(encoding="utf-8"))
    assert progress["completed_divisions"] == []           # D1 must NOT be marked complete despite finishing
    assert [c["match_id"] for c in progress["checked"] if c["status"] == "fetch_failed"] == ["M1"]

    state["m3_ok"] = True                                   # the renewed login fixes D2's problem
    resumed = refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=out,
                                  resume=True, sync=_fake_sync([]), rebuild_matchups=lambda db: [],
                                  schedule=schedule2, scoresheet=scoresheet2, resolve=RESOLVED)
    assert sorted(resumed["reconciliation"]["matches_checked"]) == ["M1", "M3"]
    assert resumed["reconciliation"]["matches_failed"] == []
    assert resumed["gaps"] == [] and resumed["coverage"] == "complete"
    assert refresh.describe_source(out / "ultimate_coach_staging.db")["accepted_current_data"] is True


def test_resume_never_claims_complete_while_a_reopened_division_keeps_failing(setup, monkeypatch):
    # The other half of 77e99da's requested regression: a match that NEVER recovers must stay an honest,
    # reported gap across resumes -- never silently dropped, never marked complete.
    from scraper.graphql_scraper import AccessTokenExpired

    source, catalog, out = setup
    con = sqlite3.connect(source)
    con.execute("INSERT INTO matches (id, external_id, home_team_id, away_team_id, home_team_name, away_team_name,"
                " match_date, status, format, session_name, home_score, away_score, is_scored) VALUES"
                " (4, 'M3', 'T1', 'T2', 'Ours', 'Theirs', '2026-09-20T19:00:00-06:00', 'COMPLETED', '8-Ball Open',"
                " 'Fall 2026', 9, 6, 1)")
    con.execute("INSERT INTO player_matches (player_id, match_id, match_date, team_id, result) VALUES"
                " (1, 4, '2026-09-20', 'T1', 'W'), (2, 4, '2026-09-20', 'T2', 'L')")
    con.commit()
    con.close()

    def schedule2(cfg, division_id):
        return {"D1": [{"match_id": "M1", "is_scored": True, "is_bye": False}],
                "D2": [{"match_id": "M3", "is_scored": True, "is_bye": False}]}[division_id]

    state = {"m3_ok": False}

    def scoresheet2(config, match_id):
        if match_id == "M1":
            raise RuntimeError("APA keeps returning a malformed scoresheet")      # never recovers
        if match_id == "M3":
            if not state["m3_ok"]:
                raise AccessTokenExpired("expired")
            return [_row(VIEWER, "W", "T1"), _row(OPP, "L", "T2")], []
        raise AssertionError(match_id)

    with pytest.raises(AccessTokenExpired):
        refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=out,
                            sync=_fake_sync([]), rebuild_matchups=lambda db: [], schedule=schedule2,
                            scoresheet=scoresheet2, resolve=RESOLVED)
    state["m3_ok"] = True
    resumed = refresh.run_refresh({"database": {}}, source_db=source, catalog_path=catalog, out_dir=out,
                                  resume=True, sync=_fake_sync([]), rebuild_matchups=lambda db: [],
                                  schedule=schedule2, scoresheet=scoresheet2, resolve=RESOLVED)
    assert resumed["reconciliation"]["matches_failed"] == ["M1"]
    assert any(g.startswith("match M1: scoresheet fetch failed") for g in resumed["gaps"])
    assert resumed["coverage"] == "partial"
    progress = json.loads((out / "refresh_progress.json").read_text(encoding="utf-8"))
    assert all(not k.startswith("D1|") for k in progress["completed_divisions"])   # D1 stays reopened
    assert refresh.describe_source(out / "ultimate_coach_staging.db")["accepted_current_data"] is False


class TestAnInterruptedRunStillRecordsWhyItStopped:
    """Seven live attempts left a directory holding nothing but an empty log.

    Interruption, crash and early failure were indistinguishable from the
    artifacts, because main() only recorded `Exception` -- and KeyboardInterrupt
    and SystemExit are not Exceptions. So the one question that mattered, "did
    it crash or was it stopped?", could not be answered from disk at all.

    A refresh that dies without saying why costs a real APA login to retry, so
    recording the cause is worth more than the handful of lines it takes.
    """

    def test_a_keyboard_interrupt_writes_a_failure_record_and_still_propagates(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(refresh, "run_refresh", boom)
        monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)
        out_root = tmp_path / "refresh"

        with pytest.raises(KeyboardInterrupt):
            refresh.main(["--out-root", str(out_root), "--source-db", str(tmp_path / "nope.db")])

        folder = refresh.LAST_OUT_DIR
        assert folder is not None and folder.is_dir()
        record = folder / "refresh_error.json"
        assert record.is_file(), sorted(f.name for f in folder.iterdir())
        assert "KeyboardInterrupt" in json.loads(record.read_text(encoding="utf-8"))["error_type"]

    def test_a_system_exit_is_recorded_the_same_way(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise SystemExit(7)

        monkeypatch.setattr(refresh, "run_refresh", boom)
        monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)

        with pytest.raises(SystemExit):
            refresh.main(["--out-root", str(tmp_path / "refresh"), "--source-db", str(tmp_path / "nope.db")])

        record = refresh.LAST_OUT_DIR / "refresh_error.json"
        assert record.is_file()
        assert "SystemExit" in json.loads(record.read_text(encoding="utf-8"))["error_type"]


class TestTheRunLeavesABreadcrumbOfHowFarItGot:
    """Nine live attempts, and the ninth ran 12 minutes AFTER the interrupt
    recorder landed and still wrote no record.

    That leaves three causes which the artifacts cannot tell apart: forced
    process termination, a failure in the directory/logging setup that happens
    OUTSIDE the handler, or a failure while writing the record itself. GPT
    49e5dd3 lists the same three.

    A stage breadcrumb separates them. It is appended and flushed at each step,
    so whatever survives says how far the run got even when nothing else does.
    """

    def _args(self, tmp_path):
        return ["--out-root", str(tmp_path / "refresh"), "--source-db", str(tmp_path / "nope.db")]

    def test_the_stage_file_records_reaching_the_refresh(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(refresh, "run_refresh", boom)
        monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)

        with pytest.raises(KeyboardInterrupt):
            refresh.main(self._args(tmp_path))

        stages = (refresh.LAST_OUT_DIR / "refresh_stage.txt").read_text(encoding="utf-8")
        assert "directory created" in stages
        assert "logging ready" in stages
        assert "loading config" in stages
        assert "config loaded" in stages

    def test_a_record_that_cannot_be_written_still_leaves_a_plain_text_fallback(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("original failure")

        def cannot_write(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(refresh, "run_refresh", boom)
        monkeypatch.setattr(refresh, "_write_failure", cannot_write)
        monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)

        refresh.main(self._args(tmp_path))

        stages = (refresh.LAST_OUT_DIR / "refresh_stage.txt").read_text(encoding="utf-8")
        assert "RuntimeError" in stages and "original failure" in stages


class TestAConsoleFailureCannotDestroyTheFailureRecord:
    """Attempt twelve showed stage lines through `finally` and NO error record.

    The handlers printed before recording, so anything that made the print fail
    -- a UnicodeEncodeError on a cp1252 console being the obvious candidate on
    this machine -- took the evidence down with it and let the original
    exception propagate. The run then looks like it vanished.

    The console is the least reliable thing in the process and the record is
    the most valuable, so the record goes first.
    """

    def test_the_record_is_written_even_when_printing_fails(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise refresh.RefreshError("synthetic stop")

        def exploding_print(*args, **kwargs):
            raise UnicodeEncodeError("charmap", "x", 0, 1, "synthetic console failure")

        monkeypatch.setattr(refresh, "run_refresh", boom)
        monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)
        monkeypatch.setattr("builtins.print", exploding_print)

        refresh.main(["--out-root", str(tmp_path / "refresh"), "--source-db", str(tmp_path / "nope.db")])

        record = refresh.LAST_OUT_DIR / "refresh_error.json"
        assert record.is_file(), sorted(f.name for f in refresh.LAST_OUT_DIR.iterdir())
        assert "RefreshError" in json.loads(record.read_text(encoding="utf-8"))["error_type"]

    def test_run_refresh_marks_that_it_was_called_before_its_prologue_can_raise(self, tmp_path, monkeypatch):
        """A missing source DB raises in run_refresh's prologue, BEFORE the old
        breadcrumb, so 'never entered' and 'raised early' looked identical."""
        monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)

        refresh.main(["--out-root", str(tmp_path / "refresh"), "--source-db", str(tmp_path / "missing.db")])

        stages = (refresh.LAST_OUT_DIR / "refresh_stage.txt").read_text(encoding="utf-8")
        assert "run_refresh: called" in stages
        assert "run_refresh: body entered" not in stages


def test_the_stage_file_names_the_instrument_that_wrote_it(tmp_path, monkeypatch):
    """A refresh directory is created only after the operator finishes logging
    in, which can be minutes after the process imported this module. Directory
    mtime therefore cannot say which code ran -- I misread stale-code runs as
    evidence about a new fix twice before adding this line.
    """
    monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)
    refresh.main(["--out-root", str(tmp_path / "refresh"), "--source-db", str(tmp_path / "missing.db")])
    stages = (refresh.LAST_OUT_DIR / "refresh_stage.txt").read_text(encoding="utf-8")
    assert stages.splitlines()[0].endswith(refresh._INSTRUMENT_VERSION)


class TestABrokenConsoleChangesNoOutcome:
    """GPT a823a33: two handler prints were still raw, so a failing console
    replaced the real outcome with a UnicodeEncodeError.

    The record was written either way, so this is not about losing evidence --
    it is about the caller being told something false. A generic failure must
    still return 5, and an interruption must still surface as the interruption
    the operator caused, not as a console encoding error.
    """

    def _broken_console(self, monkeypatch):
        def exploding_print(*args, **kwargs):
            raise UnicodeEncodeError("charmap", "x", 0, 1, "synthetic console failure")

        monkeypatch.setattr("builtins.print", exploding_print)
        monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)

    def test_a_generic_failure_still_returns_five(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("synthetic generic failure")

        monkeypatch.setattr(refresh, "run_refresh", boom)
        self._broken_console(monkeypatch)

        assert refresh.main(["--out-root", str(tmp_path / "r"), "--source-db", str(tmp_path / "x.db")]) == 5
        assert (refresh.LAST_OUT_DIR / "refresh_error.json").is_file()

    def test_an_interruption_surfaces_as_itself_not_as_a_console_error(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(refresh, "run_refresh", boom)
        self._broken_console(monkeypatch)

        with pytest.raises(KeyboardInterrupt):
            refresh.main(["--out-root", str(tmp_path / "r"), "--source-db", str(tmp_path / "x.db")])
        assert (refresh.LAST_OUT_DIR / "refresh_error.json").is_file()

    def test_the_stage_file_names_which_handler_ran(self, tmp_path, monkeypatch):
        """Attempt fourteen reached config-loaded then finally, with no record and
        no run_refresh entry. Nothing said whether a handler ran at all."""
        def boom(*args, **kwargs):
            raise RuntimeError("synthetic generic failure")

        monkeypatch.setattr(refresh, "run_refresh", boom)
        monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)

        refresh.main(["--out-root", str(tmp_path / "r"), "--source-db", str(tmp_path / "x.db")])

        stages = (refresh.LAST_OUT_DIR / "refresh_stage.txt").read_text(encoding="utf-8")
        assert "handler: generic exception" in stages
        assert "arguments resolved" in stages


class TestNoDiagnosticSinkLeaksCredentials:
    """GPT f18b690 (P1): I introduced this one.

    The inner call guard wrote str(exc) straight into refresh_stage.txt while
    every other sink -- the error JSON and the log formatter -- scrubbed it.
    HTTP libraries routinely put bearer tokens into exception text, so a
    diagnostic I added to chase a bug became the one place a credential could
    land in a file.

    Scrubbing now lives inside _stage itself rather than at its call sites, so
    a future caller cannot reintroduce the bypass by forgetting.
    """

    SENTINEL = "Bearer eyJhbGciOiJIUzI1NiJ9.ZZSYNTHETICPAYLOAD.ZZSYNTHETICSIG"

    def test_a_token_in_an_exception_never_reaches_any_diagnostic_file(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError(f"upstream rejected {self.SENTINEL} while fetching")

        monkeypatch.setattr(refresh, "run_refresh", boom)
        monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)

        assert refresh.main(["--out-root", str(tmp_path / "r"), "--source-db", str(tmp_path / "x.db")]) == 5

        leaked = []
        for produced in sorted(refresh.LAST_OUT_DIR.iterdir()):
            text = produced.read_text(encoding="utf-8", errors="replace")
            if "ZZSYNTHETICPAYLOAD" in text or "ZZSYNTHETICSIG" in text:
                leaked.append(produced.name)
        assert leaked == [], f"credential text reached: {leaked}"

        stages = (refresh.LAST_OUT_DIR / "refresh_stage.txt").read_text(encoding="utf-8")
        assert "[redacted]" in stages, stages
        assert "RuntimeError" in stages

    def test_stage_scrubs_even_when_a_caller_forgets(self, tmp_path):
        """The guarantee belongs to _stage, not to its callers."""
        out = tmp_path / "d"
        out.mkdir()
        refresh._stage(out, f"careless diagnostic {self.SENTINEL}")
        written = (out / "refresh_stage.txt").read_text(encoding="utf-8")
        assert "ZZSYNTHETICPAYLOAD" not in written
        assert "[redacted]" in written


class TestTruncationCannotDefeatRedaction:
    """GPT 60de108 (P1 remains): truncating before scrubbing re-opens the leak.

    The call site passed str(exc)[:200] into _stage. A long BARE JWT cut at 200
    characters loses its signature segment, so the two-segment remainder no
    longer matches a three-segment JWT pattern and survives redaction.

    Two defences, because either alone is brittle: scrub BEFORE truncating at
    the call site, and widen the pattern so a two-segment eyJ prefix is still
    treated as token-shaped. "eyJ" is base64 for '{"' -- a bare one in an
    exception message is a credential fragment, not prose.
    """

    LONG_BARE_JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                     + "ZZLONGPAYLOAD" * 30 + ".ZZTAILSIGNATURE")

    def test_a_long_bare_token_is_redacted_despite_truncation(self, tmp_path, monkeypatch):
        assert len(self.LONG_BARE_JWT) > 250, "sentinel must exceed the truncation window"

        def boom(*args, **kwargs):
            raise RuntimeError(f"upstream rejected {self.LONG_BARE_JWT} while fetching")

        monkeypatch.setattr(refresh, "run_refresh", boom)
        monkeypatch.setattr("scripts.repo_boundary.check_output_root", lambda *a, **k: None)

        refresh.main(["--out-root", str(tmp_path / "r"), "--source-db", str(tmp_path / "x.db")])

        leaked = [f.name for f in sorted(refresh.LAST_OUT_DIR.iterdir())
                  if "ZZLONGPAYLOAD" in f.read_text(encoding="utf-8", errors="replace")]
        assert leaked == [], f"truncated token text reached: {leaked}"

    def test_scrub_catches_a_two_segment_token_prefix(self):
        truncated = self.LONG_BARE_JWT[:200]
        assert truncated.count(".") == 1, "the sentinel must truncate to two segments"
        assert "ZZLONGPAYLOAD" not in refresh._scrub(truncated)


class TestAByeIsNotACoverageGap:
    """A bye has no scoresheet because nobody played it, so counting it as a
    completed match missing its scoresheet reports a problem that does not
    exist. Measured in refresh-20261009-035923Z: of 13 "no scoresheet" gap
    strings, 4 were byes -- every one of them a bye of the viewer's own teams
    (2026-08-23 and 2026-08-24, week 4, home and away both named Bye/BYE,
    is_bye=1, is_scored=1, zero player_matches and zero head-to-head rows).
    The division-wide ingest path already skips byes; this diff did not, so
    only the viewer's own byes were ever reported.

    The deliberately-disclosed case from audit 7a4f8b5 -- is_scored with null
    scores and zero rows, which is a real scheduling artifact rather than a
    bye -- must keep being reported, so this exclusion is on is_bye alone."""

    def test_a_played_match_with_no_scoresheet_is_still_a_gap(self):
        after = {"matches": {
            "REAL": {"date": "2026-07-18", "status": "COMPLETED", "is_scored": True, "home_score": 9.0,
                     "away_score": 6.0, "scoresheet_rows": 0, "is_bye": False},
        }, "totals": {}}

        result = refresh.diff({"matches": {}, "totals": {}}, after)

        assert result["scored_matches_without_scoresheet"] == ["REAL"]

    def test_a_bye_is_not_reported_as_a_match_missing_its_scoresheet(self):
        after = {"matches": {
            "BYE": {"date": "2026-08-23", "status": "COMPLETED", "is_scored": True, "home_score": 0.0,
                    "away_score": 10.0, "scoresheet_rows": 0, "is_bye": True},
        }, "totals": {}}

        result = refresh.diff({"matches": {}, "totals": {}}, after)

        assert result["scored_matches_without_scoresheet"] == []

    def test_the_null_score_artifact_stays_disclosed(self):
        """Audit 7a4f8b5's case is not a bye and must not be swept up by this."""
        after = {"matches": {
            "ARTIFACT": {"date": "2026-10-12", "status": "COMPLETED", "is_scored": True, "home_score": None,
                         "away_score": None, "scoresheet_rows": 0, "is_bye": False},
        }, "totals": {}}

        result = refresh.diff({"matches": {}, "totals": {}}, after)

        assert result["scored_matches_without_scoresheet"] == ["ARTIFACT"]

    def test_the_snapshot_reads_the_bye_flag_so_the_diff_can_use_it(self, tmp_path):
        """A diff cannot exclude byes if snapshot() never reads is_bye."""
        db = tmp_path / "s.db"
        con = sqlite3.connect(db)
        con.executescript(
            "CREATE TABLE matches (id INTEGER PRIMARY KEY, external_id TEXT, match_date TEXT, status TEXT,"
            " is_scored INT, home_score REAL, away_score REAL, is_bye INT, session_name TEXT);"
            "CREATE TABLE player_matches (id INTEGER PRIMARY KEY, match_id INT, player_id INT);"
            "CREATE TABLE players (id INTEGER PRIMARY KEY, external_id TEXT);"
            "INSERT INTO matches VALUES (1,'BYE','2026-08-23','COMPLETED',1,0.0,10.0,1,'Fall 2026');"
            "INSERT INTO matches VALUES (2,'REAL','2026-08-30','COMPLETED',1,9.0,6.0,0,'Fall 2026');")
        con.commit()
        con.close()

        snap = refresh.snapshot(db, {"Fall 2026"})

        assert snap["matches"]["BYE"]["is_bye"] is True
        assert snap["matches"]["REAL"]["is_bye"] is False
        assert refresh.diff({"matches": {}, "totals": {}}, snap)["scored_matches_without_scoresheet"] == ["REAL"]


class TestAByeIsNotFreshnessEvidence:
    """The sibling of TestAByeIsNotACoverageGap, found by asking where else a
    bye is treated as a played match.

    has_real_evidence() was written for audit 7a4f8b5, where APA flagged a
    match scored with NULL team scores, so it requires both scores to be
    present. A bye passes that test: APA scores byes with a forfeit shape
    (0-10 for 8-Ball, 0-70 for 9-Ball), which is non-null. Measured in
    refresh-20261009-035923Z: all four past byes pass has_real_evidence, and
    the latest bye passing it is 2026-08-24. It is latent there only because
    a real match on 2026-10-07 is later -- but the same teams have byes on
    2026-10-26 and 2026-11-01, so a refresh run just after a bye week would
    headline a freshness date backed by a match nobody played. That is the
    exact failure 7a4f8b5 fixed, reached through a different door.

    The viewer-fixture gap checks have the same blind spot: a bye on the
    verified date is scored with no scoresheet rows, so it would be reported
    as a problem when it is simply a week off."""

    def test_a_bye_does_not_become_the_latest_scored_date(self):
        after = {"matches": {
            "REAL": {"date": "2026-10-07", "status": "COMPLETED", "is_scored": True, "home_score": 9.0,
                     "away_score": 6.0, "scoresheet_rows": 10, "is_bye": False},
            "BYE": {"date": "2026-11-01", "status": "COMPLETED", "is_scored": True, "home_score": 0.0,
                    "away_score": 10.0, "scoresheet_rows": 0, "is_bye": True},
        }, "totals": {}}

        result = refresh.diff({"matches": {}, "totals": {}}, after)

        assert result["latest_scored_date_after"] == "2026-10-07"

    def test_the_before_side_also_ignores_a_bye(self):
        before = {"matches": {
            "BYE": {"date": "2026-11-01", "status": "COMPLETED", "is_scored": True, "home_score": 0.0,
                    "away_score": 70.0, "scoresheet_rows": 0, "is_bye": True},
            "REAL": {"date": "2026-09-20", "status": "COMPLETED", "is_scored": True, "home_score": 9.0,
                     "away_score": 6.0, "scoresheet_rows": 10, "is_bye": False},
        }, "totals": {}}

        result = refresh.diff(before, {"matches": {}, "totals": {}})

        assert result["latest_scored_date_before"] == "2026-09-20"

    def test_verify_fixtures_reports_whether_a_fixture_is_a_bye(self, tmp_path):
        db = tmp_path / "v.db"
        con = sqlite3.connect(db)
        con.executescript(
            "CREATE TABLE matches (id INTEGER PRIMARY KEY, external_id TEXT, home_team_id TEXT, away_team_id TEXT,"
            " match_date TEXT, status TEXT, format TEXT, session_name TEXT, home_score REAL, away_score REAL,"
            " is_scored INT, is_bye INT);"
            "CREATE TABLE players (id INTEGER PRIMARY KEY, external_id TEXT);"
            "CREATE TABLE player_matches (id INTEGER PRIMARY KEY, match_id INT, player_id INT);"
            "CREATE TABLE player_team_history (id INTEGER PRIMARY KEY, player_id INT, team_external_id TEXT,"
            " session_name TEXT);"
            "INSERT INTO players VALUES (1, 'V1');"
            "INSERT INTO player_team_history VALUES (1, 1, 'T1', 'Fall 2026');"
            "INSERT INTO matches VALUES (1, 'BYE', 'T1', 'T9', '2026-11-01T11:00:00-06:00', 'COMPLETED',"
            " 'EIGHT', 'Fall 2026', 0.0, 10.0, 1, 1);")
        con.commit()
        con.close()

        rows = refresh.verify_fixtures(db, "V1", "2026-11-01", {"Fall 2026"})

        assert len(rows) == 1 and rows[0]["match_id"] == "BYE"
        assert rows[0]["is_bye"] is True

    def test_a_bye_on_the_verified_date_is_not_reported_as_a_gap(self, setup, monkeypatch):
        source, catalog, out = setup
        con = sqlite3.connect(source)
        con.execute("INSERT INTO player_team_history (player_id, is_current, team_external_id, team_name,"
                    " session_name) VALUES (1, 1, 'T1', 'Ours', 'Fall 2026')")
        con.execute("INSERT INTO matches (id, external_id, home_team_id, away_team_id, home_team_name,"
                    " away_team_name, match_date, status, format, session_name, home_score, away_score,"
                    " is_scored, is_bye) VALUES (9, 'BYE9', 'T1', 'T2', 'Bye', 'BYE',"
                    " '2026-10-19T19:00:00-06:00', 'COMPLETED', '8-Ball Open', 'Fall 2026', 0, 10, 1, 1)")
        con.commit()
        con.close()
        monkeypatch.setattr("scraper.auth_classification.call_with_confirmed_denial_retry",
                            lambda config, fetch: fetch())

        report = refresh.run_refresh(
            {"database": {}}, source_db=source, catalog_path=catalog, out_dir=out.parent / "out-bye",
            verify_member=VIEWER, verify_date="2026-10-19", sync=_fake_sync([]),
            rebuild_matchups=lambda db: [], schedule=_schedule, scoresheet=_sheets(), resolve=RESOLVED,
            now=lambda: datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc))

        assert report["verify"]["viewer_fixtures"], "the bye must still be disclosed as the viewer's fixture"
        assert not [g for g in report["gaps"] if "BYE9" in g], \
            f"a bye is a week off, not a coverage problem: {[g for g in report['gaps'] if 'BYE9' in g]}"
