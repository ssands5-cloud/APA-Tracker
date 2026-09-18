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
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Match
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

    def test_zero_assignments_with_no_explanation_still_fails(self, run_copy):
        """The pre-existing guarantee this check exists for: genuinely empty
        lineups (a real bug, e.g. build_lineups.py never ran) must still
        fail verification when nothing declares why."""
        manifest = json.loads((run_copy / "demo_manifest.json").read_text(encoding="utf-8"))
        bundled_db = run_copy / "data" / manifest["database_file"]
        lineups_path = run_copy / "json" / "lineups.json"
        payload = json.loads(lineups_path.read_text(encoding="utf-8"))
        payload["lineups"] = []
        payload["lineups_unavailable"] = []
        lineups_path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(BuildError, match="no lineup assignments"):
            builder.verify(
                run_copy, bundled_db, sha256_file(bundled_db), "fixture",
                manifest["reconciliation"],
            )

    def test_zero_assignments_with_a_declared_reason_does_not_fail(self, run_copy):
        """The new, load-bearing behaviour: a run whose own selected scope
        exceeded the lineup optimizer's exact-search guard is a real,
        reported state (scripts/build_lineups.py's "available": False
        groups) -- not a silent failure this check should hide behind a
        hard build error."""
        manifest = json.loads((run_copy / "demo_manifest.json").read_text(encoding="utf-8"))
        bundled_db = run_copy / "data" / manifest["database_file"]
        lineups_path = run_copy / "json" / "lineups.json"
        payload = json.loads(lineups_path.read_text(encoding="utf-8"))
        payload["lineups"] = []
        payload["lineups_unavailable"] = [{
            "available": False,
            "team_id": "1", "team_name": "Our Team",
            "opponent_team_id": "2", "opponent_team_name": "Their Team",
            "format": "8-Ball Open", "session_name": "2026 Rehearsal Session",
            "unavailable_reason": "needs 3,628,800 assignments, above the 500,000 guard",
        }]
        lineups_path.write_text(json.dumps(payload), encoding="utf-8")

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


class TestResumeFlagPolicy:
    def test_resume_is_rejected_outside_live_mode(self):
        with pytest.raises(SystemExit):
            builder.main(["--mode", "fixture", "--resume"])


class TestScopeOverridePolicy:
    def test_scope_overrides_are_rejected_outside_live_mode(self):
        with pytest.raises(SystemExit):
            builder.main([
                "--mode", "fixture",
                "--opponent-team-id", "1", "--session", "S", "--format", "F",
            ])

    def test_scope_overrides_must_be_given_together(self):
        with pytest.raises(SystemExit):
            builder.main(["--mode", "live", "--opponent-team-id", "1"])

    def test_partial_scope_overrides_via_main_are_rejected(self):
        with pytest.raises(SystemExit):
            builder.main(["--mode", "live", "--session", "S", "--format", "F"])


class TestLiveScopePinning:
    def _seeded_db(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'pin.db'}")
        from database.models import Base, Player, PlayerTeamHistory

        Base.metadata.create_all(engine)
        db = Session(bind=engine)
        our, opp = "111", "222"
        session_name = "Fall 2026"
        fmt = "8-Ball Open"
        for external_id, name, team in (("1", "Ann", our), ("2", "Bob", opp)):
            player = Player(external_id=external_id, name=name)
            db.add(player)
            db.flush()
            db.add(PlayerTeamHistory(
                player_id=player.id, team_external_id=team, session_name=session_name, is_current=True,
            ))
        db.add(Match(
            external_id="M1", session_name=session_name, format=fmt,
            home_team_id=our, away_team_id=opp, is_bye=False,
        ))
        db.commit()
        return db, our, opp, session_name, fmt

    def test_all_three_overrides_pin_the_exact_scope(self, tmp_path, monkeypatch):
        db, our, opp, session_name, fmt = self._seeded_db(tmp_path)
        monkeypatch.setattr(
            "scripts.build_captain_first_edge._configured_our_team_id", lambda: our,
        )
        try:
            scope = builder._live_scope(db, opp, session_name, fmt)
        finally:
            db.close()

        assert scope == {
            "our_team_id": our, "opponent_team_id": opp,
            "session_name": session_name, "format": fmt,
        }

    def test_a_pinned_scope_with_no_real_match_is_refused(self, tmp_path, monkeypatch):
        db, our, opp, session_name, fmt = self._seeded_db(tmp_path)
        monkeypatch.setattr(
            "scripts.build_captain_first_edge._configured_our_team_id", lambda: our,
        )
        try:
            with pytest.raises(BuildError):
                builder._live_scope(db, "999999", session_name, fmt)
        finally:
            db.close()

    def test_partial_overrides_at_the_function_level_are_rejected(self, tmp_path, monkeypatch):
        db, our, opp, session_name, fmt = self._seeded_db(tmp_path)
        monkeypatch.setattr(
            "scripts.build_captain_first_edge._configured_our_team_id", lambda: our,
        )
        try:
            with pytest.raises(BuildError):
                builder._live_scope(db, opp, session_name, None)
        finally:
            db.close()


