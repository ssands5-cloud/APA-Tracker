"""Tests for scripts/build_coach_advantage_bundle.py.

One real bundle is built once for the whole module against the coherent
fixture database (scripts/build_coherent_demo.py) -- the same real,
internally-consistent 5v5 rehearsal dataset scripts/build_full_production_demo.py's
own fixture-mode tests already build against.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import build_coach_advantage_bundle as builder
from scripts.build_coherent_demo import build as build_coherent
from scripts.build_full_production_demo import FIXTURE_SCOPE


@pytest.fixture(scope="module")
def coherent_db(tmp_path_factory):
    """A private copy of the coherent rehearsal database, built to its own
    temp path -- NOT the shared data/demo_coherent.db every other test
    module's fixture also rebuilds. Sharing that file caused a real,
    reproducible Windows failure: this module's own read-only connection to
    it (TestVerifyPhase) could still hold the file open by the time
    test_build_full_production_demo.py's module fixture later tried to
    unlink() and rebuild the very same path, since Windows (unlike POSIX)
    refuses to delete a file any process still has open at all, even
    read-only."""
    return build_coherent(str(tmp_path_factory.mktemp("coach_advantage") / "demo_coherent.db"))


@pytest.fixture(scope="module")
def run_root():
    root = builder.PROJECT_ROOT / "coach-advantage-runs" / "pytest"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def run_dir(coherent_db, run_root):
    target = run_root / "fixture-test"
    builder.run_build(coherent_db, FIXTURE_SCOPE["our_team_id"], target, run_root)
    return target


@pytest.fixture
def run_copy(run_dir, tmp_path):
    destination = tmp_path / "run"
    shutil.copytree(run_dir, destination)
    return destination


class TestBundleShape:
    def test_ready_is_written_and_names_the_manifest_hash(self, run_dir):
        ready = json.loads((run_dir / "READY").read_text(encoding="utf-8"))
        manifest_hash = builder.sha256_file(run_dir / builder.MANIFEST_NAME)
        assert ready["manifest_sha256"] == manifest_hash

    def test_every_artifact_is_a_nonempty_regular_file(self, run_dir):
        manifest = json.loads((run_dir / builder.MANIFEST_NAME).read_text(encoding="utf-8"))
        for relative in manifest["artifacts"]:
            path = run_dir / relative
            assert path.is_file()
            assert path.stat().st_size > 0

    def test_checksums_cover_every_artifact_and_the_manifest(self, run_dir):
        manifest = json.loads((run_dir / builder.MANIFEST_NAME).read_text(encoding="utf-8"))
        lines = (run_dir / builder.CHECKSUMS_NAME).read_text(encoding="utf-8").splitlines()
        covered = {line.split("  ", 1)[1] for line in lines}
        assert covered == set(manifest["artifacts"]) | {builder.MANIFEST_NAME}


class TestRealFixtureContent:
    def test_player_reports_cover_the_full_roster_cross_product(self, run_dir):
        data = json.loads((run_dir / "json" / "player_matchup_engine.json").read_text(encoding="utf-8"))
        assert len(data) == 25  # 5x5 fixture roster cross-product

    def test_team_report_reconciles_direct_indirect_unknown(self, run_dir):
        data = json.loads((run_dir / "json" / "team_matchup_engine.json").read_text(encoding="utf-8"))
        assert len(data) == 1
        counts = data[0]["evidence_counts"]
        assert counts["DIRECT"] + counts["INDIRECT"] + counts["UNKNOWN"] == counts["total_feasible_pairings"]

    def test_lineup_is_embedded_in_the_team_report(self, run_dir):
        data = json.loads((run_dir / "json" / "team_matchup_engine.json").read_text(encoding="utf-8"))
        assert data[0]["lineup"] is not None
        assert len(data[0]["lineup"]["assignments"]) > 0

    def test_dashboard_embeds_both_engines_json(self, run_dir):
        html = (run_dir / "html" / "dashboard.html").read_text(encoding="utf-8")
        assert 'id="cd-player-data"' in html
        assert 'id="cd-team-data"' in html

    def test_no_categorical_verdict_language_anywhere_in_the_bundle(self, run_dir):
        for name in ("player_matchup_engine.html", "team_matchup_engine.html", "dashboard.html"):
            html = (run_dir / "html" / name).read_text(encoding="utf-8").lower()
            assert "recommended avoid" not in html
            assert "recommended target" not in html
            assert "toughest real matchup" not in html
            assert "most favorable real matchup" not in html

    def test_direct_pairings_carry_a_real_win_loss_record(self, run_dir):
        """GPT audit P1 / directive item 4 ("verify W-L records are
        present"): every DIRECT player report must carry a reconstructed
        win/loss record, not just the observed rate and a bare match
        count."""
        data = json.loads((run_dir / "json" / "player_matchup_engine.json").read_text(encoding="utf-8"))
        direct = [r for r in data if r["evidence_label"] == "DIRECT"]
        assert direct, "the coherent fixture is expected to have real DIRECT pairings"
        for report in direct:
            assert report["direct_wins"] is not None
            assert report["direct_losses"] is not None
            assert report["direct_wins"] + report["direct_losses"] == report["direct_evidence_count"]

    def test_player_reports_carry_their_real_team_scope(self, run_dir):
        """GPT audit P1: player reports must be attributable to a real
        team pairing, not just two internal player ids."""
        data = json.loads((run_dir / "json" / "player_matchup_engine.json").read_text(encoding="utf-8"))
        for report in data:
            assert report["our_team_id"]
            assert report["opponent_team_id"]

    def test_the_dashboards_player_selector_is_player_then_opponent(self, run_dir):
        """Directive item 2 / GPT audit P2: the selector must be a linked
        player-then-opponent workflow, not one flat list of every real
        pairing."""
        html = (run_dir / "html" / "dashboard.html").read_text(encoding="utf-8")
        assert 'id="pme-player"' in html
        assert 'id="pme-opponent"' in html
        assert 'id="cd-player-opponent-index"' in html


class TestPreflightRefusals:
    def test_a_non_empty_run_directory_is_refused(self, run_root):
        target = run_root / "non-empty"
        target.mkdir(parents=True, exist_ok=True)
        (target / "stale.txt").write_text("x", encoding="utf-8")
        try:
            with pytest.raises(builder.BuildError, match="not empty"):
                builder.preflight(target, run_root)
        finally:
            shutil.rmtree(target, ignore_errors=True)

    def test_an_unknown_team_id_fails_closed_not_silently_empty(self, coherent_db, run_root):
        target = run_root / "unknown-team"
        try:
            with pytest.raises(builder.BuildError, match="no real scheduled match"):
                builder.run_build(coherent_db, "no-such-team", target, run_root)
        finally:
            shutil.rmtree(target, ignore_errors=True)


class TestVerifyPhase:
    def test_the_real_bundle_passes_verification(self, coherent_db, run_dir):
        # Re-derive the same computed scopes verify() checked at build time.
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from scripts.build_captains_edge import connect_read_only

        engine = create_engine("sqlite://", creator=lambda: connect_read_only(coherent_db))
        db = Session(bind=engine)
        try:
            computed, _risk, _result = builder.compute(
                db, FIXTURE_SCOPE["our_team_id"], "Fixture Sharks",
            )
            result = builder.verify(computed)
        finally:
            db.close()
            engine.dispose()
        assert result.status == "ok"


class TestFinalizeOrdering:
    def test_a_failed_finalize_leaves_no_ready_marker(self, run_copy):
        (run_copy / "READY").unlink()
        manifest = json.loads((run_copy / builder.MANIFEST_NAME).read_text(encoding="utf-8"))
        manifest["artifacts"].append("html/does_not_exist.html")

        with pytest.raises((builder.BuildError, OSError)):
            builder.finalize(run_copy, manifest)

        assert not (run_copy / "READY").exists()
