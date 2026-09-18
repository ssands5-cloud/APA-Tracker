"""Train/evaluate research-only Ultimate Coach matchup candidates.

This command cannot activate a model or alter production. It writes only a
JSON research artifact containing chronological split counts, coefficients,
calibration parameters and final-test metrics.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from analytics.backtest_dataset import build_backtest_dataset
from analytics.matchup_candidate_model import train_candidate_models
from database.engine import create_db_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "ultimate_coach_candidate_model.json"

logger = logging.getLogger("train_ultimate_coach_candidate")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-train", type=int, default=200)
    parser.add_argument("--min-calibration", type=int, default=75)
    parser.add_argument("--min-test", type=int, default=75)
    parser.add_argument("--l2", type=float, default=1.0)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not args.db.is_file():
        logger.error("Ultimate Coach staging DB does not exist: %s", args.db)
        return 1

    engine = create_db_engine({"database": {"path": str(args.db)}}, create_tables=False)
    try:
        with Session(engine) as db:
            dataset = build_backtest_dataset(db)
    finally:
        engine.dispose()

    result = train_candidate_models(
        list(dataset.examples),
        min_train=args.min_train,
        min_calibration=args.min_calibration,
        min_test=args.min_test,
        l2=args.l2,
    )
    result["database"] = str(args.db)
    result["backtest_exclusions"] = dataset.exclusions
    result["backtest_example_count"] = len(dataset.examples)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    for format_name, report in result["formats"].items():
        logger.info(
            "%s candidate: %s train=%d calibration=%d test=%d",
            format_name,
            report["status"],
            report["split"]["train"],
            report["split"]["calibration"],
            report["split"]["test"],
        )
    logger.info("Research artifact written: %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
