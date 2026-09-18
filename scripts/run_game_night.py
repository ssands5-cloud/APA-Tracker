"""Safe game-night refresh -> verify -> Coach Cockpit -> open orchestration.

This module intentionally owns no scraper, analytics, lineup, matchup, or
rendering logic. It composes already-existing production contracts:

1. full live staging acquisition + verification (no promotion yet),
2. Coach Cockpit build against that exact staged database,
3. independent READY/manifest/checksum revalidation,
4. production database promotion only after both gates pass,
5. optional browser open of the verified Cockpit dashboard.

A failure before step 4 leaves the existing production database untouched.
Every Cockpit build gets a new run directory, so the last known-good Cockpit
also remains available when a new attempt fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.graphql_scraper import dashboard_teams_rows, fetch_dashboard_teams
from scripts import build_coach_advantage_bundle as cockpit_builder
from scripts import build_full_production_demo as production_builder

logger = logging.getLogger("run_game_night")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_RUN_ROOT = production_builder.DEFAULT_RUN_ROOT
COCKPIT_RUN_ROOT = cockpit_builder.DEFAULT_RUN_ROOT
LIVE_STAGING_DB = production_builder.LIVE_STAGING_DB

EXIT_OK = 0
EXIT_VERIFY = 12
EXIT_PRESENTATION = 13
EXIT_INTERRUPT = 130


class GameNightError(RuntimeError):
    """A fail-closed launcher error with a stable exit category."""

    def __init__(self, message: str, code: int = EXIT_VERIFY):
        super().__init__(message)
        self.code = code


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _discover_viewer_team_ids() -> list[str]:
    """Return current APA team ids for the authenticated viewer account.

    This is resolved before staging refresh. The refreshed database contains
    every team in each division, so it cannot by itself identify which teams
    belong to the logged-in member. No token or response payload is logged.
    """
    try:
        with (PROJECT_ROOT / "apa_config.yaml").open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        rows = dashboard_teams_rows(fetch_dashboard_teams(config))
    except Exception as exc:  # noqa: BLE001 - category only, never auth payload
        raise GameNightError(
            f"could not discover current APA teams: {type(exc).__name__}"
        ) from None

    team_ids = [str(row["team_id"]) for row in rows if row.get("team_id")]
    if not team_ids:
        raise GameNightError("the logged-in APA account has no current league teams")
    return team_ids


def _select_game_night_team(
    db_path: Path,
    viewer_team_ids: list[str],
    *,
    now: Optional[datetime] = None,
) -> tuple[str, dict]:
    """Pick the viewer team with the nearest upcoming unplayed real match.

    A match that started within the last 12 hours remains eligible so launching
    during league night does not jump ahead to the next scheduled match.
    """
    viewer_ids = {str(team_id) for team_id in viewer_team_ids if str(team_id)}
    if not viewer_ids:
        raise GameNightError("no current APA team ids are available for game-night selection")

    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now_utc - timedelta(hours=12)

    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            rows = conn.execute(
                """
                SELECT external_id, home_team_id, away_team_id,
                       home_team_name, away_team_name, match_date
                FROM matches
                WHERE COALESCE(is_bye, 0) = 0
                  AND COALESCE(is_scored, 0) = 0
                  AND COALESCE(is_finalized, 0) = 0
                """
            ).fetchall()
    except (OSError, sqlite3.Error) as exc:
        raise GameNightError(
            f"could not inspect refreshed schedule: {type(exc).__name__}"
        ) from None

    candidates: list[tuple[datetime, str, dict]] = []
    for external_id, home_id, away_id, home_name, away_name, match_date in rows:
        home_id = str(home_id or "")
        away_id = str(away_id or "")
        owned_sides = [team_id for team_id in (home_id, away_id) if team_id in viewer_ids]
        if not owned_sides or not match_date:
            continue
        try:
            scheduled = datetime.fromisoformat(str(match_date).replace("Z", "+00:00"))
        except ValueError:
            continue
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        scheduled_utc = scheduled.astimezone(timezone.utc)
        if scheduled_utc < cutoff:
            continue

        for team_id in owned_sides:
            opponent_name = away_name if team_id == home_id else home_name
            candidates.append(
                (
                    scheduled_utc,
                    team_id,
                    {
                        "external_id": str(external_id),
                        "match_date": str(match_date),
                        "opponent_name": str(opponent_name or "unknown opponent"),
                    },
                )
            )

    if not candidates:
        raise GameNightError("no upcoming unplayed match found for the account's current APA teams")

    candidates.sort(key=lambda item: (item[0], item[1], item[2]["external_id"]))
    _scheduled, team_id, match = candidates[0]
    return team_id, match


def verify_cockpit_bundle(run_dir: Path) -> dict:
    """Revalidate READY, manifest, checksums, containment, and dashboard path."""
    run_dir = run_dir.resolve()
    ready_path = run_dir / cockpit_builder.READY_NAME
    manifest_path = run_dir / cockpit_builder.MANIFEST_NAME
    checksums_path = run_dir / cockpit_builder.CHECKSUMS_NAME
    dashboard_path = run_dir / "html" / "dashboard.html"

    for required in (ready_path, manifest_path, checksums_path, dashboard_path):
        if not required.is_file() or required.stat().st_size == 0:
            raise GameNightError(f"verified Cockpit is missing required file: {required.name}")

    try:
        ready = json.loads(ready_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GameNightError(f"could not read Cockpit verification metadata: {type(exc).__name__}") from None

    manifest_hash = _sha256(manifest_path)
    if ready.get("manifest_sha256") != manifest_hash:
        raise GameNightError("Cockpit READY marker does not match manifest hash")
    if ready.get("run_id") != manifest.get("run_id") or manifest.get("run_id") != run_dir.name:
        raise GameNightError("Cockpit run identity does not reconcile")
    if manifest.get("promotable") is not True:
        raise GameNightError("Cockpit manifest is not marked promotable")
    if "html/dashboard.html" not in set(manifest.get("artifacts") or []):
        raise GameNightError("Cockpit manifest does not declare html/dashboard.html")

    declared_hashes = manifest.get("artifact_hashes") or {}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError:
            raise GameNightError("Cockpit checksum file has an invalid line") from None
        target = (run_dir / relative).resolve()
        if target != run_dir and run_dir not in target.parents:
            raise GameNightError(f"Cockpit checksum path escapes run directory: {relative}")
        if not target.is_file() or _sha256(target) != digest:
            raise GameNightError(f"Cockpit checksum mismatch: {relative}")
        if relative in declared_hashes and declared_hashes[relative] != digest:
            raise GameNightError(f"Cockpit manifest hash disagrees with checksum file: {relative}")

    return manifest


def run_game_night(
    *,
    resume: bool = False,
    open_browser: bool = True,
    opener: Callable[[str], bool] = webbrowser.open,
    stamp: Optional[str] = None,
    our_team_id: Optional[str] = None,
) -> Path:
    """Build a fresh verified game-night Cockpit and return dashboard.html."""
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    demo_run = DEMO_RUN_ROOT / f"game-night-refresh-{stamp}"
    cockpit_run = COCKPIT_RUN_ROOT / f"game-night-{stamp}"

    viewer_team_ids = [str(our_team_id)] if our_team_id else _discover_viewer_team_ids()

    logger.info("1/4 Refreshing APA data into a staging database...")
    production_builder.run_build(
        "live",
        demo_run,
        DEMO_RUN_ROOT,
        promote=False,
        resume=resume,
    )

    if not LIVE_STAGING_DB.is_file() or LIVE_STAGING_DB.stat().st_size == 0:
        raise GameNightError("live refresh finished without a staging database")

    if our_team_id:
        team_id = str(our_team_id)
        logger.info("Game-night team explicitly selected: %s", team_id)
    else:
        team_id, selected_match = _select_game_night_team(LIVE_STAGING_DB, viewer_team_ids)
        logger.info(
            "Game-night team selected from nearest upcoming match: team %s vs %s at %s",
            team_id,
            selected_match["opponent_name"],
            selected_match["match_date"],
        )

    staged_hash_before = _sha256(LIVE_STAGING_DB)
    logger.info("2/4 Building Coach Cockpit from the verified staging database...")
    cockpit_builder.run_build(
        LIVE_STAGING_DB,
        team_id,
        cockpit_run,
        COCKPIT_RUN_ROOT,
    )

    manifest = verify_cockpit_bundle(cockpit_run)
    staged_hash_after = _sha256(LIVE_STAGING_DB)
    if staged_hash_after != staged_hash_before:
        raise GameNightError("staging database changed while the Coach Cockpit was being built")
    if manifest.get("database_sha256") != staged_hash_after:
        raise GameNightError("Coach Cockpit was not built from the exact verified staging database")

    logger.info("3/4 Promoting verified staging data with backup protection...")
    production_builder.promote_live_database(LIVE_STAGING_DB)

    dashboard = (cockpit_run / "html" / "dashboard.html").resolve()
    built_at = manifest.get("built_at") or "unknown"
    logger.info("4/4 READY")
    logger.info("Data refresh verified; Cockpit built at %s", built_at)
    logger.info("Open: %s", dashboard)

    if open_browser:
        try:
            opened = opener(dashboard.as_uri())
        except Exception as exc:  # noqa: BLE001 - presentation only, never secret-bearing
            raise GameNightError(
                f"Cockpit is READY but the browser could not be opened ({type(exc).__name__}); "
                f"open this file manually: {dashboard}",
                EXIT_PRESENTATION,
            ) from None
        if opened is False:
            raise GameNightError(
                f"Cockpit is READY but the browser did not open; open this file manually: {dashboard}",
                EXIT_PRESENTATION,
            )

    return dashboard


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Refresh live APA data safely, build a verified Coach Cockpit, and open it."
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted live staging refresh instead of starting the staging DB over.",
    )
    parser.add_argument(
        "--our-team-id",
        help=(
            "Build for this specific current APA team instead of automatically selecting "
            "the team with the nearest upcoming unplayed match."
        ),
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Build and verify the Cockpit but do not open the browser.",
    )
    args = parser.parse_args(argv)

    try:
        run_game_night(
            resume=args.resume,
            open_browser=not args.no_open,
            our_team_id=args.our_team_id,
        )
    except GameNightError as exc:
        logger.error("GAME NIGHT FAILED: %s", exc)
        return exc.code
    except (production_builder.BuildError, cockpit_builder.BuildError) as exc:
        logger.error("GAME NIGHT FAILED: %s", exc)
        return exc.code
    except KeyboardInterrupt:
        logger.error("interrupted")
        return EXIT_INTERRUPT
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
