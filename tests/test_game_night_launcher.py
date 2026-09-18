from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
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
        our_team_id="13082948",
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
        launcher.run_game_night(
            stamp="20260918T000001Z", open_browser=False, our_team_id="13082948"
        )

    assert promoted == []


def test_checksum_failure_never_promotes_or_opens(tmp_path, monkeypatch):
    demo_root = tmp_path / "demo-runs"
    cockpit_root = tmp_path / "cockpit-runs"
    staging_db = tmp_path / "data" / "apa_tracker_regenerated.db"
    staging_db.parent.mkdir(parents=True)

    monkeypatch.setattr(launcher, "DEMO_RUN_ROOT", demo_root)
    monkeypatch.setattr(launcher, "COCKPIT_RUN_ROOT", cockpit_root)
    monkeypatch.setattr(launcher, "LIVE_STAGING_DB", staging_db)

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
            our_team_id="13082948",
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
            our_team_id="13082948",
        )

    assert exc.value.code == launcher.EXIT_PRESENTATION
    assert promoted == [staging_db]


def test_auto_selects_nearest_upcoming_match_across_current_teams(tmp_path):
    staging_db = tmp_path / "apa_tracker_regenerated.db"
    with sqlite3.connect(staging_db) as conn:
        conn.execute(
            """
            CREATE TABLE matches (
                external_id TEXT,
                home_team_id TEXT,
                away_team_id TEXT,
                home_team_name TEXT,
                away_team_name TEXT,
                match_date TEXT,
                is_bye INTEGER,
                is_scored INTEGER,
                is_finalized INTEGER
            )
            """
        )
        conn.executemany(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)",
            [
                (
                    "friday-match", "friday-team", "opponent-f",
                    "Friday Team", "Friday Opponent", "2026-09-18T19:00:00-06:00",
                ),
                (
                    "monday-match", "13082948", "opponent-m",
                    "Mark It Up", "Monday Opponent", "2026-09-21T19:00:00-06:00",
                ),
                (
                    "other-earlier", "not-ours", "opponent-x",
                    "Not Ours", "Other", "2026-09-18T18:00:00-06:00",
                ),
            ],
        )

    team_id, selected = launcher._select_game_night_team(
        staging_db,
        ["13082948", "friday-team"],
        now=datetime.fromisoformat("2026-09-17T18:00:00-06:00"),
    )

    assert team_id == "friday-team"
    assert selected["external_id"] == "friday-match"
    assert selected["match_date"] == "2026-09-18T19:00:00-06:00"
    assert selected["opponent_name"] == "Friday Opponent"


def test_multi_team_hub_builds_all_owned_teams_and_defaults_nearest(tmp_path, monkeypatch):
    demo_root = tmp_path / "demo-runs"
    cockpit_root = tmp_path / "cockpit-runs"
    staging_db = tmp_path / "data" / "apa_tracker_regenerated.db"
    staging_db.parent.mkdir(parents=True)

    monkeypatch.setattr(launcher, "DEMO_RUN_ROOT", demo_root)
    monkeypatch.setattr(launcher, "COCKPIT_RUN_ROOT", cockpit_root)
    monkeypatch.setattr(launcher, "LIVE_STAGING_DB", staging_db)
    monkeypatch.setattr(
        launcher,
        "_discover_viewer_teams",
        lambda: [
            {
                "team_id": "13082718",
                "team_name": "Brunch Ballers",
                "division_type": "EIGHT",
                "session_name": "Fall 2026",
            },
            {
                "team_id": "13082948",
                "team_name": "Mark It Up",
                "division_type": "EIGHT",
                "session_name": "Fall 2026",
            },
        ],
    )

    events: list[str] = []

    def fake_production_build(mode, run_dir, run_root, promote=False, resume=False, **kwargs):
        assert mode == "live"
        assert promote is False
        events.append("refresh")
        with sqlite3.connect(staging_db) as conn:
            conn.execute(
                """
                CREATE TABLE matches (
                    external_id TEXT,
                    home_team_id TEXT,
                    away_team_id TEXT,
                    home_team_name TEXT,
                    away_team_name TEXT,
                    match_date TEXT,
                    is_bye INTEGER,
                    is_scored INTEGER,
                    is_finalized INTEGER
                )
                """
            )
            conn.executemany(
                "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)",
                [
                    (
                        "sunday-match", "13082718", "opp-sun",
                        "Brunch Ballers", "Big Bank Theory", "2026-09-20T11:00:00-06:00",
                    ),
                    (
                        "monday-match", "13082948", "opp-mon",
                        "Mark It Up", "The Royals", "2026-09-21T19:00:00-06:00",
                    ),
                ],
            )

    def fake_cockpit_build(db_path, team_id, run_dir, run_root, **kwargs):
        assert db_path == staging_db
        assert run_root == cockpit_root / "game-night-20260918T010000Z" / "teams"
        events.append(f"cockpit:{team_id}")
        _write_bundle(run_dir, staging_db)

    def fake_promote(path):
        assert path == staging_db
        events.append("promote")

    opened: list[str] = []
    monkeypatch.setattr(launcher.production_builder, "run_build", fake_production_build)
    monkeypatch.setattr(launcher.cockpit_builder, "run_build", fake_cockpit_build)
    monkeypatch.setattr(launcher.production_builder, "promote_live_database", fake_promote)

    dashboard = launcher.run_game_night(
        stamp="20260918T010000Z",
        opener=lambda uri: opened.append(uri) or True,
    )

    assert events == [
        "refresh",
        "cockpit:13082718",
        "cockpit:13082948",
        "promote",
    ]
    expected = (
        cockpit_root / "game-night-20260918T010000Z" / "html" / "dashboard.html"
    ).resolve()
    assert dashboard == expected
    assert opened == [expected.as_uri()]

    hub = dashboard.read_text(encoding="utf-8")
    assert "My Team" in hub
    assert "Brunch Ballers" in hub
    assert "Mark It Up" in hub
    assert "13082718" in hub
    assert "13082948" in hub
    assert 'src="../teams/13082718/html/dashboard.html"' in hub

    run_dir = cockpit_root / "game-night-20260918T010000Z"
    hub_manifest = launcher.verify_game_night_hub(run_dir, launcher._sha256(staging_db))
    assert hub_manifest["selected_team_id"] == "13082718"
    assert hub_manifest["team_count"] == 2
    assert (run_dir / launcher.HUB_READY_NAME).is_file()