class TestSourceDbFlagPolicy:
    def test_source_db_is_rejected_outside_live_mode(self):
        with pytest.raises(SystemExit):
            builder.main(["--mode", "fixture", "--source-db", "data/apa_tracker.db"])

    def test_source_db_and_resume_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            builder.main(["--mode", "live", "--source-db", "data/apa_tracker.db", "--resume"])

    def test_source_db_and_promote_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            builder.main(["--mode", "live", "--source-db", "data/apa_tracker.db", "--promote"])


class TestAcquireExisting:
    def test_a_missing_database_is_refused(self, tmp_path):
        with pytest.raises(BuildError):
            builder.acquire_existing(tmp_path / "nope.db")

    def test_an_empty_database_is_refused(self, tmp_path):
        empty = tmp_path / "empty.db"
        empty.write_bytes(b"")
        with pytest.raises(BuildError):
            builder.acquire_existing(empty)

    def test_a_real_file_is_used_as_is_no_network_no_token(self, tmp_path, monkeypatch):
        source = tmp_path / "already-acquired.db"
        source.write_bytes(b"some real bytes")
        monkeypatch.delenv(builder.TOKEN_ENV, raising=False)

        db_path, result = builder.acquire_existing(source)

        assert db_path == source
        assert result.status == "ok"
        assert "no rescrape" in result.detail

    def test_run_build_never_calls_acquire_live_when_source_db_is_given(self, monkeypatch, run_root, tmp_path):
        """The load-bearing guarantee: a source-db build must not touch the
        network or require a token, even if one happens to be unset."""
        monkeypatch.delenv(builder.TOKEN_ENV, raising=False)

        def _fail_if_called(resume=False):
            raise AssertionError("acquire_live() must not be called when --source-db is given")

        monkeypatch.setattr(builder, "acquire_live", _fail_if_called)
        # Scope selection from real config/matches is exercised elsewhere;
        # here we only need to prove the source-db wiring itself, using the
        # already-built fixture database as a stand-in "already-acquired" file.
        monkeypatch.setattr(builder, "_live_scope", lambda db, *a, **k: dict(FIXTURE_SCOPE))

        source = tmp_path / "source.db"
        shutil.copy2(builder.FIXTURE_DB, source)
        target = run_root / "source-db-test"

        completed = run_build(
            "live", target, run_root, source_db=source,
        )

        manifest = json.loads((completed / "demo_manifest.json").read_text(encoding="utf-8"))
        assert manifest["database_file"] == "source.db"
        assert (completed / "READY").is_file()


