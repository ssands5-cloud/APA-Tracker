# Player vs Player export requirements

## Functional requirements

1. Build one versioned analytics document per real team/opponent/format/session
   scope from canonical current rosters.
2. Export every feasible player/opponent pair exactly once to HTML and Excel.
3. Preserve DIRECT, INDIRECT, and UNKNOWN semantics from
   `analytics.pairing_evidence`.
4. Provide stable drill-down navigation from Tonight's Match and back to the
   relevant scope.
5. Produce identical pair keys and analytics values in both formats.

## Required analytics outputs

- authoritative Stage 1 DIRECT label, distinct-match count, observed rate, and
  source scope;
- `PlayerVsPlayerSummary.total_games`/wins/losses and chronological
  `GameRecord` values from exact-pair history;
- `summary.reliability`, which is
  `analytics.matchups.reliability_weight(total_games)`;
- `skill_prob` mapped from `summary.skill_only_probability`, using the last
  real game's posted skill levels;
- separately sourced/status-labeled `modeled_win_probability`;
- explicit unavailable disclosures for omitted innings, per-opponent defense,
  break/run rate, and numeric volatility;
- whole-history and recent pair trend strings;
- `summary.next_match_projection`, labeled as the same value/status as the
  modeled probability rather than a schedule-aware computation;
- warnings, validation status, schema version, and provenance.

## Integrity requirements

- `DIRECT + INDIRECT + UNKNOWN = total feasible pairings`, by identity.
- `wins + losses = total_games`; distinct DIRECT matches remain a separately
  named Stage 1 measure and need not equal game count.
- observed rates exist only for a Stage 1 DIRECT row.
- reliability uses exactly `total_games/(total_games+3)` inside analytics and
  is never recomputed by a renderer.
- `skill_prob` uses the last recorded pair skills and is not mislabeled current.
- `next_match_projection == modeled_win_probability` exactly, with identical
  experimental validation status and no claim that a meeting is scheduled.
- nullable source gaps remain null; zero is reserved for a measured zero.
- no row is inferred from mutable names or historical participation.

## Presentation requirements

- HTML is UTF-8, offline, escaped, responsive, and keyboard accessible.
- Excel is values-only, deterministic, macro-free, and repair-free.
- UNKNOWN rows are visible by default and show literal `No data` cells.
- Experimental modeled values are visibly separated from observed facts and
  approved skill-only projections.
- Default ordering is structural and deterministic, never “best first.”

## Planned module acceptance

### `analytics/player_vs_player.py`

Already owns the pure pair summary and chronological game values, reusing the
existing Head-to-Head/Matchups functions. It intentionally owns no SQL, roster
join, evidence label, innings/defense/break-run metric, or numeric volatility;
the export adapter must honor that boundary.

### `exports/html_builder.py`

Accepts only the enriched export envelope and render options. It reuses the
existing `ui.tabs.player_vs_player` pair fragment and emits the shell in
`player_vs_player_html_structure.md`, with no SQL or model math.

### `exports/excel_builder.py`

Accepts the same document and emits the workbook described in
`player_vs_player_excel_structure.md`, including a structured no-data return
instead of a placeholder sheet.

### `ui/router.py`

Registers `player-vs-player` after Tonight's Match and before Lineup Lab. Route
parameters use external IDs plus format/session; the router validates them
against the already-built document and never performs a name-based lookup.

### `demo.py`

Calls the analytics build once, serializes the canonical document, sends that
same object to both builders, registers navigation/artifacts, and runs parity
checks. A failure in analytics, either renderer, or parity stops the demo
release. It does not duplicate `pipeline_run_all.py` acquisition/ingest logic.

## Audit and release requirements

- Focused unit tests cover reused formulas, nulls, the break/run
  non-attribution disclosure, stable ordering, and hostile text.
- Integration tests compare HTML/Excel/JSON pair identities and values.
- Fixture CI proves UNKNOWN/no-roster behavior; a fresh authenticated scrape is
  required for a production-data rehearsal.
- The implementation commit must be separate from this design commit and must
  receive an Issue #14 review before any modeled output is called validated.
