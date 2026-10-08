"""Build the private Match Night package (Phase 4D): one fixture, slim, AES-GCM encrypted, as a static
site ready for GitHub Pages (index.html lock screen, sw.js, manifest, icons, package.json).

The passphrase is read from the UC_MATCH_NIGHT_PASSPHRASE environment variable or a hidden prompt
(asked twice). It is never printed or written to disk. See docs/match_night_deployment.md.

    python scripts/build_match_night_package.py --db <staging.db> --out tmp/match_night_site [--match-id 51419770]
    python scripts/build_match_night_package.py --demo --out tmp/match_night_demo     # synthetic players only
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.match_night import MIN_PASSPHRASE, MatchNightError, build_site

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "ultimate_coach_staging.db"
DEFAULT_CONFIG = PROJECT_ROOT / "apa_config.yaml"
DEMO_PASSPHRASE = "demo-match-night-only"   # synthetic demo data only; printed on the demo lock screen


def _passphrase(env_name: str) -> str:
    value = os.environ.get(env_name)
    if value:
        return value
    first = getpass.getpass(f"Match Night passphrase (at least {MIN_PASSPHRASE} characters, input hidden): ")
    second = getpass.getpass("Repeat the passphrase: ")
    if first != second:
        raise MatchNightError("The two passphrases differ.")
    return first


def _real_payload(db: Path, config: Path):
    from sqlalchemy.orm import Session

    from analytics.ultimate_coach_cockpit_identity_bridge import build_verified_cockpit_payload
    from analytics.ultimate_coach_match_day import load_match_day_settings
    from database.engine import create_db_engine

    settings = load_match_day_settings(config)
    engine = create_db_engine({"database": {"path": str(db)}}, create_tables=False)
    try:
        with Session(engine) as session:
            payload = build_verified_cockpit_payload(session, match_day_timezone=settings.timezone)
    finally:
        engine.dispose()
    if not settings.viewer_member_external_id:
        raise MatchNightError("No viewer is configured (viewer_member_external_id in apa_config.local.yaml).")
    return payload, settings.viewer_member_external_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "tmp" / "match_night_site")
    parser.add_argument("--match-id", default=None, help="APA match id of the fixture (default: the next fixture)")
    parser.add_argument("--passphrase-env", default="UC_MATCH_NIGHT_PASSPHRASE")
    parser.add_argument("--demo", action="store_true", help="synthetic players only (tests' fixture), demo passphrase")
    args = parser.parse_args(argv)
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        if args.demo:
            from tests.test_excel_war_room_formulas import _payload as demo_payload
            payload, viewer, passphrase = demo_payload(), "1001", DEMO_PASSPHRASE
            built_at = "2026-10-07 18:00 UTC"   # the demo fixture's own timeline
        else:
            if not args.db.is_file():
                print(f"Ultimate Coach staging DB does not exist: {args.db}")
                return 1
            payload, viewer = _real_payload(args.db, args.config)
            passphrase = _passphrase(args.passphrase_env)
        result = build_site(payload, viewer_external_id=viewer, passphrase=passphrase, built_at=built_at,
                            out=args.out, match_id=args.match_id, demo=args.demo)
    except MatchNightError as exc:
        print(f"Match Night package NOT built: {exc}")
        return 2
    mn = result["fixture"]
    print("Match Night package built (encrypted):")
    print(f"  fixture : {mn['fixture_label']} · {mn['fixture_display']}")
    print(f"  players : {mn['roster_players']} on the two rosters + {mn['referenced_players']} name-only shared opponents")
    print(f"  sizes   : page {result['html_bytes']:,} bytes -> package {result['package_bytes']:,} bytes")
    print(f"  site    : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
