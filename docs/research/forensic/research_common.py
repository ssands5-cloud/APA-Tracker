"""Shared setup for the issue #119 experiment: portable archive path, record policy, repository imports."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def find_repo():
    for a in Path(__file__).resolve().parents:
        if (a / "analytics" / "ultimate_coach_confidence.py").exists():
            return a
    raise SystemExit("Run from inside the repository checkout (analytics/ not found).")


def setup(description):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--db", default=os.environ.get("UC_ARCHIVE_DB"), help="archive snapshot SQLite (or set UC_ARCHIVE_DB)")
    ap.add_argument("--out", default=".", help="directory for the results file")
    ap.add_argument("--policy", default="clean", choices=["raw", "dedup", "clean"],
                    help="raw: every decided row; dedup: drop exact repeats; clean: also drop both rows of conflicting repeats")
    ap.add_argument("--manifest", default=str(Path(__file__).resolve().parents[1] / "m3-validation" / "snapshot_manifest.json"),
                    help="snapshot manifest; the run records whether the snapshot hash matches it")
    a = ap.parse_args()
    if not a.db:
        ap.error("pass --db or set UC_ARCHIVE_DB")
    repo = find_repo()
    sys.path[:0] = [str(repo), str(repo / "scripts")]
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    db = Path(a.db).resolve()
    sha = hashlib.sha256(db.read_bytes()).hexdigest()
    expected = None
    try:
        expected = json.loads(Path(a.manifest).read_text())["snapshot_sha256"]
    except Exception:
        pass
    return db, out, a.policy, {"snapshot_sha256": sha, "manifest_sha256": expected, "matches_manifest": sha == expected}
