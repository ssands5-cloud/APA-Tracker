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
from html import escape
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
HUB_MANIFEST_NAME = "hub-manifest.json"
HUB_READY_NAME = "HUB_READY"
HUB_SCHEMA_VERSION = "game-night-team-hub-v1"

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


def _discover_viewer_teams() -> list[dict]:
    """Return the authenticated viewer's distinct current APA league teams.

    The viewer query is the ownership authority. The refreshed database contains
    every team in each division, so DB membership alone cannot tell us which
    teams belong to the logged-in member. No token or response payload is logged.
    """
    try:
        with (PROJECT_ROOT / "apa_config.yaml").open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        rows = dashboard_teams_rows(fetch_dashboard_teams(config))
    except Exception as exc:  # noqa: BLE001 - category only, never auth payload
        raise GameNightError(
            f"could not discover current APA teams: {type(exc).__name__}"
        ) from None

    teams: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        team_id = str(row.get("team_id") or "")
        if not team_id or team_id in seen or row.get("is_tournament"):
            continue
        seen.add(team_id)
        teams.append(
            {
                "team_id": team_id,
                "team_name": str(row.get("team_name") or team_id),
                "division_type": str(row.get("division_type") or ""),
                "session_name": str(row.get("session_name") or ""),
            }
        )
    if not teams:
        raise GameNightError("the logged-in APA account has no current league teams")
    return teams


def _discover_viewer_team_ids() -> list[str]:
    """Compatibility helper for callers that only need owned team ids."""
    return [team["team_id"] for team in _discover_viewer_teams()]


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


def _team_label(team: dict) -> str:
    format_name = {"EIGHT": "8-Ball", "NINE": "9-Ball"}.get(
        str(team.get("division_type") or "").upper(),
        str(team.get("division_type") or "League"),
    )
    session_name = str(team.get("session_name") or "Current session")
    return f'{team.get("team_name") or team["team_id"]} — {format_name} / {session_name} — {team["team_id"]}'


def _write_team_hub(
    run_dir: Path,
    viewer_teams: list[dict],
    selected_team_id: str,
    database_sha256: str,
) -> Path:
    """Write a selector shell over independently verified per-team Cockpits."""
    run_dir = run_dir.resolve()
    if selected_team_id not in {team["team_id"] for team in viewer_teams}:
        raise GameNightError("selected game-night team is not owned by the viewer")

    html_dir = run_dir / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = html_dir / "dashboard.html"

    team_entries: list[dict] = []
    dashboard_map: dict[str, str] = {}
    option_html: list[str] = []
    for team in viewer_teams:
        team_id = str(team["team_id"])
        child_dir = (run_dir / "teams" / team_id).resolve()
        if run_dir not in child_dir.parents:
            raise GameNightError(f"team bundle path escapes game-night run: {team_id}")
        child_manifest = verify_cockpit_bundle(child_dir)
        if child_manifest.get("database_sha256") != database_sha256:
            raise GameNightError(f"team {team_id} Cockpit was built from a different database")

        child_dashboard = child_dir / "html" / "dashboard.html"
        child_manifest_path = child_dir / cockpit_builder.MANIFEST_NAME
        relative_dashboard = f"../teams/{team_id}/html/dashboard.html"
        dashboard_map[team_id] = relative_dashboard
        team_entries.append(
            {
                "team_id": team_id,
                "team_name": str(team.get("team_name") or team_id),
                "division_type": str(team.get("division_type") or ""),
                "session_name": str(team.get("session_name") or ""),
                "bundle_dir": f"teams/{team_id}",
                "dashboard_sha256": _sha256(child_dashboard),
                "manifest_sha256": _sha256(child_manifest_path),
            }
        )
        selected = " selected" if team_id == selected_team_id else ""
        option_html.append(
            f'<option value="{escape(team_id)}"{selected}>{escape(_team_label(team))}</option>'
        )

    selected_src = dashboard_map[selected_team_id]
    dashboard_json = json.dumps(dashboard_map, sort_keys=True)
    dashboard_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>APA Coach Cockpit — My Teams</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; height: 100%; background: #0d1117; color: #f0f6fc; }}
