# Match Difficulty Heatmap

The Match Difficulty Heatmap is a descriptive visualization inside the unified
Player vs Player **Matrix View**. It converts the project's validated
current-skill-only win probability into its algebraic complement for every
feasible matrix pair. It is not a new prediction model, ranking system, lineup
selector, or recommendation surface.

The proposed analytics owner is `analytics/match_difficulty_heatmap.py`. It
consumes the already-built, canonically ordered rows from
`analytics/player_vs_player_matrix.py`; it does not query SQLite, rebuild the
pairing matrix, or read generated exports. HTML and Excel consume the same
immutable heatmap report and perform no analytics.

## Governing constraints

1. The sole numeric driver is
   `analytics.head_to_head.skill_only_win_probability`, using the two current
   roster skill levels carried by the Player-vs-Player matrix row.
2. `docs/prediction_validation.md` is the validation record for that driver.
   The history-blended `win_probability` / `modeled_win_probability` has no
   held-out rematch validation and is not a heatmap input.
3. The heatmap creates no thresholds, difficulty bands, categorical flags, or
   score-driven default order. Words such as easy, hard, danger, favorable,
   Avoid, and Target are not heatmap outputs.
4. DIRECT, INDIRECT, and UNKNOWN remain the Stage 1 evidence labels. They are
   shown separately and never change the numeric difficulty value.
5. Team Strength is a separate descriptive document. It may appear beside the
   heatmap as context after scope reconciliation, but it never enters a cell,
   aggregate, color, order, or recommendation.

These constraints are part of the public contract, not presentation advice.
Any implementation that weakens one of them is a different feature and
requires a new validation and documentation review.

## Scope and source contract

| Input | Authoritative source | Heatmap use | Required guard |
| --- | --- | --- | --- |
| Feasible pair rows | ordered `PlayerVsPlayerExportRow` values from `analytics.player_vs_player_matrix.py` | exactly one heatmap cell per matrix pair | pair keys, order, team IDs, format, and session must match the matrix exactly |
| Current skill levels | `player_skill_level` and `opponent_skill_level` on that row | only numeric inputs | either value missing produces a null cell |
| Evidence | `evidence_label` and `direct_matches` on that row | visible provenance only | copied unchanged; never used as a weight |
| Skill-only probability function | `analytics.head_to_head.skill_only_win_probability` | approved probability driver | call the public function; do not duplicate its constants or formula |
| Team Strength | independently built `TeamStrengthReport` for each team | adjacent, separately labeled context only | same run/team/session scope and source hash; never passed to the heatmap formula owner |

A missing current skill does not imply UNKNOWN evidence. DIRECT, INDIRECT, or
UNKNOWN cells can be null when either current skill is absent. Conversely, an
UNKNOWN pair with both current skills can have a numeric current-skill value.
The evidence state and metric-availability state remain independent.

## Validated descriptive metric

For a row with both current skills:

```text
current_skill_probability =
    skill_only_win_probability(player_skill_level, opponent_skill_level)

match_difficulty = 100 * (1 - current_skill_probability)
```

`match_difficulty` is the probability complement expressed on a 0–100 numeric
scale. It contains no information beyond the validated current-skill-only
probability: a larger number means only that the shared function assigns the
selected player a lower current-skill-only win probability. It does not mean
"hard," "dangerous," "avoid," or any other class or recommendation.

When either current skill is missing, both `current_skill_probability` and
`match_difficulty` are null and `null_reason` names the missing input. Null is
never converted to 0, 50, a roster average, or a value derived from history.
Raw analytics values are retained for parity; renderers may round a displayed
number only after parity checks.

The heatmap does not calculate reliability weights, row difficulty indices,
column difficulty indices, matrix difficulty indices, or weighted means. Those
would introduce new, unvalidated aggregations. Coverage is reported only as
auditable counts: feasible cells, numeric cells, and null cells.

## Analytics output

