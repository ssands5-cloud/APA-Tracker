"""Enrich every safely resolvable Ultimate Coach player with real APA lifetime stats."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from database.engine import create_db_engine
from scraper.graphql_scraper import AccessTokenExpired, AccessTokenMissing
from scraper.player_enrichment import EnrichmentError, enrich_all_players
from scheduler.graphql_sync import load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = PROJECT_ROOT / "data" / "ultimate_coach_historical_catalog.json"
DEFAULT_STAGING = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "ultimate_coach_player_enrichment_report.json"

logger = logging.getLogger("enrich_ultimate_coach_players")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "apa_config.yaml"))
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--staging-db", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.staging_db.is_file():
        logger.error("Ultimate Coach staging DB does not exist: %s", args.staging_db)
        return 1
    if not args.catalog.is_file():
        logger.error("Historical catalog does not exist: %s", args.catalog)
        return 1

    config = load_config(args.config)
    config.setdefault("database", {})["path"] = str(args.staging_db)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))

    engine = create_db_engine(config)
    try:
        with Session(engine) as db:
            try:
                report = enrich_all_players(
                    config,
                    db,
                    catalog=catalog,
                    catalog_path=args.catalog,
                    staging_db=args.staging_db,
                    report_path=args.report,
                    resume=args.resume,
                )
            except (EnrichmentError, AccessTokenMissing, AccessTokenExpired) as exc:
                logger.error("%s", exc)
                return 1
    finally:
        engine.dispose()

    logger.info(
        "Player enrichment complete: %d player/league scope(s), %d format stat row(s), "
        "%d unresolved scope(s)",
        report["counts"]["player_league_scopes_completed"],
        report["counts"]["league_stat_format_rows_written"],
        report["counts"]["unresolved_scopes"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
