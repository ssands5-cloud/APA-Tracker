"""Build the self-contained offline Ultimate Coach Scout HTML."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from analytics.ultimate_coach_scout import build_scout_payload
from database.engine import create_db_engine
from ui.ultimate_coach_scout import render_ultimate_coach_scout

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_CATALOG = PROJECT_ROOT / "data" / "ultimate_coach_historical_catalog_expanded.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "ultimate_coach_scout.html"

REPORTS = {
    "history_graph": PROJECT_ROOT / "data" / "ultimate_coach_history_graph_report.json",
    "archive": PROJECT_ROOT / "data" / "ultimate_coach_archive_report.json",
    "player_enrichment": PROJECT_ROOT / "data" / "ultimate_coach_player_enrichment_report.json",
    "backtest": PROJECT_ROOT / "data" / "ultimate_coach_backtest_report.json",
}

logger = logging.getLogger("build_ultimate_coach_scout")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.db.is_file():
        logger.error("Ultimate Coach staging DB does not exist: %s", args.db)
        return 1

    catalog = _read_json(args.catalog) or {}
    reports = {
        name: value
        for name, path in REPORTS.items()
        if (value := _read_json(path)) is not None
    }

    engine = create_db_engine({"database": {"path": str(args.db)}}, create_tables=False)
    try:
        with Session(engine) as db:
            payload = build_scout_payload(db, catalog=catalog, reports=reports)
    finally:
        engine.dispose()

    html = render_ultimate_coach_scout(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    logger.info(
        "Ultimate Coach Scout written: %d player(s), %d canonical: %s",
        payload["counts"]["players"],
        payload["counts"]["canonical_players"],
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
