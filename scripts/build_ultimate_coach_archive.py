"""Build/resume the Ultimate Coach league-wide historical staging archive."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from scraper.graphql_scraper import AccessTokenExpired, AccessTokenMissing
from scraper.historical_archive import ArchiveError, run_archive
from scheduler.graphql_sync import load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = PROJECT_ROOT / "data" / "ultimate_coach_historical_catalog.json"
DEFAULT_STAGING = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "ultimate_coach_archive_report.json"
DEFAULT_SEED = PROJECT_ROOT / "data" / "apa_tracker_career_staging.db"

logger = logging.getLogger("build_ultimate_coach_archive")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "apa_config.yaml"))
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--staging-db", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--seed-db", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = load_config(args.config)

    try:
        report = run_archive(
            config,
            catalog_path=args.catalog,
            staging_db=args.staging_db,
            report_path=args.report,
            seed_db=args.seed_db,
            resume=args.resume,
        )
    except (ArchiveError, AccessTokenMissing, AccessTokenExpired) as exc:
        logger.error("%s", exc)
        return 1

    logger.info(
        "Ultimate Coach archive crawl complete: %d division(s), %d matchup aggregate(s); %s",
        report["divisions_crawled"],
        report.get("matchups_rebuilt") or 0,
        args.staging_db,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
