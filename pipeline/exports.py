"""Committed database -> one coherent set of deliverables.

The read-only captain builders run before the workbook so its Captain's Edge
sheet is generated from the decision JSON produced by this same refresh, not
from the previous run.  ``pipeline.refresh.finalize`` guarantees the ingest
session has already committed before entering here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ui.export_excel import export_to_excel
from ui.export_json import export_to_json

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORTS_DIR = PROJECT_ROOT / "exports"
LINEUPS_JSON_NAME = "lineups.json"


def configured_db_path(config: dict[str, Any]) -> Path:
    path = Path((config.get("database") or {}).get("path") or "data/apa_tracker.db")
    return path if path.is_absolute() else PROJECT_ROOT / path


def engine_db_path(config: dict[str, Any], engine: Engine) -> Path:
    """Return the database file the active engine actually opened.

    A relative config path is resolved by SQLAlchemy against the process
    working directory.  Re-resolving it against this module's directory can
    silently point read-only builders at a different database when a
    scheduler is launched from Task Scheduler or a test temp directory.
    """
    database = engine.url.database
    if database and database != ":memory:":
        return Path(database).resolve()
    return configured_db_path(config)


def run(config: dict[str, Any], engine: Engine, captains: bool = True) -> list[tuple[str, str]]:
    """Write every artifact. Returns (label, path) for each."""
    db_path = engine_db_path(config, engine)
    exports_dir = EXPORTS_DIR
    captain_artifacts: list[tuple[str, str]] = []
    lineup_path: Path | None = None
    captain_ready = False

    if captains:
        # Both builders open SQLite read-only by path.  Build their documents
        # first so every downstream view consumes this run's decisions.
        from scripts.build_captains_edge import JSON_NAME, NoDatabaseError, build

        try:
            html_path, xlsx_path = build(str(db_path), str(exports_dir))
        except NoDatabaseError as exc:
            logger.warning("Captain's Edge skipped: %s", str(exc).splitlines()[0])
        else:
            captain_ready = True
            captain_artifacts.extend([
                ("captains html", str(html_path)),
                ("captains xlsx", str(xlsx_path)),
                ("captains json", str(exports_dir / JSON_NAME)),
            ])

            import importlib

            build_lineups = importlib.import_module("scripts.build_lineups")
            lineup_no_database_error = getattr(
                build_lineups, "NoDatabaseError", NoDatabaseError
            )
            try:
                lineup_result = build_lineups.build(str(db_path), str(exports_dir))
            except lineup_no_database_error as exc:
                logger.warning("Lineup Optimizer skipped: %s", str(exc).splitlines()[0])
            else:
                lineup_path = _lineup_output_path(lineup_result, exports_dir)
                captain_artifacts.append(("lineups json", str(lineup_path)))

    written: list[tuple[str, str]] = []
    with Session(engine) as db:
        written.append((
            "workbook",
            export_to_excel(
                db,
                config,
                captains_edge_path=exports_dir / "captains_edge.json",
                include_captains_edge=captain_ready,
            ),
        ))
        written.append(("demo json", export_to_json(db, config)))

    written.extend(captain_artifacts)

    if lineup_path is not None:
        workbook_path = Path(written[0][1]) if written else None
        if workbook_path is not None and workbook_path.is_file():
            from ui.export_excel import append_lineup_optimizer_sheet

            append_lineup_optimizer_sheet(workbook_path, lineup_path)

    with Session(engine) as db:
        written.append((
            "analysis tabs",
            str(write_tabs(
                db,
                exports_dir,
                include_captains_edge=captain_ready,
                include_lineup=lineup_path is not None,
            )),
        ))

    return written


def _lineup_output_path(result: Any, exports_dir: Path) -> Path:
    """Validate the builder's artifact path before reporting it.

    ``scripts.build_lineups.build`` returns the JSON path when it writes an
    artifact.  The fallback keeps the pipeline compatible with a builder that
    returns ``None`` after successfully writing its conventional filename,
    while the containment check prevents a future path/configuration mistake
    from making the pipeline advertise or create an output outside this
    repository's export directory.
    """
    path = Path(result) if result is not None else exports_dir / LINEUPS_JSON_NAME
    export_root = exports_dir.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(export_root)
    except ValueError as exc:
        raise ValueError(
            f"Lineup Optimizer output must be under {export_root}: {path}"
        ) from exc
    return path


# Both analysis tabs render self-contained fragments. Without this they were
# renderers nothing called: fully tested, and producing no file anyone could
# open. A tab that ships no artifact is not delivered.
TABS_NAME = "analysis_tabs.html"


def write_tabs(
    db: Session,
    out_dir: Path | None = None,
    *,
    include_captains_edge: bool = True,
    include_lineup: bool = True,
) -> Path:
    """Render the Head-to-Head and Player Trends tabs into one openable page.

    Deliberately one file with both: they answer the same question from two
    directions -- who to play, and who is moving -- and a captain at a venue
    should not have to juggle two documents. No external resources, so it
    opens from a file:// URL with no server and no internet.
    """
    import json

    from ui.tabs import captains_edge as edge_tab
    from ui.tabs import lineup_optimizer as lineup_tab
    from ui.tabs import matchups, trends

    directory = out_dir or (PROJECT_ROOT / "exports")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / TABS_NAME

    sections = [
        matchups.build(db, title="Head-to-Head"),
        trends.build(db, title="Player Trends"),
    ]

    # Lineup Optimizer writes its versioned document just before this runs.
    # An absent one means a first build, not an error -- the tab is simply
    # omitted rather than rendering an empty promise.  It is inserted first:
    # the one-to-one card is the answer, while Captain's Edge is the
    # independent per-player working view beneath it.
    lineup_path = directory / "lineups.json"
    if include_lineup and lineup_path.is_file():
        try:
            lineup_document = json.loads(lineup_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not read %s -- Lineup Optimizer tab skipped", lineup_path)
        else:
            sections.insert(0, lineup_tab.build(lineup_document, title="Lineup Optimizer"))

    # The Captain's Edge builder writes the decision document just before
    # this runs. An absent one means a first build, not an error -- the tab
    # is simply omitted rather than rendering an empty promise.
    decision_path = directory / "captains_edge.json"
    if include_captains_edge and decision_path.is_file():
        try:
            document = json.loads(decision_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not read %s -- Captain's Edge tab skipped",
                           decision_path)
        else:
            # First: it is the answer, the others are the working.
            sections.insert(0, edge_tab.build(document, title="Captain's Edge"))

    body = "\n".join(sections)
    shell = (
        '<!DOCTYPE html>\n'
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>APA Analysis</title>"
        "<style>body{margin:0;padding:20px;background:#f5f6f8;color:#15171c;"
        "font:15px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;}"
        "section{background:#fff;border:1px solid #e2e5ea;border-radius:10px;"
        "padding:16px;margin-bottom:18px;overflow-x:auto;}h2{margin:0 0 4px;font-size:16px;}"
        "</style></head><body>\n"
        f"{body}\n"
        "</body></html>"
    )
    path.write_text(shell, encoding="utf-8")
    return path
