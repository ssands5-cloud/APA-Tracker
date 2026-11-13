"""Build an offline Broadcast pair from a completed refresh and a verified history archive."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from analytics.ultimate_coach_cockpit_identity_bridge import build_verified_cockpit_payload
from analytics.ultimate_coach_match_day import load_match_day_settings
from pipeline import refresh_workbook
from ui.export_excel_ultimate_coach import write_workbook
from ui.ultimate_coach import render


def read_payload(database: Path, timezone: str) -> dict:
    if not database.is_file():
        raise FileNotFoundError(database)
    engine = create_engine("sqlite+pysqlite:///" + database.resolve().as_uri() + "?mode=ro&uri=true")
    try:
        with Session(engine) as session:
            return build_verified_cockpit_payload(session, match_day_timezone=timezone)
    finally:
        engine.dispose()


def add_archive_evidence(current: dict, archive: dict, cutoff: str) -> int:
    """Keep current rosters and fixtures, and attach verified archive matches by member ID."""
    current_by_member = {str(p["external_id"]): p["id"] for p in current["players"]}
    current_ids = set(current_by_member.values())
    next_id = max(current_ids, default=0) + 1
    mapped_ids = {}
    profiles = {}
    for player in archive["players"]:
        member = str(player["external_id"])
        if member in current_by_member:
            mapped_ids[player["id"]] = current_by_member[member]
        else:
            mapped_ids[player["id"]] = next_id
            profiles[next_id] = {**player, "id": next_id, "team_history": []}
            next_id += 1

    refreshed_matches = {
        str(row["match_external_id"])
        for row in (*current["match_day"]["fixtures"], *current["evidence"])
        if row.get("match_external_id")
    }
    additional = []
    used_profiles = set()
    for row in archive["evidence"]:
        player = mapped_ids[row["player_id"]]
        opponent = mapped_ids[row["opponent_id"]]
        if player not in current_ids and opponent not in current_ids:
            continue
        match = row.get("match_external_id")
        date = str(row.get("match_date") or "")[:10]
        if not match or str(match) in refreshed_matches or not date or date > cutoff:
            continue
        additional.append({
            **row, "player_id": player, "opponent_id": opponent, "game_key": "archive:" + str(row["game_key"]),
        })
        used_profiles.update((player, opponent))

    current["players"].extend(profiles[i] for i in sorted(used_profiles - current_ids))
    current["evidence"].extend(additional)
    added_games = len({r["game_key"] for r in additional})
    current["counts"]["players"] = len(current["players"])
    current["counts"]["head_to_head_rows"] = len(current["evidence"])
    current["counts"]["all_games"] += added_games
    current["trust"]["identity_verified_game_count"] += added_games
    current["trust"]["total_all_games_rows"] += added_games
    return added_games


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-root", type=Path, required=True, help="Folder containing the verified CURRENT.json")
    parser.add_argument("--archive-db", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="New output folder")
    args = parser.parse_args()

    pointer = json.loads((args.refresh_root / "CURRENT.json").read_text(encoding="utf-8"))
    refresh_dir = args.refresh_root.resolve()
    run = (refresh_dir / pointer["run"]).resolve()
    if run.parent != refresh_dir or not (run / "READY").is_file() or pointer.get("coverage") != "complete":
        parser.error("CURRENT.json must point to a complete refresh in --refresh-root")
    database = run / "ultimate_coach_staging.db"
    if sha256(database) != pointer["artifacts"][database.name]:
        parser.error("The refresh database does not match CURRENT.json")

    checked_at = datetime.fromisoformat(pointer["checked_at"])
    settings = load_match_day_settings(args.config)
    current = read_payload(database, settings.timezone)
    archive = read_payload(args.archive_db, settings.timezone)
    added = add_archive_evidence(current, archive, checked_at.date().isoformat())

    args.out.mkdir(parents=True, exist_ok=False)
    stamp = checked_at.strftime("%Y-%m-%d %H:%M UTC")
    viewer = {
        "viewer_member_external_id": settings.viewer_member_external_id,
        "viewer_card_number": settings.viewer_card_number,
    }
    html = args.out / "Ultimate_Coach_Broadcast.html"
    workbook = args.out / "Ultimate_Coach_Archive_Evidence.xlsx"
    html.write_text(render(current, built_at=stamp, ui="broadcast", **viewer), encoding="utf-8")
    write_workbook(current, workbook, built_at=stamp, source_db="Verified current snapshot and historical archive", **viewer)
    validation = {
        html.name: refresh_workbook.validate_html(html),
        workbook.name: refresh_workbook.recalculate_and_validate(
            workbook, captain_sheets=(*refresh_workbook.CAPTAIN_SHEETS, "Recommended Lineup", "Five-Game Plan"),
        ),
    }
    manifest = {
        "base_run": run.name,
        "archive_cutoff_inclusive": checked_at.date().isoformat(),
        "historical_games_added": added,
        "artifacts": {p.name: sha256(p) for p in (html, workbook)},
        "validation": validation,
    }
    (args.out / "history-scope.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(args.out.resolve())


if __name__ == "__main__":
    main()
