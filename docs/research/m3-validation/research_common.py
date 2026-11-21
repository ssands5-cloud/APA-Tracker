"""Shared setup for the M3 research scripts: portable archive path and repository imports."""
import argparse
import os
import sys
from pathlib import Path


def find_repo():
    for a in Path(__file__).resolve().parents:
        if (a / "analytics" / "ultimate_coach_confidence.py").exists():
            return a
    raise SystemExit("Run these scripts from inside the repository checkout (analytics/ not found).")


def setup(description):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--db", default=os.environ.get("UC_ARCHIVE_DB"), help="archive SQLite (or snapshot); or set UC_ARCHIVE_DB")
    ap.add_argument("--out", default=".", help="directory for results files")
    a = ap.parse_args()
    if not a.db:
        ap.error("pass --db or set UC_ARCHIVE_DB")
    repo = find_repo()
    sys.path[:0] = [str(repo), str(repo / "scripts")]
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    return Path(a.db).resolve(), out
