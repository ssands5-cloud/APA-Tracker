# Season Projection

Projects the real REMAINING schedule using each team's real
season-to-date record, and reports the real historical standings trend.

```
analytics/season_projection.py   win_rate() / log5_win_probability() / project_remaining_schedule() / team_volatility_curve()
```

Purely derived and purely computational, the same split every other
analytics module in this project uses -- it queries nothing itself and
is not yet wired into the pipeline/Excel/JSON layer (see "Scope" below).

## What this deliberately does NOT do

**No future lineup is simulated or assumed.** `docs/future_sheets_upstream_gaps.md`
already documents the real gap: there is no "selected upcoming lineup"
concept anywhere in this project's captured data, and inventing one to
project player-level outcomes would be fabrication. Projection here stays
at the TEAM level, using only real standings and real schedule data --
never a guessed future roster.

## The real inputs

| Concept | Real source |
| --- | --- |
| Remaining matches | `Match` rows where `is_scored` is `False` -- the same real, already-scraped schedule `ui.export_json._schedule` already surfaces for the configured team |
| A team's win rate | `StandingsSnapshot.wins` / `.losses`, real season-to-date totals |
| Standings history | every real `StandingsSnapshot` capture for one team, across real sync runs over real time |

## Win probability: the real log5 formula

Given both teams' real win rates, one match's win probability uses
**log5** (Bill James) -- a real, established sabermetrics method, not an
invented formula:

```
P(A beats B) = (pA - pA*pB) / (pA + pB - 2*pA*pB)
```

When only one side has a real decided-game record (a new opponent never
faced this season, or a season with no decided games yet for either
side), that side's own real win rate is used directly rather than
guessing the missing one. Both sides missing is `None`, never a guessed
0.5 -- 0.5 only appears from the formula's own real degenerate case
(both undefeated, or both winless).

**Upset likelihood** is the probability of the LESS-favored side winning
that specific match -- `min(p, 1-p)` -- 0.5 at a genuinely even match,
approaching 0 as one real side becomes the heavy favorite.

**Expected wins/losses** for the whole remaining schedule are simply the
sum of each remaining match's real win probability (and its complement).
A match with no real win-probability estimate at all (neither side has
decided games) is still listed for real schedule visibility, but
contributes 0 to both sums and is never flagged as high upset risk --
absence of evidence is not evidence of anything.

## Team volatility curve

A real, historical win-rate trend built from every real `StandingsSnapshot`
capture, **deduplicated to only the captures where the real (wins,
losses) record actually changed.** Without that, a team synced dozens of
times a day with no new real result would show a "curve" that's really
just noise from how often the pipeline happened to run.

**Checked against this project's own real data before shipping**: the
real, configured team's standings were captured 46 times across 3 real
days (2026-09-06 through 2026-09-09) with the record identical every
single time (`W 1 L 2` in one division, `W 0 L 3` in another). Run through
`team_volatility_curve`, that real history collapses to exactly ONE real
point per division -- an honest reflection that no real volatility exists
in the data yet, not a curve synthesized to look more interesting than it
is. As real match results accumulate, this same function will produce a
real multi-point trend without any code change.

## Scope: not yet wired into the pipeline

Unlike `analytics.lineup_risk`/`analytics.opponent_scouting`, this module
is delivered as a pure, fully-tested analytics module only -- no JSON key,
no Excel sheet, no config section yet. Two real gaps would need closing
first, honestly, rather than guessed past:

- `StandingsSnapshot` has no real `team_id` column, only `team_name`
  (a plain string) -- matching a real opponent's `Match.away_team_id` to
  their standings row requires a name-based join, which needs its own
  real verification (duplicate/renamed team names) before being trusted
  in a captain-facing export.
- Which team's remaining schedule to project (the same `apa_config.yaml`
  `team.team_id` every other per-team view already uses) needs threading
  through a real builder script, the same way `scripts.build_lineups`
  already does for the Lineup Optimizer.

Both are real, scoped, solvable follow-ups -- not fabrication risks, just
not yet done.
