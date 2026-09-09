# Planned: Clutch Rating and Numeric Trend Score (design only, not built)

Not implemented yet, on purpose. Both need a real, agreed definition
before any code — the "do not invent fields" rule that blocked Clutch
Rating and Break/Run Rate as *export* columns applies just as much to a
freshly-computed one: a plausible-looking formula nobody signed off on is
still a fabricated number once it has a column header.

## Numeric Trend Score — straightforward, both real inputs already exist

`analytics/player_trends.py` already computes, per (player, format,
session):

- `regression_slope` — SL units per match, least-squares over the
  session's full history
- `volatility` — sample stddev (ddof=1) of SL over the last 20
  observations

A numeric trend score would be a **blend of these two already-real
fields**, not a new raw measurement. The obvious shape is a
signal-to-noise ratio:

```
trend_score = regression_slope / (volatility + epsilon)
```

(`epsilon` a small constant, e.g. 0.05, so a slope with `volatility == 0`
doesn't divide by zero or produce an artificially extreme score). A
climbing player with a stable skill level scores higher than one climbing
just as fast but bouncing around — which matches `hot_cold_flag`'s own
existing gate (`HOT` requires `volatility <= 0.40`, not slope alone).

Open question before building it: should this respect the SAME gates
`hot_cold_flag` uses (`sample_size >= 5`), returning `None` below them, or
report a continuous number regardless of sample size with confidence
communicated separately? The Trend Icon work earlier explicitly avoided a
second ungated threshold disagreeing with `hot_cold_flag` — this needs the
same discipline: whatever ships must never imply more certainty than
`hot_cold_flag` already claims for the same row.

## Clutch Rating — the harder one; real data is more limited than it looks

The intuitive definition — "performs well when it matters" — needs a
real signal for *what mattered*, and the honest answer is APA's captured
data gives partial, not full, support:

- **Not available at all**: which individual game within a team match was
  the deciding one, or the score at the time a given game was played.
  `matchPositionNumber` is a fixed roster-position assignment, not
  temporal sequence — there is no real field that says "this was the
  match-deciding rack."
- **Available**: the team match's own final margin
  (`Match.home_score`/`away_score`) and which individual games a specific
  player won or lost within that match (`PlayerHeadToHead`/`PlayerMatch`).

The defensible proxy this supports: **win rate in team matches that were
close**, e.g. decided by 1-2 points, versus the player's overall win rate.
A player who wins a higher share of their individual games specifically in
close team matches has a real, measurable tendency — genuinely computed
from real events — but it is a proxy for "performs in tight matches," not
a measurement of poise or pressure performance, and should be labeled as
exactly that (`"Close-Match Win Rate"`, not `"Clutch Rating"`, unless
there's a firm reason to claim the stronger label).

Open questions before building it:
- What margin counts as "close"? (a real threshold to pick and document,
  same as `MATCHUPS_RISK_SL_GAP` or `HOT_SLOPE_MIN` elsewhere in this
  project — a judgment call, not a fitted number, and should say so)
- Minimum sample size before reporting anything (a player with one close
  match played has no real signal yet)
- Whether to shrink toward the player's overall win rate the way
  `analytics.head_to_head._expected_value` already shrinks a thin pairing
  toward a baseline, so one close-match fluke can't read as a real pattern

## Not started

No code for either yet. Confirm the open questions above (particularly
Clutch Rating's proxy definition and label) before this becomes an
analytics module and an export column, the same order every other real
metric in this project was built in: spec first, formula documented,
*then* wired into a sheet.
