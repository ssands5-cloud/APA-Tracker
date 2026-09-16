"""Tests for scripts/build_full_production_demo.py.

One real fixture bundle is built once for the whole module (the build runs
every analytics builder, so rebuilding per test would be wasteful), then the
failure modes are exercised against copies of it. Nothing here touches the
network: fixture mode rebuilds data/demo_coherent.db from
scripts/build_coherent_demo.py, and live mode is only ever exercised through
its refusal path.
"""

from __future__ import annotations

import json
import shutil

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scripts import build_full_production_demo as builder
from scripts.build_full_production_demo import (
    FEATURE_STATUS,
    FIXTURE_EXPECTATIONS,
    FIXTURE_SCOPE,
    BuildError,
    resolve_contained,
    run_build,
    sha256_file,
)


@pytest.fixture(scope="module")
def run_root():
    """Run inside the repository on purpose.

    The builder refuses any output path outside the canonical repository
    root, which is a production guarantee -- so these tests build under the
    real (gitignored) demo-runs/ tree rather than weakening that check with
    a test-only bypass.
    """
    root = builder.PROJECT_ROOT / "demo-runs" / "pytest"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def run_dir(run_root):
    target = run_root / "fixture-test"
    run_build("fixture", target, run_root)
    return target


@pytest.fixture
def run_copy(run_dir, tmp_path):
    """An isolated copy, so a tampering test cannot affect its neighbours."""
    destination = tmp_path / "run"
    shutil.copytree(run_dir, destination)
    return destination


class TestBundleShape:
    def test_ready_is_written_and_names_the_manifest_hash(self, run_dir):
        ready = json.loads((run_dir / "READY").read_text(encoding="utf-8"))
        assert ready["manifest_sha256"] == sha256_file(run_dir / "demo_manifest.json")
        assert ready["run_id"] == run_dir.name

    def test_every_required_artifact_is_a_nonempty_regular_file(self, run_dir):
        manifest = json.loads((run_dir / "demo_manifest.json").read_text(encoding="utf-8"))
        for relative in manifest["artifacts"]:
            target = run_dir / relative
            assert target.is_file(), relative
            assert target.stat().st_size > 0, relative

    def test_checksums_cover_every_artifact_and_the_manifest(self, run_dir):
        lines = (run_dir / "checksums.sha256").read_text(encoding="utf-8").splitlines()
        listed = {line.split("  ", 1)[1] for line in lines if line.strip()}
        manifest = json.loads((run_dir / "demo_manifest.json").read_text(encoding="utf-8"))

        assert set(manifest["artifacts"]) <= listed
        assert "demo_manifest.json" in listed

    def test_staging_directory_is_removed(self, run_dir):
        assert not [p for p in run_dir.iterdir() if p.name.startswith("staging-")]

    def test_index_links_the_artifacts_and_uses_no_external_resources(self, run_dir):
        index = (run_dir / "index.html").read_text(encoding="utf-8")

        assert 'href="html/team_strength.html"' in index
        assert 'href="excel/player_vs_player.xlsx"' in index
        assert "http://" not in index
        assert "https://" not in index


class TestReconciliation:
    def test_manifest_records_the_fixture_scope_exactly(self, run_dir):
        manifest = json.loads((run_dir / "demo_manifest.json").read_text(encoding="utf-8"))
        assert manifest["scope"] == FIXTURE_SCOPE

    def test_pairing_and_evidence_counts_match_the_fixture(self, run_dir):
        reconciliation = json.loads(
            (run_dir / "demo_manifest.json").read_text(encoding="utf-8")
        )["reconciliation"]

        assert reconciliation["total_feasible_pairings"] == FIXTURE_EXPECTATIONS["total_feasible_pairings"]
        assert reconciliation["DIRECT"] == FIXTURE_EXPECTATIONS["DIRECT"]
        assert reconciliation["INDIRECT"] == FIXTURE_EXPECTATIONS["INDIRECT"]
        assert reconciliation["UNKNOWN"] == FIXTURE_EXPECTATIONS["UNKNOWN"]

    def test_roster_identities_are_recorded_for_both_sides(self, run_dir):
        reconciliation = json.loads(
            (run_dir / "demo_manifest.json").read_text(encoding="utf-8")
        )["reconciliation"]

        assert len(reconciliation["our_roster_player_ids"]) == 5
        assert len(reconciliation["opponent_roster_player_ids"]) == 5
        assert not set(reconciliation["our_roster_player_ids"]) & set(
            reconciliation["opponent_roster_player_ids"]
        )

    def test_database_hash_is_locked_and_matches_the_bundled_copy(self, run_dir):
        manifest = json.loads((run_dir / "demo_manifest.json").read_text(encoding="utf-8"))
        bundled = run_dir / "data" / manifest["database_file"]

        assert sha256_file(bundled) == manifest["database_sha256"]


