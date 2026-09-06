"""Contracts for the shared production refresh boundary."""

from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import pipeline.exports as exports
import pipeline.refresh as refresh
from database.ingest import prune_h2h_advantage_not_in
from database.models import Base, Player, PlayerH2HAdvantage


@pytest.fixture
def engine(tmp_path):
    value = create_engine(f"sqlite:///{tmp_path / 'refresh.db'}")
    Base.metadata.create_all(value)
    try:
        yield value
    finally:
        value.dispose()


def test_finalize_rebuilds_before_publish_and_writes_hashed_manifest(
    engine, tmp_path, monkeypatch
):
    calls = []
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("current run", encoding="utf-8")
    monkeypatch.setattr(exports, "EXPORTS_DIR", tmp_path / "exports")

    def rebuild(_db):
        calls.append("rebuild")
        return {"matchups": 3, "h2h_advantage": 2}

    def publish(_config, _engine, *, captains=True):
        calls.append(("publish", captains))
        return [("artifact", str(artifact))]

    monkeypatch.setattr(refresh, "rebuild_derived", rebuild)
    monkeypatch.setattr(refresh, "publish", publish)

    counts, written = refresh.finalize({}, engine, export=True)

    assert calls == ["rebuild", ("publish", True)]
    assert counts == {"matchups": 3, "h2h_advantage": 2}
    assert [label for label, _ in written] == ["artifact", "refresh manifest"]

    manifest = json.loads((tmp_path / "exports" / refresh.MANIFEST_NAME).read_text())
    assert manifest["schema_version"] == 1
    assert manifest["run_id"]
    assert manifest["derived_counts"] == counts
    assert manifest["artifacts"] == [{
        "label": "artifact",
        "path": str(artifact.resolve()),
        "exists": True,
        "size_bytes": artifact.stat().st_size,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }]


def test_no_export_still_rebuilds_but_publishes_nothing(engine, monkeypatch):
    monkeypatch.setattr(refresh, "rebuild_derived", lambda _db: {"matchups": 4})

    def forbidden(*_args, **_kwargs):  # pragma: no cover - assertion is the test
        raise AssertionError("publish must not run when export=False")

    monkeypatch.setattr(refresh, "publish", forbidden)
    counts, written = refresh.finalize({}, engine, export=False)
    assert counts == {"matchups": 4}
    assert written == []


def test_failed_publish_does_not_replace_last_complete_manifest(
    engine, tmp_path, monkeypatch
):
    output = tmp_path / "exports"
    output.mkdir()
    manifest = output / refresh.MANIFEST_NAME
    manifest.write_text("last complete run\n", encoding="utf-8")
    monkeypatch.setattr(exports, "EXPORTS_DIR", output)
    monkeypatch.setattr(refresh, "rebuild_derived", lambda _db: {"matchups": 1})

    def fail(*_args, **_kwargs):
        raise RuntimeError("late exporter failed")

    monkeypatch.setattr(refresh, "publish", fail)
    with pytest.raises(RuntimeError, match="late exporter failed"):
        refresh.finalize({}, engine, export=True)
    assert manifest.read_text(encoding="utf-8") == "last complete run\n"


def test_missing_reported_artifact_cannot_be_marked_complete(
    engine, tmp_path, monkeypatch
):
    output = tmp_path / "exports"
    output.mkdir()
    manifest = output / refresh.MANIFEST_NAME
    manifest.write_text("last complete run\n", encoding="utf-8")
    monkeypatch.setattr(exports, "EXPORTS_DIR", output)
    monkeypatch.setattr(refresh, "rebuild_derived", lambda _db: {"matchups": 1})
    monkeypatch.setattr(
        refresh,
        "publish",
        lambda *_args, **_kwargs: [("missing", str(output / "missing.json"))],
    )

    with pytest.raises(FileNotFoundError, match="missing"):
        refresh.finalize({}, engine, export=True)
    assert manifest.read_text(encoding="utf-8") == "last complete run\n"


def test_h2h_pruner_removes_only_keys_without_raw_evidence(engine):
    with Session(engine) as db:
        player = Player(external_id="P1", name="Alice")
        first = Player(external_id="P2", name="Bob")
        second = Player(external_id="P3", name="Carol")
        db.add_all([player, first, second])
        db.flush()
        keep = PlayerH2HAdvantage(
            player_id=player.id,
            opponent_id=first.id,
            format="8-Ball",
            session_name="Fall 2026",
        )
        stale = PlayerH2HAdvantage(
            player_id=player.id,
            opponent_id=second.id,
            format="8-Ball",
            session_name="Fall 2026",
        )
        db.add_all([keep, stale])
        db.commit()

        removed = prune_h2h_advantage_not_in(
            db,
            {(player.id, first.id, "8-Ball", "Fall 2026")},
        )

        assert removed == 1
        assert db.query(PlayerH2HAdvantage).one().opponent_id == first.id


def test_empty_h2h_rebuild_prunes_every_stale_advantage(engine):
    with Session(engine) as db:
        player = Player(external_id="P1", name="Alice")
        opponent = Player(external_id="P2", name="Bob")
        db.add_all([player, opponent])
        db.flush()
        db.add(PlayerH2HAdvantage(
            player_id=player.id,
            opponent_id=opponent.id,
            format="8-Ball",
            session_name="Fall 2026",
        ))
        db.commit()

        counts = refresh.rebuild_analytics(db)

        assert counts["h2h_advantage"] == 0
        assert counts["h2h_pruned"] == 1
        assert db.query(PlayerH2HAdvantage).count() == 0