```text
MatchDifficultyCell
  player_id, player_external_id, player_name, player_skill_level
  opponent_id, opponent_external_id, opponent_name, opponent_skill_level
  evidence_label, direct_matches
  current_skill_probability
  match_difficulty
  formula_version, palette_version
  null_reason

MatchDifficultyReport
  our_team_external_id, opponent_team_external_id
  format, session_name
  source_manifest_id, source_database_sha256, captured_at
  formula_version
  cells[]                 # same keys and order as PlayerVsPlayerExportRow
  feasible_cell_count
  numeric_cell_count
  null_cell_count
  unavailable_reasons[]
```

The report is immutable. Its formula version is
`match-difficulty-v1-current-skill-complement` and its presentation scale is
`match-difficulty-blue-linear-v1`. It contains no Team Strength values,
history-blended probability, trend, volatility, observed win rate, reliability
weight, recommendation, or categorical difficulty field.

The implementation boundary should remain narrow:

```python
build_report(
    rows: Sequence[PlayerVsPlayerExportRow],
    *,
    source_manifest_id: str,
    source_database_sha256: str,
    captured_at: str,
) -> MatchDifficultyReport
```

The builder rejects duplicate pair keys or mixed scope. It preserves input
order and proves `numeric_cell_count + null_cell_count == feasible_cell_count`.

## Player-vs-Player Matrix integration

The heatmap is a Matrix View visualization, not a third subview or a top-level
tab. The production builder follows this order:

```text
PairingEvidenceMatrix + exact pair histories
  → analytics/player_vs_player_matrix.py
  → ordered PlayerVsPlayerExportRow values
  → analytics/match_difficulty_heatmap.py
  → ordered MatchDifficultyCell values with identical pair keys
  → unified Player vs Player HTML / Excel / script JSON
```

The same matrix rows feed the existing table and Pair View details. Activating
a heatmap cell opens the exact pair key in Pair View and preserves Matrix View
filters, axis order, and scroll position. The browser selects existing values;
it never calls the probability function or computes the complement.

Default axes follow the matrix's canonical player/opponent identity order.
Presentation controls may sort by visible name or current skill only, with
nulls last and external ID tie-breaks. Difficulty, evidence class, observed
record, modeled probability, trend, volatility, and Team Strength do not drive
default axis order.

## Team Strength integration

Team Strength remains owned by `analytics/team_strength.py` and its own
immutable `TeamStrengthReport`. The orchestrator may place two separately
labeled Team Strength context cards above or beside Matrix View and provide a
link to the Team Strength tab. Before doing so it must reconcile run ID, source
database hash, session, and the corresponding team external ID.

The cards retain the Team Strength document's own formula version, component
denominators, proxy label, null gate, and descriptive-only warning. A missing
or mismatched report displays `No data` or an unavailable reason; it never
blocks otherwise valid heatmap cells and never causes the heatmap module to
substitute a value. Team Strength values are not copied into
`MatchDifficultyReport` or `Match_Difficulty_Data`; the demo manifest links the
two independent documents by scope and hash.

## HTML structure

The heatmap extends `section#pvp-matrix-view` in the unified Player vs Player
tab:

```text
section#pvp-matrix-view
├── scope, provenance, validation-status, and descriptive-only notice
├── region#pvp-team-strength-context
│   ├── our-team context card or No data
│   ├── opponent-team context card or No data
│   └── link to Team Strength evidence
├── heatmap coverage counts: feasible / numeric / null
├── figure#pvp-difficulty-heatmap
│   ├── continuous numeric legend over the fixed 0–100 domain
│   └── one focusable cell per feasible matrix pair
├── table#pvp-difficulty-text-alternative
├── existing evidence-coverage chart and matrix table
└── formula, validation, source, and unavailable-data disclosures
```

Each numeric cell prints the displayed value and exposes an accessible label
with both identities, both current skills, evidence label, raw current-skill
probability, and raw difficulty. Evidence uses a separate text/icon or border
pattern. A null cell is gray-hatched and says `No data` with its reason; it is
not colored at any position on the numeric scale.

