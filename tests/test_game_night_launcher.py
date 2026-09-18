from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import run_game_night as launcher


def _write_bundle(run_dir: Path, staging_db: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    dashboard = run_dir / "html" / "dashboard.html"
    dashboard.parent.mkdir(parents=True, exist_ok=True)
    dashboard.write_text("<html><body>cockpit</body></html>", encoding="utf-8")

    manifest = {
        "schema_version": "coach-advantage-manifest-v1",
        "run_id": run_dir.name,
        "built_at": "2026-09-18T00:00:00+00:00",
        "database_sha256": launcher._sha256(staging_db),
        "artifacts": ["html/dashboard.html"],
        "artifact_hashes": {
            "html/dashboard.html": launcher._sha256(dashboard),
        },
        "promotable": True,
    }
    manifest_path = run_dir / launcher.cockpit_builder.MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    checksums = run_dir / launcher.cockpit_builder.CHECKSUMS_NAME
    checksums.write_text(
        f"{launcher._sha256(dashboard)}  html/dashboard.html\n"
        f"{launcher._sha256(manifest_path)}  {launcher.cockpit_builder.MANIFEST_NAME}\n",
        encoding="utf-8",
    )
    ready = {
        "schema_version": "coach-advantage-manifest-v1",
        "run_id": run_dir.name,
        "manifest_sha256": launcher._sha256(manifest_path),
    }
    (run_dir / launcher.cockpit_builder.READY_NAME).write_text(
        json.dumps(ready, indent=2), encoding="utf-8"
    )


def test_run_game_night_promotes_only_after_both_verified_builds(tmp_path, monkeypatch):
    demo_root = tmp_path / "demo-runs"
    cockpit_root = tmp_path / "cockpit-runs"
    staging_db = tmp_path / "data" / "apa_tracker_regenerated.db"
    staging_db.parent.mkdir(parents=True)

    monkeypatch.setattr(launcher, "DEMO_RUN_ROOT", demo_root)
    monkeypatch.setattr(launcher, "COCKPIT_RUN_ROOT", cockpit_root)
    monkeypatch.setattr(launcher, "LIVE_STAGING_DB", staging_db)
    monkeypatch.setattr(launcher, "_configured_our_team_id", lambda: "13082948")

    events: list[str] = []

    def fake_production_build(mode, run_dir, run_root, promote=False, resume=False, **kwargs):
        assert mode == "live"
        assert promote is False
        assert run_root == demo_root
        events.append("refresh")
        staging_db.write_bytes(b"fresh verified database")
        return run_dir

    def fake_cockpit_build(db_path, team_id, run_dir, run_root, **kwargs):
        assert db_path == staging_db
        assert team_id == "13082948"
        assert run_root == cockpit_root
        events.append("cockpit")
        _write_bundle(run_dir, staging_db)
        return run_dir

    def fake_promote(path):
        assert path == staging_db
        events.append("promote")

    opened: list[str] = []

    monkeypatch.setattr(launcher.production_builder, "run_build", fake_production_build)
    monkeypatch.setattr(launcher.cockpit_builder, "run_build", fake_cockpit_build)
    monkeypatch.setattr(launcher.production_builder, "promote_live_database", fake_promote)

    dashboard = launcher.run_game_night(
        stamp="20260918T000000Z",
        opener=lambda uri: opened.append(uri) or True,
    )

    assert events == ["refresh", "cockpit", "promote"]
    assert dashboard == (
        cockpit_root / "game-night-20260918T000000Z" / "html" / "dashboard.html"
    ).resolve()
    assert opened == [dashboard.as_uri()]


def test_cockpit_failure_never_promotes(tmp_path, monkeypatch):
    demo_root = tmp_path / "demo-runs"
    cockpit_root = tmp_path / "cockpit-runs"
    staging_db = tmp_path / "data" / "apa_tracker_regenerated.db"
    staging_db.parent.mkdir(parents=True)

    monkeypatch.setattr(launcher, "DEMO_RUN_ROOT", demo_root)
    monkeypatch.setattr(launcher, "COCKPIT_RUN_ROOT", cockpit_root)
    monkeypatch.setattr(launcher, "LIVE_STAGING_DB", staging_db)
    monkeypatch.setattr(launcher, "_configured_our_team_id", lambda: "13082948")

    def fake_production_build(*args, **kwargs):
        staging_db.write_bytes(b"fresh verified database")

    def fake_cockpit_build(*args, **kwargs):
        raise launcher.cockpit_builder.BuildError("render failed", 11)

    promoted: list[Path] = []
    monkeypatch.setattr(launcher.production_builder, "run_build", fake_production_build)
    monkeypatch.setattr(launcher.cockpit_builder, "run_build", fake_cockpit_build)
    monkeypatch.setattr(
        launcher.production_builder,
        "promote_live_database",
        lambda path: promoted.append(path),
    )

    with pytest.raises(launcher.cockpit_builder.BuildError):
        launcher.run_game_night(stamp="20260918T000001Z", open_browser=False)

    assert promoted == []


def test_checksum_failure_never_promotes_or_opens(tmp_path, monkeypatch):
    demo_root = tmp_path / "demo-runs"
    cockpit_root = tmp_path / "cockpit-runs"
    staging_db = tmp_path / "data" / "apa_tracker_regenerated.db"
    staging_db.parent.mkdir(parents=True)

    monkeypatch.setattr(launcher, "DEMO_RUN_ROOT", demo_root)
    monkeypatch.setattr(launcher, "COCKPIT_RUN_ROOT", cockpit_root)
    monkeypatch.setattr(launcher, "LIVE_STAGING_DB", staging_db)
    monkeypatch.setattr(launcher, "_configured_our_team_id", lambda: "13082948")

    def fake_production_build(*args, **kwargs):
        staging_db.write_bytes(b"fresh verified database")

    def fake_cockpit_build(db_path, team_id, run_dir, run_root, **kwargs):
        _write_bundle(run_dir, staging_db)
        (run_dir / "html" / "dashboard.html").write_text("tampered", encoding="utf-8")

    promoted: list[Path] = []
    opened: list[str] = []
    monkeypatch.setattr(launcher.production_builder, "run_build", fake_production_build)
    monkeypatch.setattr(launcher.cockpit_builder, "run_build", fake_cockpit_build)
    monkeypatch.setattr(
        launcher.production_builder,
        "promote_live_database",
        lambda path: promoted.append(path),
    )

    with pytest.raises(launcher.GameNightError, match="checksum mismatch"):
        launcher.run_game_night(
            stamp="20260918T000002Z",
            opener=lambda uri: opened.append(uri) or True,
        )

    assert promoted == []
    assert opened == []


def test_browser_failure_happens_only_after_verified_promotion(tmp_path, monkeypatch):
    demo_root = tmp_path / "demo-runs"
    cockpit_root = tmp_path / "cockpit-runs"
    staging_db = tmp_path / "data" / "apa_tracker_regenerated.db"
    staging_db.parent.mkdir(parents=True)

    monkeypatch.setattr(launcher, "DEMO_RUN_ROOT", demo_root)
    monkeypatch.setattr(launcher, "COCKPIT_RUN_ROOT", cockpit_root)
    monkeypatch.setattr(launcher, "LIVE_STAGING_DB", staging_db)
    monkeypatch.setattr(launcher, "_configured_our_team_id", lambda: "13082948")

    def fake_production_build(*args, **kwargs):
        staging_db.write_bytes(b"fresh verified database")

    def fake_cockpit_build(db_path, team_id, run_dir, run_root, **kwargs):
        _write_bundle(run_dir, staging_db)

    promoted: list[Path] = []
    monkeypatch.setattr(launcher.production_builder, "run_build", fake_production_build)
    monkeypatch.setattr(launcher.cockpit_builder, "run_build", fake_cockpit_build)
    monkeypatch.setattr(
        launcher.production_builder,
        "promote_live_database",
        lambda path: promoted.append(path),
    )

    with pytest.raises(launcher.GameNightError) as exc:
        launcher.run_game_night(
            stamp="20260918T000003Z",
            opener=lambda uri: False,
        )

    assert exc.value.code == launcher.EXIT_PRESENTATION
    assert promoted == [staging_db]


def test_browser_login_handoff_keeps_token_in_process_only(monkeypatch):
    from tools import capture_apa_graphql

    seen: list[tuple[list[str], str | None]] = []
    monkeypatch.delenv("APA_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(
        launcher,
        "main",
        lambda argv: seen.append((argv, os.environ.get("APA_ACCESS_TOKEN"))) or 0,
    )

    capture_apa_graphql._run_game_night("secret-token")

    assert seen == [([], "secret-token")]
    assert "APA_ACCESS_TOKEN" not in os.environ
