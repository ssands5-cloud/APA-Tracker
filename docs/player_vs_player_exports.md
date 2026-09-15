# Player vs Player export design

Player vs Player is a scope-bound, one-row-per-pair view of the evidence for
one current-roster player against one current-roster opponent. It is a drill-
down between Tonight's Match and Lineup Lab: the pairing matrix establishes
the complete feasible set, Player vs Player explains each pair, and Lineup Lab
may then use only its separately approved selection inputs.

This document is an export-integration plan. A concurrent implementation lane
now supplies `analytics/player_vs_player.py` and
`ui/tabs/player_vs_player.py`; this document does not modify them. The named
`exports/html_builder.py`, `exports/excel_builder.py`, `ui/router.py`, and
`demo.py` integration points do not yet exist.

## Canonical artifacts

- `exports/player_vs_player.html` — self-contained, filterable HTML with every
  feasible pairing, evidence details, source status, and explicit gaps.
- `exports/player_vs_player.xlsx` — standalone workbook with a
  `Player_vs_Player` summary sheet and a real-only `PvP_Game_History` sheet
  when games exist. A later integration may copy the same materialized rows
  into `apa_stats.xlsx`, but the production demo should not patch the existing
  workbook after generation.
- `exports/player_vs_player.json` — optional versioned interchange document
  written by the analytics/export boundary and consumed identically by HTML,
  Excel, routing, and demo orchestration. If implemented, it is the parity
  oracle for both renderers.

## Analytics document contract

The current analytics API is deliberately pair-focused and pure:

```text
database.queries.head_to_head_history(db, player_id, opponent_id)
  -> chronological list[PlayerHeadToHead]

analytics.player_vs_player.summarize(rows, player_id, opponent_id,
                                     recent_games=5, match_dates={...})
  -> PlayerVsPlayerSummary
```

`PlayerVsPlayerSummary` contains `player_id`, `opponent_id`, `total_games`,
`wins`, `losses`, `sl_delta`, `reliability`,
`modeled_win_probability`, `skill_only_probability`, `trend`, `recent_trend`,
`next_match_projection`, and the chronological `games` tuple. `GameRecord`
contains match ID/date, result, both posted skill levels, points, 9-ball balls,
format, and session.

Because the summary does not own current-roster identity, team/scope identity,
or Stage 1 evidence labels, a future application adapter in `demo.py` must
combine it with the selected canonical `PairingEvidenceMatrix`. That adapter
creates a versioned export document containing names/external IDs, scope,
`evidence_label`, Stage 1 distinct-match counts/observed rate, the unmodified
summary, source/validation status, and explicit unavailable-field notes. The
HTML and Excel builders both consume that same document. Renderers do not query
the database, recalculate analytics, or fill a null.

## Required analytics behavior

### DIRECT history

The export's DIRECT label and distinct-match count come from
`analytics.pairing_evidence`, with its exact player/opponent, team IDs, format,
session, recognized-result, finalized/scored/non-bye gate. The separate
`PlayerVsPlayerSummary.games` timeline is the exact-pair chronological game
history supplied by `database.queries.head_to_head_history` after the adapter
restricts it to the selected scope.

```text
direct_matches = Stage 1 distinct authoritative match count
observed_win_rate = Stage 1 wins / distinct authoritative matches
total_games = count(recognized exact-pair game rows in PlayerVsPlayerSummary)
wins + losses = total_games
```

One team match can contain more than one legitimate game for the same player,
so `direct_matches` and `total_games` are separately named and must not be
forced equal. `observed_win_rate` is null outside DIRECT. UNKNOWN or INDIRECT
is never shown as an observed 0% record.

### Reliability weight

The module imports `analytics.matchups.reliability_weight` rather than copying
the formula:

```text
reliability_weight(n) = n / (n + 3)
```

In the current summary, `n` is `total_games` (recognized game rows), not the
Stage 1 distinct-match count. The column is therefore labeled “History
reliability (games).” It is descriptive evidence strength. The export layer
must not multiply it into another field or create a new blended score.

### Skill probability

The current `skill_only_probability` (export label: `skill_prob`) delegates to
`analytics.head_to_head.skill_only_win_probability` using the two posted skill
levels on the last real game in the supplied pair history:

```text
log_odds = 0.40 * (last_game_own_skill_level - last_game_opponent_skill_level)
skill_prob = clamp(sigmoid(log_odds), 0.02, 0.98)
```

It is null when there is no pair history or either last-game skill level is
missing. It must be labeled “last recorded skill-gap probability,” not current
roster probability. This is the production skill-only function graded against
106 recorded outcomes in `docs/prediction_validation.md`.

### Modeled win probability