The color ramp is continuous and decorative. It uses the fixed probability
domain, not data quantiles or semantic cutoffs. To make HTML and Excel
deterministic, both interpolate linearly with `t = match_difficulty / 100`
between RGB `(239, 243, 255)` at 0 and RGB `(8, 81, 156)` at 100. Each channel
uses `floor(interpolated_channel + 0.5)`, avoiding language/runtime rounding
differences. No interval creates a named or behavioral class. Numeric text
appears on a neutral high-contrast badge, so text color does not require a
difficulty cutoff. The text-alternative table remains fully usable without
color.

## Excel structure

The heatmap extends the existing `player_vs_player.xlsx`; it does not create a
parallel workbook.

### `Match_Difficulty_Heatmap`

Our players are rows and opponents are columns in canonical identity order.
Frozen row/column headers show names, external IDs, and current skills. Numeric
cells contain raw 0–100 values and the same continuous, versioned presentation
color interpolation as HTML. Null cells contain literal `No data` and a null
reason is available through the paired audit sheet. There are no formulas,
conditional-format rules, or threshold legends.

### `Match_Difficulty_Data`

One row per feasible pair, in matrix order, with this fixed column sequence:

1. Session
2. Format
3. Our Team External ID
4. Opponent Team External ID
5. Player ID
6. Player External ID
7. Player Name
8. Player Current SL
9. Opponent ID
10. Opponent External ID
11. Opponent Name
12. Opponent Current SL
13. Evidence Label
14. Direct Matches
15. Current-Skill Probability
16. Match Difficulty
17. Formula Version
18. Null Reason

IDs remain text. Numeric probability/difficulty values remain numeric. The
workbook is values-only, macro-free, and contains no external links, hidden
helpers, volatile values, renderer formulas, Team Strength duplication, or
content-dependent ordering.

## Validation and audit gates

- For every numeric cell, compare the raw probability with a direct call to
  `skill_only_win_probability` and the raw difficulty with its exact
  complement before display rounding.
- Prove matrix-row keys and heatmap-cell keys are identical, unique, complete,
  and in the same order.
- Prove missing skill on either side yields null for every evidence class;
  prove UNKNOWN with both skills can remain numeric.
- Prove changing DIRECT history count, evidence label, observed record,
  modeled probability, trend, volatility, or either Team Strength report does
  not change any cell value or heatmap ordering.
- Reject any reliability weight, aggregate difficulty index, threshold list,
  categorical difficulty field, score-driven default order, or renderer-side
  metric calculation.
- Compare analytics, script JSON, HTML, the Excel grid, and the audit sheet by
  pair key and raw value before rounding or color interpolation.
- Verify coverage counts reconcile, null reasons survive every surface, HTML
  is escaped and self-contained, and the workbook opens without repair.
- Record the formula version, palette version, validation-report version,
  source hash, pair count, numeric/null counts, and artifact hashes in the demo
  manifest.

Any parity, scope, validation-status, or audit failure marks the heatmap
unavailable and blocks a production bundle in which it is required. The system
does not fall back to the history-blended model, an older artifact, or 50/50.

## Current status and implementation handoff

This document is the reviewed implementation contract. The heatmap analytics,
Matrix View rendering, Excel sheets, builder registration, manifest fields,
and tests are not yet implemented.

| Planned file | Responsibility |
| --- | --- |
| `analytics/match_difficulty_heatmap.py` | build the immutable cell report from ordered Player-vs-Player matrix rows; own the complement and counts only |
| `ui/tabs/player_vs_player_unified.py` | render the report inside Matrix View and compose separate Team Strength context without recalculation |
| `ui/export_html_player_vs_player.py` | include the same Matrix View heatmap/text alternative in the standalone HTML artifact |
| `ui/export_excel_player_vs_player.py` | add the two values-only heatmap parity sheets to the existing workbook |
| Player-vs-Player/full-demo builder path | build the matrix once, build the heatmap once, reconcile independent Team Strength scope, and register parity/manifest results |

The demo opens Matrix View, reads the descriptive-only notice and continuous
numeric legend, activates one measured cell to open Pair View, returns with
state intact, and shows both an UNKNOWN-evidence numeric cell and a missing-
skill `No data` cell when the snapshot contains them. Team Strength is then
opened as independent evidence, not as an explanation or adjustment of any
heatmap cell.
