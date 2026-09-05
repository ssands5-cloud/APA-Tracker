"""End-to-end APA run: scrape -> ingest -> exports -> tests.

Step 1 shells out, because the scraper drives a real browser and is contract-
bound (see README-scraper.md); it owns its own process. Steps 2-4 are
imported and called directly rather than shelled out: the previous version
ran `python pipeline/normalize_fixtures.py`, `pipeline/build_sqlite.py`,
`pipeline/build_excel.py`, `demo/build_demo.py` and `demo/render_demo_html.py`
-- five files that have never existed in this repository. Every run died at
step 2, and the failure looked like a missing file rather than a missing
design.

Usage:
    python pipeline_run_all.py                # everything
    python pipeline_run_all.py --skip-scrape  # reuse existing fixtures
    python pipeline_run_all.py --skip-tests
"""

import env_loader  # noqa: F401,E402  -- loads .env before anything else

import argparse
import subprocess
import sys
from pathlib import Path

# The directory this file actually lives in. An earlier version used
# .parent.parent, which resolved one level ABOVE the repo, so every command it
# built pointed outside the project.
ROOT = Path(__file__).resolve().parent


def run(cmd: list[str], label: str) -> None:
    """Run a step as a list, never a shell string.

    shell=True with an interpolated path split "APA Tracker Scorekeeper" at
    the space and reported `can't open file 'C:\\Users\\ssand\\Desktop\\APA'`.
    A list argv has no quoting rules to get wrong.
    """
    print(f"\n=== {label} ===")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"FAILED: {label}")
        sys.exit(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-scrape", action="store_true",
                        help="reuse the fixtures already on disk")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    # 1. Scrape the live league into fixtures. Owns its own process because it
    #    drives a browser and completes an interactive consent step.
    if args.skip_scrape:
        print("\n=== 1. Scrape: SKIPPED (using existing fixtures) ===")
    else:
        run([sys.executable, str(ROOT / "scraper" / "full_auto_scrape.py")],
            "1. Scrape APA league data")

    # 2-4. Fixtures -> SQLite -> workbook / demo JSON / Captain's Edge.
    run([sys.executable, "-m", "pipeline"],
        "2. Ingest fixtures, rebuild matchups, write exports")

    # 5. Prove the tree still holds together.
    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q"], "3. Test suite")

    print("\n=== APA Tracker pipeline completed successfully ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
