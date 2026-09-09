# Win Probability

A hand-rolled, transparent logistic model estimating P(win) for one
player-vs-opponent pairing, computed alongside (never in place of) the
Lineup Optimizer's existing real signals.

```
analytics/win_probability.py   compute_win_probability() / sl_delta() / race_difficulty()
scripts/build_lineups.py       resolves the real inputs, calls compute_win_probability
analytics/lineup_optimizer.py  PairingCandidate.modeled_win_probability
apa_config.yaml                win_probability: (weights) / lineup_optimizer.weight_modeled_win_probability
```

## Why a second "win probability" exists

`analytics.lineup_optimizer.PairingCandidate` already has a real
`win_probability` field, sourced from `player_h2h_advantage.win_probability`
-- an OBSERVED rate from actual head-to-head history (see
`docs/lineup_optimizer.md`). This module's output is a different kind of
number: a computed ESTIMATE, derived from other real signals via a
formula. The two are never conflated under one name: the observed rate
stays `win_probability`; this module's estimate is
`modeled_win_probability`, a separate field, separate config key, and
separate weight in the Lineup Optimizer's own score formula
(`weight_win_probability` vs `weight_modeled_win_probability`).

## The formula

```
z = weight_sl_delta * SLDelta
  + weight_wr_sl    * WR_SL
  + weight_wr_h2h   * WR_H2H
  - weight_volatility * Volatility

P(win) = 1 / (1 + e^(-logistic_scale * z))
```

clamped to `[clamp_min, clamp_max]` (0.02/0.98 by default) so a real
upset always stays possible and a result is never predicted as an
absolute certainty either way.

| Input | Real source | Missing value |
| --- | --- | --- |
| `SLDelta` | `Player.skill_level` (player) minus `Player.skill_level` (opponent) -- both real, current roster values | 0 |
| `WR_SL` | this player's real win rate, from `player_head_to_head`, against every real opponent sharing the SAME opponent skill level (`scripts.build_lineups.fetch_win_rates_by_skill_level`) | 0 |
| `WR_H2H` | reused directly from the existing, real `player_h2h_advantage.win_probability` -- not recomputed | 0 |
| `Volatility` | `player_trends.volatility` -- the same real Player Trend Analyzer signal `analytics.captains_edge.risk_factor` already uses, but the RAW value, not that combined one | 0 |

Every missing input is treated as **0**, not excluded, and NOT the
neutral 0.5 `analytics.lineup_optimizer.pairing_score` uses for ITS four
inputs. That's a deliberate difference: `pairing_score`'s 0.5 default
means "assume average" for a 0..1 rate; `compute_win_probability`'s 0
default means "this factor contributes nothing to z" -- the right
reading for a difference-from-zero term (`SLDelta`) and for rates whose
absence genuinely carries no signal either way in this formula.

## Verification against real data

Before picking the default weights, each input was checked for real
DIRECTION against this project's own 106 decided `player_head_to_head`
games (68 8-Ball, 38 9-Ball) -- no ML library was used for this (none is
used anywhere in this module); this was a hand-rolled comparison of real
win rates across buckets of each raw signal, the same kind of check
`analytics.close_match_performance.CLOSE_MATCH_MARGIN`'s own docstring
describes for its 14-match sample.

**SLDelta** -- clean, real, monotonic-ish signal:

| SLDelta | n | win rate |
| --- | --- | --- |
| -1 | 23 | 0.391 |
| 0 | 44 | 0.500 |
| +1 | 23 | 0.609 |

Mean SLDelta on real wins: +0.208; on real losses: -0.208. Direction
confirmed; `weight_sl_delta = 0.15` is a conservative magnitude given
SLDelta is an unnormalized raw difference (roughly -3..+3 in this real
data), not a 0..1 rate like the other three inputs.

**WR_SL** -- real direction confirmed, but on a genuinely small sample: only
14 of the 106 real rows had at least one OTHER real game (a real,
leave-one-out check, excluding the row being predicted) against an
opponent sharing that skill level. Mean WR_SL on real wins: 0.750 (n=8);
on real losses: 0.333 (n=6). Real direction, real numbers -- but 14 rows
is too small to trust the exact magnitude, so `weight_wr_sl = 0.20` is
provisional, the same honest caveat `CLOSE_MATCH_MARGIN` gives its own
14-match sample.

**WR_H2H** -- reuses the already-validated, already-shipped real
`win_probability` (Wij), already weighted at 0.30 in the existing Lineup
Optimizer formula (`WEIGHT_WIN_PROBABILITY`). `weight_wr_h2h = 0.30`
mirrors that same real, already-in-production value rather than
re-deriving a second number for the identical underlying signal.

