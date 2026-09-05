# Data fields: what's real, what's derived, what we don't fabricate

This is the single source of truth for where every exported column
actually comes from: which columns are raw API values, which are
computed here, and which the API simply doesn't provide. "Gate A" of
the workbook-redesign work (see the project's own notes on that) is
scoped to keeping this file matched to code: this doc is corrected
against `git grep`-able evidence, never asserted from memory.

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
| As Of | Derived | The sync's own capture timestamp, not an API field. |

**Wins / Losses are not Standings columns.** APA ranks by cumulative
session points and `DIVISION_STANDINGS_QUERY` returns no win/loss
record, so the Standings sheet, its JSON export, and the
`standings_snapshots` table carry no such field. Both scraper paths
(`division_standings_rows()` and the single-team `standings_rows()`
fallback) emit the same three-column shape: team, rank, points.

A team-level win/loss record is still computable from real per-match
results — `analytics/team_stats.py` does exactly that from `PlayerMatch`
rows — but it is a match-history derivation, not a standings field, and
is reported there rather than on this sheet.

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
