"""Build the standalone offline Ultimate Coach Excel companion workbook.

Derives from the same build_verified_cockpit_payload() output as the
standalone HTML (scripts/build_ultimate_coach_html.py), so the two cannot
silently disagree about who is a verified player or which games count as
evidence -- see ui/export_excel_ultimate_coach.py for the workbook design.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from analytics.ultimate_coach_cockpit_identity_bridge import build_verified_cockpit_payload
from analytics.ultimate_coach_match_day import load_match_day_settings
from database.engine import create_db_engine
from ui.export_excel_ultimate_coach import write_workbook

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "ultimate_coach.xlsx"
DEFAULT_CONFIG = PROJECT_ROOT / "apa_config.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    if not args.db.is_file():
        print(f"Ultimate Coach staging DB does not exist: {args.db}")
        return 1

    settings = load_match_day_settings(args.config)
    engine = create_db_engine({"database": {"path": str(args.db)}}, create_tables=False)
    try:
        with Session(engine) as db:
            payload = build_verified_cockpit_payload(db, match_day_timezone=settings.timezone)
    finally:
        engine.dispose()

    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    output_path = write_workbook(
        payload, args.output, built_at=built_at, source_db=args.db.name,
        viewer_member_external_id=settings.viewer_member_external_id,
        viewer_card_number=settings.viewer_card_number,
    )
    print(
        f"Ultimate Coach Excel written: {payload['counts']['players']} players, "
        f"{payload['counts']['head_to_head_rows']} evidence rows -> {output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
