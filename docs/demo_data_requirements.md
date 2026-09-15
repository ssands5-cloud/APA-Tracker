# Demo data requirements

The demo's credibility comes from showing the boundaries of the snapshot, not
from maximizing row counts. This is the authoritative input checklist.

## Entity and field requirements

| Entity | Required real fields | Used by |
| --- | --- | --- |
| Team | immutable `external_id`, display `name` | controls, identity, exports |
| Player | `external_id`, `name`, current `skill_level`, roster totals where supplied | roster cards, skill-only probability |
| Match | `external_id`, both team IDs/names, `format`, `session_name`, date/status, scores, scored/finalized/bye flags | scopes, DIRECT gate, schedule |
| PlayerMatch | player/match linkage, team identity, match date, result, skill level, score fields | player history and validation |
| PlayerHeadToHead | player/opponent/match IDs, both skill levels, recognized result, format/session, points/balls | DIRECT evidence, H2H aggregates |
| PlayerTeamHistory | player, `team_external_id`, division/session, `is_current`, skill/name metadata | canonical current roster |
| StandingsSnapshot | capture time, team, rank, wins/losses/points when the source supplies them | standings and freshness |
| PlayerCareerStats | player, format, lifetime totals and update time | career tab and freshness |
| PlayerMatchup | player/opponent scope, counts/rates/context, score/confidence | legacy analysis tabs |
| PlayerH2HAdvantage | player/opponent scope, recognized record, score/probability/expected output | Captain's Edge legacy artifact |
| PlayerTrend | player/format/session, sample/current skill, slope, volatility, stability, flag, projection | trend analysis and coverage |

## Evidence-specific requirements

- A DIRECT row requires at least one distinct scored, finalized, non-bye match
  whose H2H row and parent match agree on team IDs, format, and session.
- An INDIRECT row requires real current skill levels on both canonical roster
  rows; it does not borrow another opponent's record.
- UNKNOWN is correct when either requirement is missing. The UI keeps it in the
  matrix and counts it in Data Coverage.
- Distinct-match counts must deduplicate repeated per-game rows within one
  scoresheet. Conflicting facts for the same match fail closed.

## Freshness and provenance

Record the fixture capture time, maximum `StandingsSnapshot.captured_at`, and
per-row `PlayerCareerStats.updated_at` where present. Do not create a synthetic
per-player “last synced” field. The database path, config hash, repository
commit, and artifact hashes belong in the manifest.

## Known gaps to surface

The fixture sample used in CI does not contain `PlayerTeamHistory`, so a CI
captain-first page may correctly report unavailable rosters and zero feasible
pairings. A stale existing DB may also lack
`player_team_history.team_external_id`; the supported remedy is regeneration.
The API does not provide per-opponent innings or per-opponent defensive shots,
and those must remain named unavailable fields rather than guessed columns.

