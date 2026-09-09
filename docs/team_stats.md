# Team_Stats

One row per team, in the Excel export's "Team_Stats" sheet. Real,
currently-computable aggregates only.

```
analytics/team_stats.py   team_match_record / average_skill_level / opponent_strength_index
ui/export_excel.py        _team_stats_dataframe -- queries + assembles the sheet
```

| Column | Source |
|---|---|
| Team Name | `Team.name` |
| Matches Played / Won / Lost | `team_match_record()` — derived from `Match.home_score`/`away_score`/`is_bye`, independently of the Standings sheet's API-reported numbers (`StandingsSnapshot`) |
| Win % | `wins / matches_played`; `None` (not 0) with nothing decided yet |
| Home Record / Away Record | the same match record, split by whether the team was `home_team_id` or `away_team_id` |
| Average SL | mean of `Player.skill_level` across the team's real roster |
| Opponent Strength Index | mean `opponent_skill_level` from real `PlayerHeadToHead` rows for this team's players — who they've actually faced, not a league-wide average |

## What this deliberately excludes

Clutch Rating, a numeric Trend Score, Break/Run Rate, and Defensive Shot
Rate are **not** columns here. None of them are real fields anywhere in
this project — checked against `database/models.py` and every captured
API query. Building them would mean inventing numbers, which is exactly
what this project has consistently refused to do elsewhere (see
`docs/head_to_head.md`'s "Unavailable APA Fields"). If a real,
honestly-computed version of any of them gets built later — from real
events, with a documented formula — it earns its own spec and its own
module; this sheet does not grow speculative columns to make room for it
ahead of time.

## A team name can appear more than once

A real team's name is not a unique key: the same organization can field
separate teams per division/format (confirmed against the real database —
two distinct `Team` rows, different `external_id`, both named "Brunch
Ballers"). Each row here is one real `Team` record, not one name.
