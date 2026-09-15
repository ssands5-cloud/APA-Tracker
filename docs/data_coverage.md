# Data Coverage

Data Coverage is the audit view for one real Player-vs-Player matrix scope. It
answers what evidence exists, which players lack skill levels, what sample size
backs each pairing, when the available source snapshots were refreshed, and
which requested facts APA Tracker cannot honestly provide.

The analytics module, HTML tab, Excel exporter, and read-only builder exist at
the current repository tip. Their contracts are documented below. Unified demo
navigation and cross-tab script JSON remain planned.

## Analytics responsibility

`analytics/data_coverage.py` is pure. It accepts an already-built
`PairingEvidenceMatrix` plus caller-supplied refresh timestamps. It performs no
SQL, scraping, roster discovery, evidence classification, probability modeling,
or mutation.

Its public entry point is:

```python
build_report(
    matrix: PairingEvidenceMatrix,
    *,
    standings_refreshed_at: str | None = None,
    career_stats_refreshed_at: Mapping[str, str | None] | None = None,
) -> DataCoverageReport
```

The returned immutable document contains:

```text
DataCoverageReport
  our_team_external_id
  opponent_team_external_id
  format
  session_name
  missing_skill_levels: tuple[MissingSkillLevel, ...]
  evidence_coverage: EvidenceCoverage
  sample_sizes: tuple[SampleSize, ...]
  standings_refreshed_at
  career_stats_refreshed_at
  unavailable_fields
```

### Missing skill levels

`MissingSkillLevel` identifies side (`our` or `opponent`), internal ID,
external ID, and name. A player missing a skill across multiple pairings appears
once, keyed by side and internal ID. Rows sort by side and case-insensitive
name. A missing player is named; it is not merely included in an aggregate.

### Evidence coverage

`EvidenceCoverage` copies the already-reconciled matrix counts for DIRECT,
INDIRECT, UNKNOWN, and total feasible pairings. Percentages use:

```text
label_pct = round(label_count / total_feasible_pairings, 4)
```

When total feasible pairings is zero, all three percentages are null. The
module never reports a misleading 0% or 100% for a zero denominator and never
recomputes a label.

### Sample sizes

One `SampleSize` exists for every matrix pairing, in matrix order. It carries
player/opponent IDs and names, evidence label, current roster skill levels, and
model source. `direct_matches` is the Stage 1 distinct authoritative-match
count for DIRECT only; it is null for INDIRECT and UNKNOWN. The module does not
invent an INDIRECT game count.

### Refresh timestamps

The analytics module carries supplied timestamps through unchanged:

- `standings_refreshed_at` is the real maximum
  `StandingsSnapshot.captured_at` fetched by the builder for the team display
  name because that table has no team ID;
- `career_stats_refreshed_at` maps player external ID to the real maximum
  `PlayerCareerStats.updated_at` across available formats.

Missing source rows stay null/absent. There is no synthetic “today,” viewer-
clock freshness computation, or undocumented stale threshold.

The name-based standings lookup is a disclosed schema limitation. The builder
must warn or fail when the display name is empty or ambiguous; the timestamp
must not be presented as immutable team-ID provenance.

### Fixed unavailable fields

The current module always discloses:

- innings, which are not captured by the APA operations used here;
- per-opponent defensive-shot average, because only a lifetime career value
  exists;
- canonical current-roster identity for an opponent never captured by a real
  roster/TeamStat ingest—the player is absent from the matrix rather than
  assumed absent;
- per-player sync timestamps finer than the standings/career signals above.

Other feature-specific gaps—per-opponent break/run attribution and numeric
Player-vs-Player volatility—remain disclosed in their owning views. Categorical
opponent-risk flags are deliberately outside the product contract, not a
missing-data field to count or label. A future Data Coverage extension may add
new factual gaps only through explicit fields and tests, never by silently
appending renderer text.

## Data acquisition boundary

`scripts/build_data_coverage.py` owns the read-only query/assembly boundary. For
one required opponent/format/session scope it:

1. builds the canonical `PairingEvidenceMatrix`;
2. resolves display names;
3. queries the standings and career refresh signals described above;
4. calls `build_report` once;
5. passes the same report to HTML and Excel renderers;
6. writes `exports/data_coverage.html` and `exports/data_coverage.xlsx`.

It opens SQLite in read-only mode and does not call the schema-creating engine.
The builder must not infer roster rows, repair a stale database, or replace a
missing timestamp.

## Implemented HTML structure

`ui/tabs/data_coverage.py::render` returns a self-contained fragment:

```text
section.dc-tab
├── heading and team/opponent/format/session scope
├── table.dc-coverage
│   ├── DIRECT count and percentage
│   ├── INDIRECT count and percentage
│   ├── UNKNOWN count and percentage
│   └── total feasible pairings
├── missing-skill list
├── table.dc-samples
│   └── one row per feasible pair
├── refresh-date section
└── unavailable-field list
```

