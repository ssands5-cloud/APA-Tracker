"""Central path configuration for APA Tracker data.

All scripts should import from here instead of constructing data paths
from PROJECT_ROOT.  Set APA_DATA_ROOT in the environment (or .env) to
override the default; this makes the whole pipeline portable across
machines and drives without touching source code.

Usage:
    from paths import APA_DB, DATABASES_DIR, REFRESH_DIR, ...

Environment variables:
    APA_DATA_ROOT   Root of all data storage (default: D:\\APA-Tracker-Data)
    APA_DB_PATH     Override the active production DB path
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data root reads from env; defaults to D:\APA-Tracker-Data so code stays
# on C: while data lives on D:.
APA_DATA_ROOT = Path(os.environ.get("APA_DATA_ROOT", r"D:\APA-Tracker-Data"))

# ---------------------------------------------------------------------------
# D: subdirectories  (created by the storage-migration setup step)
# ---------------------------------------------------------------------------

DATABASES_DIR    = APA_DATA_ROOT / "databases"
BACKUPS_DIR      = APA_DATA_ROOT / "backups"
REFRESH_DIR      = APA_DATA_ROOT / "refresh-data"
EXPORTS_DIR      = APA_DATA_ROOT / "exports"
HISTORY_DIR      = APA_DATA_ROOT / "historical-seasons"
SNAPSHOTS_DIR    = APA_DATA_ROOT / "snapshots"
REPORTS_DIR      = APA_DATA_ROOT / "reports"
LOGS_DIR         = APA_DATA_ROOT / "logs"
SCORESHEETS_DIR  = APA_DATA_ROOT / "scoresheets"
STATISTICS_DIR   = APA_DATA_ROOT / "statistics"
ARCHIVE_DIR      = APA_DATA_ROOT / "archive"

# ---------------------------------------------------------------------------
# Canonical active database
# ---------------------------------------------------------------------------

# APA_DB_PATH lets a single script target a different database without
# touching anything else (e.g. a test DB or a refresh candidate).
APA_DB = Path(os.environ.get("APA_DB_PATH", str(DATABASES_DIR / "apa_tracker.db")))

# Regenerated DB written by refresh_ultimate_coach_current_session.py
APA_DB_REGENERATED = DATABASES_DIR / "apa_tracker_regenerated.db"

# Demo databases
DEMO_DB          = DATABASES_DIR / "demo_coherent.db"
DEMO_APA_DB      = DATABASES_DIR / "demo_apa_tracker.db"

# ---------------------------------------------------------------------------
# Backward-compat shim — used during the migration phase while scripts are
# being updated one by one.  Remove after all scripts reference D: paths.
# ---------------------------------------------------------------------------

LEGACY_DATA_DIR = _PROJECT_ROOT / "data"


def ensure_data_dirs() -> None:
    """Create all D: subdirectories if they do not exist yet.

    Safe to call at script startup; no-ops when directories already exist.
    """
    for d in (
        DATABASES_DIR, BACKUPS_DIR, REFRESH_DIR, EXPORTS_DIR,
        HISTORY_DIR, SNAPSHOTS_DIR, REPORTS_DIR, LOGS_DIR,
        SCORESHEETS_DIR, STATISTICS_DIR, ARCHIVE_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