`modeled_win_probability` is the existing full
`analytics.head_to_head.win_probability` supplied by the analytics module, not
created in a renderer. Its source must be
`analytics.head_to_head:direct-history-and-skill` and its validation status must
state that the history term has zero held-out rematch predictions in the
current validation set. It may be displayed as experimental context, but it
may not drive ordering, coloring, recommendations, or any additional derived
projection. The current `next_match_projection` alias may be displayed only
with the identical experimental status.

The export must never blend `observed_win_rate`, `reliability_weight`,
`skill_prob`, and `modeled_win_probability` into a new score.

### Innings and defense averages

The analytics summary intentionally has no `avg_innings` or `avg_defense`
field. Captured APA data exposes no innings at any granularity and no per-match
or per-opponent defensive-shot measure. The export consumes that absence as a
named `unavailable-upstream` disclosure and renders “No data”; it does not add
numeric placeholders. `PlayerCareerStats.defensive_shot_avg` is a real
lifetime, per-format value but cannot fill a Player vs Player defense average.

### Break/run rate

The analytics summary intentionally has no `break_run_rate`. Captured events
are player-and-team-match scoped, while a player can face multiple opponents in
one match. The export renders the module's explicit “not attributable per
opponent” disclosure and no value. It must not derive a rate in the builder,
even for apparently unambiguous rows, because that would create an export-only
analytics rule with no shared contract or audit.

### Volatility and trend analysis

The current summary supplies `trend` (first-versus-last own skill across the
full pair history) and `recent_trend` (the same rule across the last five games
by default). It does not supply numeric volatility. The export therefore shows
the two trends and renders Volatility as “No data — not produced by Player vs
Player analytics.” It must not join `player_trends.volatility` in a renderer,
turn the disputed HOT/COLD badge into pair advice, or fold form into a
probability.

### Next-match projection

The current summary defines:

```text
next_match_projection = modeled_win_probability
```

This is an alias of the same value, not a second computation, and the module
does not inspect the schedule. The export must label it “Forward-looking pair
projection (history + last recorded skill)” and state that it does not prove
these players are scheduled to meet. Because the history term lacks held-out
rematch evidence in the current validation set, it is experimental context and
not approved lineup advice. It is null when the underlying modeled value is
null.

## Ordering rules

Default order is structural, never score-driven:

1. upcoming scope date/week, with missing date/week last;
2. normalized session name, format (`8-ball`, then `9-ball`, then other);
3. player name case-insensitively, then player external ID;
4. opponent name case-insensitively, then opponent external ID.

DIRECT, INDIRECT, and UNKNOWN rows keep those positions. User-selected filters
may narrow the view, but the exported source order and row numbers stay stable.
Ties never depend on database insertion order.

## UNKNOWN handling

Every canonical feasible pair appears exactly once through the export envelope.
For an UNKNOWN pair, `summarize([])` produces zero games/wins/losses, zero
reliability, null probabilities/projection, `no data` trends, and an empty game
timeline. The row remains in HTML and Excel, carries `evidence_label = UNKNOWN`,
and explains missing inputs. It is not hidden, assigned a neutral 50%, or
ranked as if a score existed.

## Deterministic formatting

- UTF-8 HTML and JSON; fixed workbook sheet/table names.
- ISO-8601 UTC timestamps sourced from the run manifest, not the viewer's clock.
- Probabilities display to one decimal percent; stored JSON retains the
  analytics value. Counts are integers and skill deltas use fixed precision.
- Stable column order, stable sort keys, fixed Excel widths, and no platform-
  dependent auto-sizing.
- No volatile formulas, random IDs, locale-dependent dates, or conditional
  formatting based on the current time.
- HTML and Excel must show identical row count, pair keys, labels, and numeric
  values before presentation rounding.

## Audit constraints

- No fabricated values, silent zero defaults, neutral probability fallbacks,
  proxy innings/defense fields, or export-layer heuristics.
- No history-plus-skill blending beyond a separately sourced analytics output,
  and no unvalidated output presented as approved advice.
- No roster inference from historical participation; both sides come from
  canonical current `PlayerTeamHistory` rows.
- No renderer-side SQL or analytics. Any parity mismatch between HTML and
  Excel fails the demo build.
- No empty placeholder workbook sheet. If there are no feasible rows, omit the
  sheet and record the unavailable reason in the manifest; HTML may show the
  explicit unavailable state.

## Planned wiring

| Module | Responsibility |
| --- | --- |
| `analytics/player_vs_player.py` | Existing pure pair summary and chronological game records; no database query |
| `ui/tabs/player_vs_player.py` | Existing self-contained single-pair HTML fragment; reuse inside the export shell |
| `exports/html_builder.py` | Planned document-to-HTML shell/index; safe routing and reuse of the existing tab renderer |
| `exports/excel_builder.py` | Planned export-envelope-to-XLSX renderer; deterministic values and formatting |
| `ui/router.py` | Add `player-vs-player` navigation and row-level drill-down URLs without recomputation |
| `demo.py` | Orchestrate one analytics build, feed the identical document to both renderers, verify parity, and register artifacts |
