# Unified Player vs Player Excel structure

The workbook is the offline companion to the unified HTML tab. It contains the
whole matrix and a materialized selected-pair detail without formulas, macros,
or a second analytics implementation. The current exporter writes
`exports/player_vs_player.xlsx`; future demo integration may add the selected
pair sheet but must preserve the implemented matrix sheets and values.

## `Player_vs_Player`

This is the canonical matrix sheet. It contains one row for every feasible
pair, including UNKNOWN, in the matrix module's structural order.

| Column | Field | Source / rule |
| --- | --- | --- |
| A | `session` | matrix scope |
| B | `format` | matrix scope |
| C | `our_team_id` | canonical external team ID, text |
| D | `opponent_team_id` | canonical external team ID, text |
| E | `player_id` | canonical internal player ID, integer |
| F | `player_external_id` | canonical external player ID, text |
| G | `player_name` | display only |
| H | `player_skill_level` | current roster SL or blank/No data |
| I | `opponent_id` | canonical internal opponent ID, integer |
| J | `opponent_external_id` | canonical external opponent ID, text |
| K | `opponent_name` | display only |
| L | `opponent_skill_level` | current roster SL or blank/No data |
| M | `evidence_label` | DIRECT / INDIRECT / UNKNOWN |
| N | `direct_matches` | Stage 1 distinct authoritative team matches |
| O | `win_rate` | Stage 1 observed DIRECT rate; null otherwise |
| P | `total_games` | recognized exact-pair game rows |
| Q | `wins` | recognized wins |
| R | `losses` | recognized losses |
| S | `sl_delta` | average posted opponent-minus-own SL |
| T | `reliability` | `n/(n+3)`, using `total_games` |
| U | `skill_prob` | last-recorded skill-gap probability |
| V | `modeled_win_probability` | experimental full pair model |
| W | `model_validation_status` | explicit held-out-rematch status |
| X | `trend` | full explicit-pair trend |
| Y | `recent_trend` | recent explicit-pair trend |
| Z | `next_match_projection` | exact alias of modeled probability |
| AA | `danger_flag` | boolean only when threshold approved; otherwise null |
| AB | `favorable_flag` | boolean only when threshold approved; otherwise null |
| AC | `flag_status` | approved version or `UNAVAILABLE_NOT_VALIDATED` |
| AD | `data_notes` | deterministic source-gap/disclosure text |

`danger_flag` and `favorable_flag` are the machine fields behind Recommended
Avoid and Recommended Target. They are not formulas and must never both be true.
At the current audit state both remain null and `flag_status` explains why.
Neither is derived in Excel or inferred from formatting.

The implemented v1 workbook lacks internal IDs, skill delta, validation-status,
flag, and disclosure columns. Those are explicit demo-integration deltas. Until
a separately reviewed renderer change adds them, the manifest must describe the
omissions and the demo must not claim workbook parity for absent columns.

## `Selected_Pair`

This optional, materialized sheet mirrors Pair View for the pair selected when
the demo bundle is built. It contains a two-column field/value table using the
same fields and values as its `Player_vs_Player` row, followed by the full
unavailable-data and model-validation disclosures. It contains no lookup
formulas or dropdown-driven recomputation. If no pair is selected, omit the
sheet and record that fact in the manifest.

## `PvP_Game_History`

Create this sheet only when at least one real `GameRecord` exists. Columns are
Player ID, Player External ID, Opponent ID, Opponent External ID, Match ID,
Match Date, Result, Own Posted SL, Opponent Posted SL, Points Earned, 9-Ball
Balls, Format, and Session. Rows follow parent matrix order and then each
summary's chronological order.

The implemented v1 history sheet contains external IDs but not internal IDs;
adding them is a documented integration enhancement. Missing dates remain null
and display as `No data`; they are never generated from workbook time.

## Ordering and formatting

- Initial rows sort by session, format (8-ball, 9-ball, other), player
  name/external ID, then opponent name/external ID. Scores and flags never
  affect source order.
- Freeze the header row, enable filters across real rows, and use fixed column
  widths. Do not auto-size from captured names.
- External IDs are text; counts/IDs are integers; raw probabilities are numeric
  values with deterministic percentage display; `sl_delta` and reliability use
  three decimals.
- Null data remains null in cells. A nearby status/note column explains it;
  numeric zero is reserved for measured zero.
- Evidence/flag fills are supplemental to literal text and use a fixed palette.
- There are no volatile formulas, VBA, external links, hidden helper sheets,
  locale-dependent dates, or current-time conditional formatting.
- Workbook metadata uses the run-manifest timestamp.

## Validation

Load the workbook with openpyxl and compare pair keys, raw metrics, nulls,
status fields, and game keys against the script JSON before display rounding.
Assert no duplicate/missing matrix row, no UNKNOWN suppression, no formula,
macro, external link, hidden sheet, or repair prompt. When flag status is not
approved, assert both flag cells are null for every row.