**Volatility** -- real check was genuinely inconclusive: mean volatility on
real wins (0.061, n=23) was slightly HIGHER than on real losses (0.052,
n=27) -- the opposite of the assumed "more volatile is worse" direction,
though on a small sample and a tiny raw difference, not something to
confidently reverse a sign over. `weight_volatility = 0.05` stays small
and mirrors the existing Lineup Optimizer's own `WEIGHT_RISK_PENALTY`
(0.05) for the same underlying volatility signal, rather than asserting a
direction this real check didn't clearly support.

**None of these four weights are claimed as precisely fit or optimal.**
106 real decided games is too small a sample to responsibly fit five free
parameters with confidence (this is exactly why RaceDifficulty, a fifth,
is left out entirely below rather than added on top of an
already-uncertain fit). These are real-direction-checked, deliberately
conservative starting defaults, expected to be revisited as more real
data accumulates -- not settled, final coefficients.

## Race chart verification (and why RaceDifficulty isn't implemented)

APA's real "Games Must Win" race-to-X charts were located and verified
directly (not assumed from memory): `rules.poolplayers.com`, "The
Equalizer® Handicap System" → "Games Must Win Charts"
(https://rules.poolplayers.com/the-equalizer-handicap-system/games-must-win-charts/),
fetched at native resolution from the underlying chart images
(`8-ball-mustwin.png`, `9-ball-mustwin.png`) and transcribed cell by cell.

**8-Ball singles/team chart** -- a genuine two-dimensional interaction
(each cell is `your_race/opponent_race`, and YOUR OWN race target changes
depending on the opponent's skill level, not just your own):

| You \ Opp | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- |
| **2** | 2/2 | 2/3 | 2/4 | 2/5 | 2/6 | 2/7 |
| **3** | 3/2 | 2/2 | 2/3 | 2/4 | 2/5 | 2/6 |
| **4** | 4/2 | 3/2 | 3/3 | 3/4 | 3/5 | 2/5 |
| **5** | 5/2 | 4/2 | 4/3 | 4/4 | 4/5 | 3/5 |
| **6** | 6/2 | 5/2 | 5/3 | 5/4 | 5/5 | 4/5 |
| **7** | 7/2 | 6/2 | 5/2 | 5/3 | 5/4 | 5/5 |

Verified fully symmetric (SL4 vs SL6 gives the same two numbers, in the
right order, as SL6 vs SL4) and **stepped, not linear** -- SL2 and SL3
both get 2/2 at even skill, SL6 and SL7 both get 5/5; the race length
does not increase by a constant amount per skill-level step.

**9-Ball singles/team chart** -- NOT a two-dimensional interaction: each
player's own required points is a pure function of their OWN skill level
alone, independent of the opponent's:

| Skill Level | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Points to win | 14 | 19 | 25 | 31 | 38 | 46 | 55 | 65 | 75 |

Also stepped, not linear (gaps: 5, 6, 6, 7, 8, 9, 10, 10 -- widening, not
constant). Confirmed structurally different from 8-Ball's chart (a real,
citable difference between the two formats, not an assumption that they
match).

**Why this isn't wired into the model despite being verified**: a
race-length-derived signal plausibly overlaps with `SLDelta` above -- how
much longer or shorter your required race is, relative to your
opponent's, is itself mostly determined by the same skill-level pairing
`SLDelta` already captures. Whether that overlap would double-count the
same real signal (and bias the model, not just add noise) was not
checked against real data before this shipped, and six real weights would
compound the already-small-sample fitting problem described above.
`analytics.win_probability.race_difficulty()` exists as a real function
with the real, verified chart data available to a future implementation,
but always returns `0.0` -- a documented gap, not a fabricated stand-in.
There is no `weight_race_difficulty` key in `apa_config.yaml`'s
`win_probability` section for the same reason: nothing multiplies a
placeholder.

## Integration into the Lineup Optimizer

`analytics.lineup_optimizer.LineupWeights` gained a fifth field,
`modeled_win_probability`, defaulting to **0.0** -- `pairing_score`'s
formula becomes

```
Fij = weight_matchup_score*Sij + weight_win_probability*Wij
    + weight_confidence*ECi + weight_risk_penalty*RPi
    + weight_modeled_win_probability*MPij
```

With the default 0.0, `MPij` (this module's estimate) contributes
nothing -- every existing lineup keeps its exact original score until
`apa_config.yaml`'s `lineup_optimizer.weight_modeled_win_probability` is
explicitly set non-zero.
