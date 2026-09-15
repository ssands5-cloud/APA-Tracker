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
5. **Build documents and exports** — run `pipeline.exports.run` against the
   final read-only database. Planned `demo.py` obtains the Stage 1 matrix and
   one map of complete exact-pair histories (currently all-history across
   format/session), calls
   `analytics.player_vs_player_matrix.build_matrix_export` once, obtains the
   Lineup Lab document, and then builds one `DataCoverageReport` from those
   matrix plus query-layer refresh timestamps. General schema/source and Lineup
   reconciliation stay in the manifest verification layer. Only after those immutable
   documents exist does it render Player vs Player, Data Coverage, Captain's
   Edge, and captain-first outputs. The HTML renderer reuses the explicit-pair
   fragment for each row. Do not call `summarize` again in the orchestrator,
   run a second ingest, or open the live database writable.
6. **Verify** — run artifact existence/size checks, JSON schema checks,
   workbook-open checks, HTML safety checks, matrix reconciliation, and
   source-database identity checks. Compare every matrix pair/game key and
   value across HTML, Excel, and optional JSON before rounding, then verify each
   embedded explicit-pair detail against its matrix row.
7. **Present** — write a small local index with links to the static pages and
   open it only after verification. A local HTTP server is optional; `file:`
   links must remain functional.
8. **Finalize** — write `demo_manifest.json`, checksums, command-line options,
   test results, and a redacted human summary. Keep or clean scratch data only
   according to an explicit flag.

## Unified Player vs Player assembly

After `build_matrix_export`, `demo.py` creates one serializable document with a
schema version, run/source identity, canonical scope, matrix counts, ordered
rows, nested pair summaries/games, unavailable-field notes, and risk-flag
status. It encodes that document with the repository's safe script-JSON helper
into `<script type="application/json" id="pvp-data">`.

The Player vs Player tab is registered once in the existing `ui/tabs` shell.
`ui/router.py` sets `view=matrix` for scope-only navigation and `view=pair` plus
the two external player IDs for a selected comparison. Browser code parses the
document once and uses pair keys to switch panels. It may filter/sort a display
copy and draw accessible inline SVG, but it may not call analytics, infer
missing values, or create Avoid/Target flags.

The Excel renderer receives the same ordered rows directly, not reparsed HTML
and not browser-mutated state. If a selected pair is materialized in Excel, the
orchestrator passes its key explicitly and verifies that it exists in the
matrix.

## Data Coverage assembly

The orchestrator gathers standings/career refresh inputs through read-only
query functions, then calls `analytics.data_coverage.build_report` once after
matrix construction. It embeds the resulting document as safely escaped
`script#coverage-data`, sends the same object to `data_coverage.xlsx`, and
copies its summary/status into the manifest. Links from other tabs carry only a
metric key/entity key used to select an existing report row.

If matrix denominator reconciliation, timestamp acquisition, source hashing in
the manifest, or coverage render parity fails, the run stops before
presentation. The orchestrator may not
silently omit the tab or replace a null rate with 0%/100%.

## Optional production acquisition

A full live demo may prepend the guarded scrape-and-ingest flow specified in
`scrape_and_ingest_pipeline.md`. It is opt-in, never an implicit fallback, and
must finish reconciliation and verification before exports start. Fixture mode
remains the default for CI and never makes a live APA request.

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
