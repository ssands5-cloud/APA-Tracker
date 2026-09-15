# Opponent Volatility Profile

The Opponent Volatility Profile summarizes how much each opponent's captured
skill level has varied in the selected format/session. It consumes the existing
`PlayerTrend.volatility` and `sl_stability` values; it does not infer
per-opponent-game volatility, shot variance, temperament, or match risk.

The proposed composition owner is `analytics/opponent_volatility.py`. It
accepts canonical opponent-roster identities and already-built `PlayerTrend`
rows. It queries nothing and does not modify `analytics/player_vs_player.py`.

## Volatility index

For a player whose existing last-20 sample standard deviation is `sigma`:

```text
sl_stability    = 1 / (1 + sigma)
volatility_index = 100 * (1 - sl_stability)
                 = 100 * sigma / (1 + sigma)
```

This monotonic transformation places the unbounded skill-level standard
deviation on a 0–100 display scale without changing its order. It is null when
`sigma`/`sl_stability` is null. A measured zero means at least two real readings
with no observed skill-level variation; it is different from missing evidence.

The formula version is `opponent-volatility-v1-sl-transform`. The report always
carries raw `sigma`, `sl_stability`, last-20 `sample_size`, full-session slope,
format, and session beside the index. The index is descriptive and has no
validated match-outcome interpretation.

## Consistency descriptors

Descriptors use evidence state and the sign of the measured value only. There
are no invented high/medium/low cutoffs:

| Descriptor | Rule | Meaning |
| --- | --- | --- |
| `Insufficient evidence` | volatility is null | fewer than two usable readings in the window |
| `No observed SL variation` | volatility equals 0 | multiple readings, all the same skill level |
| `Observed SL variation` | volatility is greater than 0 | at least one skill-level difference exists |

The exact numeric value and sample size remain primary. The descriptor cannot
be restyled as danger, favorable, Avoid/Target, or a traffic-light category.

## Opponent-team summary

For a canonical opponent roster, the profile reports:

```text
team_volatility_index = median(available player volatility_index values)
coverage = measured opponent players / canonical opponent roster size
```

Median is used because the team summary is descriptive and should not be
dominated by one player's large observed change. No minimum coverage is
invented: one measured player yields a real median plus visibly low coverage;
zero measured players yields null. The player rows remain available so the
summary can always be audited.

## Data sources and identity

- Opponent membership: current `PlayerTeamHistory` rows with exact opponent
  `team_external_id`, session, and `is_current`.
- Volatility fields: persisted `PlayerTrend` keyed by player, normalized
  format, and session.
- Identity/name: `Player.external_id` and `Player.name`; name is display-only.
- Provenance: builder-supplied source-manifest ID and capture timestamp.

Missing normalized-format mapping, ambiguous membership, or duplicate trend
rows fails closed. A trend from another format/session is never substituted.

## Current status and wiring contract

The pure profile, formula/descriptor constants, immutable player/team rows,
median/coverage behavior, standalone read-only builder, HTML fragment,
two-sheet workbook, and focused tests are implemented. Production provenance,
the full accessible plot/interaction, pair/live joins, full-demo registration,
and cross-artifact parity remain. Existing `analytics/opponent_scouting.py`
consumes a raw volatility value inside a legacy threshold-based danger model;
it is a separate legacy product and must not become the formula, descriptor,
ordering, or color owner for this profile. The dedicated profile keeps the
numeric transform, evidence state, player rows, and team median independent of
all danger flags.

| File | Current responsibility or required completion |
| --- | --- |
| `analytics/opponent_volatility.py` | implemented pure `build_profile(...)` over canonical roster identities and scoped `PlayerTrend` rows; owns transform, descriptors, median, coverage, and formula version |
| `ui/tabs/opponent_volatility.py` | implemented summary/list/table baseline without thresholds; add the accessible neutral dot plot, interaction, safe script JSON, and run provenance |
| `ui/export_excel_opponent_volatility.py` | implemented two values-only sheets from the immutable profile; add manifest parity checks |
| `scripts/build_opponent_volatility.py` | implemented read-only exact-roster/session query, duplicate-trend guard, and standalone HTML/XLSX output; add missing-player/team guards and production containment/provenance |
| Player-vs-Player / Live Assistant adapters | join the already-built row/profile by exact opponent external ID, format, session, run, and source hash |

