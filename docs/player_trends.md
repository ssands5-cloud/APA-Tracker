# Player Trend Analyzer

One row per (player, format): how a player's **skill level** has been moving
lately, how settled it is, and a documented heuristic for upward SL pressure.

```
analytics/player_trends.py      the maths
scripts/build_player_trends.py  builds every row from stored history
player_trends                   the table it writes
ui/tabs/trends.py               the demo tab
export_excel.py                 the "Player Trends" sheet
```

The subject of the trend metrics is **skill level**, not points earned.
`avg_points_last_20` is the one points-based figure, kept as descriptive
context rather than as an input to any trend.

Every input is real captured data — `PlayerMatch.skill_level` and
`.points_earned`, format from the joined `Match`. Nothing is synthesised.
This project holds no innings and no defensive-shot figures (APA does not
expose them — see `docs/data-fields.md`), and none are invented here.

This document *is* the governing spec. Every constant below appears in the
code as a named module constant, and every one is asserted by a test.

## The two spans

These deliberately differ, and conflating them would break one of them:

| Metric | Span |
|---|---|
| `trend_slope` | **all** matches in that format, uncapped |
| `volatility_last_20` | the **last 20** matches only |
| `matches_considered` | SL observations in the last-20 window |

## Regression slope

Least squares of skill level against match order, with xᵢ = i, 1-indexed
chronologically:

```
slope = (n Σxᵢyᵢ − Σxᵢ Σyᵢ) / (n Σxᵢ² − (Σxᵢ)²)
```

**Units: SL per match.** Positive means the skill level is climbing.

Uses every match in the session, not just the volatility window. Only
observations with a real skill level count.

## Volatility

**Sample** standard deviation (ddof = 1) of skill level over the last 20
matches:

```
ȳ = (1/n) Σ yᵢ
σ = sqrt( (1/(n−1)) Σ (yᵢ − ȳ)² )
```

### Why ddof = 1

Sample rather than population standard deviation, because this *estimates*
how variable a player's skill level is from a finite set of observations
rather than describing a closed population. The two differ materially at the
small n this data actually has: over `[4, 6]`, the sample stddev is 1.41 and
the population stddev 1.00.

Verified in tests against `statistics.stdev` rather than against this
implementation's own output.

## SL stability

```
stability = 1 / (1 + σ)
```

1.0 is perfectly stable; approaches 0.0 as the skill level swings. **Not a
variance** — it is a normalised inverse of volatility.

No thresholds are baked into the metric. Thresholds exist only in the
hot/cold classification below.

## Hot / cold / neutral

Absolute thresholds — every player is judged against the spec, not against
other players. There is no quartile and no population pass.

| Flag | Condition |
|---|---|
| **hot** | `slope ≥ +0.05` **and** `σ ≤ 0.40` |
| **cold** | `slope ≤ −0.05` **and** `σ ≤ 0.40` |
| **neutral** | anything else that was measurable |
| **NULL** | insufficient evidence |

Both conditions are required. A steep slope through an erratic skill level is
noise, not a trend, so it reads neutral rather than hot.

Thresholds are inclusive at the boundary.

## Projected SL-change probability

A transparent heuristic. **Not a learned model, and not APA's own re-rating
projection.**

```
p = clamp( 0.5 · tanh(4 · slope) · (1 − σ) · n/20,  0,  1 )
```

| Term | Role |
|---|---|
| `tanh(4 · slope)` | turns SL-per-match pressure into a bounded signal |
| `(1 − σ)` | damps an erratic skill level |
| `n/20` | damps a thin sample; n is capped at 20 |
| `clamp(…, 0, 1)` | keeps the result a probability |

Every constant is named in `analytics/player_trends.py` — there are no
opaque numbers.

Two consequences worth stating plainly:

- **A downward trend yields 0.0**, because the clamp floors the negative
  product. The heuristic describes *upward* pressure only; direction lives in
  `trend_slope`, which is stored alongside it.
- **A σ above 1.0** drives `(1 − σ)` negative and the clamp takes it to 0.0.
  That is the intended reading: no confidence at all, not a hidden negative.

## Minimum evidence

| Metric | Minimum observations | If insufficient |
|---|---|---|
| `trend_slope` | 2 | NULL |
| `volatility_last_20` | 2 (in window) | NULL |
| `sl_stability` | volatility required | NULL |
| `hot_cold_flag` | 5 | NULL |
| `projected_sl_change_probability` | 5 | NULL |

## NULL behaviour

NULL means *not enough evidence*, and is never replaced by a fabricated zero.
The distinction is load-bearing:

- `volatility = NULL` — one match, so no spread was observable
- `volatility = 0.0` — several matches, and the skill level genuinely never moved
- `hot_cold_flag = NULL` — fewer than 5 matches, so no classification was attempted
- `hot_cold_flag = "neutral"` — measured, and unremarkable

Both the demo tab and the Excel sheet render NULL as **"No data"**, never as
a blank cell or a zero, and "No data" always sorts last rather than as zero.

## `trend_strength` — not defined by this spec

The table carries a `trend_strength` column that the governing spec does not
define. Rather than introduce a new constant, it reuses the spec's own slope
transform:

```
strength = |tanh(4 · slope)|
```

That keeps every constant in the module traceable to this document. It is
flagged here and in the code as the one derived-not-specified metric, and
should be replaced as soon as a definition exists.

## Limitations

- **The current data cannot exercise the gated metrics.** The most any player
  has in one format is 4 matches, and both `hot_cold_flag` and
  `projected_sl_change_probability` require 5. Every one of those fields is
  currently NULL across all 72 rows. That is the spec working as written, not
  a defect — the columns populate as the season accumulates matches.
- **A slope over 2 observations is exact by construction.** Two points always
  fit a line perfectly, so a slope at the minimum is a description of those
  two results, not evidence of a trend. `matches_considered` is stored beside
  it so a reader can weigh it.
- **Skill level is a step function**, changing only when the league re-rates.
  A least-squares line through step data measures the average rate of
  re-rating, not a continuous improvement curve.
- **The heuristic is not validated against outcomes.** No record of actual
  APA re-rating decisions exists in this project, so nothing here has been
  checked against whether a predicted change occurred.

## Rebuilding

```bash
python -m pipeline                      # ingest + exports
python -m scripts.build_player_trends   # then this table
```

Upserted on `(player_id, format)` — always current, not snapshotted.
Re-running is idempotent.
