# Win-Probability Model Validation

Checks `analytics.head_to_head.win_probability` against real recorded match
outcomes. That function is the source of `Wij` in the Lineup Optimizer's
objective — `Fij = 0.50*Sij + 0.30*Wij + 0.15*ECi + 0.05*RPi`
([docs/lineup_optimizer.md](lineup_optimizer.md)) — so this is, concretely,
"how much should the optimizer trust 30% of its own scoring formula."

```
analytics/prediction_validation.py   the two analyses and the grading maths
scripts/validate_predictions.py      builds the report from the real database
exports/prediction_validation.json   the report (gitignored, regenerated)
```

Run it with:

```bash
python scripts/validate_predictions.py
python -m scripts.validate_predictions
python scripts/validate_predictions.py --bins 10   # finer calibration buckets
```

This is a standalone diagnostic, **not** part of `python -m pipeline`. It
answers "is the model any good", which is a maintainer question, not
something a captain needs recomputed on every sync.

## Why two separate analyses

`win_probability` blends two real terms in log-odds space: a skill-level
gap, and the pairing's own historical record (Laplace-smoothed, damped by
`reliability_weight(n)`). They have different validation requirements, so
they're graded separately rather than only ever as one combined number that
could hide which half is doing the work.

### Analysis A — the skill-level term, cross-sectional

A player's `own_skill_level` and the opponent's `opponent_skill_level` are
both posted **before** a given match is played — APA's handicap system rates
players from history outside that specific match. Grading the skill-only
prediction against that same match's own W/L result is therefore a
legitimate, non-circular test: the predictor already existed independently
of the outcome it's predicting. No held-out split is needed. Runs on every
`player_head_to_head` row that carries both skill levels and a recognised
result.

### Analysis B — the historical-record term, walk-forward

The record term is about a *pairing's* past meetings, so validating it
correctly requires an actual walk-forward: for the k-th meeting between one
player and one specific opponent, predict using `win_probability(rows[:k])`
— strictly earlier games only — then grade against game k's real result.
Grading against `rows[:k+1]` instead (letting the prediction see the very
game it's being scored on) would be circular, not a validation. A pairing's
very first meeting is never scored — there is nothing prior to predict from.

## Current real findings

As of the last run against `data/apa_tracker.db` (106 head-to-head rows, 106
distinct pairings):

| Metric | Model (skill-only) | Always guess 50/50 |
|---|---|---|
| Brier score (lower is better, 0.25 = coin flip) | **0.2416** | 0.25 |
| Log loss (lower is better, ln 2 ≈ 0.6931 = coin flip) | **0.6755** | 0.6931 |
| Accuracy | **56.6%** | 50% |

The skill term carries real but modest signal. Splitting by whether the two
players were actually at the same skill level makes this concrete:

| Games | n | Accuracy |
|---|---|---|
| Even skill level (delta = 0) | 44 | 50.0% (a coin flip, correctly — the term has nothing to say when there's no gap) |
| A real skill gap either direction | 62 | 61.3% |

The calibration curve tracks well where there's enough data to judge it: the
`[0.4-0.6)` bucket (90 of 106 games — most real pairings in this data are
close in skill) predicts 0.50 and observes 0.50; the `[0.6-0.8)` bucket (8
games) predicts 0.71 and observes 0.625. `mean_calibration_error` is exactly
0.0 overall — no systematic over- or under-confidence in aggregate — though
see [Known gaps](#known-gaps) about what that can and can't rule out. No bias
by format was found: 8-ball (n=68, Brier 0.238) and 9-ball (n=38, Brier
0.248) land close together.

**Analysis B currently has zero held-out predictions.** Every one of the 106
pairings in the database has met exactly once — `pairings_with_a_rematch` is
0. This is a real state of the data, not a defect in the check: the
historical-record term is real, documented, and unit-tested
([tests/test_head_to_head.py](../tests/test_head_to_head.py)), but it has
never yet been exercised against a second meeting the way it will be used in
production. Re-run `scripts/validate_predictions.py` once rematches start
appearing in a season's data — `data_summary.pairings_with_a_rematch` in the
JSON report is the number to watch.

## Known gaps

- **Small sample.** 106 games is enough to see a real, non-zero effect, not
  enough to trust the exact calibration-curve shape in the sparse
  `[0.2-0.4)` / `[0.6-0.8)` buckets (8 games each). Re-run as the season's
  data grows.
- **`mean_calibration_error ≈ 0` is necessary, not sufficient.** Over- and
  under-confident errors can cancel in the mean; the bucketed
  `calibration_curve` output is what actually rules that out, and is worth
  reading alongside the single number rather than instead of it.
- **The full `Sij` (matchup_score) input is not covered here.** The
  season-scoped `matchup_score` that Captain's Edge feeds the optimizer
  (`analytics.captains_edge`) depends on a player's skill-level trend and
  volatility computed from their *entire* season history, not just one
  pairing. Backtesting it correctly means reconstructing what that
  trend/volatility looked like at each point in time, which is a
  meaningfully larger project than this pass — flagged here rather than
  quietly skipped.
- **Skill-level-only is an ablation, not a competing model.** It exists to
  isolate whether the record term is pulling its weight once real rematches
  exist; it is not a proposal to replace `win_probability` with something
  simpler.
