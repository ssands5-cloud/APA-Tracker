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
- Team Strength offense pooling, defense-proxy PF/PA orientation, fifth-player
  depth floor, equal-component composite, full-component null gate, formula
  version, and invalid-denominator rejection.
- Season Projection log5 branches, one-side/no-rate behavior, expected totals,
  real-schedule retention, identity ambiguity, and standings-history
  deduplication.
- Trend Analyzer independently verifies least-squares slope and sample standard
  deviation, full-session versus last-20 spans, exact five-observation/±0.05/
  0.40 boundaries, `trend_score` denominator floor/null gate/sign, and literal
  descriptive indicator labels.
- Opponent Volatility verifies `100 * sigma / (1 + sigma)`, zero/null
  distinction, median/coverage, exact player-format-session join, and absence
  of pair-specific or categorical-risk claims.
- Match Difficulty verifies `100 * (1 - current_skill_probability)` from the
  shared validated function, identical ordered matrix keys, feasible/numeric/
  null count reconciliation, the versioned continuous palette interpolation,
  and hatched null cells. Tests reject metric thresholds, categorical fields,
  reliability weights, aggregate difficulty indices, and score-driven order.
  History, evidence count/class, modeled probability, trend, volatility, and
  Team Strength must not affect a cell.
- Live Assistant scope/hash validation, availability re-solve or exact static
  scenario selection, assignment/unassigned/legality reconciliation, note
  template provenance, and separation of captain input from source facts.
- Isolation tests prove Opponent Volatility never imports legacy
  opponent-scouting danger categories and the Live Assistant never consumes
  strongest/danger/high-risk summary rankings as a substitute for its source
  documents.

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
- Compare Team Strength HTML/XLSX/JSON raw components and denominators; compare
  Season Projection schedule/source-status/probability/expected totals; compare
  Trend/Volatility keys, spans, nulls, and values before rounding.
- Compare heatmap keys/raw probabilities/raw complements/null reasons against
  the complete matrix across analytics, script JSON, HTML, Excel grid, and
  audit sheet before rounding. Verify that the Live Assistant references the
  same immutable documents rather than recalculating them.
- Cross-feature isolation tests vary both Team Strength reports while holding
  matrix rows constant and prove every heatmap value, count, order, and color
  is unchanged. A mismatched Team Strength run/hash must hide only the context
  card, not rewrite or suppress the heatmap.
- Run Full Production Demo Builder fixture mode twice and compare deterministic
  bundle content. Verify the launcher refuses absent/invalid READY, manifest,
  checksum, or database-hash state.
- Assert database-writing trend population finishes before the builder locks
  the source hash, and no later analytics/export phase opens SQLite writable.
- Assert manifest and checksums exist and revalidate before READY is written;
  interrupt each finalization step and prove the launcher refuses the partial
  run.
- Assert the launcher discovers the run only from the versioned completion
  event or explicit `--verified-run`, never from human log text, directory
  recency, or a filename glob.

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
- Exercise all-null/all-zero/one-point/exactly-20/more-than-20 trend histories,
  missing Team Strength components, no remaining schedule, ambiguous standings
  names, and mismatched Live Assistant run/scope hashes.
- Assert fixture CI cannot use live builder/launcher flags, DNS, HTTP, browser
  open, or non-loopback serving.

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
with the selected row, a categorical opponent-risk field exists, Team Strength
renormalizes missing components, a heatmap cell uses the blended model or Team
Strength, any difficulty threshold/weighted aggregate exists, trend
spans/gates disagree, Season Projection drops a remaining match, the Live
Assistant mixes run scopes, or the page contains a fabricated fallback. A
fixture CI run may pass with unavailable rosters when that is the fixture's
truthful state; that is a guard-path assertion, not evidence that the
production snapshot is ready.
