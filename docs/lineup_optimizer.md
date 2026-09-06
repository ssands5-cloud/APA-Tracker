# Lineup Optimizer

The Lineup Optimizer turns the independent Captain's Edge recommendations into
one legal lineup card.  Captain's Edge can select the same opponent for two
players because it answers each player's question independently.  This module
solves the whole assignment at once, so an opponent is assigned at most once.

The implementation is deliberately split into a pure engine and a read-only
builder:

| Layer | File | Responsibility |
| --- | --- | --- |
| Engine | `analytics/lineup_optimizer.py` | Score a candidate cell and solve the exact one-to-one assignment. No database or file I/O. |
| Builder | `scripts/build_lineups.py` | Read persisted Head-to-Head and Trend rows, resolve team identity, build matrices, and serialize the result. |
| Pipeline | `pipeline/exports.py` | Run the builder after ingest has committed, report `exports/lineups.json`, and append the solved card to the workbook. |
| Views | `ui/tabs/lineup_optimizer.py`, `ui/export_excel.py` | Render the same JSON in the self-contained analysis page and a `Lineup Optimizer` Excel sheet. |

## Inputs and score

The builder reads only values already computed by the analytics pipeline:

| Optimizer input | Stored source | Treatment |
| --- | --- | --- |
| `matchup_score` | `player_h2h_advantage.matchup_score` | Stored as 0--100. The builder preserves that raw value and converts it to 0--1 for the optimizer. |
| `win_probability` | `player_h2h_advantage.win_probability` | Validated 0--1; invalid values become `null` with a warning. |
| `confidence` | `player_trends` through `analytics.captains_edge.confidence` | Player-level signal for the same normalized format and session. |
| `risk_factor` | `player_trends` through `analytics.captains_edge.risk_factor` | Player-level signal for the same normalized format and session. |

For player `i` against opponent `j`, the pure engine computes:

```text
Fij = 0.50 * matchup_score
    + 0.30 * win_probability
    + 0.15 * effective_confidence
    + 0.05 * (1 - effective_risk)
```

Missing components use `0.5` only for this internal arithmetic.  The raw
export keeps them `null`; it never presents a fabricated neutral measurement
as evidence.  A candidate with no source H2H row is retained as an explicit
missing edge (`source_pairing: false`) so that a sparse matrix does not force
the builder to invent a matchup.

## Grouping and identity

An assignment is solved independently for each:

```text
(own team, opponent team, format, session)
```

Team IDs from the `players` join are preferred.  When a scoresheet player row
has no team ID, the builder falls back only to an exact name that maps to one
team.  Ambiguous or missing own/opponent team identities are retained in the
raw `pairings` list, marked ineligible, and excluded from a lineup.  The
builder never creates an “unknown opponent” bucket: mixing opponents from
different teams would produce a card that cannot be used at a match.

Within an eligible group, the builder forms the full Cartesian matrix of the
players and opponents observed for that team pair.  Missing H2H edges are
therefore visible and can receive a neutral internal score, while the JSON
still identifies them as unobserved.

## Assignment and tie-breaks

The engine checks every valid injective assignment exactly.  It does not use a
greedy approximation.  Unequal rosters are supported: the smaller side is
fully assigned and the remainder is listed in `unassigned_players` or
`unassigned_opponents`.  A safety guard rejects inputs requiring more than
500,000 permutations rather than silently taking an unbounded amount of time.

Candidates are compared in this order:

1. Maximize the sum of `Fij` (`objective_total`).
2. Minimize the sum of effective player risk (`total_risk`).
3. Maximize the sum of effective player confidence (`total_confidence`).
4. Choose the lexicographically smallest `(player_name, opponent_name)` pair
   sequence, sorted by player name.

Assignments receive a rank by final cell score.  Every assignment includes a
short rationale naming the strongest known signals; unknown form or stability
is stated plainly.

## JSON artifact

`exports/lineups.json` is rewritten atomically on every build.  A temporary
file is written in the same directory, flushed, and replaced into place, so a
stale lineup cannot survive and readers never see a partially written JSON
document.

Top-level fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer payload version (`1` currently). |
| `generated_at` | UTC ISO-8601 build time. |
| `source_db` | Resolved database path used for the read-only build. |
| `pairing_rows` | Number of raw H2H advantage rows read. |
| `pairings` | Raw rows plus validation, resolution, and normalized internal fields. |
| `players_with_trends` | Number of database players with trend rows. |
| `eligible_pairing_rows` | Rows safe to include in an assignment group. |
| `lineups` | One solved document per team/opponent/format/session group. |
| `resolution_warnings` | Deduplicated non-fatal data-quality warnings. |

Each `lineups[]` entry carries team/opponent IDs and names, format/session,
roster resolution method, source row counts, `assignments`, unassigned slots,
objective/risk/confidence totals, and whether a tie-break was needed.
Assignments carry both the raw 0--100 `matchup_score_raw` and the normalized
0--1 `matchup_score`, plus `source_pairing`, `confidence`, `risk_factor`,
`final_score`, `lineup_rank`, and `rationale`.

After a successful builder run, the pipeline adds a `Lineup Optimizer` sheet
to the existing workbook.  It shows the raw stored score and source signals;
missing values are the literal `No data`, while the computed final score is
labeled separately.  Re-running replaces the prior sheet, so a stale card
cannot accumulate beside the current one.  The analysis page uses the same
JSON and places this legal one-to-one card before the independent Captain's
Edge working view.

## Running it

The normal production path runs it automatically after ingest and the other
analytics builders:

```powershell
python -m pipeline
```

To rebuild only this artifact from an existing database:

```powershell
python scripts/build_lineups.py
python scripts/build_lineups.py --db path\to\apa.db --out-dir exports
```

The pipeline's `--no-captains` option skips Captain's Edge and Lineup
Optimizer together.  A missing or unreadable database produces a warning and
does not prevent the earlier workbook/JSON exports from completing.

## Missing data and current limitations

`null` means that the source did not provide a value.  It is never rewritten
as zero, and the neutral defaults are never serialized as observed evidence.
Confidence and risk remain `null` until a matching Trend row has enough data.

The current ingest contains both roster and scoresheet player identities.  A
name fallback is safe only when that name maps to one roster team; unresolved
rows are intentionally omitted from assignments and called out in
`resolution_warnings`.  Unifying those upstream ID spaces is a separate
ingest change with a wider blast radius.

The optimizer has not yet been evaluated against actual match outcomes.  It
is a transparent decision aid, not a fitted probability model.
