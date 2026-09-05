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
    return written
