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


def configured_db_path(config: dict[str, Any]) -> Path:
    path = Path((config.get("database") or {}).get("path") or "data/apa_tracker.db")
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
    try:
        html_path, xlsx_path = build(str(db_path), str(PROJECT_ROOT / "exports"))
    except NoDatabaseError as exc:
        logger.warning("Captain's Edge skipped: %s", str(exc).splitlines()[0])
        return written

    written.append(("captains html", str(html_path)))
    written.append(("captains xlsx", str(xlsx_path)))

    with Session(engine) as db:
        written.append(("analysis tabs", str(write_tabs(db))))

    return written


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
    from ui.tabs import matchups, trends

    directory = out_dir or (PROJECT_ROOT / "exports")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / TABS_NAME

    sections = [
        matchups.build(db, title="Head-to-Head"),
        trends.build(db, title="Player Trends"),
    ]

    # The Captain's Edge builder writes the decision document just before
    # this runs. An absent one means a first build, not an error -- the tab
    # is simply omitted rather than rendering an empty promise.
    decision_path = PROJECT_ROOT / "exports" / "captains_edge.json"
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
