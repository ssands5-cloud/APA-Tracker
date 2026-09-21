"""Run the Ultimate Coach live build from a browser login.

The browser is only an authentication bridge. Credentials stay inside the real
APA login page and the access token stays in memory for this Python process.

Fresh:
    python tools/run_ultimate_coach_browser.py

Resume after interruption:
    python tools/run_ultimate_coach_browser.py --resume

A confirmed token expiry no longer exits the runner. It reopens the real APA
login bridge and continues from checkpoints after authentication succeeds.

This runner has no production-promotion step.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

GRAPHQL_HOST = "gql.poolplayers.com"
LEAGUE_URL = "https://league.poolplayers.com"


def capture_access_token() -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "Playwright is not installed. Run:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )

    token_holder: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        def on_response(response) -> None:
            if GRAPHQL_HOST not in response.url:
                return
            request = response.request
            auth = request.headers.get("authorization")
            if auth:
                token_holder["token"] = auth

        context.on("response", on_response)
        print("=" * 72)
        print("ULTIMATE COACH AUTHENTICATION")
        print("  1. Log into APA normally in the Chromium window.")
        print("  2. If APA shows Continue to Member Services, click it.")
        print("  3. Wait until Member Services is fully loaded.")
        print("  4. Return here and press Enter.")
        print("=" * 72)
        page.goto(LEAGUE_URL)
        try:
            input("\nPress Enter after Member Services is fully loaded... ")
        except (EOFError, KeyboardInterrupt):
            pass
        browser.close()

    return token_holder.get("token")


def run_pipeline(token: str, *, resume: bool) -> int:
    """Run seed catalog -> history graph -> archive -> enrichment with one token."""
    from scraper.graphql_scraper import fetch_dashboard_teams
    from scheduler.graphql_sync import load_config
    from scripts.build_historical_catalog import main as catalog_main
    from scripts.build_ultimate_coach_archive import (
        DEFAULT_STAGING,
        main as archive_main,
    )
    from scripts.expand_ultimate_coach_history import (
        DEFAULT_OUTPUT as EXPANDED_CATALOG,
        DEFAULT_REPORT as HISTORY_GRAPH_REPORT,
        main as history_graph_main,
    )
    from scripts.enrich_ultimate_coach_players import (
        DEFAULT_REPORT as ENRICHMENT_REPORT,
        main as enrichment_main,
    )

    os.environ["APA_ACCESS_TOKEN"] = token
    try:
        config = load_config(str(_REPO_ROOT / "apa_config.yaml"))
        viewer = fetch_dashboard_teams(config)
        if not viewer.get("id"):
            print("\nAPA authentication was observed but viewer identity is unavailable.")
            print("Run the command again and wait until Member Services fully loads.")
            return 1
        print("\nAPA AUTH OK - authenticated viewer found.")

        from scripts.build_historical_catalog import DEFAULT_OUTPUT as SEED_CATALOG

        if not resume or not SEED_CATALOG.is_file():
            print("\n[1/4] Building authenticated-member seed catalog...")
            if catalog_main([], raise_auth=True):
                return 1
        else:
            print(f"\n[1/4] Reusing seed catalog for resume: {SEED_CATALOG}")

        graph_resume = (
            resume
            and EXPANDED_CATALOG.is_file()
            and HISTORY_GRAPH_REPORT.is_file()
        )
        print("\n[2/4] Recursively expanding history through real roster members...")
        graph_args = ["--resume"] if graph_resume else []
        if history_graph_main(graph_args, raise_auth=True):
            print("\nHistory graph expansion stopped for a non-authentication error.")
            print("Checkpoint files were left intact.")
            return 1

        archive_resume = resume and DEFAULT_STAGING.is_file()
        print("\n[3/4] Building/resuming league-wide historical archive...")
        archive_args = ["--catalog", str(EXPANDED_CATALOG)]
        if archive_resume:
            archive_args.append("--resume")
        if archive_main(archive_args, raise_auth=True):
            print("\nArchive stopped for a non-authentication error.")
            print("Checkpoint files were left intact.")
            return 1

        enrich_resume = resume and ENRICHMENT_REPORT.is_file()
        print("\n[4/4] Enriching every safely resolvable player with APA career stats...")
        enrich_args = ["--catalog", str(EXPANDED_CATALOG)]
        if enrich_resume:
            enrich_args.append("--resume")
        if enrichment_main(enrich_args, raise_auth=True):
            print("\nPlayer enrichment stopped for a non-authentication error.")
            print("Checkpoint files were left intact.")
            return 1

        print("\nULTIMATE COACH DATA FOUNDATION COMPLETE")
        print(f"  expanded catalog: {EXPANDED_CATALOG}")
        print(f"  staging: {DEFAULT_STAGING}")
        print("  production database was not promoted or replaced.")
        return 0
    finally:
        os.environ.pop("APA_ACCESS_TOKEN", None)


def _auth_failure_detail(exc: BaseException) -> str:
    """Return the server error text without printing the token itself."""
    cause = exc.__cause__
    if cause is not None:
        return str(cause)
    return str(exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    from scraper.graphql_scraper import AccessTokenExpired, AccessTokenMissing

    resume = bool(args.resume)
    refresh_count = 0

    while True:
        token = capture_access_token()
        if not token:
            print("\nNo authenticated GraphQL token was observed. Nothing was run.")
            return 1

        try:
            return run_pipeline(token, resume=resume)
        except (AccessTokenMissing, AccessTokenExpired) as exc:
            refresh_count += 1
            resume = True
            print("\n" + "=" * 72)
            print("APA AUTHENTICATION NEEDS REFRESH")
            print(f"  confirmed auth interruption #{refresh_count}")
            print(f"  server signal: {_auth_failure_detail(exc)}")
            print("  crawl checkpoints are preserved.")
            print("  the authentication browser will reopen automatically.")
            print("  after Member Services loads, press Enter and the crawl will resume.")
            print("  no PowerShell command is required.")
            print("=" * 72)
            continue


if __name__ == "__main__":
    raise SystemExit(main())
