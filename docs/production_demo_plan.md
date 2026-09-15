# Production demo plan

The production demo is assembled from one fresh authenticated scrape, one
regenerated database, and a versioned set of static exports. The detailed
architecture, regeneration, test, release, and walkthrough contracts live in
the adjacent `demo_*.md` documents.

## Unified Player vs Player section

### Placement in the flow

The whole matrix appears after Tonight's Match establishes the real scope. An
explicit comparison is opened from one matrix row before Lineup Lab shows an
assignment:

```text
Tonight's Match → Player vs Player (Matrix View → Pair View)
→ Lineup Lab → Data Coverage → Exports
```

This order makes the complete evidence surface inspectable before the
assignment and gives one pair's history a clear drill-down boundary. UNKNOWN
rows stay visible in the matrix.

### Trigger

The captain opens one `player-vs-player` navigation tab from the selected
Tonight's Match scope. Scope-only navigation opens Matrix View. A row selection
changes the same route to `view=pair` and carries both external player IDs plus
team/opponent/format/session. `ui/router.py` resolves only against prebuilt
matrix rows; names are display metadata.

### Display

Matrix View opens in canonical structural order with every feasible pair. Its
rows come from `analytics/player_vs_player_matrix.py`. Pair View uses the
selected row's nested `PlayerVsPlayerSummary` from
`analytics/player_vs_player.py` and shows its recognized-game record, history
reliability, last-recorded skill probability, separately labeled experimental
model output, whole/recent trends, named data gaps, and identical projection
alias. No export-layer combined score exists.

The demo labels the scope split: Stage 1 evidence is selected-format/session,
while the current explicit summary uses all chronological history returned for
the two IDs. Individual games retain their real format/session. The UI does not
imply a filter that the query did not apply.

### Export

`demo.py` registers the implemented `player_vs_player.html` and
`player_vs_player.xlsx` matrix artifacts from one matrix result. The HTML
embeds the separately owned explicit-pair fragment at each row's Details
anchor; the workbook carries all matrix rows and real game history. The
manifest records both hashes, row counts, and pair keys.

### Validation

The build first verifies matrix pair-key reconciliation and HTML/Excel parity,
then verifies each embedded explicit-pair detail against its source matrix row
and nested games. Null semantics, source tags, structural order, escaping,
workbook readability, and prohibited formulas/macros/external links are gates.
Any mismatch blocks presentation.

## Captain's Edge integration

Captain's Edge consumes the same immutable Player vs Player matrix document; it
does not call either analytics module again. For the currently selected
opponent/player context it may render an **Opponent Risk Profile** containing
evidence label, sample counts, observed record/rate, current and last-recorded
skills, reliability, trends, experimental model status, missing-data notes, and
a link into Pair View.

`Recommended Avoid` and `Recommended Target` map to reserved `danger_flag` and
`favorable_flag` fields. At present both are unavailable because the history
model has no held-out rematch cohort and no approved decision threshold. The
production demo must show **Not available — threshold not validated**, not
derive flags from modeled probability, volatility, or an invented cutoff.

A future flag may be displayed only after a reviewed specification records the
input field, threshold, training/holdout cohorts, calibration and decision
metrics, version, approval, and effective date. Captain's Edge consumes the
delivered boolean/status; it never evaluates the threshold in a renderer.

The profile is a build-time snapshot. It changes only on regeneration and may
be stale after roster, skill, schedule, or availability changes. Availability
filters may hide an unavailable player from candidate views, but must not erase
the canonical source row or rewrite its historical evidence. The UI shows the
capture time and availability state beside the profile.

## Data Coverage integration

After Player vs Player Matrix is built, `analytics/data_coverage.py` produces
one audit document from that matrix plus real standings/career refresh
timestamps. The demo renders that document as the
Data Coverage tab and `data_coverage.html`/`.xlsx`. Tonight's Match, Pair View,
Matrix View, Lineup Lab, and Captain's Edge link to metric keys in the embedded
report; they do not calculate their own coverage percentages.

The presenter uses this tab to inspect missing skills,
DIRECT/INDIRECT/UNKNOWN totals, per-pair sample size, source refresh times, and
known unavailable fields. General roster/schema and Lineup Lab assignment
reconciliation remain manifest checks until the coverage analytics contract is
extended. A zero denominator remains null. Failure to construct or reconcile
the report blocks the production demo.

## Optional scrape and ingest

The full demo builder may invoke the opt-in live acquisition contract in
`scrape_and_ingest_pipeline.md` before building artifacts. Live mode requires an
explicit flag and a safe credential source; fixture mode denies network access.
Both create a fresh database, reconcile it, and verify it before export. An
authentication or verification failure never falls back to a stale snapshot.

## Current blockers

- The analytics split and standalone matrix exporters exist; the unified tab,
  router state, script-JSON envelope, Captain's Edge profile, and `demo.py`
  integration remain to be implemented and audited.
- A fresh authenticated scrape and regenerated schema are still required for a
  rich production dataset.
- Data Coverage analytics and standalone renderers exist in the implementation
  lane; unified tab/script-JSON/demo-builder wiring remains to be completed and
  audited.
- The full history-plus-skill modeled probability and its identical
  `next_match_projection` alias are display-only until real held-out rematch
  validation exists; the current module does not establish a scheduled meeting.
- Per-opponent innings and defense averages have no captured APA source and
  must remain explicit gaps.
- Break/run is captured per team match, not per opponent, and numeric volatility
  is not produced by the current pair analytics contract; both remain explicit
  export gaps.
- The current matrix HTML needs its numeric-volatility and held-out-rematch
  disclosures plus keyboard-accessible sorting/responsive containment before
  release; the workbook needs a documented decision for fields present only in
  the HTML detail contract.
- Data Coverage unified wiring must correct the current zero-pair HTML Total
  row (which prints 100%) and disclose/guard its name-based standings timestamp
  lookup before production presentation.
