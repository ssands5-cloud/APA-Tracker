# Trend Analyzer

The Trend Analyzer is the demo/export presentation contract for the implemented
player trend pipeline. `analytics/player_trends.py` remains the formula owner;
`scripts/build_player_trends.py` persists one aggregate per player, format, and
session. This document does not introduce a second trend calculation.

The subject is captured skill level over match order. A trend is descriptive
history, not a claim about effort, health, future match outcome, or an APA
re-rating decision.

## Inputs and spans

Input observations are real `PlayerMatch.skill_level` values ordered by joined
`Match` chronology and scoped to player/format/session. Null skill readings are
excluded rather than replaced.

| Metric | Span | Minimum evidence |
| --- | --- | ---: |
| `regression_slope` | all usable observations in the session | 2 |
| `volatility` | most recent 20 usable observations | 2 |
| `sample_size` | count in that most-recent-20 window | n/a |
| `trend_score` | slope and volatility from their distinct spans | 5 and measurable volatility |
| hot/cold/neutral indicator | same slope/volatility values | 5 and measurable volatility |

The all-session slope and 20-observation volatility window must never be
silently made the same span.

## Trend score

The implemented score is:

```text
trend_score = regression_slope / (volatility + 0.05)
```

`regression_slope` is least-squares skill-level change per match. `volatility`
is the sample standard deviation (`ddof=1`) over the last 20 readings. The
`0.05` denominator floor is a documented heuristic constant that prevents an
undefined/infinite ratio for an unchanged level; it is not fitted.

The function returns null whenever the existing hot/cold classifier's evidence
gate is closed: fewer than five observations, missing volatility, or missing
slope. Zero is valid when a measured slope is exactly zero. Renderers consume
the returned value and never recompute, rescale, percentile-rank, or threshold
it.

## Descriptive hot/cold indicators

The existing `hot_cold_flag` field is presented as a **trend indicator**, not a
recommendation or risk flag:

| Display | Exact implemented condition |
| --- | --- |
| `HOT` | slope ≥ +0.05 SL/match, volatility ≤ 0.40, sample size ≥ 5 |
| `COLD` | slope ≤ −0.05 SL/match, volatility ≤ 0.40, sample size ≥ 5 |
| `NEUTRAL` | evidence gate is open and neither directional condition holds |
| `No data` | evidence gate is closed |

The terms describe the direction and steadiness of captured skill-level
history only. They cannot alter lineup selection, produce Avoid/Target advice,
or be combined with Player-vs-Player probability into a hidden category.

## Analytics/presentation document

The dashboard adapter reads the persisted `PlayerTrend` row and adds only
identity/provenance plus the pure `trend_score` result already used by JSON and
Excel. One row contains:

```text
player_id, player_external_id, player_name
format, session_name, sample_size, current_skill_level
regression_slope, volatility, sl_stability
hot_cold_indicator, trend_score
projected_sl_change_probability
source_manifest_id, captured_at, availability_reason
```

`projected_sl_change_probability` is the existing transparent heuristic for
upward SL pressure, not a learned probability and not an input to trend score.
The UI labels it separately or omits it; it may not be called a match-win
forecast.

## Architecture, UX, and routing

```text
PlayerMatch + Match chronology
    → analytics/player_trends.py
    → persisted PlayerTrend + immutable presentation rows
    → Trend Analyzer HTML / Excel / script JSON
```

The analytics module remains the only formula owner. The query/build layer
validates player, normalized format, session, chronology, and manifest scope;
the renderer only formats delivered fields. The proposed `trend-analyzer` route
opens the selected team/session summary and optionally carries an exact player
external ID. An invalid selection returns to the canonical table with an
explicit message instead of choosing a similarly named player.

Summary, Player History, and Formula/Provenance are in-page views under the
same tab. Selecting a table row opens that player's real history chart and
updates URL/fragment state. Keyboard/back navigation restores the selection.
Client-side controls may filter and visibly sort delivered rows, but cannot
recalculate slope, change the 20-reading volatility window, extrapolate the
chart, or convert an unavailable indicator to NEUTRAL.

## HTML charts and tables

The proposed Trend Analyzer section uses:

```text
section#trend-analyzer
├── scope/provenance and descriptive-only disclosure
├── summary counts: measured / HOT / COLD / NEUTRAL / No data
├── figure#trend-score-bars
├── figure#skill-history-chart for the selected player
├── table#trend-analyzer-table
└── formula, sample-size, and limitation notes
```

The diverging trend-score bar chart has a fixed zero center. Positive bars use
blue, negative bars use orange, zero uses a neutral line, and missing values use
a gray hatched `No data` marker. Color is supplemented by sign and text. Axis
bounds derive symmetrically from the largest finite absolute delivered score;
if every measured score is zero, the fixed display domain is −1 to +1. This is
display scaling only and never changes the value.

The selected-player history chart plots real skill readings in chronological
order and may overlay the delivered linear slope as a clearly labeled trend
line. Missing observations create gaps. It does not extrapolate beyond the last
real match.

The table columns are Player, Format, Session, Sample, Current SL, Slope
(SL/match), Volatility (last 20), Stability, Trend Score, Trend Indicator, and
Upward-SL Heuristic. Default order is format, session, player name, and external
ID. User sorting is one visible column at a time with nulls last and identity
tie-breaks.

## Excel layout

The existing general workbook `Player Trends` sheet remains the canonical
values export until the dedicated production artifact is wired. The finalized
dedicated design for `trend_analyzer.xlsx` contains:

- `Trend_Analyzer`: one row per player/format/session with every field above;
- `Trend_History`: one row per real skill observation with player/match IDs,
  date/order, format/session, and skill level.

Rows use the same canonical ordering as HTML. Numeric values stay numeric;
nulls stay blank with a status column. Indicator cells carry literal text and
an accessible fixed fill, never a formula. Workbooks contain no macros,
external links, hidden helpers, volatile time functions, or recalculated trend
formulas.

## Demo integration

The demo opens Trend Analyzer after Player-vs-Player evidence and before the
Opponent Volatility summary. The presenter selects one measured player to
trace slope, last-20 volatility, trend score, sample, and descriptive indicator
back to real observations, then selects a thin-data player to show `No data`.
Captain's Edge and the Live Assistant may repeat the same delivered fields as
separate descriptive context; no trend field changes pair probabilities,
heatmap cells, Team Strength, or lineup selection.

The build manifest records the normalized scope, formula constants, row keys,
history keys, and source hash. HTML, Excel, script JSON, and the persisted
`PlayerTrend` rows reconcile before display rounding. The artifact index links
to the HTML section and the canonical general-workbook sheet or dedicated
values-only workbook selected by the release manifest.

## Validation strategy

- Pin regression slope against independently calculated examples.
- Pin volatility against `statistics.stdev`, including last-20 windowing.
- Test the exact ±0.05, 0.40, and five-observation boundaries.
- Verify `trend_score` null gating, denominator floor, sign, and zero behavior.
- Prove chronology changes slope and that missing readings are excluded without
  compressing scope metadata.
- Compare database, JSON, HTML, Excel, and manifest raw values and row keys
  before rounding.
- Assert that chart coordinates map only delivered values and that no future
  extrapolation or recommendation text appears.
- Cover hostile names, all-null, all-zero, one-observation, exactly-20, and
  more-than-20 histories.
