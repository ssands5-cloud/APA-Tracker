# Close-Match Win Rate

Specced in `docs/planned_analytics_design.md` before this was built —
replaces what earlier drafts called "Clutch Rating". Renamed on purpose:
this measures a real, narrow thing — win rate specifically in team matches
that were close — not poise or pressure performance in general, and must
never be labeled more strongly than what it actually is.

```
analytics/close_match_performance.py   is_close_match / close_match_performance / close_match_band
ui/export_excel.py                     "Close_Match_Stats" sheet
ui/export_json.py                      "close_match_stats" in apa_data.json
```

## What's real and what isn't

APA's captured data has no field for which individual game within a team
match was the deciding one, or the score at the time a given game was
played (`matchPositionNumber` is a fixed roster-position assignment, not
temporal sequence). What IS real: the team match's own final margin
(`Match.home_score`/`away_score`) and which individual games a specific
player won or lost within that match (`PlayerHeadToHead`). This module
uses only those two — no new upstream export, no new pipeline stage.

## A close match is a real, decided, CONFIRMED result

`is_close_match` excludes, in order: a missing `Match` row; a bye (no real
opponent to be close against); a match that isn't `is_scored`, or is
scored but not yet `is_finalized` (an unconfirmed score is not decided
evidence yet — the same guard `analytics.team_stats.team_match_record`
already applies); a missing score on either side; and a tie (not a
decided result either way). A real review of an earlier commit found this
wasn't fully enforced — byes, unscored/unfinalized matches, and ties could
still register as "close" — before this was tightened.

## The numbers

| Field | Meaning |
|---|---|
| `close_matches_played` | DISTINCT real team matches (by `match_id`, not `PlayerHeadToHead` rows) decided by `CLOSE_MATCH_MARGIN` (4) points or fewer — the sample-size gate counts matches, not games, so playing several games within one close team match can't masquerade as several independent pieces of evidence |
| `close_games_played` | the raw row count within those same close matches — kept separately because `close_win_rate` is genuinely a per-game rate; only the sample-size gate needs distinct matches |
| `close_win_rate` | raw win rate across `close_games_played`; `None` below `CLOSE_MATCH_MIN_SAMPLE` (3) DISTINCT close matches |
| `overall_matches_played` / `overall_win_rate` | the same player's real record across ALL their head-to-head games — the baseline, from the same population, not a different source |
| `shrunk_win_rate` | `close_win_rate` pulled toward `overall_win_rate`, weighted by `analytics.matchups.reliability_weight(close_matches_played) = n / (n + 3)` — the same shrinkage curve this project already uses for a thin head-to-head record, not a second formula |
| `close_match_band` | `"Strong"` / `"Even"` / `"Struggles"` / `"Unknown"` — `shrunk_win_rate` compared to the player's own `overall_win_rate`, not a league-wide bar (see `CLOSE_MATCH_BAND_MARGIN`, 10 percentage points) |

`close_match_band` lives in `analytics/close_match_performance.py` and is
imported by both `ui/export_excel.py` and `ui/export_json.py` — one
function, so the workbook and the JSON document can never label the same
player differently.

## The close-match threshold is provisional

`CLOSE_MATCH_MARGIN = 4` was checked against this project's own real data,
not picked blind: the 14 decided team matches in the database when this
was written had margins `[2, 2, 2, 4, 5, 6, 6, 8, 9, 10, 14, 14, 21, 28]`
(median 8) — 4 is the real bottom quartile of matches actually played.
Genuinely provisional: 14 matches is a small sample, and 8-ball/9-ball
divisions may play to different point totals, which could argue for a
per-format threshold once there's enough data in each to check that
separately rather than guess.

## A player not listed

A player with zero real `PlayerHeadToHead` rows has nothing to report and
is omitted entirely — the same reasoning `docs/matchups.md`'s dropdown
note applies elsewhere: absence here means no evidence exists, not a
computed zero.
