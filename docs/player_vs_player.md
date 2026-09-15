# Player vs Player

A focused head-to-head comparison view for two specific real players:
`analytics/player_vs_player.py` (the pure computation) and
`ui/tabs/player_vs_player.py` (the reporter that renders it).

## Correcting the request this feature was built from

The task that produced this feature specified a `game_results` table and a
query shaped like:

```sql
SELECT * FROM game_results
WHERE (player_id = :p1 AND opponent_id = :p2)
   OR (player_id = :p2 AND opponent_id = :p1)
ORDER BY date ASC;
```

**No `game_results` table exists in this project's schema.** The real
per-game table is `PlayerHeadToHead` (`database/models.py`), and the real,
already-shipped query for exactly this shape already exists:
`database.queries.head_to_head_history(db, player_id, opponent_id)` --
every game between two specific players, chronological, oldest first. This
feature is built on that real query, not a new one, and not the imagined
table. See `database/queries.py`.

The request also asked for average innings, per-opponent defensive shots,
and a break/run rate. None of the three is implemented -- see
[What this deliberately does not include](#what-this-deliberately-does-not-include)
below for the real, sourced reason for each. No placeholder, proxy,
estimate, synthetic value, or fabricated substitute is used for any of
them.

## Data source

```
database.queries.head_to_head_history(db, player_id, opponent_id)
  -> list[PlayerHeadToHead], chronological (oldest first)

analytics.player_vs_player.summarize(rows, player_id, opponent_id)
  -> PlayerVsPlayerSummary
```

`analytics/player_vs_player.py` does not query the database itself --
consistent with every other analytics module in this project, it takes
already-fetched real rows and computes. `match_dates` (an optional
`{match_id: date_string}` map) is a caller-supplied parameter for
resolving a real date per game; `PlayerHeadToHead` has no ORM relationship
back to `Match`, so that resolution is a query-layer concern, not this
module's. Wiring a real builder script that resolves dates from the
database and writes a standalone HTML/Excel export is a disclosed,
separate follow-up, not part of this pass (see
[Not yet built](#not-yet-built)).

## Formulas -- all reused, none new

Every number `analytics.player_vs_player.summarize` produces is a direct
call into the pre-existing, already-validated `analytics.head_to_head` /
`analytics.matchups` modules. No new blending, no new heuristic, no second
scoring layer:

| Field | Formula | Source |
| --- | --- | --- |
| `wins` / `losses` | Count of recognized `W`/`L` results | `analytics.head_to_head.win_loss` |
| `total_games` | Count of recognized-result rows | `analytics.matchups.recognized_results` |
| `sl_delta` | Mean(opponent SL - own SL) across all games | `analytics.head_to_head.average_skill_level_delta` |
| `reliability` | `n / (n + 3)`, `n` = recognized game count | `analytics.matchups.reliability_weight` |
| `modeled_win_probability` | Skill term + reliability-weighted, Laplace-smoothed history term, in log-odds space | `analytics.head_to_head.win_probability` |
| `skill_only_probability` | Skill-gap term alone, evaluated on the most recently posted skill levels from the pair's last real game | `analytics.head_to_head.skill_only_win_probability` |
| `trend` | "up"/"down"/"stable"/"no data", first-vs-last own skill level across all games | `analytics.head_to_head.skill_level_trend` |
| `recent_trend` | The same first-vs-last rule, scoped to only the last `recent_games` (default 5) games | `analytics.player_vs_player.recent_trend` (a thin wrapper, not a new rule) |
| `next_match_projection` | Identical to `modeled_win_probability` | Same value, restated under the name the UI uses for a forward-looking read |

`skill_only_probability` is shown as separate, labeled context next to
`modeled_win_probability` -- never blended into one number, matching the
observed-vs-modeled separation rule this project applies everywhere else
(see `docs/captain_first_edge_experience.md` §5 for the same principle
applied to the captain-first views).

## What this deliberately does not include

- **Innings.** Has never appeared in any query APA's API returns to this
  project (checked every captured operation in `parser/apa_graphql.py`).
  Not a real captured field anywhere in this schema. No `avg_innings` or
  innings-based volatility metric is computed -- there is nothing real to
  compute it from. (Same finding `docs/matchups.md`'s "Two things this
  deliberately doesn't include" section already documents for the
  Matchup Advantage Engine.)
- **Defensive shot average, per opponent.** Exists in this schema only as
  a lifetime, career-wide number (`PlayerCareerStats.defensive_shot_avg`,
  from `getEightBallStats`) -- never per-opponent. There is no real
  per-pairing figure to report. (Same finding as above.)
- **Break/run rate, per opponent.** A new finding from building this
  feature, not previously documented: break/run events
  (`PlayerMatch.eight_on_break`/`eight_break_and_run`/`nine_on_snap`/
  `nine_break_and_run`) are captured per MATCH, not per opponent. A single
  match can include games against more than one opponent --
  `PlayerHeadToHead`'s own docstring cites a real scoresheet (match
  51007724) where one player played two different opponents in the same
  match -- so a match-level break/run count cannot be honestly attributed
  to one specific pairing.

## UI layout

`ui/tabs/player_vs_player.py::render(summary, player_name, opponent_name)`
returns one self-contained HTML fragment, no external resources (same
posture as `ui/tabs/matchups.py`/`ui/tabs/tonights_match.py`):

1. **Header** -- both real player names, total recognized games, W-L
   record, and the not-captured disclosure (always shown, not only when
   relevant, so it is never mistaken for something that was simply left
   off this particular pairing).
2. **Stats table** -- modeled win probability, the skill-only ablation,
   average skill delta, reliability weight, both trend readings, and the
   next-match projection. A missing value renders as the literal text
   "No data", never a blank cell or a fabricated 0%/50%.
3. **Timeline** -- one real, dependency-free inline-SVG marker per game in
   chronological order, colored by its real result (win/loss/unrecognized).
   Not a chart library; matches this project's no-external-resources rule.
4. **Games table** -- every real game, sortable by clicking a column
   header (the same client-side sort idiom `ui/tabs/matchups.py` already
   uses), with match id, date (when supplied), result, both skill levels,
   points, 9-ball ball count, format, and session.

## Example

Two players at a real +1 skill-level edge (own SL 5, opponent SL 4), one
real recorded game, a win:

| Field | Value |
| --- | --- |
| `modeled_win_probability` | 63.9% |
| `skill_only_probability` | 59.9% |
| `reliability` | 0.25 |
| `wins` / `losses` | 1 / 0 |

The single win nudges the estimate up from the skill-only baseline by a
modest amount (`reliability_weight(1) = 0.25` of the way), not to a
falsely confident near-100% -- the same calibration property
`docs/stage3_lineup_lab_scoring.md` §4 documents for the identical shared
formula. (Values pinned as a regression test in
`tests/test_player_vs_player.py::TestFixtureRegression`.)

## The matrix/export layer (built in a later pass)

`analytics/player_vs_player_matrix.py` combines this module's per-pair
summary with `analytics.pairing_evidence.PairingEvidenceMatrix` for a
whole scope, one row per feasible pairing (DIRECT/INDIRECT/UNKNOWN alike),
in a stable structural order (never score-sorted). It does not modify or
duplicate this module -- see its own docstring for the exact split. Built
on top of it:

- `ui/export_html_player_vs_player.py` -- one self-contained HTML export
  for a whole scope: a sortable summary table of every feasible pairing,
  each row linking to its full detail section (rendered by reusing
  `ui/tabs/player_vs_player.py::render` directly, not a second
  implementation).
- `ui/export_excel_player_vs_player.py` -- a standalone workbook (never a
  patch to the existing `apa_stats.xlsx`), with a `Player_vs_Player`
  summary sheet and a `PvP_Game_History` sheet that is omitted entirely
  when no real game exists anywhere in the scope (never an empty
  placeholder sheet). Fixed column widths and column order -- no
  content-derived auto-sizing, so the same real data always produces byte-
  comparable output.
- `scripts/build_player_vs_player_export.py` -- the real, read-only
  (`mode=ro`) database builder tying the three together: resolves real
  match dates (`Match.match_date`, since `PlayerHeadToHead` has no ORM
  relationship back to `Match`), fetches each pairing's real
  `head_to_head_history`, and writes `exports/player_vs_player.html` and
  `exports/player_vs_player.xlsx`.

**A request for this layer also asked for `danger_flag`/`favorable_flag`
columns and Captain's Edge "Recommended Avoid/Target" indicators derived
from `modeled_win_probability`. Neither is implemented.** Per
`docs/stage3_lineup_lab_scoring.md` §1 (Issue #14's own fail-closed finding
against the identical value), the DIRECT history term inside
`modeled_win_probability` has zero held-out rematch predictions in the
current validation set -- there is no validated basis for a categorical
danger/favorable/avoid/target judgment on top of it today, and inventing
one would repeat the exact "unfitted threshold" pattern already fail-closed
against `analytics.opponent_scouting` (win probability below 0.40 OR
volatility >= 0.50, both invented and never checked against outcomes). If
that data-honesty gap closes (real held-out rematches become available and
a threshold is written down, sourced, and checked against them first, per
`docs/captain_first_edge_experience.md` §10's rule), this is a real,
buildable follow-up -- not implemented here as a placeholder or a silently
lowered bar.

## Not yet built

Deliberately out of scope, to keep this a small, reviewable stage:

- Wiring this export into the existing multi-tab demo assembly
  (`scripts/render_demo_html.py`/`analysis_tabs.html`) or into
  `exports/captain_first_edge.html`.
- A combined single-page "Pair View / Matrix View" toggle inside one tab
  (today, the pair view and the matrix export are two separate real
  artifacts -- `ui/tabs/player_vs_player.py::render` for one pairing, and
  `ui/export_html_player_vs_player.py::render_export` for a whole scope,
  which already embeds every pairing's full detail section inline rather
  than requiring a toggle to see it).
- A live-credential scraping/ingestion CLI (`scripts/scrape_and_ingest.py`)
  -- a real, substantial, security-sensitive undertaking (credential
  handling, safe error handling, mocked tests) that was requested alongside
  this work but deliberately not attempted in the same pass as everything
  above.

## Audit constraints

- No frozen scraper contract change.
- No fabricated data or invented APA statistic.
- Reuses `analytics.head_to_head`/`analytics.matchups` exactly as they
  already exist; introduces no new weight, threshold, or blending formula.
- `docs/reproducible_builds.md`, `scripts/reproducible_build.py`,
  `tests/test_reproducible_build.py`, and `dist/BUILD_INFO.json` are not
  touched.
