"""Audit Ultimate Coach staging identity provenance without changing the DB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy.orm import Session

from analytics.ultimate_coach_data_contract import build_contract
from analytics.ultimate_coach_identity_namespace_audit import audit_identity_namespace
from database.engine import create_db_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "ultimate_coach_identity_namespace_audit.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    if not args.db.is_file():
        print(f"Ultimate Coach staging DB does not exist: {args.db}")
        return 1

    engine = create_db_engine({"database": {"path": str(args.db)}}, create_tables=False)
    try:
        with Session(engine) as db:
            contract = build_contract(db)
            report = audit_identity_namespace(contract)
    finally:
        engine.dispose()

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    counts = report["counts"]
    print(
        "Identity namespace audit complete: "
        f"games={counts['all_games_rows']}, "
        f"verified_games={counts['identity_verified_games']}, "
        f"quarantined_games={counts['quarantined_games']}, "
        f"suspect_participants={counts['suspect_participants']}, "
        f"indeterminate_participants={counts['indeterminate_participants']}, "
        f"structural_issues={counts['structural_issues']}"
    )
    print(f"Report: {args.report}")
    print("Read-only audit. No database rows were changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
