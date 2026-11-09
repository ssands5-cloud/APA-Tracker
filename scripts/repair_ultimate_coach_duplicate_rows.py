"""Inspect duplicate score rows, or repair exact duplicates in a NEW database copy.

This is an offline candidate repair, not a refresh or production promotion.
It never changes the source or rewrites refresh coverage. Conflicting rows
are refused; the private repair report maps every removed row to its survivor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.repo_boundary import check_output_root

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class RepairRefused(RuntimeError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def inspect_database(source: Path) -> dict:
    """Compare every stored column except row id; never guess between conflicts."""
    with closing(read_only(source)) as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(player_matches)")]
        if not {"id", "player_id", "match_id"}.issubset(columns):
            raise RepairRefused("The source lacks the expected player_matches keys.")
        fields = [name for name in columns if name != "id"]
        groups = db.execute(
            "SELECT player_id, match_id FROM player_matches "
            "WHERE player_id IS NOT NULL AND match_id IS NOT NULL "
            "GROUP BY player_id, match_id HAVING COUNT(*) > 1 "
            "ORDER BY player_id, match_id"
        ).fetchall()
        repairs, conflicts = [], []
        selection = ", ".join(quote(name) for name in ["id", *fields])
        for player, match in groups:
            rows = db.execute(
                f"SELECT {selection} FROM player_matches WHERE player_id=? AND match_id=? ORDER BY id",
                (player, match),
            ).fetchall()
            if any(row[1:] != rows[0][1:] for row in rows[1:]):
                conflicts.append({"player_pk": player, "match_pk": match, "row_pks": [r[0] for r in rows]})
            else:
                repairs.append({
                    "player_pk": player, "match_pk": match, "kept_row_pk": rows[0][0],
                    "removed_row_pks": [r[0] for r in rows[1:]],
                    "comparison_sha256": hashlib.sha256(repr(rows[0][1:]).encode()).hexdigest().upper(),
                })
        return {
            "duplicate_groups": len(groups), "exact_groups": len(repairs),
            "conflict_groups": len(conflicts), "redundant_rows": sum(len(r["removed_row_pks"]) for r in repairs),
            "compared_columns": fields, "repairs": repairs, "conflicts": conflicts,
        }


def table_counts(db: sqlite3.Connection) -> dict[str, int]:
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {table: db.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()[0] for table in tables}


def repair_copy(source: Path, output: Path) -> dict:
    source, output = Path(source), Path(output)
    if not source.is_file():
        raise RepairRefused("Source database does not exist.")
    if Path(str(source) + "-wal").exists() and Path(str(source) + "-wal").stat().st_size:
        raise RepairRefused("Source has a nonempty WAL; wait for the writer to close/checkpoint it.")
    check_output_root(output, PROJECT_ROOT)
    if output.exists():
        raise RepairRefused("Output already exists; no existing candidate will be overwritten.")
    before_hash = digest(source)
    inspection = inspect_database(source)
    if inspection["conflict_groups"]:
        raise RepairRefused("Conflicting duplicate rows exist; no repaired copy was created.")
    with closing(read_only(source)) as db:
        for table in table_counts(db):
            if any(row[2] == "player_matches" for row in db.execute(f"PRAGMA foreign_key_list({quote(table)})")):
                raise RepairRefused("A table references player_matches row IDs; a remapping plan is required.")

    check_output_root(output, PROJECT_ROOT)
    output.mkdir(parents=True, exist_ok=False)
    candidate = output / "ultimate_coach_staging.db"
    report_path = output / "duplicate_repair_report.json"
    check_output_root(candidate, PROJECT_ROOT)
    with closing(read_only(source)) as original, closing(sqlite3.connect(candidate)) as db:
        original.backup(db)
        if inspect_database(candidate) != inspection:
            raise RepairRefused("The source changed while its repair plan was copied; candidate is unaccepted.")
        before_counts = table_counts(db)
        check_output_root(candidate, PROJECT_ROOT)
        with db:
            for repair in inspection["repairs"]:
                db.executemany("DELETE FROM player_matches WHERE id=?", [(pk,) for pk in repair["removed_row_pks"]])
        after_counts = table_counts(db)
        expected = dict(before_counts)
        expected["player_matches"] -= inspection["redundant_rows"]
        if after_counts != expected or inspect_database(candidate)["duplicate_groups"]:
            raise RepairRefused("Candidate verification failed; no refresh or release is accepted.")
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RepairRefused("Candidate SQLite integrity check failed.")
    after_hash = digest(source)
    wal = Path(str(source) + "-wal")
    if after_hash != before_hash or (wal.exists() and wal.stat().st_size):
        raise RepairRefused("Source changed during repair; candidate must remain unaccepted.")

    source_report = source.with_name("refresh_report.json")
    report = {
        "schema": "ultimate-coach-duplicate-copy-repair-v1",
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "source_database": str(source.resolve()), "source_sha256_before": before_hash,
        "source_sha256_after": after_hash, "source_unchanged": True,
        "source_refresh_report_sha256": digest(source_report) if source_report.is_file() else None,
        "candidate_database": str(candidate.resolve()), "candidate_sha256": digest(candidate),
        "accepted_current_data": False,
        "note": "Offline exact-duplicate repair only. Existing refresh gaps were not re-fetched or resolved; "
                "this report is not a refresh_report.json and does not authorize promotion.",
        "before_counts": before_counts, "after_counts": after_counts, **inspection,
    }
    check_output_root(report_path, PROJECT_ROOT)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, help="Create a new private candidate folder; omit for inspection only.")
    args = parser.parse_args(argv)
    try:
        result = repair_copy(args.source_db, args.out_dir) if args.out_dir else inspect_database(args.source_db)
    except (RepairRefused, sqlite3.Error, OSError, RuntimeError) as exc:
        print(f"Refused: {type(exc).__name__}: {exc}")
        return 2
    print(json.dumps({key: result[key] for key in ("duplicate_groups", "exact_groups", "conflict_groups", "redundant_rows")}))
    if args.out_dir:
        print("New offline candidate created; accepted_current_data=false. Repair mapping stays local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
