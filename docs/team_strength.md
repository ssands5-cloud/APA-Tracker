# Team Strength Analyzer

The Team Strength Analyzer is an implemented, pure analytics document for one
canonical team/session scope. It combines three transparent, bounded
descriptive components into `team_strength_index`. It is not an APA statistic,
a fitted outcome model, a lineup selector, or a strength category.

The analytics owner is `analytics/team_strength.py`. Query assembly
belongs in a read-only builder; HTML and Excel consume the same immutable
report and perform no math.

## Scope and source contract

Every report is keyed by team external ID, session, division when available,
source-manifest ID, and capture time. Format may be carried only when the
configuration or captured division establishes it unambiguously. The builder
must not join by team name when a canonical ID exists.

| Input | Source | Use | Required guard |
| --- | --- | --- | --- |
| Canonical roster | current `PlayerTeamHistory` rows | player membership and per-player session record | exact `team_external_id`, session, and `is_current`; duplicate identity blocks the report |
| Player results | `PlayerTeamHistory.matches_won` and `matches_played` | offense and depth | played must be positive and wins must be between zero and played |
| Team scores | finalized, scored, non-bye `Match` rows | defense proxy and match sample | selected team must be exactly home or away; both scores must be present and nonnegative |
| Current skill | `PlayerTeamHistory.skill_level` | roster context and coverage only | missing remains null; skill does not enter the strength index |
| Standings | `StandingsSnapshot` | separate current rank/record context | name-only schema limitation must be disclosed; standings do not enter the index |

`Player.win_pct` is not an index input because it can be overwritten as a
player appears in more than one roster context. The team/session-owned history
row is the authoritative proposed source. If the source cannot prove that a
history row belongs to the requested format, the report labels offense/depth
as team-session scope rather than pretending they are format-specific.

## Version 1 metrics

All component values use a 0–100 scale. Calculations retain full precision;
renderers round only for presentation. A measured zero is valid. A missing
denominator produces null, never zero or 50.

### Offense index

The offense component is the pooled individual-match win rate for canonical
current-roster rows with a positive played count:

```text
W = sum(player_matches_won)
P = sum(player_matches_played)
offense_index = 100 * W / P                     when P > 0
                null                            otherwise
```

Pooling counts prevents a player with one match from receiving the same weight
as a player with twenty. The display label is **Roster result rate**, with
`W`, `P`, contributing-player count, and scope shown beside it. “Offense” is a
product heading, not a claim that APA captured shot-level offense.

### Defense index

APA Tracker has no team-level defensive-event feed and must not reinterpret
the lifetime player `defensive_shot_avg` as opponent-specific defense. Version
1 therefore uses a clearly named **team-score containment proxy** over eligible
team matches:

```text
PF = total selected-team points in eligible matches
PA = total opponent points in eligible matches
defense_index = 100 * (1 - PA / (PF + PA))      when PF + PA > 0
                null                            otherwise
```

This is the selected team's share of scored match points, expressed from the
points-allowed side. It is not a defensive-shot rate, and the UI must always
show `PF`, `PA`, eligible-match count, and the word “proxy.” Ties and unfinished
matches do not enter the calculation.

### Depth index

Depth is the observed result-rate floor at the fifth roster position. For each
canonical current player with at least one recorded match:

```text
r_i = player_matches_won / player_matches_played
```

Sort `r_i` descending, then player external ID ascending. If at least five
players are scoreable:

```text
depth_index = 100 * fifth-highest r_i
```

Otherwise `depth_index` is null. The report shows every player rate and sample
size, identifies the fifth-player row, and reports total/scoreable roster
coverage. The metric is an observed depth floor, not a 23-rule legality score;
legal-lineup counts may be shown separately but never blended into it.

### Team strength index

Version 1 gives the three components equal, explicit weight:

```text
team_strength_index =
    (offense_index + defense_index + depth_index) / 3
```

The composite is null unless all three components are present. It never
renormalizes over the available subset because that would make two teams with
different missing components incomparable. The report carries
`formula_version = team-strength-v1-equal-components` and each component's raw
numerator, denominator, row count, and availability reason.

Equal weighting is a design assumption, not a learned coefficient. Before the
index is used predictively, a separate validation study must freeze historical
training/holdout cohorts and compare it with simpler baselines. Until then it
supports descriptive comparison only and cannot generate strong/weak tiers,
lineup recommendations, or color-coded advice.

## Analytics output

The implemented immutable report contains:

```text
TeamStrengthReport
  team_external_id, team_name, session_name, division_id, format
  source_manifest_id, captured_at, formula_version
  team_strength_index
  offense_index, offense_wins, offense_played, offense_player_count
  defense_index, points_for, points_against, defense_match_count
  depth_index, roster_count, scoreable_player_count, depth_player_id
  player_rows[]
  match_rows[]
  current_rank, standings_record
  unavailable_reasons[]
```

Rows are immutable and already ordered. The module accepts source rows as
arguments, queries nothing, changes no database state, and does not import a UI
renderer.

## Architecture, UX, and routing

```text
verified SQLite → read-only scope query → analytics/team_strength.py
                → immutable TeamStrengthReport
                → HTML / Excel / script JSON / demo manifest
```

The proposed UI registers one `team-strength` navigation entry in the existing
tab/router structure. Its route carries the canonical team ID, session,
division/format when proven, and the run ID. It never accepts a team name as an
identity key. A stale or unavailable route renders the scoped `No data` state
and a link to Data Coverage; it does not select the first team.

