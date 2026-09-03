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

from sqlalchemy import Engine, create_engine

from database.models import Base

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "data/apa_tracker.db"


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
    return engine
