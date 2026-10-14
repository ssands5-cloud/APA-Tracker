import json
import sqlite3

import pytest

from scripts import repair_ultimate_coach_duplicate_rows as repair


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, "check_output_root", lambda path, repo: path)
    path = tmp_path / "source.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE player_matches (id INTEGER PRIMARY KEY, player_id INTEGER, match_id INTEGER, "
                   "result TEXT, skill_level INTEGER, future_column TEXT)")
        db.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY, recorded TEXT)")
        db.execute("INSERT INTO matches VALUES (1, 'preserved')")
        db.executemany("INSERT INTO player_matches VALUES (?, ?, ?, ?, ?, ?)", [
            (1, 1, 10, "W", 5, "same"), (2, 1, 10, "W", 5, "same"), (3, 1, 10, "W", 5, "same"),
            (4, 2, 10, "L", 4, "other"),
            (5, 1, None, "W", 5, "historical"), (6, 1, None, "W", 5, "historical"),
        ])
    return path


def test_copy_repairs_exact_rows_and_preserves_source_history_and_report(source, tmp_path):
    source_report = source.with_name("refresh_report.json")
    source_report.write_text(json.dumps({"coverage": "partial", "gaps": ["not refreshed here"]}))
    before, report_before = source.read_bytes(), source_report.read_bytes()
    output = tmp_path / "candidate"

    result = repair.repair_copy(source, output)

    assert source.read_bytes() == before and source_report.read_bytes() == report_before
    assert result["source_sha256_before"] == result["source_sha256_after"]
    assert result["accepted_current_data"] is False
    assert result["redundant_rows"] == 2
    assert result["repairs"][0]["kept_row_pk"] == 1
    assert result["repairs"][0]["removed_row_pks"] == [2, 3]
    assert result["compared_columns"] == ["player_id", "match_id", "result", "skill_level", "future_column"]
    with sqlite3.connect(output / "ultimate_coach_staging.db") as db:
        assert db.execute("SELECT id FROM player_matches ORDER BY id").fetchall() == [(1,), (4,), (5,), (6,)]
        assert db.execute("SELECT * FROM matches").fetchall() == [(1, "preserved")]
    assert not (output / "refresh_report.json").exists()
    saved = json.loads((output / "duplicate_repair_report.json").read_text())
    assert saved["candidate_sha256"] == repair.digest(output / "ultimate_coach_staging.db")
    assert saved["source_refresh_report_sha256"] == repair.digest(source_report)


def test_conflicting_new_column_refuses_every_repair_before_output_creation(source, tmp_path):
    with sqlite3.connect(source) as db:
        db.execute("UPDATE player_matches SET future_column='conflicting evidence' WHERE id=3")
    before = source.read_bytes()
    output = tmp_path / "candidate"
    assert repair.inspect_database(source)["conflict_groups"] == 1
    with pytest.raises(repair.RepairRefused, match="Conflicting"):
        repair.repair_copy(source, output)
    assert source.read_bytes() == before and not output.exists()


def test_existing_candidate_is_never_overwritten(source, tmp_path):
    output = tmp_path / "candidate"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep")
    with pytest.raises(repair.RepairRefused, match="already exists"):
        repair.repair_copy(source, output)
    assert sentinel.read_text() == "keep"
    assert list(output.iterdir()) == [sentinel]


def test_declared_references_require_a_remapping_plan(source, tmp_path):
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE evidence_notes (row_id INTEGER REFERENCES player_matches(id))")
    output = tmp_path / "candidate"
    with pytest.raises(repair.RepairRefused, match="remapping"):
        repair.repair_copy(source, output)
    assert not output.exists()


def test_nonempty_wal_refuses_copy(source, tmp_path):
    wal = source.with_name(source.name + "-wal")
    wal.write_bytes(b"synthetic writer activity")
    with pytest.raises(repair.RepairRefused, match="WAL"):
        repair.repair_copy(source, tmp_path / "candidate")


def test_source_hash_change_cannot_yield_a_success_report(source, tmp_path, monkeypatch):
    real_digest, count = repair.digest, 0

    def changing_digest(path):
        nonlocal count
        if path == source:
            count += 1
            if count == 2:
                return "different-source-hash"
        return real_digest(path)

    monkeypatch.setattr(repair, "digest", changing_digest)
    output = tmp_path / "candidate"
    with pytest.raises(repair.RepairRefused, match="Source changed"):
        repair.repair_copy(source, output)
    assert not (output / "duplicate_repair_report.json").exists()


def test_boundary_refusal_happens_before_any_output(source, tmp_path, monkeypatch):
    def refuse(path, repo):
        raise RuntimeError("boundary refused")

    monkeypatch.setattr(repair, "check_output_root", refuse)
    output = tmp_path / "candidate"
    with pytest.raises(RuntimeError, match="boundary"):
        repair.repair_copy(source, output)
    assert not output.exists()


def test_inspection_cli_prints_only_aggregate_counts_and_does_not_write(source, capsys):
    before = source.read_bytes()
    assert repair.main(["--source-db", str(source)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "duplicate_groups": 1, "exact_groups": 1, "conflict_groups": 0, "redundant_rows": 2,
    }
    assert source.read_bytes() == before
