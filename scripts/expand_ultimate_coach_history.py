"""Expand Ultimate Coach history through every safely connected roster member."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from scraper.graphql_scraper import AccessTokenExpired, AccessTokenMissing
from scraper.historical_graph import HistoryGraphError, expand_historical_catalog
from scheduler.graphql_sync import load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = PROJECT_ROOT / "data" / "ultimate_coach_historical_catalog.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "ultimate_coach_historical_catalog_expanded.json"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "ultimate_coach_history_graph_report.json"

logger = logging.getLogger("expand_ultimate_coach_history")


def main(argv: list[str] | None = None, *, raise_auth: bool = False) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "apa_config.yaml"))
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.seed.is_file():
        logger.error("Seed historical catalog does not exist: %s", args.seed)
        return 1

    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    config = load_config(args.config)

    try:
        expanded, report = expand_historical_catalog(
            config,
            seed_catalog=seed,
            seed_catalog_path=args.seed,
            output_path=args.output,
            report_path=args.report,
            resume=args.resume,
        )
    except (AccessTokenMissing, AccessTokenExpired) as exc:
        if raise_auth:
            raise
        logger.error("%s", exc)
        return 1
    except (HistoryGraphError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    logger.info(
        "History graph expansion complete: %d session(s), %d division(s), "
        "%d member/league scope(s), %d source limitation(s)",
        expanded["counts"]["sessions"],
        expanded["counts"]["divisions"],
        report["counts"]["processed_member_league_scopes"],
        report["counts"]["source_limitations"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
