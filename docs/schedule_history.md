# Schedule (your team's real match history)

`apa_data.json`'s `"schedule"` key. One row per real game the configured
team's players have played, from `Match` + `PlayerHeadToHead` — the same
real sources `docs/close_match_performance.md` and `docs/matchups.md`
already use.

```
ui/export_json.py   _schedule(db, config)
```

## "Your team" is real, not invented

`apa_config.yaml`'s `team.team_id` is a real, already-configured value —
checked against the real database before this was built: it resolves to a
genuine `Team` row this project's own account actually plays on (`Player`
rows for "Paul Smith" exist on multiple real teams; `13082948` / "Mark It
Up" is one of them). `_configured_team_id()` reads it; `_schedule()`,
`_team_roster()` and `_opponent_rosters()` all key off the same value, so
they can never disagree about who "your team" is. Empty (not a guess) when
no team is configured, or the configured id matches no real `Team` row.

## Columns

| Field | Source |
|---|---|
| `week` / `date` | `Match.week` / `Match.match_date` |
| `opponent_team` | `Match.home_team_name` or `away_team_name`, whichever side isn't the configured team |
| `your_player` / `your_player_sl` | `PlayerHeadToHead.player` / `.own_skill_level` |
| `opponent_player` / `opponent_player_sl` | `PlayerHeadToHead.opponent` / `.opponent_skill_level` |
| `result` | `PlayerHeadToHead.result` ("W"/"L"/`null`) |
| `match_margin` | `abs(Match.home_score - Match.away_score)`, `null` until scored — the same real figure `analytics.close_match_performance.is_close_match` already uses |

## What's deliberately absent

**Racks, notes, a "clutch" flag, and a "break/run" flag.** None of these
are real fields anywhere in this project's captured data — checked against
`database/models.py` and every captured API query before this was
written. APA's data has no field for which individual game within a team
match was the deciding one, or the score at the time a given game was
played (see `docs/close_match_performance.md`'s "What's real and what
isn't" for the same limitation already documented there). A "notes" field
would need a human to write it; nothing in this pipeline generates prose.
