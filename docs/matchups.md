# Matchup Advantage Engine

Gives a captain a per-opponent read on each player: real head-to-head
record, how it's trending, and a single 0-100 score to sort by when
setting a lineup.

## Where it comes from

No new query, no new scrape. A team match's `MatchPage` already returns,
per individual game, `matchPositionNumber`/`playerPosition` on both the
home and away side. Standard APA team format plays same-numbered positions
against each other (position 1 home vs. position 1 away, and so on), so
pairing those rows tells you exactly who played whom — not just which two
teams faced off.

- `scraper/graphql_scraper.py::head_to_head_rows(match)` does the pairing,
  from real captured field names — see its docstring and
  `database/models.py`'s `PlayerHeadToHead` for why this is reading a
  documented field, not guessing at an ambiguous id the way the career-stats
  alias id was.
- `database/ingest.py::ingest_head_to_head()` writes one raw row per
  (player, match) into `player_head_to_head` — both directions of a
  pairing, since each side has its own result/points/skill level.
- `analytics/matchup_builder.py::build_matchups()` groups those raw rows,
  scores each group (`analytics/matchups.py`), and upserts the aggregate
  into `player_matchups`. Called directly by
  `scheduler.graphql_sync.run_all_teams()` (right after head-to-head
  ingestion, before export) and by `scripts/build_demo.py`, so the
  Excel/JSON outputs always include current matchup data as part of a
  normal sync or demo build. `scripts/build_matchups.py` is a thin CLI
  wrapper around the same function, for recomputing on demand against an
  existing database without a network call.

## How the score is computed

`analytics/matchups.py::matchup_score(rows, trend, volatility)`:

```
weight       = sample_size_weight(n)                 # 0 -> 1.0, ramping up to FULL_CONFIDENCE_GAMES (10)
win_swing    = (weighted_win_rate(rows) - 0.5) * 80   # recency-weighted head-to-head record: ±40 swing
skill_swing  = opponent_skill_modifier(rows)          # bonus/penalty from wins' skill-level gap, capped ±10

score = 50
       + weight * (win_swing + skill_swing)   # the actual head-to-head evidence, damped by sample size
       + trend_modifier(trend)                # +5 up / -5 down / 0 stable or no data -- NOT damped by weight
       - volatility_penalty(vol)              # 3 points per real change, capped at 15 -- NOT damped by weight
clamped to [0, 100]
```

- **Win rate** is the actual won/lost record against *that specific*
  opponent (from `player_head_to_head`), not a season-wide average. The
  `matchup_score` formula uses a **recency-weighted** version
  (`weighted_win_rate`) — see "Recency bias" below — while the exported
  "Win Rate" column stays the plain, unweighted record.
- **Sample-size weighting** (`sample_size_weight`) scales the win-rate and
  opponent-skill swing by how many games you've actually got, from 0 at
  zero games up to full strength at `FULL_CONFIDENCE_GAMES` (10) — a
  heuristic choice, not a statistically fitted one. This is what fixes the
  original gap: a 1-0 record and a 10-0 record no longer score the same,
  because the 1-0 record's swing gets multiplied by roughly 0.1 instead of
  1.0. **Trend and volatility are NOT scaled by this** — they describe the
  player's current form in general, not something this one opponent's
  game count should dilute.
- **Opponent-skill-level weighting** (`opponent_skill_modifier`): a win
  against a higher-skill-level opponent earns a bonus; a win against a
  lower-skill-level one costs a (smaller, capped) penalty — 2 points per
  skill level of average gap on WON games only, capped at ±10. This was
  deliberately left out of the first version of this engine (APA's own
  point-per-skill-level handicap already compensates for a gap in the
  scoring itself, so a second adjustment risks double-counting), and has
  been added back in on explicit direction — that tradeoff is a product
  decision about how a captain wants the tool weighted, not a data
  question. It's scoped to wins only: there's no evidence base yet for how
  a *loss* to a much stronger opponent should compare to a loss against an
  even one, so that stays out for now. `avg_opponent_skill_level` is still
  reported as plain descriptive context alongside the score.
- **Trend** and **volatility** are about the *player*, not the pair — the
  same signal the Skill Level tab shows (`analytics/skill_level_trends.py`),
  reused here rather than recomputed. A player trending up gets a small
  boost across every matchup; one whose skill level keeps bouncing around
  gets a small penalty across every matchup.
- **No history yet** → score is `50` (neutral), not a guess in either
  direction.

### Recency bias

`weighted_win_rate(rows)` gives a more recent game slightly more say than
an older one — a linear ramp from 0.7× (oldest game) to 1.3× (most recent),
not a dominant effect. `rows` must already be in chronological order,
oldest first, for this to mean anything; `database.queries.head_to_head_history`/
`all_head_to_head` guarantee that ordering (by `Match.match_date`, falling
back to insertion order when a date is missing or tied — see their
docstrings for the one real caveat: `Match.match_date` is stored as
delivered text, not a true datetime, so this relies on the live API's ISO
8601 format sorting correctly as plain text, which it does).

### Confidence score

A new, separate 0-100 number (`analytics/matchups.py::confidence_score`,
its own `Confidence Score` column/key) answering "how much should you
trust `matchup_score`?" — because sample-size weighting means a 1-0
matchup and a well-established 8-2 one can now land on similar scores,
and confidence is what tells them apart. Averages three independently
documented components:

