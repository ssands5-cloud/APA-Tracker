# Season Projection

Projects the real REMAINING schedule using each team's real
season-to-date record, and reports the real historical standings trend.

```
analytics/season_projection.py   win_rate() / log5_win_probability() / project_remaining_schedule() / team_volatility_curve()
```

Purely derived and purely computational, the same split every other
analytics module in this project uses -- it queries nothing itself and
is not yet wired into the production demo/Excel/JSON layer (see
"Integration status" below).

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

## Projection model contract

The unit of projection is one real remaining team match, never an invented
player matchup. Inputs are:

- the selected team's season-to-date wins and losses;
- each scheduled opponent's season-to-date wins and losses when the captured
  standings identity can be resolved unambiguously;
- the real unscored schedule with match ID, opponent ID/name, week, format, and
  session;
- captured standings history for the descriptive historical curve.

`analytics/season_projection.py` returns one `RemainingMatchProjection` per
scheduled match and one aggregate `SeasonProjection`. The planned immutable
demo document combines those analytics values with explicit builder-supplied
source status and actual totals. Required document outputs are:

| Output | Definition |
| --- | --- |
| `win_probability` | log5 probability when both real rates exist; documented single-side fallback when only one exists; null when neither exists |
| `upset_likelihood` | `min(win_probability, 1 - win_probability)`; null with no probability |
| `expected_wins` | sum of available remaining-match probabilities |
| `expected_losses` | sum of their complements |
| `projected_final_wins` | builder-level display value: actual wins plus expected remaining wins |
| `projected_final_losses` | builder-level display value: actual losses plus expected remaining losses |
| `coverage` | projected remaining matches divided by total non-bye remaining matches; null for no remaining schedule |
| `standings_points` | real record-change points returned by `team_volatility_curve` |

The two projected-final fields are exact presentation additions from supplied
actual totals and the analytics output; they are not persisted as observed
standings. Renderers receive them precomputed and do not add values in the
browser or workbook.

### Assumptions and limitations

- Season win rate is treated as stationary over the remaining schedule.
- Remaining matches are aggregated as independent expectations; the sum is not
  a guaranteed integer record and does not model playoff qualification.
- Log5 uses only team records. It does not account for future player lineup,
  home/away, travel, forfeits, availability, skill changes, or opponent
  volatility.
- The one-side fallback is a declared behavior, not an imputed opponent rate.
  The output carries `BOTH_RATES`, `OUR_RATE_ONLY`, `OPPONENT_RATE_ONLY`, or
  `NO_RATE` source status for every match.
- The current implementation's `high_upset_risk_matches` uses a caller-supplied
  0.40 cutoff. The production demo presents the underlying numeric
  `upset_likelihood` and cutoff provenance, not a categorical warning or
  recommendation. The cutoff is not fitted to APA outcomes.
- `StandingsSnapshot` currently has team name rather than immutable team ID.
  Ambiguous/missing name resolution leaves the opponent rate unavailable; it
  never chooses the first matching name.
- Capture time and remaining-schedule count are part of every output. A stale
  snapshot is not described as live.

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

## HTML layout

The proposed `season_projection.html` is a self-contained presentation of one
immutable projection document:

```text
section#season-projection
├── team/session scope, capture time, and model disclosure
├── actual record and remaining-schedule coverage cards
├── expected remaining W/L and projected-final record cards
├── figure#season-projection-curve
│   ├── real historical win-rate points
│   └── visually separate projected endpoint, when available
├── table#remaining-match-projections
└── assumptions, source-status legend, and missing-data notes
```

The remaining-match table contains week/date, match ID, opponent identity,
actual source rates, probability source status, win probability, and upset
likelihood. Rows follow real schedule order: normalized date, week, then match
ID. Unknown dates remain null and use the later keys; no generated date is
shown. A missing probability says `No data` and remains in the table.

The chart never connects across missing points. Historical observations use a
solid line; any projected endpoint uses a dashed line and explicit “projection”
label. Accessible text repeats every point. No playoff band, confidence
interval, final rank, or categorical season outcome is invented.

## Excel layout

The proposed `season_projection.xlsx` contains three values-only sheets.

### `Season_Projection`

One row for the selected scope with team ID/name, session/format, actual W/L,
actual win rate, remaining match count, projected match count, coverage,
expected remaining W/L, projected-final W/L, model/formula version, capture
time, source-manifest ID, and unavailable reason.

### `Remaining_Matches`

One row per real remaining match with week/date, match/team IDs, opponent name,
both source win rates, probability-source status, win probability, upset
likelihood, and source timestamp. Raw probabilities use numeric percentage
format; nulls remain blank with a status column.

### `Standings_History`

One row per deduplicated record change: capture timestamp, wins, losses, win
rate, rank, and points when sourced. Rows remain chronological. A single real
point is valid; a header-only sheet is valid only when the manifest explicitly
records that no standings history exists.

The workbook uses fixed widths, frozen headers, literal IDs, and no formulas,
macros, external links, hidden helpers, volatile dates, or workbook-side
projection logic.

## Ordering, unavailable data, and parity

- Remaining scheduled matches are never dropped because a rate is missing.
- `NO_RATE` is an unavailable estimate; it is not converted to 50%.
- Opponent rates are keyed by immutable team ID after a verified identity join.
- HTML, Excel, JSON, and manifest compare raw probabilities, expected totals,
  source status, schedule keys, and historical points before display rounding.
- Deterministic ties use opponent team ID and match ID, never a probability or
  viewer-local clock.

## Integration status: not yet wired into the pipeline

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
not yet done. Production wiring calls the existing pure analytics once, builds
one immutable document, and passes it to the HTML/Excel renderers and demo
manifest. Any identity ambiguity, output mismatch, or renderer-added formula
blocks the Season Projection demo section.