class TestLiveModeResume:
    def test_without_resume_seeds_from_production_and_syncs_incrementally(self, monkeypatch, tmp_path):
        monkeypatch.setenv(builder.TOKEN_ENV, "test-token")
        staging_db = tmp_path / "staged.db"
        staging_db.write_bytes(b"stale partial data")
        production_db = tmp_path / "production.db"

        from database.engine import create_db_engine
        create_db_engine({"database": {"path": str(production_db)}}).dispose()
        production_bytes = production_db.read_bytes()

        monkeypatch.setattr(builder, "LIVE_STAGING_DB", staging_db)
        monkeypatch.setattr(builder, "LIVE_PRODUCTION_DB", production_db)

        import scheduler.graphql_sync as sync_module

        seen_resume = {}

        def fake_run_division_wide(config_path, export=False, db_path=None, resume=False):
            seen_resume["value"] = resume
            seen_resume["file_existed_at_call_time"] = Path(db_path).exists()
            seen_resume["seed_matches_production"] = Path(db_path).read_bytes() == production_bytes
            return {"coverage_gaps": [], "division_wide": {
                "teams_ingested": 0, "matches_ingested": 0, "scored_matches_with_scoresheet": 0,
            }}

        monkeypatch.setattr(sync_module, "run_division_wide", fake_run_division_wide)

        _, result = builder.acquire_live(resume=False)

        assert seen_resume["value"] is True
        assert seen_resume["file_existed_at_call_time"] is True
        assert seen_resume["seed_matches_production"] is True
        assert "incremental seed" in result.detail

    def test_without_production_database_first_run_still_starts_clean(self, monkeypatch, tmp_path):
        monkeypatch.setenv(builder.TOKEN_ENV, "test-token")
        staging_db = tmp_path / "staged.db"
        staging_db.write_bytes(b"stale partial data")
        production_db = tmp_path / "missing-production.db"
        monkeypatch.setattr(builder, "LIVE_STAGING_DB", staging_db)
        monkeypatch.setattr(builder, "LIVE_PRODUCTION_DB", production_db)

        import scheduler.graphql_sync as sync_module

        seen_resume = {}

        def fake_run_division_wide(config_path, export=False, db_path=None, resume=False):
            seen_resume["value"] = resume
            seen_resume["file_existed_at_call_time"] = Path(db_path).exists()
            from database.engine import create_db_engine
            create_db_engine({"database": {"path": db_path}}).dispose()
            return {"coverage_gaps": [], "division_wide": {
                "teams_ingested": 0, "matches_ingested": 0, "scored_matches_with_scoresheet": 0,
            }}

        monkeypatch.setattr(sync_module, "run_division_wide", fake_run_division_wide)

        builder.acquire_live(resume=False)

        assert seen_resume["value"] is False
        assert seen_resume["file_existed_at_call_time"] is False

    def test_with_resume_an_existing_staging_file_is_preserved(self, monkeypatch, tmp_path):
        monkeypatch.setenv(builder.TOKEN_ENV, "test-token")
        staging_db = tmp_path / "staged.db"

        from database.engine import create_db_engine
        create_db_engine({"database": {"path": str(staging_db)}}).dispose()
        original_bytes = staging_db.read_bytes()
        monkeypatch.setattr(builder, "LIVE_STAGING_DB", staging_db)

        import scheduler.graphql_sync as sync_module

        seen_resume = {}

        def fake_run_division_wide(config_path, export=False, db_path=None, resume=False):
            seen_resume["value"] = resume
            seen_resume["file_existed_at_call_time"] = Path(db_path).exists()
            seen_resume["bytes_preserved"] = Path(db_path).read_bytes() == original_bytes
            return {"coverage_gaps": [], "division_wide": {
                "teams_ingested": 0, "matches_ingested": 0, "scored_matches_with_scoresheet": 0,
            }}

        monkeypatch.setattr(sync_module, "run_division_wide", fake_run_division_wide)

        builder.acquire_live(resume=True)

        assert seen_resume["value"] is True
        assert seen_resume["file_existed_at_call_time"] is True
        assert seen_resume["bytes_preserved"] is True


class TestLiveMode:
    def test_acquire_live_populates_player_h2h_advantage(self, monkeypatch, tmp_path):
        """A real live run surfaced this: build_lineups.py and Captain's
        Edge's Decision Engine both read player_h2h_advantage, but neither
        run_all_teams() nor run_division_wide() ever populate it -- only
        scripts/build_head_to_head.py does, and nothing called it for a
        live acquisition. Fixture mode never caught this because
        build_coherent_demo.py already calls it directly."""
        monkeypatch.setenv(builder.TOKEN_ENV, "test-token")
        staging_db = tmp_path / "staged.db"
        monkeypatch.setattr(builder, "LIVE_STAGING_DB", staging_db)

        from database.engine import create_db_engine
        from database.models import Match, Player, PlayerHeadToHead

        def fake_run_division_wide(config_path, export=False, db_path=None, resume=False):
            # acquire_live() deletes any existing staging file before this
            # call (fresh-scrape semantics), so the real ingestion has to
            # happen here, inside the mock, exactly as a real scrape would.
            engine = create_db_engine({"database": {"path": db_path}})
            with Session(engine) as seed:
                seed.add(Match(external_id="M1", session_name="S", format="8-Ball Open"))
                seed.flush()
                match = seed.query(Match).filter_by(external_id="M1").one()
                a = Player(external_id="A", name="Ann")
                b = Player(external_id="B", name="Bob")
                seed.add_all([a, b])
                seed.flush()
                seed.add(PlayerHeadToHead(
                    player_id=a.id, opponent_id=b.id, match_id=match.id,
                    own_skill_level=5, opponent_skill_level=4, result="W",
                    points_earned=3.0, format="8-Ball Open", session_name="S",
                ))
                seed.commit()
            engine.dispose()
            return {
                "coverage_gaps": [],
                "division_wide": {
                    "teams_ingested": 1, "matches_ingested": 1,
                    "scored_matches_with_scoresheet": 1,
                },
            }

        import scheduler.graphql_sync as sync_module
        monkeypatch.setattr(sync_module, "run_division_wide", fake_run_division_wide)

        builder.acquire_live()

        check_engine = create_db_engine({"database": {"path": str(staging_db)}})
        with Session(check_engine) as db:
            from database.models import PlayerH2HAdvantage
            count = db.query(PlayerH2HAdvantage).count()
        check_engine.dispose()
        assert count > 0

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
