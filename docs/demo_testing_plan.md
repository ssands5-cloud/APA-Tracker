# Demo testing plan

The demo test plan proves both the happy path and the integrity of an honest
no-data result. It is design-only until the orchestration script exists.

## Test categories

### Unit and contract tests

- Argument parsing, stable exit codes, output containment, and manifest schema.
- Fixture manifest redaction and auth-operation exclusion.
- Database model/schema completeness, foreign-key enforcement, and stale-schema
  detection including `team_external_id`.
- Pairing labels, distinct-match counting, scope filtering, and exact matrix
  reconciliation.
- Player vs Player recognized-game arithmetic, history reliability, last-game
  skill-only probability, identical modeled/projection alias, unavailable
  innings/defense/break-run/volatility disclosures, and stable pair/game order.
- Lineup Lab score, maximum matching, unassigned reconciliation, legality gate,
  and exact-search bound.

### Pipeline integration

- Run the committed sample fixture through real ingest and real exporters.
- Assert that every expected artifact is created and loadable.
- Run the identical input twice into two scratch directories and compare all
  deterministic fields; exclude only documented timestamps and absolute paths.
- Compare Player vs Player HTML, Excel, and optional JSON by pair/game key and
  pre-rounding value; assert distinct team-match count is not conflated with
  recognized game count.
- Verify all outputs share the same database/config/source manifest.

### Security and robustness

- Inject hostile names, IDs, model-source strings, and error messages into
  fixture rows; assert no HTML/script break-out.
- Confirm no external network URL or token appears in HTML, JSON, XLSX, logs,
  or the manifest.
- Exercise missing roster, ambiguous membership, stale schema, empty history,
  invalid result, conflicting same-match fact, and overlarge assignment paths.

### Live smoke and manual review

- With a fresh authenticated capture, run the real browser/scrape path once in
  a controlled rehearsal environment.
- Open each HTML page in Chromium and verify controls, keyboard navigation,
  narrow-window layout, workbook links, and visible no-data language.
- Manually follow the walkthrough and record the commit, capture time, and
  artifact hashes in the release evidence.

## Acceptance gates

No demo is presented when a required phase fails, the database is stale, an
artifact is missing without a documented reason, the matrix counts do not
reconcile, or the page contains a fabricated fallback. A fixture CI run may
pass with unavailable rosters when that is the fixture's truthful state; that
is a guard-path assertion, not evidence that the production snapshot is ready.
