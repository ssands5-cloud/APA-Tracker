"""Run the pipeline: fixtures -> SQLite -> exports.

    python -m pipeline                 # ingest + every export
    python -m pipeline --ingest-only   # stop after the database
    python -m pipeline --no-captains   # skip Captain's Edge and lineup artifacts

Step 1 of the whole run (the scrape itself) is deliberately NOT here --
`scraper/full_auto_scrape.py` is contract-bound and owns that. This starts
where fixture generation ends.
"""

from __future__ import annotations

import argparse
import logging
import sys

import env_loader  # noqa: F401  -- loads .env before anything reads it

from database.engine import create_db_engine
from scheduler.graphql_sync import load_config
from sqlalchemy.orm import Session

from pipeline.fixtures import FixtureStore
from pipeline.ingest import run as ingest_run
from pipeline.refresh import finalize

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixture-backed APA ingest pipeline.")
    parser.add_argument("--fixtures", help="fixture root (default: scraper/sanitized_fixtures)")
    parser.add_argument("--config", default="apa_config.yaml")
    parser.add_argument("--ingest-only", action="store_true", help="stop after the database")
    parser.add_argument("--no-captains", action="store_true", help="skip Captain's Edge")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        store = FixtureStore(args.fixtures).load()
    except FileNotFoundError as exc:
        print(f"\n{exc}\n")
        return 1

    if not store.count:
        print("\nNo usable fixtures found. Run the scraper first.\n")
        return 1

    config = load_config(args.config)
    engine = create_db_engine(config)

    with Session(engine) as db:
        counts = ingest_run(db, store, refresh_derived=False)

    # The same committed-row boundary used by scheduled/live production.
    derived, written = finalize(
        config,
        engine,
        export=not args.ingest_only,
        captains=not args.no_captains,
    )
    counts.update(derived)

    print("\nIngest complete:")
    for key in sorted(counts):
        print(f"  {key:16} {counts[key]}")

    if args.ingest_only:
        return 0
    print("\nExports written:")
    for label, path in written:
        print(f"  {label:16} {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
