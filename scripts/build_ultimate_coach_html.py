"""Build the standalone offline Ultimate Coach Scout & Compare HTML."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from analytics.ultimate_coach_cockpit_identity_bridge import build_verified_cockpit_payload
from database.engine import create_db_engine
from ui.ultimate_coach import render

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "ultimate_coach.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if not args.db.is_file():
        print(f"Ultimate Coach staging DB does not exist: {args.db}")
        return 1

    engine = create_db_engine({"database": {"path": str(args.db)}}, create_tables=False)
    try:
        with Session(engine) as db:
            payload = build_verified_cockpit_payload(db)
    finally:
        engine.dispose()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    html = render(\n        payload,\n        built_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),\n        consume_evidence=True,\n    )
    args.output.write_text(html, encoding="utf-8")
    print(
        f"Ultimate Coach HTML written: {payload['counts']['players']} players, "
        f"{payload['counts']['head_to_head_rows']} evidence rows -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
