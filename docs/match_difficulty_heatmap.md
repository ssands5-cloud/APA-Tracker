# Match Difficulty Heatmap

**Draft for review.** No design document existed for this module before this
draft (confirmed by searching every filename variant in `docs/`); nothing here
has been implemented. It is written to the same rigor as the other analytics
design docs in this repository (`docs/team_strength.md`,
`docs/opponent_volatility.md`) and is intended for review by the documentation
lane before any code is written.

The Match Difficulty Heatmap is a proposed grid view over one already-built
`analytics.pairing_evidence.PairingEvidenceMatrix`: our canonical roster on one
axis, the opponent's canonical roster on the other, one descriptive difficulty
value per feasible cell. It introduces no new predictive model. Every number
it shows already exists and is already validated elsewhere in this project;
this document composes them into a grid and adds no threshold, category, or
color tier that is not already established.

## Why this doc is conservative

Two real constraints from Issue #14's own findings bound every choice below:

- `analytics.head_to_head.win_probability` (the history-blended estimate) is
  **not validated for ranking or selection** -- `docs/prediction_validation.md`
  records zero held-out predictions for the DIRECT history term, because every
  one of the 106 recorded real pairings has met exactly once. This is why
  Stage 3 Lineup Lab scoring and `analytics/opponent_risk_profile.py` both use
  only `analytics.head_to_head.skill_only_win_probability`, which IS validated
  (Brier 0.2416 vs. 0.25 baseline, 56.6% accuracy over the same 106 outcomes).
  This document follows that same precedent and uses skill-only probability
  exclusively for the numeric cell value. `modeled_win_probability` is never
  read, never displayed, and never blended in.
- No fitted or eyeballed cutoff exists for what counts as "hard" or "easy."
  Every categorical Avoid/Target/danger/favorable flag proposed elsewhere in
  this project has been declined for exactly this reason (§13 of
  `docs/captain_first_edge_experience.md`). This document produces a
  continuous descriptive number and an evidence label -- never a bucket.

## Scope and source contract

| Input | Source | Use | Required guard |
| --- | --- | --- | --- |
| Feasible pairs | `PairingEvidenceMatrix.pairings` | one row per (our player, opponent player) already computed by Stage 1 | exact team/format/session scope already enforced by `build_pairing_evidence_matrix` |
| Current skill levels | `PairingEvidence.player_skill_level` / `.opponent_skill_level` | the only input to the cell's numeric value | either side missing means the cell has no numeric value -- never a guessed mid skill |
| Evidence label | `PairingEvidence.evidence_label` | shown beside the number, never folded into it | DIRECT / INDIRECT / UNKNOWN exactly as Stage 1 classified it |
| DIRECT sample | `PairingEvidence.direct_evidence_count` | shown as context; also the reliability weight's only input | 0 for INDIRECT/UNKNOWN, real count for DIRECT |
| Team Strength | `analytics.team_strength.TeamStrengthReport` (both teams, already built) | separate summary context alongside the grid, never blended into a cell | each team's own report, own `unavailable_reasons` |

The heatmap owner is the proposed `analytics/match_difficulty_heatmap.py`. It
accepts an already-built `PairingEvidenceMatrix` and, optionally, both teams'
already-built `TeamStrengthReport`. It queries nothing, computes no head-to-head
history itself beyond calling the existing `skill_only_win_probability`
function, and does not modify `analytics/pairing_evidence.py`,
`analytics/lineup_lab.py`, or `analytics/opponent_risk_profile.py`.

## Cell value

For a feasible pair with both skill levels known:

```text
difficulty = 100 * (1 - skill_only_win_probability(player_skill_level, opponent_skill_level))
```

