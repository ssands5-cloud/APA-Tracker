"""Run the Ultimate Coach live build from a browser login.

The browser is only an authentication bridge. Credentials stay inside the real
APA login page and the access token stays in memory for this Python process.
This module never reads, types, requests, or stores an APA username or
password anywhere, in either mode below -- there is no credential-handling
code in this file at all.

Fresh, manual (default -- you click through the login and press Enter):
    python tools/run_ultimate_coach_browser.py

Resume after interruption:
    python tools/run_ultimate_coach_browser.py --resume

Persistent (password-free unattended token refresh -- see
capture_access_token_persistent()'s own docstring for the exact contract):
    python tools/run_ultimate_coach_browser.py --resume --persistent-auth

--manual-auth is accepted as an explicit alias for the default (unchanged)
manual behavior.

A confirmed token expiry no longer exits the runner. It reopens the real APA
login bridge (manual or persistent, matching whichever mode this run started
in) and continues from checkpoints after authentication succeeds.

This runner has no production-promotion step.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

GRAPHQL_HOST = "gql.poolplayers.com"
LEAGUE_URL = "https://league.poolplayers.com"

# .session_cache/ is already gitignored. A persistent Chromium *profile
# directory* is not a credential by itself -- it is the same on-disk state
# a real browser always keeps (cookies, local storage) so a real, already
# logged-in APA web session can be reused across process restarts. The
# short-lived GraphQL access token itself is never written here or
# anywhere else: it only ever exists in the local token_holder variable
# below and in the APA_ACCESS_TOKEN environment variable for the lifetime
# of run_pipeline(), popped in that function's own finally block.
SESSION_PROFILE_DIR = _REPO_ROOT / ".session_cache" / "apa_chromium"

# How long to wait for a real authorized GraphQL request to appear -- long
# enough for a human to complete one real manual login by hand on the very
# first (bootstrap) run of a fresh profile, but still a bounded wait: on a
# later, unattended reauth cycle where no one is present, this same
# timeout is what turns a genuinely dead web session into a clean
# "MANUAL APA LOGIN REQUIRED" stop rather than an infinite hang.
PERSISTENT_AUTH_TIMEOUT_S = 300


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


def capture_access_token_persistent(
    *, timeout_s: float = PERSISTENT_AUTH_TIMEOUT_S
) -> str | None:
    """Password-free unattended token capture using a persistent Chromium
    profile.

    Contract:
      - Opens a PERSISTENT profile under SESSION_PROFILE_DIR so a real,
        already-authenticated APA web session (cookies, local storage) is
        reused across process restarts, exactly like a real browser you
        never close.
      - Watches gql.poolplayers.com traffic with the SAME
        context.on("response", ...) pattern capture_access_token() (the
        manual path) already uses -- it never assumes a URL, page title,
        or timer alone means success. Success is defined as: a real
        request to that host actually carried a real `authorization`
        header.
      - Requires NO input(): it polls in a loop instead of blocking on
        Enter. This is the one behavioral difference from the manual path
        that this whole feature exists to provide.
      - If APA shows the real "Continue to Member Services" transitional
        page (existing, already-confirmed UI text from the manual flow's
        own instructions), clicks it automatically -- explicitly
        authorized, and not a credential-handling action. This click is
        debounced by visibility transition: it fires once when the control
        first becomes actionable, then withholds further clicks for as
        long as that same control remains visible, and is only willing to
        click again if the control disappears and later genuinely
        reappears (a new transitional page, not the same one still
        loading).
      - Never reads, requests, fills, or even looks for a username or
        password field. If the real APA login form is what's actually
        showing (because the persistent web session itself has expired,
        not just the short-lived GraphQL token), this function does NOT
        attempt to detect or interact with it in any way -- it simply
        keeps waiting for an authorized GraphQL call up to the bounded
        timeout, exactly as it would for any other reason no token has
        appeared yet. If a human is present (the bootstrap run) they can
        complete that real login by hand within the window; if no one is
        present (an unattended overnight cycle), the timeout elapses and
        this returns None, and the caller reports MANUAL APA LOGIN
        REQUIRED rather than retrying forever or attempting anything with
        the form.
      - Bounded by ``timeout_s`` in all cases -- never an infinite wait.
      - Never captures a screenshot, video, HAR, or trace: none of those
        are enabled anywhere in this function.

    Returns the raw authorization header value, held only in a local
    variable, or None if no authorized GraphQL call was observed within
    the timeout.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "Playwright is not installed. Run:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )

    SESSION_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    token_holder: dict[str, str] = {}

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(SESSION_PROFILE_DIR),
            headless=False,
            # No record_video_dir, no record_har_path, and tracing is
            # never started anywhere in this function -- see the
            # docstring's "never a screenshot/video/HAR/trace" invariant.
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()

            def on_response(response) -> None:
                if GRAPHQL_HOST not in response.url:
                    return
                request = response.request
                auth = request.headers.get("authorization")
                if auth:
                    token_holder["token"] = auth

            context.on("response", on_response)

            print("=" * 72)
            print("ULTIMATE COACH PERSISTENT AUTHENTICATION")
            print(f"  persistent profile: {SESSION_PROFILE_DIR}")
            print("  if this profile is already logged into APA, a token")
            print("  will be captured automatically -- no action needed.")
            print("  if APA shows its real login page, you may log in by")
            print("  hand now; this script will never see or touch that")
            print("  form. No Enter key is needed either way.")
            print("=" * 72)
            page.goto(LEAGUE_URL)

            deadline = time.monotonic() + timeout_s
            # Debounced by visibility transition, not by a sleep: click once
            # when the control first becomes actionable, then withhold
            # further clicks for as long as that same visible control is
            # still on screen (APA hasn't navigated away from it yet). A
            # later click is allowed again only if the control disappears
            # and then genuinely reappears -- a new transitional page, not
            # the same one still loading.
            continue_button_was_visible = False
            while time.monotonic() < deadline and not token_holder.get("token"):
                page.wait_for_timeout(500)
                if not token_holder.get("token"):
                    try:
                        continue_button = page.get_by_text(
                            "Continue to Member Services", exact=False
                        )
                        is_visible = bool(
                            continue_button.count() and continue_button.first.is_visible()
                        )
                        if is_visible and not continue_button_was_visible:
                            continue_button.first.click(timeout=2000)
                            print("  clicked 'Continue to Member Services'.")
                        continue_button_was_visible = is_visible
                    except Exception:
                        continue_button_was_visible = False  # not shown for every account/session -- not an error

            if not token_holder.get("token"):
                print("\nMANUAL APA LOGIN REQUIRED")
                print(
                    f"  no authorized GraphQL request was observed within "
                    f"{int(timeout_s)}s."
                )
                print("  the persistent APA web session may have expired.")
                print("  checkpoints are untouched. Log in by hand in the")
                print("  persistent profile and run this command again.")
                return None

            print("  persistent session authenticated -- token captured.")
            return token_holder["token"]
        finally:
            context.close()


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
    auth_mode = parser.add_mutually_exclusive_group()
    auth_mode.add_argument(
        "--persistent-auth",
        action="store_true",
        help=(
            "Password-free unattended token refresh using a persistent "
            "Chromium profile (.session_cache/apa_chromium/). No input() "
            "required once the profile is authenticated. Falls back to "
            "MANUAL APA LOGIN REQUIRED (never autofill) if the underlying "
            "APA web session itself has expired."
        ),
    )
    auth_mode.add_argument(
        "--manual-auth",
        action="store_true",
        help="Explicit alias for the default manual login-and-Enter flow.",
    )
    args = parser.parse_args(argv)

    from scraper.graphql_scraper import AccessTokenExpired, AccessTokenMissing

    resume = bool(args.resume)
    persistent = bool(args.persistent_auth)
    refresh_count = 0

    capture = capture_access_token_persistent if persistent else capture_access_token

    while True:
        token = capture()
        if not token:
            if persistent:
                # capture_access_token_persistent() already printed the
                # full MANUAL APA LOGIN REQUIRED explanation.
                return 1
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
            if persistent:
                print("  reopening the persistent profile automatically...")
                print("  no Enter key or PowerShell command is required.")
            else:
                print("  the authentication browser will reopen automatically.")
                print("  after Member Services loads, press Enter and the crawl will resume.")
                print("  no PowerShell command is required.")
            print("=" * 72)
            continue


if __name__ == "__main__":
    raise SystemExit(main())