The sample table columns are Player, Opponent, Evidence, Direct Matches, Player
SL, Opponent SL, and Model Source. Null is displayed as `No data`. When no
skill is missing, the view explicitly says every matrix player has a real
posted skill; when no career timestamps exist, it says so.

The current HTML hardcodes `100%` on the Total row even when total feasible
pairings is zero, while the three label percentages correctly render `No data`.
That inconsistency is a release blocker: unified demo wiring must render the
zero-total Total percentage as `No data` and add a regression test. It must not
change the analytics report, whose zero-total label percentages are already
null.

The current fragment has no chart or embedded JSON. The unified demo target
wraps it as the Data Coverage tab and may add an accessible stacked
DIRECT/INDIRECT/UNKNOWN count chart above the table. The chart must consume the
delivered counts, repeat them as text, and never recalculate or rank evidence.

For unified-tab integration, the orchestrator safely embeds the report in
`<script type="application/json" id="coverage-data">`. Browser code reads it
once with `textContent`/`JSON.parse`, validates scope and count reconciliation,
and performs display-only filtering. Captured strings use escaped text nodes;
there are no runtime network requests or browser-side analytics.

## Implemented Excel structure

`ui/export_excel_data_coverage.py` always produces a standalone workbook,
including when total feasible pairings is zero, because the zero-coverage audit
result is meaningful.

### `Data_Coverage`

This mixed audit sheet contains, in order:

1. scope identifiers (our team, opponent, format, session);
2. an Evidence Label / Count / Percentage table for DIRECT, INDIRECT, UNKNOWN,
   and Total;
3. standings and per-player career refresh dates;
4. the named missing-skill list (Side, Player, External ID), or an explicit
   none-missing row;
5. the fixed unavailable-field list.

Evidence percentages use `0.0%` number formatting. A zero-total percentage cell
is null. Column widths and header styling are fixed.

### `Sample_Sizes`

This sheet always exists, even with zero pairings. It contains Player,
Opponent, Evidence, Direct Matches, Player SL, Opponent SL, and Model Source,
one row per `SampleSize`. It freezes the header, enables a filter, and uses
fixed widths. A header-only `Sample_Sizes` sheet correctly represents a real
zero-pair audit; it is not a fabricated success dataset.

The workbook contains materialized values only: no formulas, VBA, external
links, hidden helper sheets, volatile dates, content-based auto-sizing, or
renderer-derived status. IDs/timestamps remain text. HTML/Excel parity compares
raw counts, percentages, missing-player identities, sample rows, timestamps,
and unavailable text before display formatting.

## Ordering and UNKNOWN handling

- Evidence rows use fixed DIRECT, INDIRECT, UNKNOWN, Total order.
- Missing skills use analytics order: side, then case-insensitive name.
- Sample sizes preserve matrix order; score/probability does not reorder them.
- Career timestamps sort by external ID in both current renderers.
- UNKNOWN counts and sample rows remain visible. UNKNOWN is not observed 0%, a
  neutral 50%, or a missing row.
- A real numeric zero stays zero; a missing rate/count input remains null with
  `No data` presentation.

## Demo integration

The target navigation sequence is Tonight's Match → Player vs Player → Lineup
Lab → Data Coverage → Exports. The demo orchestrator builds the matrix first,
then builds Data Coverage from that exact matrix before rendering. The same
report feeds:

- the Data Coverage top-level tab;
- `data_coverage.html` and `data_coverage.xlsx`;
- coverage summary links in Tonight's Match, Player vs Player, Lineup Lab, and
  Captain's Edge;
- `demo_manifest.json` row/count/hash checks.

Cross-tab links carry an existing section/filter key only. They may focus the
missing-skill, evidence, refresh, sample-size, or unavailable-field section but
cannot mutate report values or hide the underlying full document.

The current `DataCoverageReport` does not include Lineup Lab assignment
coverage, general schema status, a run ID, or source hashes. Until a reviewed
extension adds those fields, the demo manifest owns those checks and must not
claim they came from `analytics/data_coverage.py`.

## Acceptance and tests

- Unit tests cover missing-skill deduplication, evidence count/percentage
  parity, zero totals, DIRECT-vs-INDIRECT sample semantics, timestamp
  passthrough, and fixed unavailable fields.
- HTML tests cover escaping, visible percentages, named missing skills,
  unavailable disclosures, and honest zero-pair rendering, including the Total
  row regression above.
- Excel tests require both sheets, evidence counts, named missing players,
  percentage formatting, deterministic structure, and a repair-free openpyxl
  round trip.
- Builder tests use a temporary SQLite database and verify read-only source
  queries and both artifact paths.
- Unified-demo tests compare HTML, Excel, embedded JSON, matrix counts, and
  manifest values; hostile text must not escape HTML/script JSON.
- CI uses fixtures/mocks only and makes no live APA request.
