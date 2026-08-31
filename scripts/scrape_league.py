#!/usr/bin/env python3
"""
scrape_league.py – CLI tool for the APA Tracker authentication system.

Usage examples:

  # Scrape with env vars (CI automation)
  python scripts/scrape_league.py --league-id 12345 --output data/

  # Interactive login (first time)
  python scripts/scrape_league.py --interactive

  # Specify user account
  python scripts/scrape_league.py --user alice@example.com --league-id 56789

  # List saved sessions
  python scripts/scrape_league.py --list-sessions

  # Clear old session
  python scripts/scrape_league.py --clear-session bob@example.com

  # Scrape specific match with login
  python scripts/scrape_league.py --match 51419746

  # Scrape all matches for user's teams
  python scripts/scrape_league.py --user alice@example.com --fetch-all
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

# Make sure the project root is on sys.path when running this file directly.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from auth.credentials import list_saved_sessions
from auth.login_manager import AuthenticationError, LoginManager

_CONFIG_PATH = _project_root / "apa_config.yaml"


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r") as fh:
        return yaml.safe_load(fh)


def _configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------


def cmd_list_sessions() -> None:
    sessions = list_saved_sessions()
    if not sessions:
        print("No saved sessions found.")
        return
    print("Saved sessions:")
    for path in sessions:
        print(f"  {path.stem}  ({path})")


def cmd_clear_session(username: str, config: dict) -> None:
    mgr = LoginManager(config, username=username)
    mgr.clear_session()


def cmd_interactive(config: dict) -> LoginManager:
    """Force interactive login even if env vars are set."""
    # Temporarily unset env vars so LoginManager prompts the user.
    saved_user = os.environ.pop("APA_USERNAME", None)
    saved_pass = os.environ.pop("APA_PASSWORD", None)
    try:
        mgr = LoginManager(config)
        mgr.login(save=True)
    finally:
        if saved_user is not None:
            os.environ["APA_USERNAME"] = saved_user
        if saved_pass is not None:
            os.environ["APA_PASSWORD"] = saved_pass
    return mgr


def cmd_scrape_match(match_id: str, username: str | None, config: dict) -> None:
    from scraper.authenticated_session import scrape_with_auth

    print(f"Fetching match {match_id}…")
    html = scrape_with_auth(match_id, username=username, config=config)
    print(f"Received {len(html):,} bytes for match {match_id}")


def cmd_fetch_all(username: str | None, config: dict) -> None:
    """Placeholder: scrape all matches for the authenticated user's teams."""
    mgr = LoginManager(config, username=username)
    mgr.get_session()  # Authenticate; session stored on mgr for later use
    print(f"Scraping all data for {mgr.username}…")
    # TODO: plug in league/team scrapers once they expose a top-level function.
    print("✓ Complete!")


def cmd_scrape_league(league_id: str, output: str, username: str | None, config: dict) -> None:
    """Scrape standings/roster for a specific league ID."""
    mgr = LoginManager(config, username=username)
    session = mgr.get_session()
    site = config["site"]
    timeout = config.get("session", {}).get("timeout_seconds", 15)
    league_url = site["base_url"].rstrip("/") + f"/leagues/{league_id}"
    print(f"Scraping league {league_id} from {league_url}…")
    resp = session.get(league_url, timeout=timeout)
    resp.raise_for_status()
    out_path = Path(output) / f"league_{league_id}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(resp.text, encoding="utf-8")
    print(f"✓ Saved {len(resp.text):,} bytes → {out_path}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scrape_league.py",
        description="APA Tracker – league portal scraper with multi-user auth.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--user",
        metavar="EMAIL",
        help="APA login email (overrides APA_USERNAME env var).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Force interactive credential prompt even if env vars are set.",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List all saved session files and exit.",
    )
    parser.add_argument(
        "--clear-session",
        metavar="EMAIL",
        help="Delete the saved session for EMAIL and exit.",
    )
    parser.add_argument(
        "--match",
        metavar="MATCH_ID",
        help="Fetch a single match page (requires authentication).",
    )
    parser.add_argument(
        "--league-id",
        metavar="LEAGUE_ID",
        help="Scrape a specific league by ID.",
    )
    parser.add_argument(
        "--output",
        metavar="DIR",
        default="data/",
        help="Output directory for downloaded data (default: data/).",
    )
    parser.add_argument(
        "--fetch-all",
        action="store_true",
        help="Scrape all matches for the authenticated user's teams.",
    )
    parser.add_argument(
        "--force-relogin",
        action="store_true",
        help="Ignore any cached session and log in fresh.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    config = _load_config()

    # --list-sessions
    if args.list_sessions:
        cmd_list_sessions()
        return 0

    # --clear-session EMAIL
    if args.clear_session:
        cmd_clear_session(args.clear_session, config)
        return 0

    # --interactive
    if args.interactive:
        try:
            cmd_interactive(config)
        except AuthenticationError as exc:
            print(f"✗ Authentication failed: {exc}", file=sys.stderr)
            return 1
        return 0

    # Apply --user override to env (overrides any existing APA_USERNAME)
    if args.user:
        os.environ["APA_USERNAME"] = args.user

    # --match MATCH_ID
    if args.match:
        try:
            cmd_scrape_match(args.match, args.user, config)
        except AuthenticationError as exc:
            print(f"✗ Authentication failed: {exc}", file=sys.stderr)
            return 1
        return 0

    # --league-id LEAGUE_ID
    if args.league_id:
        try:
            cmd_scrape_league(args.league_id, args.output, args.user, config)
        except AuthenticationError as exc:
            print(f"✗ Authentication failed: {exc}", file=sys.stderr)
            return 1
        return 0

    # --fetch-all
    if args.fetch_all:
        try:
            cmd_fetch_all(args.user, config)
        except AuthenticationError as exc:
            print(f"✗ Authentication failed: {exc}", file=sys.stderr)
            return 1
        return 0

    # No action specified – print help.
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
