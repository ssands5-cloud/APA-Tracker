# Ultimate Coach Builder Handoff

## Status

Builder branch: `builder/ultimate-coach-foundation`

Stacked draft PR: #31, based on the frozen PR #30 head. PR #30 itself is not
modified by this work.

The live discovery rehearsal established that the authenticated account exposes
three league aliases, eight historical sessions and 36 resolved divisions in
the observed catalog path, with the earliest observed sessions in 2024. That is
source evidence, not a claim that APA has no earlier data globally.

## Non-negotiable data policy

Ultimate Coach stores and analyzes real APA source data only.

- no guessed ids
- no reconstructed scoresheets
- no synthetic historical matches
- no name-only identity merges
- missing upstream data remains missing and is reported
- EIGHT and NINE evidence remains separate
- league aliases remain league-scoped
- probability output stays disabled until a held-out backtest/calibration gate
  is implemented and passes

## Builder slices implemented

### 1. Historical catalog

New captured read-only query documents in `parser/apa_graphql.py`:

- `AliasSessionStatsDropdown`
- `AliasSessionStats`
- `leagueDivisions`

New scraper accessors normalize those operations without exposing auth data.

`scraper/historical_catalog.py` builds:

member -> per-league aliases -> sessions per format -> every division APA
exposes for each known session.

The same session discovered through EIGHT and NINE is deduplicated before the
league/division call. Empty upstream responses are written as
`source_limitations`; they are not interpreted as proof of completeness.

CLI: `python scripts/build_historical_catalog.py`

Output: `data/ultimate_coach_historical_catalog.json`

### 2. League-wide historical archive

`scraper/historical_archive.py` consumes the verified catalog and reuses
PR #30's historical-safe `sync_division_wide` path.

Safety properties:

- writes only `data/ultimate_coach_staging.db` by default
- seeds from `data/apa_tracker_career_staging.db` when available
- no promotion option exists
- catalog SHA-256 is pinned across resume
- every completed division is checkpointed
- interrupted divisions are retried with scoresheet-resume semantics
- old sessions use historical roster/identity mode
- actual current session uses current-roster mode
- missing scoresheets are recorded as coverage observations instead of being
  manufactured or forcing the recovered data to be discarded

CLI:
`python scripts/build_ultimate_coach_archive.py`

Resume:
`python scripts/build_ultimate_coach_archive.py --resume`

### 3. All-player lifetime enrichment

A new table, `player_league_career_stats`, stores lifetime stats by:

`player + league + format`

and also records the APA alias id used as source provenance.

This avoids the pre-existing global `PlayerCareerStats(player, format)`
limitation, which cannot safely represent a member who has distinct per-league
aliases.

`scraper/player_enrichment.py` only enriches a player when:

1. exact historical team membership maps that player to a real catalog league;
2. the player's external id is a numeric canonical APA member id; and
3. `FormatsByMemberId` yields exactly one alias for that league.

Zero or multiple aliases are recorded as unresolved and are never guessed.

CLI:
`python scripts/enrich_ultimate_coach_players.py`

Resume:
`python scripts/enrich_ultimate_coach_players.py --resume`

### 4. Transparent scouting evidence

`analytics/scouting_evidence.py` produces career evidence for any two
canonical players in one exact format:

- direct W/L
- shared-opponent set
- each player's real W/L against every shared opponent
- pooled shared-opponent record
- average own/opponent skill levels from those observed games

It explicitly reports probability status `NOT_CALIBRATED`. It does not call
the existing heuristic matchup score or emit a new probability.

### 5. One-command browser runner

`python tools/run_ultimate_coach_browser.py`

opens Chromium for the user to authenticate normally, keeps the token in memory
only, validates viewer identity, then runs catalog -> archive -> enrichment.

After token expiry/interruption:

`python tools/run_ultimate_coach_browser.py --resume`

No username, password, token or cookies are persisted. There is no production
promotion step.

## Required Claude audit

Audit PR #31 from scratch after CI is green. At minimum verify:

1. every new GraphQL document exactly matches the committed real capture;
2. no auth material can be printed, serialized, committed or written to reports;
3. historical catalog deduplication cannot collapse separate leagues;
4. catalog/session mismatches fail closed;
5. archive resume refuses catalog SHA drift;
6. archive never writes production and has no promotion route;
7. historical/current roster flags are correct per session;
8. player enrichment cannot confuse scoresheet alias ids with member ids;
9. multi-league players cannot overwrite one another's career stats;
10. ambiguous member->league alias resolution stays unresolved;
11. shared-opponent evidence does not cross EIGHT/NINE formats;
12. no code path claims calibrated odds/probabilities from the new evidence;
13. full test suite passes on Python 3.12 and 3.13.

## Still intentionally not built

- calibrated win-probability model
- held-out chronological backtest
- Brier/log-loss/calibration reporting
- UI presentation of the new shared-opponent evidence
- production promotion/merge

Those stay blocked until the real league-wide archive and enrichment run have
been inspected and Claude independently audits this foundation.
