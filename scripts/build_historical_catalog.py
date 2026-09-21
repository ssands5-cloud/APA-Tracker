"""Write the Ultimate Coach historical catalog as sanitized JSON.

This command is discovery only. It never modifies production/staging databases
and never fetches rosters, schedules, match scoresheets, or player PII beyond
the ids/names already returned by the catalog operations.

Authentication uses the repository's normal APA_ACCESS_TOKEN mechanism.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from scraper.graphql_scraper import AccessTokenExpired, AccessTokenMissing, fetch_dashboard_teams
from scraper.historical_catalog import build_historical_catalog
from scheduler.graphql_sync import load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "ultimate_coach_historical_catalog.json"

logger = logging.getLogger("build_historical_catalog")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "apa_config.yaml"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config = load_config(args.config)
    try:
        viewer = fetch_dashboard_teams(config)
        member_id = viewer.get("id")
        if not member_id:
            raise RuntimeError("dashboardTeams returned no authenticated viewer id")
        report = build_historical_catalog(config, int(member_id))
    except (AccessTokenMissing, AccessTokenExpired, RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    logger.info(
        "Historical catalog written: %d alias(es), %d session(s), %d division(s), "
        "%d source limitation(s): %s",
        report["counts"]["aliases"],
        report["counts"]["sessions"],
        report["counts"]["divisions"],
        len(report["source_limitations"]),
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
