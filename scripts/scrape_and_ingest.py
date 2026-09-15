"""Full APA scrape-and-ingest CLI: divisions, teams, matches, standings,
player career stats, team history, and head-to-head reconciliation, in one
real run against the live APA GraphQL API.

This is a thin, secure CLI wrapper around the existing, already-shipped,
already-tested pipeline -- it does not duplicate or reimplement any
scraping or ingest logic:

    scheduler.graphql_sync.run_all_teams(config_path, export=...)

already does everything this command's docstring asks for: dashboard
teams and matches, per-division standings, per-team rosters, per-match
scoresheets, unconditional head-to-head reconciliation for every scored
match (ingest_head_to_head runs even when a corrected scoresheet now has
zero pairings, so a stale row is reconciled away rather than left
forever), the account's own career stats (getEightBallStats) and
cross-season team history (TeamStat), and the Matchup Advantage Engine
rebuild -- see scheduler/graphql_sync.py's own extensive docstrings for
exactly why each step is real and shaped the way it is. This script adds
only the safe CLI/credential boundary around that real pipeline.

Credential handling
--------------------
The live path (scraper/graphql_scraper.py, scheduler/graphql_sync.py) is
the current, active scraping contract, and it already authenticates with
one real, short-lived bearer token, read from the environment
(`APA_ACCESS_TOKEN`) or `apa_config.yaml`'s `apa.access_token` -- never
from a CLI argument (a raw `--token VALUE` would land in shell history and
process listings). `--username`/`--password` are accepted here for CLI
compatibility with an operator's expectations, but they name environment
variables (`--username-env`/`--password-env`), not raw values, and they
are currently UNUSED: the real live path authenticates by token only.
Username/password login (`auth/login.py`) belongs to a DIFFERENT, older,
explicitly frozen scraping contract (`scraper/full_auto_scrape.py`) that
this script does not touch, modify, or wire into -- doing so would need
its own explicit authorization. Passing `--username-env`/`--password-env`
without a live token-based scrape configured is a no-op today, and this
script says so rather than silently ignoring the flags.

No secret value is ever logged, printed, or included in an error message
-- only the name of the environment variable a secret was (or was not)
read from.

Modes
-----
    --live           Perform a real, authenticated GraphQL scrape and
                      ingest via run_all_teams(). Requires APA_ACCESS_TOKEN
                      (or apa_config.yaml's apa.access_token) to be set.
    --dry-run        Validate configuration and credential presence
                      without making any network request or writing to
                      the database.

There is no `--fixtures` replay mode here: run_all_teams() always performs
real GraphQL calls by design (see its own docstring -- it discovers teams/
divisions/aliases from the live account, not from static config), so a
fixture-based rehearsal of this exact command is out of scope for this
pass. tests/test_scrape_and_ingest.py exercises this script's own CLI/
credential/dry-run logic with run_all_teams mocked out entirely -- no live
APA request is made in CI, and none is made when this file is imported.

Usage:
    python scripts/scrape_and_ingest.py --dry-run
    APA_ACCESS_TOKEN=... python scripts/scrape_and_ingest.py --live
    python scripts/scrape_and_ingest.py --live --token-env MY_TOKEN_VAR
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_ENV = "APA_ACCESS_TOKEN"


class CredentialError(RuntimeError):
    """A required credential was not available -- never includes the
    credential's own value, only which environment variable was checked."""


def _token_present(config_path: str, token_env: str) -> bool:
    """True when a real token is available from the environment or
    apa_config.yaml, without ever returning or logging the token itself."""
    if os.environ.get(token_env):
        return True
    try:
        import yaml

        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except Exception:  # pragma: no cover - config is advisory here, never required
        return False
    token = (config.get("apa") or {}).get("access_token")
    return bool(token) and "your token here" not in str(token)


def _require_token(config_path: str, token_env: str) -> None:
    if not _token_present(config_path, token_env):
        raise CredentialError(
            f"No real access token found. Set the {token_env} environment "
            f"variable, or apa_config.yaml's apa.access_token, to a real "
            "APA GraphQL bearer token before running --live."
        )


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="apa_config.yaml", help="Path to apa_config.yaml")
    parser.add_argument("--live", action="store_true",
                         help="Perform a real, authenticated scrape and ingest")
    parser.add_argument("--dry-run", action="store_true",
                         help="Validate configuration and credentials; no network request, no write")
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV,
                         help=f"Environment variable holding the real bearer token (default: {DEFAULT_TOKEN_ENV})")
    parser.add_argument("--username-env", default=None,
                         help="Environment variable holding a username -- currently unused; "
                              "the live path authenticates by token only (see module docstring)")
    parser.add_argument("--password-env", default=None,
                         help="Environment variable holding a password -- currently unused; "
                              "the live path authenticates by token only (see module docstring)")
    parser.add_argument("--no-export", action="store_true",
                         help="Skip the Excel/JSON export step after ingest")
    args = parser.parse_args(argv)

    if args.live == args.dry_run:
        logger.error("Pass exactly one of --live or --dry-run.")
        return 1

    if args.username_env or args.password_env:
        logger.warning(
            "--username-env/--password-env were given but are currently unused: "
            "the live scraping path (scheduler.graphql_sync) authenticates by "
            "bearer token only. See this script's module docstring."
        )

    try:
        _require_token(args.config, args.token_env)
    except CredentialError as exc:
        logger.error(str(exc))
        return 1

    if args.dry_run:
        logger.info(
            "Dry run: configuration and credentials look real. No network "
            "request was made and nothing was written."
        )
        return 0

    from scheduler.graphql_sync import run_all_teams

    counts = run_all_teams(config_path=args.config, export=not args.no_export)
    logger.info("Scrape and ingest complete: %s", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
