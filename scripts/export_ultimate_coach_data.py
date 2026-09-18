"""Export the canonical Ultimate Coach data contract to CSV + manifest.

These files are the shared raw-data layer for Excel/HTML/reporting. They are
views of SQLite, not a second source of truth.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from analytics.ultimate_coach_data_contract import build_contract
from database.engine import create_db_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_OUT = PROJECT_ROOT / "exports" / "ultimate_coach_data"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.db.is_file():
        print(f"Ultimate Coach staging DB does not exist: {args.db}")
        return 1

    engine = create_db_engine({"database": {"path": str(args.db)}}, create_tables=False)
    try:
        with Session(engine) as db:
            contract = build_contract(db)
    finally:
        engine.dispose()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in contract["tables"].items():
        _write_csv(args.out_dir / f"{name}.csv", rows)

    manifest = {
        "schema": contract["schema"],
        "database": str(args.db),
        "counts": contract["counts"],
        "notes": contract["notes"],
        "files": {
            name: f"{name}.csv"
            for name in contract["tables"]
        },
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        "Ultimate Coach data contract exported: "
        + ", ".join(f"{name}={count}" for name, count in contract["counts"].items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
