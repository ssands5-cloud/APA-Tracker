"""Database -> deliverables.

The workbook and demo JSON come from the existing exporters. Captain's Edge
is built last and separately, because it opens the database **read-only** by
path rather than sharing this session -- see
``scripts.build_captains_edge``. That means it must run after the ingest
session has committed, or it would read a database that does not yet contain
the rows it is meant to report.
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


def configured_exports_dir(config: dict[str, Any]) -> Path:
    """Where the read-only builders (Captain's Edge, Lineup Optimizer) and
    the analysis tabs page write, in addition to the workbook/JSON paths
    `config["export"]` already controls.

    Defaults to the module-level `EXPORTS_DIR` (the real project's
    `exports/`) exactly as before this existed -- only a caller that sets
    `export.exports_dir` in its config changes anything, which is what lets
    a CI or build-verification run redirect every artifact into a scratch
    directory without monkeypatching module globals.
    """
    override = (config.get("export") or {}).get("exports_dir")
    if not override:
        return EXPORTS_DIR
    path = Path(override)
    return path if path.is_absolute() else PROJECT_ROOT / path


def run(config: dict[str, Any], engine: Engine, captains: bool = True) -> list[tuple[str, str]]:
    """Write every artifact. Returns (label, path) for each."""
    written: list[tuple[str, str]] = []

    with Session(engine) as db:
        written.append(("workbook", export_to_excel(db, config)))
        written.append(("demo json", export_to_json(db, config)))

    if not captains:
        return written

    # Imported here rather than at module scope: scripts/ is a sibling
    # package and this keeps the workbook exports usable even if the
    # Captain's Edge builder is unavailable.
    from scripts.build_captains_edge import NoDatabaseError, build

    db_path = configured_db_path(config)
    exports_dir = configured_exports_dir(config)
    try:
        html_path, xlsx_path = build(str(db_path), str(exports_dir))
    except NoDatabaseError as exc:
        logger.warning("Captain's Edge skipped: %s", str(exc).splitlines()[0])
        return written

    written.append(("captains html", str(html_path)))
    written.append(("captains xlsx", str(xlsx_path)))

    # The whole captain-facing export is intentionally built in one place,
    # after ingest has committed and after Captain's Edge has read the same
    # database.  Lineup Optimizer is a separate artifact because it solves a
    # one-to-one assignment, while Captain's Edge still ranks each player
    # independently.  Keep the import lazy so --no-captains remains a true
    # fast path and does not require this optional builder to be importable.
    # import_module consults sys.modules directly, which keeps this lazy
    # boundary easy to stub in orchestration tests even if another test has
    # already imported the real builder package.
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
        written.append(("lineups json", str(lineup_path)))
        # export_to_excel runs before the read-only builders so its existing
        # Captain's Edge contract remains unchanged.  Once lineups.json is
        # available, append the solved card to that same workbook; tests that
        # stub the workbook path (rather than creating a real file) simply
        # exercise the JSON/HTML path and skip this optional post-process.
        workbook_path = Path(written[0][1]) if written else None
        if workbook_path is not None and workbook_path.is_file():
            from ui.export_excel import append_lineup_optimizer_sheet

            append_lineup_optimizer_sheet(workbook_path, lineup_path)

    with Session(engine) as db:
        written.append(("analysis tabs", str(write_tabs(db, out_dir=exports_dir))))

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


def write_tabs(db: Session, out_dir: Path | None = None) -> Path:
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
    if lineup_path.is_file():
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
    if decision_path.is_file():
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
