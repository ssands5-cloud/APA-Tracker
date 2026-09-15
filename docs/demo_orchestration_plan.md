# Demo orchestration plan

Claude can implement the future launcher as a thin orchestrator around existing
entry points. It should coordinate, validate, and report; it should not copy
scraper or analytics logic into a new script.

## Phases

1. **Preflight** — resolve the repository root, parse arguments, check Python
   version, import dependencies, verify config, and create a run-specific
   output directory. Reject an output path outside the repository boundary.
2. **Acquire** — in live mode invoke `scraper/full_auto_scrape.py` as a
   subprocess after the guarded login. In fixture mode validate the supplied
   fixture root and skip network access.
3. **Manifest** — enumerate fixture files (excluding auth operations), record
   operation names, entity IDs, byte counts, SHA-256 hashes, and capture time.
   Never print response bodies.
4. **Build database** — write a new SQLite file in the run directory and call
   `python -m pipeline --fixtures ... --config ... --ingest-only` or the
   equivalent Python entry point. Schema checks happen before any export.
5. **Build exports** — run `pipeline.exports.run` and
   `scripts/build_captain_first_edge.py` against the same database and output
   directory. Do not call a second ingest or open the live database writable.
6. **Verify** — run artifact existence/size checks, JSON schema checks,
   workbook-open checks, HTML safety checks, matrix reconciliation, and
   source-database identity checks.
7. **Present** — write a small local index with links to the static pages and
   open it only after verification. A local HTTP server is optional; `file:`
   links must remain functional.
8. **Finalize** — write `demo_manifest.json`, checksums, command-line options,
   test results, and a redacted human summary. Keep or clean scratch data only
   according to an explicit flag.

## Process and idempotency rules

- Each external step is a list-argument subprocess with captured exit code;
  shell interpolation is forbidden.
- A run gets a unique directory. Re-running never appends to an existing
  SQLite file or mixes two capture dates.
- A failed phase stops all later phases and returns a stable non-zero exit code.
- Every path reported in the manifest is relative to the run root, with no
  absolute credential or user-profile paths.
- Cleanup never deletes the canonical database or source fixtures; it removes
  only the explicitly created run directory and temporary browser state.

## What the orchestrator must not do

It must not synthesize rosters, fill missing skill levels, rewrite scoresheets,
enable excluded analytics, alter the scraper contract, or “repair” a stale
schema in place. It also must not silently downgrade from live data to a stale
database when authentication fails.

