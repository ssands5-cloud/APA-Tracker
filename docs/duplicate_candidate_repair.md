# Offline duplicate candidate repair

`scripts/repair_ultimate_coach_duplicate_rows.py` provides a local, copy-only
way to investigate inherited duplicate score rows without another APA login.
It does not resolve failed network requests or promote a database.

Run from a canonical APA Tracker linked worktree:

```powershell
# Inspection only: reads the supplied DB and prints aggregate counts.
python scripts/repair_ultimate_coach_duplicate_rows.py --source-db "<finalized candidate DB>"

# Optional repair: the output folder must not exist and must be inside canonical APA Tracker.
python scripts/repair_ultimate_coach_duplicate_rows.py --source-db "<finalized candidate DB>" --out-dir "<canonical repo>\tmp\duplicate-repair-candidate"
```

Every stored `player_matches` column except the row primary key is compared.
Only rows with a bound player and match are considered. Unbound historical
rows, matches, head-to-head rows, and other tables are preserved. Conflicting
duplicates refuse the entire repair before a copy is created. Declared foreign
key references to score-row IDs also require a separate remapping plan.

The source is opened read-only, copied using SQLite backup, and hashed before
and after. Output paths use the existing repository and reparse-point guards.
Existing output folders are never overwritten. A nonempty source WAL is refused
so an active writer cannot be mistaken for a finalized source.

The new folder contains a repaired DB and `duplicate_repair_report.json`, with
source/candidate hashes, table counts, comparison hashes, and a mapping of each
removed row primary key to its survivor. Keep this report private: it contains
internal record keys. The CLI prints aggregate counts only.

`accepted_current_data` is always false. The original `refresh_report.json` is
neither edited nor copied as a claim about the changed DB. The repair does not
prove current membership, authoritative result parity, current-session
completeness, or release readiness. The original refresh gaps must still be
resolved or explicitly retained; a new authoritative refresh and subsequent
artifact/native verification remain separate requirements.

If a later verification fails, the new output folder is preserved for diagnosis
and no successful repair report is issued. It must not be treated as accepted
data. No source database or old build is deleted by this tool.
