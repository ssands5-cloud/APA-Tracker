# Full Pipeline Integration

What "the pipeline" means in this repo, concretely, and what is now actually
verified end-to-end rather than merely asserted.

```
pipeline_run_all.py             scrape -> `python -m pipeline` -> test suite
pipeline/__main__.py            fixtures -> SQLite -> shared production refresh
pipeline/refresh.py             reconcile every derived table -> exports -> manifest
tests/test_pipeline_run_all.py  orchestration: step order, --skip-* flags, failure propagation
tests/test_full_pipeline_integration.py   real fixtures -> real ingest -> every real exporter
```

## The two entry points

- **`python -m pipeline`** — fixtures already on disk -> SQLite -> every
  export (workbook, demo JSON, Captain's Edge, Lineup Optimizer, analysis
  tabs). Steps: `pipeline.ingest.run` (teams/roster/standings/matches/scores
  /head-to-head), then `pipeline.refresh.finalize` rebuilds every derived
  table, publishes every artifact, and writes the completion manifest last.
- **`pipeline_run_all.py`** — the full chain including the scrape itself:
  shells out to `scraper/full_auto_scrape.py` (a real browser + login + an
  interactive consent step — see [README-scraper.md](../README-scraper.md)),
  then `python -m pipeline`, then the test suite. `--skip-scrape` reuses
  fixtures already on disk; `--skip-tests` skips the third step.

## What is now actually verified

Before this pass, every existing pipeline test either unit-tested one
ingest/analytics/export function in isolation with hand-built ORM rows, or
tested `pipeline.exports.run`'s orchestration with the real exporters
monkeypatched out (`tests/test_pipeline_exports.py`'s `stub_exporters`).
Nothing proved the actual command a captain runs works front to back.

**`tests/test_full_pipeline_integration.py`** now does, with nothing
stubbed: a small but realistic two-team, one-match fixture tree (in the
scraper's real documented layout) runs through the real
`pipeline.ingest.run` and the real `pipeline.refresh.finalize` — Player Trend
Analyzer, Head-to-Head Advantage Engine, Captain's Decision Engine and the
Lineup Optimizer all included — and every one of the eight reported artifacts
(workbook, demo JSON, Captain's Edge HTML/XLSX, `lineups.json`, the analysis
tabs page, Captain's Edge JSON, and refresh manifest) is checked for real
content: the actual player names, the actual
match result, the actual solved one-to-one assignment. Output is redirected
into a temp directory for the duration of each test (never the real
project's `exports/`), which a dedicated test in the same file verifies
directly by snapshotting the real directory before and after.

**Determinism** — `TestFullPipelineDeterminism` runs the identical fixture
tree through the identical chain twice, into two independent directories,
and diffs every content artifact. Two fields are excluded because they are
*expected* to vary and are not a determinism bug: a wall-clock ingest
timestamp (`generated_at` / `captured_at` / the workbook's "As Of" column)
and an absolute database path recorded for provenance
(`lineups.json`'s `source_db`). With those two excluded, all seven content
artifacts (everything except the per-run completion manifest)
— all ten workbook sheets, all three JSON exports, both HTML pages, the
Captain's Edge workbook — are identical byte-for-byte (HTML/JSON) or
value-for-value (workbook cells) across the two runs.

The completion manifest is intentionally not deterministic: every successful
production run gets a new UUID and UTC timestamps. Its own integration check
instead verifies that it covers every artifact with a real SHA-256 digest.

**`tests/test_pipeline_run_all.py`** — `pipeline_run_all.py` itself had no
test at all. `main()` gained an optional `argv` parameter (matching
`pipeline/__main__.py`'s existing convention) so it can be driven directly
in a test rather than only through `sys.argv`. Covered with
`subprocess.run` mocked out (these steps are a real browser and a real
recursive pytest invocation — nothing to actually run here): step order,
`--skip-scrape` / `--skip-tests`, and — the one that actually matters — a
failing step raises `SystemExit` with that step's own return code and the
chain never reaches the next step (a failed ingest must never be followed
by "successfully" running the test suite, or a captain-facing export).

## What this does NOT cover — real, disclosed gaps

- **`pipeline_run_all.py` is not run as a real subprocess in CI.** The new
  tests prove its own orchestration logic is correct (mocked) and prove the
  pieces it calls work correctly together end-to-end (the integration test,
  calling the same functions directly). Nothing runs the literal script
  start-to-finish in CI, because step 1 is a real login against a live
  third-party site and must not run unattended in CI.
- **Dependencies are not pinned.** `requirements.txt` uses `>=` lower
  bounds only (`pandas>=2.0`, `openpyxl>=3.1`, ...), no upper bounds and no
  lockfile. Two installs months apart can resolve different versions of a
  library the exports depend on for formatting — a real gap in
  "reproducible builds" as usually meant, distinct from the output
  *determinism* verified above (which only checks two runs against the
  *same* installed environment). Deliberately not fixed in this pass: a
  lockfile or pinned upper bounds is a real workflow change (what a
  contributor runs to update a dependency) that deserves a decision, not a
  unilateral change bundled into an integration-testing pass.
- **The scraper itself (`scraper/full_auto_scrape.py`) has no automated
  integration test** — it drives a real browser against a real login. Its
  contract is documented in README-scraper.md; verifying it stays a manual
  "run it against the real site" check.
