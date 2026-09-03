"""Database engine construction, shared by every scheduler entry point.

Exists because each job used to build its own engine with
``create_engine(f"sqlite:///{path}")`` and nothing created the directory the
path points into. ``data/`` is gitignored and absent from a fresh clone, so
the first run of any job died with "unable to open database file" before
doing any work -- the same one-line gap repeated in three places.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect

from database.models import Base

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "data/apa_tracker.db"


class StaleSchemaError(RuntimeError):
    """The database file predates the current models and lacks columns."""


def check_schema(engine: Engine) -> list[str]:
    """Return descriptions of columns the models expect but the file lacks.

    ``Base.metadata.create_all`` creates missing TABLES but never alters
    existing ones, so a database written by an older build keeps its old
    columns and the first insert fails with a bare "no such column: ...".
    There is no migration tooling here and none is warranted: every row is
    re-fetchable from the API, so the fix is to delete the file.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    missing: list[str] = []

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue  # create_all will make it
        present = {column["name"] for column in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name not in present:
                missing.append(f"{table_name}.{column.name}")
    return missing


def create_db_engine(config: dict, create_tables: bool = True) -> Engine:
    """Return an engine for the configured SQLite file, creating what's missing.

    Creates the parent directory and (unless told otherwise) the tables, so a
    first run on a clean checkout works rather than failing on a missing
    directory.
    """
    db_path = Path((config.get("database") or {}).get("path") or DEFAULT_DB_PATH)
    if db_path.parent and not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Created database directory %s", db_path.parent)

    engine = create_engine(f"sqlite:///{db_path}")
    if create_tables:
        Base.metadata.create_all(engine)

        missing = check_schema(engine)
        if missing:
            raise StaleSchemaError(
                f"{db_path} was written by an older version and is missing "
                f"{len(missing)} column(s): {', '.join(missing)}.\n\n"
                f"Every row in it can be re-fetched from the API, so the fix is "
                f"to delete the file and re-run:\n"
                f"    del \"{db_path}\"      (PowerShell)\n"
                f"    rm {db_path}          (bash)"
            )
    return engine
