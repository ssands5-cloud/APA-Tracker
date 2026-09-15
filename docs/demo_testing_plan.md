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
- Player vs Player Matrix complete row retention, separate distinct-match/game
  counts, stable structural order, and `rows_for_player` filtering.
- Explicit Player vs Player recognized-game arithmetic, history reliability,
  last-game skill-only probability, identical modeled/projection alias,
  unavailable innings/defense/break-run/volatility disclosures, and stable game
  order.
- Unified-tab routing, valid/invalid pair-key selection, back/forward state,
  Pair/Matrix keyboard behavior, and escaped script-JSON schema validation.
- Opponent Risk Profile source mapping, build-time/availability labels, and
  descriptive ordering. Tests assert that any selected sort names one visible
  source field/direction, places nulls last, and uses canonical identity
  tie-breaks.
- Schema and presentation tests assert that Avoid/Target, danger/favorable,
  risk-tier, traffic-light, and equivalent categorical fields/labels/styles are
  absent. Modeled probability cannot drive the default order or a composite.
- Data Coverage missing-skill deduplication/order, matrix count/percentage
  parity, zero-total null behavior, DIRECT-vs-INDIRECT sample semantics,
  timestamp passthrough, fixed unavailable fields, and immutable inputs.
- Data Coverage HTML zero-pair regression: DIRECT/INDIRECT/UNKNOWN and Total
  percentages must all render `No data`, never a hardcoded 100%.
- Lineup Lab score, maximum matching, unassigned reconciliation, legality gate,
  and exact-search bound.

### Pipeline integration

- Run the committed sample fixture through real ingest and real exporters.
- Assert that every expected artifact is created and loadable.
- Run the identical input twice into two scratch directories and compare all
  deterministic fields; exclude only documented timestamps and absolute paths.
- Compare Matrix HTML, Excel, and optional JSON by pair/game key and pre-rounding
  value; assert distinct team-match count is not conflated with recognized game
  count. Compare each embedded explicit-pair detail with its source matrix row
  and nested chronological games.
- Verify all outputs share the same database/config/source manifest.
- Verify Captain's Edge risk-profile values equal the selected matrix row and
  that HTML/script JSON/Excel agree on the active descriptive sort field,
  direction, null placement, and canonical tie-break order.
- Compare Data Coverage HTML, Excel, script JSON, and manifest by scope and pair
  order; reconcile evidence counts/percentages, missing-skill identities,
  sample sizes, refresh timestamps, and unavailable text before rounding.
- Run the optional scrape-and-ingest CLI entirely against mocked transports and
  fixtures; assert live network use is impossible in CI.

### Security and robustness

- Inject hostile names, IDs, model-source strings, and error messages into
  fixture rows; assert no HTML/script break-out.
- Confirm no external network URL or token appears in HTML, JSON, XLSX, logs,
  or the manifest.
- Exercise token-stdin/environment auth selection, redaction, live/fixture mode
  exclusivity, output containment, and a hard network-deny guard.
- Exercise missing roster, ambiguous membership, stale schema, empty history,
  invalid result, conflicting same-match fact, and overlarge assignment paths.
- Exercise zero-pair, complete-skill, missing-skill, mixed-evidence,
  UNKNOWN-only, missing-timestamp, and hostile-text Data Coverage fixtures.

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
reconcile, an evidence percentage uses a denominator other than total feasible
pairings, Pair/Matrix route state is inconsistent, Captain's Edge disagrees
with the selected row, an unvalidated risk flag is non-null, or the page
contains a fabricated fallback. A fixture CI run may
pass with unavailable rosters when that is the fixture's truthful state; that
is a guard-path assertion, not evidence that the production snapshot is ready.