def test_multi_team_child_failure_never_promotes_or_opens(tmp_path, monkeypatch):
    demo_root = tmp_path / "demo-runs"
    cockpit_root = tmp_path / "cockpit-runs"
    staging_db = tmp_path / "data" / "apa_tracker_regenerated.db"
    staging_db.parent.mkdir(parents=True)

    monkeypatch.setattr(launcher, "DEMO_RUN_ROOT", demo_root)
    monkeypatch.setattr(launcher, "COCKPIT_RUN_ROOT", cockpit_root)
    monkeypatch.setattr(launcher, "LIVE_STAGING_DB", staging_db)
    monkeypatch.setattr(
        launcher,
        "_discover_viewer_teams",
        lambda: [
            {"team_id": "team-a", "team_name": "Team A", "division_type": "EIGHT", "session_name": "Fall"},
            {"team_id": "team-b", "team_name": "Team B", "division_type": "NINE", "session_name": "Fall"},
        ],
    )

    def fake_production_build(*args, **kwargs):
        with sqlite3.connect(staging_db) as conn:
            conn.execute(
                """
                CREATE TABLE matches (
                    external_id TEXT, home_team_id TEXT, away_team_id TEXT,
                    home_team_name TEXT, away_team_name TEXT, match_date TEXT,
                    is_bye INTEGER, is_scored INTEGER, is_finalized INTEGER
                )
                """
            )
            conn.execute(
                "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)",
                ("next", "team-a", "opp", "Team A", "Opponent", "2026-09-20T11:00:00-06:00"),
            )

    def fake_cockpit_build(db_path, team_id, run_dir, run_root, **kwargs):
        if team_id == "team-b":
            raise launcher.cockpit_builder.BuildError("team build failed", 11)
        _write_bundle(run_dir, staging_db)

    promoted: list[Path] = []
    opened: list[str] = []
    monkeypatch.setattr(launcher.production_builder, "run_build", fake_production_build)
    monkeypatch.setattr(launcher.cockpit_builder, "run_build", fake_cockpit_build)
    monkeypatch.setattr(
        launcher.production_builder,
        "promote_live_database",
        lambda path: promoted.append(path),
    )

    with pytest.raises(launcher.cockpit_builder.BuildError, match="team build failed"):
        launcher.run_game_night(
            stamp="20260918T010001Z",
            opener=lambda uri: opened.append(uri) or True,
        )

    assert promoted == []
    assert opened == []
    assert not (
        cockpit_root / "game-night-20260918T010001Z" / launcher.HUB_READY_NAME
    ).exists()


def test_hub_verification_rejects_tampered_child_dashboard(tmp_path):
    run_dir = tmp_path / "game-night-test"
    staging_db = tmp_path / "staging.db"
    staging_db.write_bytes(b"verified staging database")
    db_hash = launcher._sha256(staging_db)
    teams = [
        {"team_id": "team-a", "team_name": "Team A", "division_type": "EIGHT", "session_name": "Fall"},
        {"team_id": "team-b", "team_name": "Team B", "division_type": "NINE", "session_name": "Fall"},
    ]
    for team in teams:
        _write_bundle(run_dir / "teams" / team["team_id"], staging_db)

    launcher._write_team_hub(run_dir, teams, "team-a", db_hash)
    launcher.verify_game_night_hub(run_dir, db_hash)

    tampered = run_dir / "teams" / "team-b" / "html" / "dashboard.html"
    tampered.write_text("tampered", encoding="utf-8")

    with pytest.raises(launcher.GameNightError, match="checksum mismatch"):
        launcher.verify_game_night_hub(run_dir, db_hash)


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
