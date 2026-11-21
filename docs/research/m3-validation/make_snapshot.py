"""Build a compact, schema-compatible archive snapshot for the research scripts (read-only on the source).

Keeps only the columns the studies read, in primary-key order, and writes a manifest with row counts,
date range and sha256. The snapshot contains real league data: keep it local (never commit it).
Usage: python make_snapshot.py --source archive.sqlite --out snapshot_dir
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

TABLES = {
    "matches": ("id", "home_team_id", "away_team_id", "home_score", "away_score", "match_date", "format", "is_scored", "is_bye"),
    "player_head_to_head": ("player_id", "opponent_id", "match_id", "own_skill_level", "opponent_skill_level", "result", "format"),
    "player_matches": ("player_id", "match_id", "team_id", "skill_level"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    dest = out / "archive_snapshot.sqlite"
    if dest.exists():
        dest.unlink()
    src = sqlite3.connect(Path(a.source).resolve().as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    manifest = {"tables": {}}
    for t, cols in TABLES.items():
        decl = {r[1]: (r[2] or "") for r in src.execute(f"PRAGMA table_info({t})")}
        dst.execute(f"CREATE TABLE {t} ({', '.join(c + ' ' + decl[c] for c in cols)})")
        rows = src.execute(f"SELECT {', '.join(cols)} FROM {t} ORDER BY rowid").fetchall()
        dst.executemany(f"INSERT INTO {t} VALUES ({', '.join('?' * len(cols))})", rows)
        manifest["tables"][t] = {"rows": len(rows), "columns": list(cols)}
    dst.commit()
    lo, hi, n = dst.execute("SELECT MIN(match_date), MAX(match_date), COUNT(*) FROM matches WHERE is_scored=1").fetchone()
    manifest["scored_matches"] = {"count": n, "first": lo, "last": hi}
    dst.execute("VACUUM"); dst.close()
    manifest["snapshot_sha256"] = hashlib.sha256(dest.read_bytes()).hexdigest()
    manifest["snapshot_bytes"] = dest.stat().st_size
    (out / "snapshot_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