`skill_only_win_probability` is `analytics.head_to_head`'s own validated
function (Log5-derived from current skill levels only). Subtracting from 1
reframes it from "our player's win probability" to "how hard this matchup is
for our player" on the same validated 0-100 scale -- a relabeling, not a new
formula. `difficulty` is `None` when either skill level is missing (an
UNKNOWN-evidence pairing under Stage 1's own classification); it is never
imputed from a league average or a neutral 50.

## Evidence label and reliability weight

Each cell also carries, unchanged from Stage 1:

- `evidence_label` (DIRECT / INDIRECT / UNKNOWN);
- `direct_evidence_count` (0 when not DIRECT);
- `reliability_weight = 1 + direct_evidence_count` -- the same standard
  weighted-mean weight `analytics/opponent_risk_profile.py` already uses (not
  a new statistical model): baseline 1 for INDIRECT/UNKNOWN, growing with real
  recorded history for DIRECT pairs, never reaching zero.

These are descriptive metadata about how much evidence backs the cell. They
are never multiplied into `difficulty` itself -- the numeric value stays the
validated skill-only percentage regardless of sample size; the UI shows both
side by side so a viewer can judge confidence without the module hiding it
inside a single blended number.

## Roster-level and team-level summaries

For one of our players against the full opponent roster (a row summary):

```text
row_difficulty_index = reliability-weighted mean of that row's real difficulty values
                      = sum(reliability_weight_i * difficulty_i) / sum(reliability_weight_i)
                        over cells with a real (non-null) difficulty_i
                      = None when no cell in the row has a real difficulty
```

The same reliability-weighted mean, over all real cells in the matrix, gives a
`matrix_difficulty_index` -- one descriptive number for "how hard this whole
matchup looks," always shown alongside its coverage (`real cells / feasible
cells`) so a thin matrix is never presented as equivalent to a well-evidenced
one. Column (per-opponent-player) summaries use the same formula across a
column. All three summaries are optional context; the per-cell grid remains
the primary, always-visible view and is never hidden behind a summary number.

## Team Strength context (not blended)

Both teams' `TeamStrengthReport.team_strength_index` (and its three
components) may be shown as a separate summary card beside the grid -- for
example "Our Team Strength: 62.4 · Opponent Team Strength: 58.1." This is
purely contextual. It is never averaged, multiplied, or otherwise combined
with any cell's `difficulty` value or with `matrix_difficulty_index`: Team
Strength is a team/session-level descriptive index built from entirely
different real inputs (pooled win rate, score-containment proxy, depth floor)
and combining it with a pairwise skill-only estimate would be a new,
unvalidated blended model -- exactly what this project has repeatedly declined
to invent. A team missing its composite (per `docs/team_strength.md`'s
all-or-nothing rule) shows `No data` in this card; the grid itself is
unaffected.

## Analytics output

```text
MatchDifficultyCell
  our_player_id, our_player_external_id, our_player_name
  opponent_player_id, opponent_player_external_id, opponent_player_name
  our_skill_level, opponent_skill_level
  difficulty                     # None when either skill level is missing
  evidence_label
  direct_evidence_count
  reliability_weight

MatchDifficultyReport
  our_team_external_id, our_team_name
  opponent_team_external_id, opponent_team_name
  format, session_name
  source_manifest_id, captured_at, formula_version
  cells[]                        # one per feasible pair, Stage 1 order preserved
  matrix_difficulty_index, matrix_coverage
  row_summaries[]                # one per our-roster player: index, coverage
  column_summaries[]             # one per opponent-roster player: index, coverage
  our_team_strength_index, opponent_team_strength_index   # context only, Optional
  unavailable_reasons[]
```

Rows are immutable and preserve `PairingEvidenceMatrix.pairings` order. The
module queries nothing, changes no database state, and imports no UI
renderer -- the same posture as every analytics module in this project.

## HTML layout

```text
section#match-difficulty-heatmap
├── scope/provenance and descriptive-only notice (quotes the two constraints above)
├── Team Strength context card (or explicit No data state per side)
├── matrix summary: matrix_difficulty_index and coverage
├── figure#match-difficulty-grid
│   one our-player row × one opponent-player column;
│   cell shows difficulty (or "No data"), evidence-label glyph, and
│   direct_evidence_count on hover/focus; a UNKNOWN/INDIRECT cell is visually
│   distinct from a DIRECT one by pattern, not color-only
├── table#match-difficulty-rows (row summaries, sortable by one visible column)
├── table#match-difficulty-columns (column summaries)
└── formula, source, and unavailable-data disclosure
```

The grid uses one sequential, colorblind-safe scale over the continuous 0-100
`difficulty` value -- no traffic-light red/yellow/green, no fixed "danger"
color, and no cutoff that turns a number into a labeled zone. A `None` cell is
shown with diagonal hatching and the literal text "No data," never blank and
never a color that could be misread as a measured low/high value. Every color
is paired with a legible number so the grid remains legible without color.

## Excel layout

`match_difficulty_heatmap.xlsx` contains values only:

- `Match_Difficulty_Cells`: one row per feasible pair with both player
  identities, skill levels, `difficulty`, evidence label, direct evidence
  count, and reliability weight;
- `Match_Difficulty_Rows`: one row per our-roster player with `row_difficulty_index`
  and its coverage;
- `Match_Difficulty_Columns`: one row per opponent-roster player, same shape;
- `Match_Difficulty_Summary`: one row with `matrix_difficulty_index`,
  `matrix_coverage`, both teams' Team Strength indices (or blank/`No data`),
  formula version, scope, and capture time.

All sheets freeze headers, use fixed widths, retain IDs as text, and contain
no formula, macro, hidden helper, external link, or content-dependent
ordering -- the same convention every other export in this project follows.
An empty cells sheet (a scope with zero feasible pairs) is still written with
headers and a zero row count rather than omitted, since "no feasible pairs"
is itself a real, auditable fact about the scope, distinct from "not built."

## Current status and wiring contract

Not yet implemented. This document exists to be reviewed before any of the
following is written:

| Planned file | Required public responsibility |
| --- | --- |
| `analytics/match_difficulty_heatmap.py` | pure `build_report(matrix, our_team_strength=None, opponent_team_strength=None, ...)`; owns the cell formula, reliability weighting, and summary aggregation; imports `skill_only_win_probability` and never `win_probability` |
| `ui/tabs/match_difficulty_heatmap.py` | render the grid, row/column tables, and Team Strength context card from one immutable report; no recomputation |
| `ui/export_excel_match_difficulty_heatmap.py` | write the four values-only sheets above |
| `scripts/build_match_difficulty_heatmap.py` | read-only exact-scope query/reconciliation: builds (or reuses) the real `PairingEvidenceMatrix` via `analytics.pairing_evidence.build_pairing_evidence_matrix` and, when available, both teams' `TeamStrengthReport`, then calls the analytics module once |
| Captain's Edge / Live Assistant adapters | link to the heatmap by exact run/scope/hash; never re-derive a cell value locally |

The standalone command contract mirrors this project's other per-scope
builders:

```text
python scripts/build_match_difficulty_heatmap.py --our-team-id ID
    --opponent-team-id ID --format NAME --session NAME --out-dir PATH
```

`--our-team-id` defaults to `apa_config.yaml`'s `team.team_id` when omitted,
matching every other builder in this project. The database is opened
read-only; the command triggers no scrape and does not mutate
`PairingEvidenceMatrix`'s own build path.

## Validation strategy

- Pin the cell formula against `skill_only_win_probability`'s own already-pinned
  examples (`1 - p` at known skill-level pairs).
- Prove a missing skill level on either side yields `None`, never an imputed
  average.
- Prove `reliability_weight` matches `analytics/opponent_risk_profile.py`'s
  own formula exactly (shared precedent, not a second implementation).
- Prove row/column/matrix summaries are reliability-weighted means over only
  real cells, with correct coverage when some cells are `None`.
- Prove Team Strength context never changes a cell value or a summary index
  (a cross-feature test, same discipline as `docs/opponent_volatility.md`'s
  own validation section).
- Assert no categorical class name (`danger`, `avoid`, `target`, `risk-*`) and
  no `modeled_win_probability` reference appear anywhere in the HTML or Excel
  output.
- Cover zero feasible pairs, an all-UNKNOWN matrix, an all-DIRECT matrix, and
  hostile player names.
- Compare analytics, HTML, Excel, and script-JSON row order and raw values
  before display rounding.

## Demo integration (proposed)

The heatmap opens after Player-vs-Player evidence and before the Live
Assistant, consistent with the Live Assistant doc's own screen structure,
which already links to it ("selected Pair View and match-difficulty heatmap
link"). The presenter shows one DIRECT cell, one UNKNOWN cell, and the
row/matrix summary's coverage figure to demonstrate that a thin matrix is
never presented as equivalent to a well-evidenced one.
