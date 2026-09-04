# Data fields: what's real, what's derived, what we don't fabricate

This is the single source of truth for where every exported column
actually comes from. It exists because an outside audit assumed some
columns were fabricated placeholders when they weren't (Standings'
Wins/Losses -- see below) and, separately, because it's genuinely useful
to know at a glance which columns are raw API values versus computed
here. "Gate A" of the workbook-redesign work (see the project's own
notes on that) is scoped to fixing this file to match code, not the
other way around: this doc is corrected against `git grep`-able
evidence, never asserted from memory.

Legend:
- **Raw** — copied straight from a captured GraphQL field, no math.
- **Derived** — computed here from raw fields (an average, a sum, a
  count, a formula). Still real, still traceable, just not a 1:1 API copy.
- **None (honest gap)** — the API genuinely doesn't provide this; we
  report it as missing (blank cell / `null`), never a guessed number.

## Standings sheet

| Column | Provenance | Source |
|---|---|---|
| Rank | Raw | `division.teams[].standing` (`DIVISION_STANDINGS_QUERY`) |
| Team | Raw | `division.teams[].name` |
| Points | Raw | `division.teams[].sessionTotalPoints` |
| Wins / Losses | **None (honest gap)**, in the normal multi-division path | `division_standings_rows()` sets these to `None` explicitly, with a comment stating why: *"this endpoint does not return them at all -- APA ranks by cumulative session points, not a maintained win/loss record -- and a guessed count is worse than an honest gap."* They render as blank cells, not zeros or fabricated numbers. |
| Wins / Losses (single-team fallback only) | Derived | The older, single-team-only path (`standings_rows()`, used only when no division id is configured) computes these by comparing our own team's points against the opponent's on every match the API marks scored. This IS a real derivation from real per-match data — not a placeholder — and is documented as such in the function's own docstring. It also stays `None` until at least one match is scored. |
| As Of | Derived | The sync's own capture timestamp, not an API field. |

**Correcting a specific audit claim:** an outside review flagged
Standings' Wins/Losses as fake/placeholder data to be dropped. Checked
against the actual code (`scraper/graphql_scraper.py:division_standings_rows`
and `:standings_rows`): neither path fabricates a number. One honestly
returns `None` because the field doesn't exist upstream; the other
derives real wins/losses from real scored match results. Nothing was
removed as a result of that claim -- the column already behaves exactly
as "don't fabricate" would require.

## Player Stats sheet

| Column | Provenance | Source |
|---|---|---|
| Player, Team, Skill Level | Raw | `Player` row / roster fields |
| Matches, Wins, Losses, Win % | Derived (two possible sources) | From per-match history (`PlayerMatch` rows) where present; falls back to raw roster season totals otherwise. The **Source** column says which, so a 0 is never ambiguous between "played none" and "no match detail available." |
| PPM, PA | Raw | Roster fields (`upsert_roster`) |
| Avg Points | Derived | Average of `points_earned` across a player's match rows |
| 8-Ball On Breaks / Break & Runs, 9-Ball On Snaps / Break & Runs | Derived | Summed across a player's `PlayerMatch` rows from the real per-match `eightOnBreak`/`eightBallBreakAndRun`/`nineOnSnap`/`nineBallBreakAndRun` fields (`MATCH_DETAIL_QUERY`) |
| Source | Meta | Labels which of the two Matches/Wins/Losses sources above applied |

## Career Stats sheet

| Column | Provenance | Source |
|---|---|---|
| Player, Format | Raw | `getEightBallStats` |
| Matches Won, Matches Played, CLA, Defensive Shot Avg, Matches (Last 2 Yrs), Last Played | Raw | `getEightBallStats`'s `EightBallStats`/`NineBallStats` lifetime aggregate |
| On Breaks, Break & Runs, Mini Slams, Rackless, Skunks | Derived | Summed across every `alias.players` session-entry of the matching format (`getEightBallStats`) -- the API reports these per-session, not as a single lifetime total, so this module sums them. Rackless is 8-ball-only and Skunks is 9-ball-only; each is `null` on the other format's row. |

## Team History sheet

All columns **Raw**, from `TeamStat`.

## Skill Level History sheet

All columns **Raw** — a direct read of `PlayerMatch.skill_level` per match, already written by the scoresheet ingest path. `Source` is a constant label (`"scoresheet"`), not a computed value.

## Matchups sheet

Everything except `Format`/`Session` (raw, threaded from team context) is
**Derived** — this is the Matchup Advantage Engine's whole purpose. Full
formula writeup: `docs/matchups.md`.

## Fields we do NOT fabricate

Checked every captured query (`parser/apa_graphql.py`) for these before
ever being asked to add them. None exist anywhere in the real API as
captured so far. They will never appear in an export unless a real,
captured field is found and cited here first:

- **Innings** (any per-match/per-player inning count)
- **Defensive Shots**, per match or per opponent (only a lifetime
  *average*, `defensiveShotAvg`, exists — already exposed as `Career
  Stats.Defensive Shot Avg`)
- **Dead Balls**
- **Captain ID / Captain Name**
- **League Operator**
- **Night of Week**
- **Season Start / Season End**
- **Scoresheet URL** — a `scoresheet` field exists on `TEAM_SCHEDULE_QUERY`'s
  match object, but its actual shape (a URL? a boolean flag?) has never
  been parsed or captured with real data, so it stays unused until that's
  confirmed — not guessed at.

If any of these turn out to be real and captured after all, the fix is
to cite the exact query and field here first, then wire it in — the same
process every other field in this document went through.
