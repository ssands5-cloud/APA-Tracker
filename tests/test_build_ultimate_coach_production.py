"""Safety tests for the offline Ultimate Coach production-candidate builder."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_ultimate_coach_production as builder


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_db(path):
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE fixture (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO fixture(value) VALUES ('stable')")
        conn.commit()
    finally:
        conn.close()
    return path


def _safe_payload():
    return {
        "players": [{"id": 1, "name": "Fixture Player"}],
        "evidence": [{"player_id": 1, "opponent_id": 2}],
        "counts": {"players": 1, "head_to_head_rows": 1, "all_games": 1},
        "trust": {"verified_identity_count": 1},
        "probability_publication": "FORBIDDEN",
        "matchup_probability": None,
        "predictive_confidence": None,
        "requires_live_apa_login": False,
        "database_mutated": False,
        "name_matching_used": False,
    }


def test_candidate_uses_snapshot_and_never_publishes_database(monkeypatch, tmp_path):
    source = _source_db(tmp_path / "ultimate.db")
    before = _hash(source)
    out = tmp_path / "candidate"

    monkeypatch.setattr(builder, "_build_payload", lambda snapshot: _safe_payload())
    monkeypatch.setattr(
        builder,
        "render",
        lambda payload, built_at: "<html><body>Ultimate Coach</body></html>",
    )

    completed = builder.build_candidate(source, out)

    assert completed == out.resolve()
    assert _hash(source) == before
    assert (out / builder.HTML_NAME).is_file()
    assert (out / builder.MANIFEST_NAME).is_file()
    assert (out / builder.READY_NAME).is_file()
    assert not (out / "build_snapshot.db").exists()

    manifest = json.loads((out / builder.MANIFEST_NAME).read_text(encoding="utf-8"))
    ready = json.loads((out / builder.READY_NAME).read_text(encoding="utf-8"))

    assert manifest["source_database_sha256"] == before
    assert manifest["safety"]["source_database_promoted"] is False
    assert manifest["safety"]["probability_publication"] == "FORBIDDEN"
    assert ready["manifest_sha256"] == builder._sha256(out / builder.MANIFEST_NAME)
    assert ready["html_sha256"] == builder._sha256(out / builder.HTML_NAME)


def test_candidate_refuses_probability_unlock_and_publishes_nothing(monkeypatch, tmp_path):
    source = _source_db(tmp_path / "ultimate.db")
    out = tmp_path / "candidate"
    unsafe = _safe_payload()
    unsafe["probability_publication"] = "ALLOWED"

    monkeypatch.setattr(builder, "_build_payload", lambda snapshot: unsafe)

    with pytest.raises(builder.CandidateError, match="probability_publication"):
        builder.build_candidate(source, out)

    assert not out.exists()


def test_candidate_refuses_empty_verified_player_surface(monkeypatch, tmp_path):
    source = _source_db(tmp_path / "ultimate.db")
    out = tmp_path / "candidate"
    empty = _safe_payload()
    empty["counts"] = {"players": 0, "head_to_head_rows": 1, "all_games": 1}

    monkeypatch.setattr(builder, "_build_payload", lambda snapshot: empty)

    with pytest.raises(builder.CandidateError, match="no selectable players"):
        builder.build_candidate(source, out)

    assert not out.exists()


def test_snapshot_detects_source_change_and_deletes_snapshot(monkeypatch, tmp_path):
    source = _source_db(tmp_path / "ultimate.db")
    destination = tmp_path / "snapshot.db"
    real_sha = builder._sha256
    calls = {"n": 0}

    def changing_sha(path):
        if path == source.resolve():
            calls["n"] += 1
            if calls["n"] == 2:
                return "changed-during-backup"
        return real_sha(path)

    monkeypatch.setattr(builder, "_sha256", changing_sha)

    with pytest.raises(builder.CandidateError, match="changed during snapshot"):
        builder._snapshot_sqlite(source.resolve(), destination)

    assert not destination.exists()


def test_candidate_is_not_published_if_ready_write_fails(monkeypatch, tmp_path):
    """READY must be written inside the private temp directory before publish.

    A failure at the READY write boundary must leave no public candidate
    directory behind. This catches any future reordering that publishes the
    temp directory first and only then attempts to create READY.
    """
    source = _source_db(tmp_path / "ultimate.db")
    out = tmp_path / "candidate"

    monkeypatch.setattr(builder, "_build_payload", lambda snapshot: _safe_payload())
    monkeypatch.setattr(
        builder,
        "render",
        lambda payload, built_at: "<html><body>Ultimate Coach</body></html>",
    )

    original_write_text = Path.write_text

    def fail_ready(self, *args, **kwargs):
        if self.name == builder.READY_NAME:
            raise OSError("simulated READY write failure")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_ready)

    with pytest.raises(OSError, match="simulated READY write failure"):
        builder.build_candidate(source, out)

    assert not out.exists(), "candidate must not become public before READY succeeds"
    assert not any(
        child.name.startswith(".uc-candidate-") for child in tmp_path.iterdir()
    ), "failed private build directory must be cleaned up"
