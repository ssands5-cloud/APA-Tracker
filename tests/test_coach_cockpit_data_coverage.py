"""Regression coverage for v1.1 Coach Cockpit Data Coverage integration."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scripts import build_coach_advantage_bundle as builder
from scripts.build_captains_edge import connect_read_only
from scripts.build_coherent_demo import build as build_coherent
from scripts.build_full_production_demo import FIXTURE_SCOPE
from ui import coach_cockpit


@pytest.fixture(scope="module")
def coherent_db(tmp_path_factory):
    return build_coherent(str(tmp_path_factory.mktemp("coach_cockpit") / "demo_coherent.db"))


@pytest.fixture(scope="module")
def computed(coherent_db):
    engine = create_engine("sqlite://", creator=lambda: connect_read_only(coherent_db))
    db = Session(bind=engine)
    try:
        scopes, risk, result = builder.compute(
            db, FIXTURE_SCOPE["our_team_id"], "Fixture Sharks",
        )
        yield scopes, risk, result
    finally:
        db.close()
        engine.dispose()


@pytest.fixture(scope="module")
def run_dir(coherent_db):
    root = builder.PROJECT_ROOT / "coach-advantage-runs" / "pytest-v11-cockpit"
    target = root / "fixture-test"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    try:
        builder.run_build(coherent_db, FIXTURE_SCOPE["our_team_id"], target, root)
        yield target
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_every_usable_scope_reuses_its_matrix_for_data_coverage(computed):
    scopes, _risk, _result = computed
    usable = [scope for scope in scopes if scope.matrix is not None]
    assert usable
    for scope in usable:
        assert scope.coverage_report is not None
        counts = scope.matrix.counts
        coverage = scope.coverage_report.evidence_coverage
        assert (
            coverage.direct_count,
            coverage.indirect_count,
            coverage.unknown_count,
            coverage.total,
        ) == (
            counts["DIRECT"],
            counts["INDIRECT"],
            counts["UNKNOWN"],
            counts["total_feasible_pairings"],
        )


def test_generated_dashboard_contains_existing_data_coverage_report(run_dir):
    html = (run_dir / "html" / "dashboard.html").read_text(encoding="utf-8")
    assert 'id="data-coverage-freshness"' in html
    assert "Data Coverage &amp; Freshness" in html
    assert "Evidence coverage" in html
    assert "Missing skill levels" in html
    assert "Sample sizes" in html
    assert "Standings last captured:" in html
    assert "Player career stats last updated:" in html
    assert "No age threshold" in html


def test_cockpit_keeps_match_night_runtime_intact(run_dir):
    html = (run_dir / "html" / "dashboard.html").read_text(encoding="utf-8")
    assert 'id="mn-comparison"' in html
    assert 'id="mn-lineup"' in html
    assert "window.__matchNightTestHooks" in html
    assert "Data Coverage &amp; Freshness" in html


def test_cockpit_contains_wide_coverage_tables_locally_not_by_hiding_overflow(run_dir):
    html = (run_dir / "html" / "dashboard.html").read_text(encoding="utf-8")
    assert '.dc-embedded { margin: 10px 0; overflow-x: auto; }' in html
    assert "overflow-x: hidden" not in html
    assert '<details class="dc-embedded">' in html


def test_missing_data_coverage_is_disclosed_not_invented():
    html = coach_cockpit.render([], [], [], "Fixture Sharks", data_coverage_reports=())
    assert "No Data Coverage report is available for this bundle." in html
    assert "Data Coverage &amp; Freshness" in html


def test_composition_fails_closed_if_base_dashboard_body_contract_changes(monkeypatch):
    monkeypatch.setattr(coach_cockpit, "render_dashboard", lambda *args, **kwargs: "<html></html>")
    with pytest.raises(ValueError, match="exactly one </body>"):
        coach_cockpit.render([], [], [], "Fixture Sharks", data_coverage_reports=())