The query boundary starts from current `PlayerTeamHistory` memberships for the
exact opponent team external ID and session, joins `Player` identity, and then
requires at most one matching `PlayerTrend` per player/normalized-format/
session. Every roster player remains in the output even when the trend row is
absent. Duplicate membership or trend rows block the profile; missing rows
produce null values and reduce coverage.

The standalone command contract is:

```text
python scripts/build_opponent_volatility.py --db PATH
    --opponent-team-id ID --session NAME [--format NAME] --out-dir PATH
```

The database is read-only, and the command does not trigger trend population,
fall back across sessions, or accept a display name as identity. When format is
omitted, production must reject multiple matching format rows for a player
rather than collapse them. The full builder should build each needed opponent
profile once, reuse it in all surfaces, and record its player-key set and median
inputs in the manifest.

## Player-vs-Player integration

The unified Player-vs-Player tab may join one opponent's volatility profile by
exact opponent ID, normalized format, and session. It appears as:

- `Opponent volatility index (overall SL history)`;
- raw SL standard deviation and last-20 sample size;
- the consistency descriptor;
- an explicit **not pair-specific** scope label.

The field remains separate from DIRECT history, reliability, observed win
rate, current-skill probability, modeled probability, and match-difficulty
heatmap value. It cannot alter the evidence label, matrix canonical order,
Lineup Lab score, or Opponent Risk Profile category because no such category
exists. Missing volatility remains `No data` and does not become zero.

## Captain's Edge and Live Assistant integration

Captain's Edge consumes the same immutable volatility row already joined to the
matrix document. It may surface a note such as “Observed opponent SL variation:
0.42 over 8 readings,” or “Opponent SL variation: insufficient evidence.” It
must not translate the value into a recommendation.

The Live Assistant may sort a descriptive opponent list by the visible
volatility index when the captain explicitly selects that column. The heading
states the field/direction, nulls sort last, and canonical opponent identity
breaks ties. It cannot blend volatility with win probability, trend, or team
strength into a hidden risk score.

## HTML and Excel layout

The HTML profile contains a team median/coverage card, a fixed-axis 0–100 dot
plot of measured opponents, and a table with Player, Sample, Raw Volatility,
Stability, Volatility Index, Consistency Descriptor, Trend Slope, Format,
Session, and Source Status. Missing values use gray hatching plus `No data`.
The chart uses one neutral sequential blue scale and no danger colors.

The future `opponent_volatility.xlsx` contains:

- `Opponent_Volatility`: one team summary row with index, measured/roster
  counts, coverage, formula version, scope, capture time, and source hash;
- `Opponent_Volatility_Players`: one row per canonical opponent, including
  nulls, with all table fields above.

Rows default to opponent name/external ID. A requested numeric sort must be
recorded in metadata and retain null-last/identity tie-break behavior. The
workbook is values-only and contains no formula, macro, external link, hidden
sheet, or threshold-based conditional formatting.

## UX, routing, and demo integration

The unified Player-vs-Player Pair View exposes one opponent profile inline,
while the proposed `opponent-volatility` detail route opens the complete
opponent roster for the same team/format/session/run scope. Exact external IDs
are routing keys; display names are never used to repair a missing join.
Returning from the detail route restores the selected pair and Matrix View
filters.

The HTML's team card, neutral dot plot, and player table are three views of the
same immutable document. Clicking a point focuses its table row and announces
the numeric value, sample, and descriptor. Sorting is explicit, reversible,
null-last, and recorded in presentation state. The UI has no default
"riskiest" order and never promotes a value into an alert.

In the demo, Opponent Volatility follows Trend Analyzer: the presenter proves
the exact transform for one player, then the opponent-team median and coverage.
The same row is opened from Player-vs-Player and Captain's Edge to demonstrate
identity/scope parity. The workbook's summary and all-player sheets, the HTML,
script JSON, and manifest must agree on raw sigma, stability, index, descriptor,
sample, median inputs, nulls, and row order before the feature is promotable.

## Validation

Tests pin the algebraic transformation, zero/null distinction, median for odd
and even counts, roster coverage, exact scope join, duplicate rejection,
canonical order, and HTML/Excel/script-JSON parity. Cross-feature tests prove
that adding or removing volatility never changes Player-vs-Player evidence,
skill-only heatmap values, or Lineup Lab selection.