The self-contained report embeds the immutable document in escaped,
non-executable script JSON. Browser controls may switch between Summary,
Roster Evidence, and Match Evidence sections and sort one visible column at a
time. They cannot recompute a component, renormalize a missing composite, or
change the exported source order. Back/forward navigation restores section and
sort state without fetching data.

## Current status and wiring contract

`analytics/team_strength.py`, the standalone read-only builder, HTML fragment,
three-sheet workbook, and their focused tests are implemented. The analytics
module is the sole formula owner and returns the immutable
`TeamStrengthReport` described above. Production-demo provenance, stricter
scope/identity guards, artifact containment, registration, and cross-artifact
parity remain; none should reimplement its calculations.

| File | Current responsibility and remaining production work |
| --- | --- |
| `ui/tabs/team_strength.py` | implemented `render(report, title="Team Strength") -> str`; add run provenance, safe script JSON/navigation hooks, and Data Coverage routing |
| `ui/export_excel_team_strength.py` | implemented `build_workbook`/`write_workbook` with the three fixed sheets below; add manifest parity verification |
| `scripts/build_team_strength.py` | implemented read-only query assembly and HTML/XLSX output for an exact team/session; harden mixed-format, missing-player, standings-ambiguity, and contained-output checks |
| `pipeline/exports.py` | pending: invoke the adapter once for the selected scope and register both artifacts without reopening the database |
| full production demo builder | pending: include report, hashes, row counts, formula version, null reasons, and parity results in the run manifest |

The standalone builder assembles the core inputs as follows; production cutover
must enforce every guard named here:

1. Resolve exactly one `Team` by external ID; a missing/duplicate identity
   blocks the report.
2. Join `PlayerTeamHistory` to `Player` for the exact team external ID,
   session, and `is_current=True`. Canonical roster duplicate detection exists;
   production must also reject a missing joined player and invalid W/P counts
   before calling analytics.
3. Select only finalized, scored, non-bye `Match` rows in the requested
   session where the team is exactly home or away. Require both scores and
   orient PF/PA from the selected team.
4. Resolve standings only as separately labeled context. The standalone builder
   uses the schema's team name; production must make zero or multiple viable
   identities unavailable rather than selecting one. Standings never change
   the index.
5. Sort source player/match rows canonically, call `build_report` once, and
   pass that exact object to both renderers.

The standalone command contract is:

```text
python scripts/build_team_strength.py --db PATH --our-team-id ID
    --session NAME --out-dir PATH
```

`--our-team-id` may come from configuration; `--session` is required. The
standalone builder currently derives format from the first eligible match.
Production must reject mixed formats or carry only a proven exact format; it
may not relabel team-session player totals as format-specific. The database is
opened read-only. The full builder must additionally enforce repository-
contained new output and must never reuse a stale artifact after failure.

## HTML layout

The proposed `team_strength.html` is self-contained:

```text
section#team-strength
├── scope/provenance and descriptive-only notice
├── Team Strength Index card or explicit No data state
├── three component cards
│   ├── Offense: roster result rate and W/P coverage
│   ├── Defense: team-score containment proxy and PF/PA
│   └── Depth: fifth-player floor and roster coverage
├── figure#team-strength-components (three bars on a 0–100 axis)
├── table#team-strength-roster
├── table#team-strength-matches
├── standings context (not an index input)
└── formula, source, and unavailable-data disclosure
```

The chart repeats exact numeric values in text. Null components use a hatched
`No data` position and are omitted from the composite. No red/green strength
tier, gauge threshold, league percentile, or browser-side calculation is
allowed.

## Excel layout

The proposed `team_strength.xlsx` contains values only:

### `Team_Strength`

One row per team scope with IDs, session/division/format, formula version, all
four indices, raw W/P and PF/PA denominators, contributing counts, standings
context, capture time, source-manifest ID, and unavailable reason. Percent-like
indices use `0.00`; underlying rates remain numeric, not preformatted strings.

### `Team_Strength_Players`

One row per canonical roster player: team/player IDs, name, current skill,
wins, played, observed rate, contributes-to-offense, scoreable-for-depth, and
depth order. Rows sort observed rate descending with nulls last and player
external ID as the tie-break; an explicit Boolean identifies the fifth-player
depth row.

### `Team_Strength_Matches`

One row per eligible finalized match: match ID/date/week, format/session,
opponent team ID/name, home/away, points for, points against, and source status.
Rows sort by normalized match date when available, then week and match ID.

All sheets freeze headers, use fixed widths, retain IDs as text, and contain no
formulas, macros, hidden helpers, external links, volatile dates, or
content-dependent ordering.

## Demo and validation contract

The demo opens Team Strength after establishing the selected team and before
Season Projection. HTML, Excel, script JSON, and manifest must agree on scope,
formula version, raw denominators, component values, player/match keys, nulls,
and ordering before rounding. Tests cover exact formulas, invalid counts,
missing components, fewer than five scoreable players, multi-team name
collisions, zero denominators, hostile text, and deterministic parity.

The presenter first reads the composite availability, then opens each component
to show its raw evidence. The demo explicitly calls the defense value a proxy
and shows that a missing component makes the composite unavailable. The Team
Strength values may appear as separately labeled context in Captain's Edge and
the Live Assistant, but they never alter Player-vs-Player values or Lineup Lab
selection. The artifact index links to both `team_strength.html` and
`team_strength.xlsx`, and Data Coverage owns any freshness or missing-source
explanation.
