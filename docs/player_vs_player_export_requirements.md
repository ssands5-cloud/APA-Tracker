# Player vs Player export requirements

## Ownership and presentation split

| Product | Owner | Implemented presentation |
| --- | --- | --- |
| Explicit pair comparison | `analytics/player_vs_player.py` | `ui/tabs/player_vs_player.py` fragment embedded at each matrix detail anchor |
| Whole-matrix drill-down | `analytics/player_vs_player_matrix.py` | `player_vs_player.html` and `player_vs_player.xlsx` |

The pair module answers one explicit comparison. The matrix module composes a
supplied Stage 1 matrix and supplied exact-pair histories into one stable row
per feasible pair. Neither renderer owns queries, roster construction,
analytics formulas, or cross-product logic.

## Functional requirements

1. Build one matrix document for a real team/opponent/format/session scope.
2. Preserve every feasible pair exactly once, including UNKNOWN.
3. Open one explicit-pair comparison from a matrix row using stable external
   IDs plus scope, never names.
4. Export the matrix to HTML and Excel while preserving the explicit-pair
   component boundary inside the HTML details.
5. Keep HTML and Excel matrix rows and games in parity.

## Required outputs

The matrix row consumes its Stage 1 label, distinct-match count, observed rate,
current identities/skills, and the nested explicit `PlayerVsPlayerSummary`.
The summary supplies recognized record, average skill delta,
`reliability_weight`, `skill_only_probability`, `modeled_win_probability`,
whole/recent trends, `next_match_projection`, and chronological game history.

Exports must disclose that innings, per-opponent defense, per-opponent
break/run, and numeric volatility are unavailable. They must also disclose
that the full model/projection history term has no held-out rematch validation.
The current HTML covers the first three source gaps in its explicit-pair note
but not numeric volatility or the full held-out-validation statement; these are
demo-integration blockers, not permission to omit or fabricate values.

The unified export deliberately defines no `danger_flag`, `favorable_flag`,
Avoid/Target, threshold-version, or equivalent categorical fields. Captain's
Edge consumes the same descriptive values and may sort by one visible field,
but it cannot create a composite score or category.

## Integrity requirements

- Matrix pair keys equal Stage 1 expected pair keys exactly.
- `DIRECT + INDIRECT + UNKNOWN` equals total feasible pairs.
- `wins + losses == total_games`; distinct matches need not equal games.
- Observed rates are not synthesized for INDIRECT or UNKNOWN rows.
- `skill_only_probability` is labeled as last-recorded, not current-roster.
- `next_match_projection == modeled_win_probability` and shares its
  experimental status.
- Null stays null through the document; `No data` is presentation text only.
- No metric blend, fallback 50%, score-based ordering, or export-only heuristic
  is permitted.

## Integration plan

The existing `ui/export_html_player_vs_player.py` and
`ui/export_excel_player_vs_player.py` accept the tuple of
`PlayerVsPlayerExportRow`. The HTML renderer delegates each detail to the
existing pair renderer; the Excel renderer materializes matrix and game rows.
Future `exports/html_builder.py` and `exports/excel_builder.py` demo integration
must delegate to these renderers rather than duplicate them. Shared formatting
helpers may be reused, but analytics and SQL may not.

`ui/router.py` adds one Player vs Player navigation entry. It opens Matrix View
for a scope and resolves Pair View to an existing row/detail key. `demo.py` invokes
`scripts/build_player_vs_player_export.py` or the same build functions once,
registers `player_vs_player.html`/`.xlsx`, and validates them. It must not loop
over `summarize` independently or rebuild the matrix in an exporter.

## Acceptance requirements

- Unit tests cover complete row retention, separate match/game counts, empty
  history, unavailable disclosures, and structural ordering.
- Integration tests compare HTML/Excel/JSON by pair and game key before
  rounding and exercise hostile text.
- Workbooks load without repair and contain no formulas, macros, hidden sheets,
  or external links.
- A parity, identity, provenance, or null-semantics failure blocks the demo.
- The implementation must be reviewed separately under Issue #14 before an
  experimental modeled value is described as validated advice.