.team-hub {{ height: 100%; display: grid; grid-template-rows: auto 1fr; }}
.team-bar {{ display: flex; gap: 14px; align-items: center; flex-wrap: wrap; padding: 12px 16px;
  background: #161b22; border-bottom: 1px solid #30363d; }}
.team-bar strong {{ font-size: 18px; }}
.team-bar label {{ display: flex; align-items: center; gap: 8px; font-weight: 700; }}
.team-bar select {{ min-width: min(520px, 76vw); max-width: 100%; background: #0d1117; color: #f0f6fc;
  border: 1px solid #30363d; border-radius: 8px; padding: 9px 12px; }}
.team-note {{ color: #9da7b3; font-size: 12px; }}
iframe {{ width: 100%; height: 100%; border: 0; background: #0d1117; }}
@media (max-width: 620px) {{
  .team-bar {{ align-items: stretch; }}
  .team-bar label {{ display: block; width: 100%; }}
  .team-bar select {{ width: 100%; min-width: 0; margin-top: 6px; }}
}}
</style>
</head>
<body>
<div class="team-hub">
  <div class="team-bar">
    <strong>APA Coach Cockpit</strong>
    <label>My Team
      <select id="my-team-select">
        {''.join(option_html)}
      </select>
    </label>
    <span class="team-note">Each team view is independently verified from the same refreshed APA data snapshot.</span>
  </div>
  <iframe id="team-cockpit-frame" title="Selected team Coach Cockpit" src="{escape(selected_src)}"></iframe>
</div>
<script>
const TEAM_DASHBOARDS = {dashboard_json};
const picker = document.getElementById("my-team-select");
const frame = document.getElementById("team-cockpit-frame");
picker.addEventListener("change", function () {{
  const next = TEAM_DASHBOARDS[picker.value];
  if (next) frame.src = next;
}});
</script>
</body>
</html>
""",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": HUB_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "database_sha256": database_sha256,
        "selected_team_id": selected_team_id,
        "team_count": len(team_entries),
        "teams": team_entries,
        "hub_dashboard": "html/dashboard.html",
        "hub_dashboard_sha256": _sha256(dashboard_path),
        "promotable": True,
    }
    manifest_path = run_dir / HUB_MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / HUB_READY_NAME).write_text(
        json.dumps(
            {
                "schema_version": HUB_SCHEMA_VERSION,
                "run_id": run_dir.name,
                "manifest_sha256": _sha256(manifest_path),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return dashboard_path


def verify_game_night_hub(run_dir: Path, expected_database_sha256: str) -> dict:
    """Revalidate the selector shell and every child Cockpit before promotion."""
    run_dir = run_dir.resolve()
    ready_path = run_dir / HUB_READY_NAME
    manifest_path = run_dir / HUB_MANIFEST_NAME
    dashboard_path = run_dir / "html" / "dashboard.html"
    for required in (ready_path, manifest_path, dashboard_path):
        if not required.is_file() or required.stat().st_size == 0:
            raise GameNightError(f"game-night team hub is missing required file: {required.name}")

    try:
        ready = json.loads(ready_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GameNightError(f"could not read game-night hub metadata: {type(exc).__name__}") from None

    if ready.get("schema_version") != HUB_SCHEMA_VERSION:
        raise GameNightError("game-night hub READY schema is not recognized")
    if ready.get("manifest_sha256") != _sha256(manifest_path):
        raise GameNightError("game-night hub READY marker does not match manifest hash")
    if ready.get("run_id") != manifest.get("run_id") or manifest.get("run_id") != run_dir.name:
        raise GameNightError("game-night hub run identity does not reconcile")
    if manifest.get("database_sha256") != expected_database_sha256:
        raise GameNightError("game-night hub database hash does not match staging")
    if manifest.get("hub_dashboard_sha256") != _sha256(dashboard_path):
        raise GameNightError("game-night hub dashboard checksum mismatch")
    if manifest.get("promotable") is not True:
        raise GameNightError("game-night hub is not marked promotable")

    teams = manifest.get("teams") or []
    if not teams or manifest.get("team_count") != len(teams):
        raise GameNightError("game-night hub team inventory does not reconcile")
    team_ids = {str(team.get("team_id") or "") for team in teams}
    if manifest.get("selected_team_id") not in team_ids:
        raise GameNightError("game-night hub selected team is not in its verified inventory")

    for team in teams:
        team_id = str(team.get("team_id") or "")
        child_dir = (run_dir / str(team.get("bundle_dir") or "")).resolve()
        if not team_id or run_dir not in child_dir.parents:
            raise GameNightError("game-night hub contains an invalid team bundle path")
        child_manifest = verify_cockpit_bundle(child_dir)
        if child_manifest.get("database_sha256") != expected_database_sha256:
            raise GameNightError(f"team {team_id} bundle database hash does not match staging")
        if team.get("manifest_sha256") != _sha256(child_dir / cockpit_builder.MANIFEST_NAME):
            raise GameNightError(f"team {team_id} manifest hash changed after hub finalization")
        if team.get("dashboard_sha256") != _sha256(child_dir / "html" / "dashboard.html"):
            raise GameNightError(f"team {team_id} dashboard hash changed after hub finalization")

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

    if our_team_id:
        viewer_teams = [{
            "team_id": str(our_team_id),
            "team_name": str(our_team_id),
            "division_type": "",
            "session_name": "",
        }]
    else:
        viewer_teams = _discover_viewer_teams()
    viewer_team_ids = [team["team_id"] for team in viewer_teams]

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

    selected_match: Optional[dict] = None
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
    if our_team_id:
        logger.info("2/4 Building Coach Cockpit from the verified staging database...")
        cockpit_builder.run_build(
            LIVE_STAGING_DB,
            team_id,
            cockpit_run,
            COCKPIT_RUN_ROOT,
        )
        manifest = verify_cockpit_bundle(cockpit_run)
        if manifest.get("database_sha256") != staged_hash_before:
            raise GameNightError("Coach Cockpit was not built from the exact verified staging database")
        dashboard = (cockpit_run / "html" / "dashboard.html").resolve()
        built_at = manifest.get("built_at") or "unknown"
    else:
        logger.info(
            "2/4 Building independently verified Coach Cockpits for %d current team(s)...",
            len(viewer_teams),
        )
        team_root = cockpit_run / "teams"
        for team in viewer_teams:
            team_run = team_root / team["team_id"]
            cockpit_builder.run_build(
                LIVE_STAGING_DB,
                team["team_id"],
                team_run,
                team_root,
            )
            team_manifest = verify_cockpit_bundle(team_run)
            if team_manifest.get("database_sha256") != staged_hash_before:
                raise GameNightError(
                    f'team {team["team_id"]} Cockpit was not built from the exact staging database'
                )

        dashboard = _write_team_hub(
            cockpit_run,
            viewer_teams,
            team_id,
            staged_hash_before,
        ).resolve()
        manifest = verify_game_night_hub(cockpit_run, staged_hash_before)
        built_at = manifest.get("built_at") or "unknown"

    staged_hash_after = _sha256(LIVE_STAGING_DB)
    if staged_hash_after != staged_hash_before:
        raise GameNightError("staging database changed while the Coach Cockpit was being built")

    logger.info("3/4 Promoting verified staging data with backup protection...")
    production_builder.promote_live_database(LIVE_STAGING_DB)

    logger.info("4/4 READY")
    logger.info("Data refresh verified; Cockpit built at %s", built_at)
    if selected_match is not None:
        logger.info(
            "Default team opens to the nearest match: %s at %s",
            selected_match["opponent_name"],
            selected_match["match_date"],
        )
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