- **Sample size** — `sample_size_weight(n) * 100`: 0 at zero games, 100 at
  `FULL_CONFIDENCE_GAMES` or more.
- **Volatility** — `100 - 15 * volatility`, floored at 0: the same per-
  change cost `volatility_penalty` charges the score itself.
- **Trend stability** — `stable` is trusted most (100); a trend actively
  moving (`up` or `down`) means the player's true current level is a
  moving target, not a settled one (70); `no data` is a genuine unknown,
  landing in between (50).

### Format and session

A player's 8-ball record against an opponent doesn't predict their 9-ball
one, and a stale prior session's record isn't "current form" the way this
session's is — `player_matchups` is grouped and scored by
`(player, opponent, format, session_name)`, not just `(player, opponent)`.
Neither field comes from `MatchPage` itself (it has no division/session
info); both are threaded in from the originating team's own context
(`dashboard_teams_rows()`'s `division_type`/`session_name`, or the
single-team path's `team_row()`) onto `Match` at ingestion, and
`ingest_head_to_head()` copies them from the resolved `Match` row onto
each `PlayerHeadToHead` it writes. A row ingested without that context
(an older sync, or a caller with no team data handy) still aggregates,
under a shared `NULL`/`NULL` bucket, rather than being dropped. The
Excel sheet and JSON export both carry `Format`/`format` and
`Session`/`session_name` columns so two rows for the same two names
aren't a mystery duplicate.

### Reconciling corrected scoresheets

The API returns a match's COMPLETE current scoresheet on every fetch, not
a diff — if a lineup correction changes who played which position,
re-ingesting must not leave the old pairing sitting alongside the
corrected one. `ingest_head_to_head()` reconciles at match level: every
existing `player_head_to_head` row for a match being re-ingested is
deleted before the current rows are inserted, scoped to just the
match_ids actually present in that call (a different match's rows are
untouched). If that reconciliation leaves a `(player, opponent, format,
session)` group with zero remaining head-to-head rows anywhere,
`build_matchups()` prunes its now-unsupported `player_matchups` row too
(`database/ingest.py::prune_matchups_not_in`) — the aggregate is rebuilt
from scratch each run, not just upserted on top of whatever was already there.

### Result validation

`PlayerMatch.result`/`PlayerHeadToHead.result` are normalized to exactly
`"W"`, `"L"`, or `None` at ingestion (`database/ingest.py::_normalize_result`)
— a missing value, a blank string, or anything the API doesn't document as
a result (`"UNKNOWN"`, a typo) becomes `None`, never a silent loss. Every
win-rate calculation and the sample size `matchup_score`/`confidence_score`
use are based on RECOGNIZED-result games only
(`analytics/matchups.py::recognized_results`) — a row with an unreadable
result doesn't count as a loss, and doesn't inflate the sample either.

### Referential integrity

SQLite doesn't enforce foreign keys unless a connection explicitly turns
them on — `database/engine.py::create_db_engine()` now does, for every
connection it opens. This is what would have caught, at insert time
instead of silently, the exact real bug that motivated
`PlayerMatch`'s docstring: a row pointing at a match that doesn't exist.

## Two things this deliberately doesn't include

The original spec for this feature asked for "average innings" and
"defensive shots vs. each opponent." Neither is a real field:

- **Innings** has never appeared in any query this API returns (checked
  every captured operation in `parser/apa_graphql.py`) — not an APA
  8-ball/9-ball stat this app has ever seen.
- **Defensive shot average** only exists as a career-wide number
  (`PlayerCareerStats.defensive_shot_avg`, from `getEightBallStats`), never
  per-opponent — there's nothing to average per matchup.

Rather than invent numbers for either, `avg_points_earned` and
`avg_opponent_skill_level` stand in: real, per-opponent, and actually
present in the data.

## A known limitation, inherited rather than new

Opponent identity here relies on the same `member`/roster id resolution
used everywhere else in this app. A real person who ends up mapped to two
different ids (a gap flagged, but not yet confirmed, in
`docs/graphql-captures/*/HANDOFF.md`) will show up as two separate,
incomplete opponents here rather than one merged one — smaller sample
sizes, not wrong numbers. This isn't a new bug from the Matchup Advantage
Engine; it's the same open question this project has already been
tracking, just now visible in a new place.

## Using it as a captain

1. Run a sync (`python -m scheduler.graphql_sync`) or the demo build --
   both already call `build_matchups()` themselves as part of the run.
   `python scripts/build_matchups.py` is there for recomputing on demand
   against an already-synced database, not a required extra step.
2. Open the "Matchups" sheet in the Excel export, or the "Matchups" tab in
   the demo/dashboard page, for each of your players.
3. "Recommended opponents" (score ≥ 65) and "opponents to be cautious of"
   (score ≤ 35) are the standout cases — most matchups will sit close to
   the neutral 50 baseline early in a season, which is real information
   too (there just isn't a strong signal yet, and the `Confidence Score`
   column will say so).
4. Check the `Confidence Score` alongside `Matchup Score` before treating
   either number as a verdict — a high `Matchup Score` with a low
   `Confidence Score` is a small, promising sample, not an established
   edge.
5. A row with `Has History` = "No" means exactly that: this player and
   that opponent are both known (each has real head-to-head history
   against someone), but never against each other yet. It's shown at a
   neutral 50/0-confidence rather than being left off the sheet, so "no
   data" and "an even matchup" never look the same as "we don't know this
   pair exists" -- the last of those used to be silent absence.
