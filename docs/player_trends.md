# Player Trend Analyzer

One row per (player, format, session): how a player's **skill level** has
been moving, how settled it is, and a documented heuristic for upward SL
pressure.

```
analytics/player_trends.py      the maths
scripts/build_player_trends.py  builds and prunes from stored history
player_trends                   the table it writes
ui/tabs/trends.py               the demo tab
export_excel.py                 the "Player Trends" sheet
```

The subject of every metric is **skill level**. Points earned are not an
input to any of it.

Every input is real captured data — `PlayerMatch.skill_level`, with format
and session from the joined `Match`. Nothing is synthesised. This project
holds no innings and no defensive-shot figures (APA does not expose them —
see `docs/data-fields.md`), and none are invented here.

This document *is* the governing spec. Every constant appears in the code as
a named module constant and is asserted by a test.

## The two spans

These deliberately differ, and conflating them would break one:

| Metric | Span |
|---|---|
| `regression_slope` | **all** observations in the session, uncapped |
| `volatility` | the **last 20** observations only |
| `sample_size` | observations in the last-20 window |

## Regression slope

Least squares of skill level against match order, with xᵢ = i, 1-indexed
chronologically:

```
slope = (n Σxᵢyᵢ − Σxᵢ Σyᵢ) / (n Σxᵢ² − (Σxᵢ)²)
```

**Units: SL per match.** Positive means the level is climbing. `NULL` below
2 observations. Only observations with a real skill level count.

## Volatility

**Sample** standard deviation (ddof = 1) of skill level over the last 20
observations:

```
ȳ = (1/n) Σ yᵢ
σ = sqrt( (1/(n−1)) Σ (yᵢ − ȳ)² )
```

`NULL` below 2 observations in the window.

### Why ddof = 1

Sample rather than population standard deviation, because this *estimates*
how variable a player's skill level is from a finite set of observations,
rather than describing a closed population. The two differ materially at the
small n this data actually has — over `[4, 6]` the sample stddev is 1.41 and
the population stddev 1.00.

Verified in tests against `statistics.stdev`, not against this
implementation's own output.

## SL stability

```
stability = 1 / (1 + σ)
```

1.0 is perfectly stable; approaches 0.0 as the level swings. **Not a
variance** — a normalised inverse of volatility. `NULL` whenever volatility
is `NULL`.

No thresholds are baked into the metric; they exist only in the
classification below.

## Hot / Cold / Neutral

Absolute thresholds. Every player is judged against the spec, not against
other players — there is no quartile and no population pass.

| Flag | Condition |
|---|---|
| **HOT** | `slope ≥ +0.05` **and** `σ ≤ 0.40` **and** `sample_size ≥ 5` |
| **COLD** | `slope ≤ −0.05` **and** `σ ≤ 0.40` **and** `sample_size ≥ 5` |
| **NEUTRAL** | anything else that was measurable |
| **NULL** | `sample_size < 5` or `σ` is NULL |

Every condition is required. A steep slope through an erratic skill level is
noise, not a trend, so it reads NEUTRAL rather than HOT. Thresholds are
inclusive at the boundary.

## Projected SL-change probability

A transparent heuristic. **Not a learned model, and not APA's own re-rating
projection.**

```
p = clamp( 0.5 · tanh(4 · slope) · (1 − σ) · n/20,  0,  1 )
```

with n capped at 20.

| Term | Role |
|---|---|
| `tanh(4 · slope)` | turns SL-per-match pressure into a bounded signal |
| `(1 − σ)` | damps an erratic skill level |
| `n/20` | damps a thin sample |
| `clamp(…, 0, 1)` | keeps the result a probability |

Every constant is named in `analytics/player_trends.py` — there are no opaque
numbers.

Two consequences worth stating plainly:

- **A downward trend yields 0.0**, because the clamp floors the negative
  product. The heuristic describes *upward* pressure only; direction lives in
  `regression_slope`, stored alongside it.
- **A σ above 1.0** drives `(1 − σ)` negative and the clamp takes it to 0.0 —
  no confidence at all, not a hidden negative.

`NULL` when slope or volatility is `NULL`, or `sample_size < 5`.

## Minimum evidence

| Metric | Minimum observations | If insufficient |
|---|---|---|
| `regression_slope` | 2 | NULL |
| `volatility` | 2 (in the last 20) | NULL |
| `sl_stability` | volatility required | NULL |
| `hot_cold_flag` | 5 | NULL |
| `projected_sl_change_probability` | 5 | NULL |

## NULL behaviour

NULL means *not enough evidence*, and is **never** replaced by a fabricated
zero. The distinction is load-bearing:

- `volatility = NULL` — one observation, so no spread was measurable
- `volatility = 0.0` — several observations, and the level genuinely never moved
- `hot_cold_flag = NULL` — fewer than 5 observations, so nothing was classified
- `hot_cold_flag = 'NEUTRAL'` — measured, and unremarkable

Both the demo tab and the Excel sheet render NULL as **"No data"** — never a
blank cell, never a zero — and it always sorts last rather than as zero.

`sample_size` and `current_skill_level` are `NOT NULL`; a group with no
usable skill level at all is skipped by the builder rather than written with
placeholder values.

## Storage

```
UNIQUE (player_id, format, session_name)
INDEX  (format, session_name)
```

`format` is normalised to `'8-ball'` / `'9-ball'`. The captured data says
`'8-Ball Open'` / `'9-Ball Open'`; `normalize_format` maps those and leaves
anything unrecognised **unchanged** rather than forcing it into a bucket it
may not belong in — a masters or tournament division must not be silently
relabelled.

The builder **prunes** aggregates whose underlying matches have disappeared
(a reconciled match, a corrected scoresheet, a player moved off a session).
Without that, an aggregate outlives its evidence and keeps being reported as
current.

## Limitations

- **The current data cannot exercise the gated metrics.** The most any player
  has in one format and session is 4 observations, and both `hot_cold_flag`
  and `projected_sl_change_probability` require 5. All 72 rows currently
  carry NULL for both. That is the spec working as written, not a defect —
  the columns populate as the season accumulates.
- **A slope over 2 observations is exact by construction.** Two points always
  fit a line perfectly, so a slope at the minimum describes those two
  results rather than evidencing a trend. `sample_size` is stored beside it
  so a reader can weigh it.
- **Skill level is a step function**, changing only when the league re-rates.
  A least-squares line through step data measures the average rate of
  re-rating, not a continuous improvement curve.
- **The heuristic is not validated against outcomes.** No record of actual
  APA re-rating decisions exists in this project, so nothing here has been
  checked against whether a predicted change occurred.
- **`sample_size` counts the volatility window, not the whole session.** A
  player with 30 observations reports `sample_size = 20`, while the slope
  still uses all 30.

## Rebuilding

```bash
python -m pipeline                      # ingest + exports
python -m scripts.build_player_trends   # then this table
```

Upserted on `(player_id, format, session_name)`, then pruned. Re-running is
idempotent.
