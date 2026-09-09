# Design history: Trend Score and Close-Match Win Rate

**Both are now built** — this doc is kept as the record of how they were
specced *before* any code, not a statement that they're still pending.
Current docs: `docs/player_trends.md`'s "Trend Score" section and
`docs/close_match_performance.md`. The discipline below (finalize the
definition first, then implement) is why neither shipped with a
plausible-looking formula nobody had signed off on — the "do not invent
fields" rule that blocked Clutch Rating and Break/Run Rate as *export*
columns applies just as much to a freshly-computed one.

**Neither needs a new upstream export or a new pipeline stage.** Both are
computable entirely from fields already ingested today
(`analytics/player_trends.py`'s output; `Match`/`PlayerHeadToHead` rows).
That's the answer to "what upstream fields are needed": none — the
constraint on both is definitional (what should the number mean), not
data availability.

## Trend Score — finalized definition

`analytics/player_trends.py` already computes, per (player, format,
session):

- `regression_slope` — SL units per match, least-squares over the
  session's full history
- `volatility` — sample stddev (ddof=1) of SL over the last 20
  observations
- `hot_cold_flag` — `HOT` requires `slope >= 0.05`, `volatility <= 0.40`,
  `sample_size >= 5`; `COLD` the mirror; else `NEUTRAL`; `None` below
  `sample_size >= 2`

Trend Score is a blend of the first two, not a new raw measurement:

```
trend_score = regression_slope / (volatility + 0.05)
```

`0.05` (not a fitted value, a heuristic floor): real observed volatility
in this project's own fixtures runs roughly 0.2-0.7 once a player has
enough history to compute it at all, so a floor this small only matters
when volatility is nearly zero (a genuinely rock-steady player), where it
keeps the ratio finite without materially damping the signal at any
realistic real volatility level.

**Gate closed**: yes, reuse `hot_cold_flag`'s own gate — return `None`
whenever `hot_cold_flag` is `None` (today: `sample_size < 2`, or
`volatility` unavailable). A continuous score for a row `hot_cold_flag`
itself refuses to call HOT/COLD/NEUTRAL would claim more confidence than
this project's own tested classifier already claims for that same row —
the exact mistake the Trend Icon work upstream of this doc was built to
avoid.

## Close-Match Win Rate (the metric earlier drafts called "Clutch Rating")

Renamed on purpose, and finalized as the name here: this measures a real,
narrow thing — win rate specifically in close team matches — not poise or
pressure performance in general, and should never be labeled more strongly
than what it actually is.

**What's real and what isn't**: APA's captured data has no field for which
individual game within a team match was the deciding one, or the score at
the time a given game was played (`matchPositionNumber` is a fixed
roster-position assignment, not temporal sequence). What IS real: the team
match's own final margin (`Match.home_score`/`away_score`) and which
individual games a specific player won or lost within that match
(`PlayerHeadToHead`/`PlayerMatch`).

**Close-match threshold, checked against this project's own real data,
not picked blind**: the 14 decided team matches in the current database
have margins `[2, 2, 2, 4, 5, 6, 6, 8, 9, 10, 14, 14, 21, 28]` (median 8).
**Margin <= 4** is the finalized threshold — it captures the bottom
quartile of real matches actually played (4 of 14) without being so tight
it only ever matches a single-point squeaker. Stated as a heuristic, not a
fitted one, the same way `MATCHUPS_RISK_SL_GAP`/`HOT_SLOPE_MIN` are
elsewhere in this project — and flagged as genuinely provisional: 14
matches is a small sample, and 8-ball/9-ball divisions may play to
different point totals, which could argue for a per-format threshold once
there's enough data in each to check that separately rather than guess.

**Minimum sample, finalized**: `>= 3` close matches played before
reporting anything; `None` below that, the same "no data" convention as
`volatility`/`regression_slope`.

**Shrinkage, finalized**: reuse the existing `analytics.matchups.
reliability_weight(n) = n / (n + 3)` curve — the same shrinkage this
project already uses for a thin head-to-head record — rather than invent a
second one. At the `n >= 3` floor above, a close-match win rate is
weighted `3/6 = 0.5` toward the player's overall win rate; it only
approaches full weight past roughly 10 close matches played, which a
single season is unlikely to reach for most players. That's intentional:
a small, real pattern should read as tentative, not asserted.

```
shrunk_close_match_win_rate =
    reliability_weight(n) * close_match_win_rate
    + (1 - reliability_weight(n)) * overall_win_rate
```

## Built, following the order below

Both were implemented in exactly the order this doc's own closing note
called for: an analytics module with its own tests first
(`analytics/player_trends.trend_score`;
`analytics/close_match_performance.py`), then wired into `ui/export_json.py`
and `ui/export_excel.py`. See `docs/player_trends.md` and
`docs/close_match_performance.md` for the current, maintained
documentation — this file is the design history, not the source of truth
for behavior going forward.
