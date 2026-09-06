# Production Refresh

All ingest entry points now converge on `pipeline.refresh.finalize`. This is
the production boundary between raw APA facts and captain-facing output.

## Order of operations

1. The caller finishes raw ingest and closes its SQLAlchemy session.
2. `player_matchups` is rebuilt and reconciled from raw head-to-head games.
3. `player_h2h_advantage` is rebuilt and stale pairings are pruned, including
   the all-empty case after a corrected scoresheet removes the last game.
4. `player_trends` is rebuilt and stale groups are pruned.
5. The derived transaction commits.
6. Captain's Edge and Lineup Optimizer read that committed database.
7. The workbook, JSON, and combined analysis page consume the same current
   decision documents.
8. `exports/refresh_manifest.json` is atomically replaced last.

The fixture pipeline, live all-team and single-team GraphQL commands, daily
job, and weekly job all use this ordering. A token-backed daily run delegates
to the all-team command so scheduled production cannot silently omit the
account's other teams.

## Completion manifest

The manifest is the marker for the last fully completed export run. It has a
UUID `run_id`, UTC start/completion timestamps, derived row counts, and for
every reported artifact:

- its resolved path;
- whether the file exists;
- its byte size; and
- its SHA-256 digest.

The file is written through a temporary file and renamed only after every
exporter returns successfully. If a late exporter fails, the exception still
fails the scheduler and the previous manifest remains the last known complete
run. Raw and derived database commits are not rolled back by an export error.

The artifact files are generated sequentially; they are not claimed to be a
filesystem-wide atomic transaction. Consumers that need to verify a coherent
set should use the last manifest and compare its recorded hashes.

## No-export mode

`python -m scheduler.graphql_sync --no-export` still rebuilds and prunes every
derived table. It writes no workbook, JSON, HTML, or manifest. This keeps the
database internally consistent while preserving an explicit no-files mode.
