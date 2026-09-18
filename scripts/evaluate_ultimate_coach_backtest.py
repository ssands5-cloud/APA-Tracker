"""Build Ultimate Coach backtest examples and evaluate the skill-only baseline."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from sqlalchemy.orm import Session

from analytics.backtest_dataset import build_backtest_examples
from analytics.baseline_evaluation import evaluate_skill_only_baseline
from database.engine import create_db_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "ultimate_coach_backtest_report.json"

logger = logging.getLogger("evaluate_ultimate_coach_backtest")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.db.is_file():
        logger.error("Ultimate Coach staging DB does not exist: %s", args.db)
        return 1

    engine = create_db_engine({"database": {"path": str(args.db)}}, create_tables=False)
    try:
        with Session(engine) as db:
            examples = build_backtest_examples(db)
    finally:
        engine.dispose()

    evaluation = evaluate_skill_only_baseline(examples)
    report = {
        "schema": "ultimate-coach-backtest-v1",
        "database": str(args.db),
        "example_count": len(examples),
        "example_counts_by_format": {
            "EIGHT": sum(1 for row in examples if row.format == "EIGHT"),
            "NINE": sum(1 for row in examples if row.format == "NINE"),
        },
        "baseline_evaluation": evaluation,
        "examples": [asdict(row) for row in examples],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    logger.info(
        "Backtest report written: %d example(s), evaluated=%d, output=%s",
        len(examples),
        evaluation["overall"]["examples_evaluated"],
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
