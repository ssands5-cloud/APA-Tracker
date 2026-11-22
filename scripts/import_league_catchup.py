"""Import saved League Catch-up scoresheets into a NEW copy of the archive DB.

Offline: never contacts APA and never writes the source archive. Replays
scheduler.graphql_sync.sync_division_wide against the files saved by
tools/league_catchup.py, only for divisions that hold played matches the
archive has no games for. Writes a JSON report next to the new database.

Usage:
  python scripts/import_league_catchup.py --dry-run
  python scripts/import_league_catchup.py --out <new.db>
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.league_catchup_import import CatchupImportError, run_import  # noqa: E402


def main_checkout() -> Path:
    for parent in [REPO, *REPO.parents]:
        if parent.name == ".worktrees":
            return parent.parent
    return REPO


MAIN = main_checkout()
LIVE_DATA = MAIN.parent / "APA-Tracker-Ultimate-Coach-Live" / "data"
CATCHUP = MAIN / "tmp" / "ultimate-coach-release"
DEFAULT_SOURCE = LIVE_DATA / "ultimate_coach_staging.db"
DEFAULT_CATALOG = LIVE_DATA / "ultimate_coach_historical_catalog_expanded.json"
DEFAULT_STORES = [CATCHUP / "league-catchup", CATCHUP / "catchup-20261112"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=Path, help="new database file to create (must not exist)")
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    ap.add_argument("--store", type=Path, action="append",
                    help="catch-up store, newest first (repeatable); defaults to league-catchup then catchup-20261112")
    ap.add_argument("--since", default="2024-01-01")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="continue an interrupted import into the existing --out file")
    ap.add_argument("--report", type=Path, help="report path (default: <out>.report.json)")
    args = ap.parse_args()
    if not args.dry_run and not args.out:
        ap.error("--out is required unless --dry-run")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        report = run_import(source_db=args.source_db, out_db=args.out or Path("unused.db"),
                            catalog_path=args.catalog, stores=args.store or DEFAULT_STORES,
                            since=args.since, today=args.today, dry_run=args.dry_run,
                            resume=args.resume)
    except CatchupImportError as exc:
        print(f"IMPORT STOPPED: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, indent=1, sort_keys=True)
    if args.dry_run:
        print(json.dumps(report["pending_before"], indent=1))
        return 0
    report_path = args.report or args.out.with_suffix(".report.json")
    report_path.write_text(text + "\n", encoding="utf-8")
    summary = {k: report.get(k) for k in ("status", "problems", "pending_before", "pending_after",
                                          "counts_delta", "existing_games_unchanged", "source_unchanged",
                                          "out_quick_check", "matchups_rebuilt")}
    print(json.dumps(summary, indent=1))
    print(f"report: {report_path}")
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