class TestUnimplementedFeatures:
    def test_unimplemented_features_are_declared_not_implemented(self, run_dir):
        manifest = json.loads((run_dir / "demo_manifest.json").read_text(encoding="utf-8"))

        assert manifest["feature_status"]["match_difficulty_heatmap"] == "not_implemented"
        assert manifest["feature_status"]["captains_live_assistant"] == "not_implemented"

    def test_no_placeholder_artifact_is_emitted_for_them(self, run_dir):
        names = {p.name for p in (run_dir / "html").iterdir()}

        assert "match_difficulty_heatmap.html" not in names
        assert "captains_live_assistant.html" not in names

    def test_index_says_they_are_not_implemented(self, run_dir):
        index = (run_dir / "index.html").read_text(encoding="utf-8")

        assert "Not implemented" in index
        assert "Match Difficulty Heatmap: not implemented" in index
        assert "Captains Live Assistant: not implemented" in index


class TestVerifiedFixtureLabelling:
    def test_index_states_the_source_is_fixture_rehearsal_data(self, run_dir):
        index = (run_dir / "index.html").read_text(encoding="utf-8")

        assert "VERIFIED FIXTURE" in index
        assert "not live APA production evidence" in index

    def test_index_shows_run_id_build_time_and_database_hash(self, run_dir):
        index = (run_dir / "index.html").read_text(encoding="utf-8")
        manifest = json.loads((run_dir / "demo_manifest.json").read_text(encoding="utf-8"))

        assert manifest["run_id"] in index
        assert manifest["database_sha256"][:16] in index

    def test_manifest_labels_the_source(self, run_dir):
        manifest = json.loads((run_dir / "demo_manifest.json").read_text(encoding="utf-8"))
        assert manifest["source_label"] == "verified_fixture"


class TestPreflightRefusals:
    def test_a_non_empty_run_directory_is_refused(self, run_root):
        target = run_root / "already-there"
        target.mkdir(parents=True, exist_ok=True)
        (target / "leftover.txt").write_text("stale", encoding="utf-8")
        try:
            with pytest.raises(BuildError) as excinfo:
                builder.preflight(target, run_root)
        finally:
            shutil.rmtree(target, ignore_errors=True)

        assert excinfo.value.code == builder.EXIT_PREFLIGHT
        assert "not empty" in str(excinfo.value)

    def test_a_run_root_outside_the_repository_is_refused(self, tmp_path):
        target = tmp_path / "runs" / "escape"

        with pytest.raises(BuildError, match="escapes the repository boundary"):
            builder.preflight(target, tmp_path / "runs")

    def test_a_path_outside_the_repository_is_refused(self, tmp_path):
        with pytest.raises(BuildError, match="escapes the repository boundary"):
            resolve_contained(tmp_path / "elsewhere", builder.PROJECT_ROOT)

    def test_a_traversal_path_is_refused(self):
        with pytest.raises(BuildError, match="escapes the repository boundary"):
            resolve_contained(builder.PROJECT_ROOT / ".." / "escape", builder.PROJECT_ROOT)


class TestArtifactValidation:
    def test_an_empty_artifact_fails_the_build(self, run_copy):
        (run_copy / "html" / "team_strength.html").write_text("", encoding="utf-8")

        with pytest.raises(BuildError) as excinfo:
            builder._require_nonempty(run_copy / "html", builder.HTML_ARTIFACTS, "html")

        assert "empty" in str(excinfo.value)
        assert excinfo.value.code == builder.EXIT_RENDER

    def test_a_missing_artifact_fails_the_build(self, run_copy):
        (run_copy / "html" / "team_strength.html").unlink()

        with pytest.raises(BuildError, match="missing"):
            builder._require_nonempty(run_copy / "html", builder.HTML_ARTIFACTS, "html")

    def test_a_stale_undeclared_artifact_fails_the_build(self, run_copy):
        (run_copy / "html" / "stale_leftover.html").write_text("old", encoding="utf-8")

        with pytest.raises(BuildError, match="unexpected"):
            builder._require_nonempty(run_copy / "html", builder.HTML_ARTIFACTS, "html")


class TestVerifyPhase:
    def _reconciliation(self, **overrides):
        base = {
            "our_roster_count": 5,
            "opponent_roster_count": 5,
            "our_roster_player_ids": [1, 2, 3, 4, 5],
            "opponent_roster_player_ids": [6, 7, 8, 9, 10],
            "total_feasible_pairings": 25,
            "DIRECT": 5,
            "INDIRECT": 20,
            "UNKNOWN": 0,
        }
        base.update(overrides)
        return base

    def test_a_changed_database_hash_fails_the_run(self, run_copy):
        manifest = json.loads((run_copy / "demo_manifest.json").read_text(encoding="utf-8"))
        bundled_db = run_copy / "data" / manifest["database_file"]

        with pytest.raises(BuildError, match="database hash changed"):
            builder.verify(run_copy, bundled_db, "0" * 64, "fixture", self._reconciliation())

    def test_counts_that_do_not_sum_to_the_total_fail(self, run_copy):
        manifest = json.loads((run_copy / "demo_manifest.json").read_text(encoding="utf-8"))
        bundled_db = run_copy / "data" / manifest["database_file"]

        with pytest.raises(BuildError, match="do not sum"):
            builder.verify(
                run_copy, bundled_db, sha256_file(bundled_db), "fixture",
                self._reconciliation(DIRECT=4),
            )

    def test_a_mixed_scope_roster_cross_product_mismatch_fails(self, run_copy):
        manifest = json.loads((run_copy / "demo_manifest.json").read_text(encoding="utf-8"))
        bundled_db = run_copy / "data" / manifest["database_file"]

        with pytest.raises(BuildError, match="roster cross-product"):
            builder.verify(
                run_copy, bundled_db, sha256_file(bundled_db), "fixture",
                self._reconciliation(our_roster_count=4),
            )

    def test_a_workbook_disagreeing_with_the_matrix_fails(self, run_copy):
        manifest = json.loads((run_copy / "demo_manifest.json").read_text(encoding="utf-8"))
        bundled_db = run_copy / "data" / manifest["database_file"]
        reconciliation = self._reconciliation(
            our_roster_count=6, total_feasible_pairings=30, INDIRECT=25
        )

        with pytest.raises(BuildError, match="pair row"):
            builder.verify(
                run_copy, bundled_db, sha256_file(bundled_db), "fixture", reconciliation
            )

    def test_the_real_bundle_passes_verification(self, run_copy):
        manifest = json.loads((run_copy / "demo_manifest.json").read_text(encoding="utf-8"))
        bundled_db = run_copy / "data" / manifest["database_file"]

        result = builder.verify(
            run_copy, bundled_db, sha256_file(bundled_db), "fixture",
            manifest["reconciliation"],
        )

        assert result.status == "ok"


class TestFinalizeOrdering:
    def test_a_failed_finalize_leaves_no_ready_marker(self, run_copy):
        (run_copy / "READY").unlink()
        manifest = json.loads((run_copy / "demo_manifest.json").read_text(encoding="utf-8"))
        manifest["artifacts"].append("html/does_not_exist.html")

        with pytest.raises((BuildError, OSError)):
            builder.finalize(run_copy, manifest)

        assert not (run_copy / "READY").exists()


class TestLiveMode:
    def test_a_missing_token_fails_with_an_actionable_message(self, monkeypatch):
        monkeypatch.delenv(builder.TOKEN_ENV, raising=False)

        with pytest.raises(BuildError) as excinfo:
            builder.acquire_live()

        message = str(excinfo.value)
        assert builder.TOKEN_ENV in message
        assert "/authorize" in message
        assert excinfo.value.code == builder.EXIT_AUTH

    def test_it_never_offers_a_username_password_fallback(self, monkeypatch):
        monkeypatch.delenv(builder.TOKEN_ENV, raising=False)

        with pytest.raises(BuildError) as excinfo:
            builder.acquire_live()

        assert "never falls back" in str(excinfo.value)

    def test_the_token_value_is_never_echoed(self, monkeypatch, run_copy):
        monkeypatch.setenv(builder.TOKEN_ENV, "super-secret-token-value")
        manifest = json.loads((run_copy / "demo_manifest.json").read_text(encoding="utf-8"))
        engine = create_engine(
            "sqlite://", creator=lambda: builder.connect_read_only(
                run_copy / "data" / manifest["database_file"]
            ),
        )
        db = Session(bind=engine)
        try:
            with pytest.raises(BuildError) as excinfo:
                builder._live_scope(db)
        finally:
            db.close()
            engine.dispose()

        assert "super-secret-token-value" not in str(excinfo.value)

    def test_fixture_expectations_are_not_applied_to_live_runs(self, run_copy):
        """Live data has its own real shape and must not be asserted against
        the rehearsal fixture's 5x5/25-pairing figures."""
        manifest = json.loads((run_copy / "demo_manifest.json").read_text(encoding="utf-8"))
        bundled_db = run_copy / "data" / manifest["database_file"]
        # Internally consistent, but nothing like the fixture's shape.
        live_shaped = {
            "our_roster_count": 8,
            "opponent_roster_count": 7,
            "our_roster_player_ids": list(range(8)),
            "opponent_roster_player_ids": list(range(8, 15)),
            "total_feasible_pairings": 56,
            "DIRECT": 6,
            "INDIRECT": 50,
            "UNKNOWN": 0,
        }

        with pytest.raises(BuildError) as fixture_mode:
            builder.verify(
                run_copy, bundled_db, sha256_file(bundled_db), "fixture", live_shaped
            )
        assert "fixture expectation" in str(fixture_mode.value)

        # The same figures in live mode raise only the workbook-parity
        # complaint, never a fixture-expectation one.
        with pytest.raises(BuildError) as live_mode:
            builder.verify(
                run_copy, bundled_db, sha256_file(bundled_db), "live", live_shaped
            )
        assert "fixture expectation" not in str(live_mode.value)
