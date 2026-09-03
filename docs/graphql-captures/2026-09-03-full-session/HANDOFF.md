# Handoff: real live capture, 2026-09-03 — build these next

This directory is a **real, live capture** from `scraper/full_apa_scrape.py`
running successfully end-to-end for the first time (after the Python 3.14
Windows `asyncio.run()` bug was found and worked around with 3.12 — see
`README.md` and `scraper/diagnose_eventloop.py`). All 55 files verified
sanitized (types only, zero real names/emails/etc. survived) by a script
that walked every value in every file and flagged anything that wasn't a
type marker, a count marker, or a real GraphQL enum — zero hits. Safe to
build against.

Directory layout: `<entity type>/<entity id>/<operation>.json`. `global/global/`
holds operations not yet classified to division/team/match (see
`scraper/full_apa_scrape.py`'s `OPERATION_ENTITY` table).

## Three things worth building from this capture, in priority order

### 1. `dashboardTeams` + `matchesByViewer` — no team_id needed at all

`global/global/dashboardTeams.json` and `global/global/matchesByViewer.json`.
Both take **zero variables** — they're scoped to the logged-in viewer
implicitly. This is a real upgrade over the current design:
`apa_config.yaml` hardcodes one `team.team_id`, but this capture proves the
account plays on **4 teams**. `dashboardTeams` lists all of them
(`viewer.leagueTeams` + `viewer.tournamentTeams`); `matchesByViewer` returns
every one of those teams' full match lists in one call, using the same
`matchListItem` shape `TEAM_SCHEDULE_QUERY`/`DIVISION_SCHEDULE_QUERY`
already use.

**Before wiring `matchesByViewer` in**, trim it the same way
`MATCH_DETAIL_QUERY`/`DIVISION_SCHEDULE_QUERY` already are (see
`parser/apa_graphql.py`'s comment above those two): the real query pulls
`orderItems { order { member { firstName lastName } } }` — billing/order
PII with no reason to be requested or stored. Write our own trimmed
document requesting everything else, same pattern as those two.

Add to `parser/apa_graphql.py`:
```python
DASHBOARD_TEAMS_QUERY = """
query dashboardTeams {
  viewer {
    id
    ... on Member {
      leagueTeams: teams(type: [RELEASED, WEEKLY], current: true) {
        id name standing totalTeamMatchesPlayed isTied
        division { id type isTournament }
        league { id slug }
        session { id name }
      }
      tournamentTeams: teams(type: [TOURNAMENT], current: true) {
        id name standing totalTeamMatchesPlayed isTied
        division { id type isTournament }
        league { id slug }
        session { id name }
      }
    }
  }
}
"""

MATCHES_BY_VIEWER_QUERY = """
query matchesByViewer {
  viewer {
    id
    ... on Member {
      teams {
        id name number
        session { id name }
        matches {
          type id isBye status startTime isMine isScored isFinalized isPlayoff tableNumber
          results { homeAway points { total } }
          home { id name number }
          away { id name number }
        }
      }
    }
  }
}
"""
```
(dropped from the real query, deliberately: `orderItems`, `fee`, `scoresheet`,
`isPaid`, `membershipExpires` -- billing/account fields with no reason to be
stored for score tracking.)

In `scraper/graphql_scraper.py`, add `fetch_dashboard_teams(config)` and
`fetch_matches_by_viewer(config)` (same shape as `fetch_division_standings`:
call `execute(...)`, catch `GraphQLAuthError` -> `AccessTokenExpired`,
return the relevant sub-object), plus row-mapping functions:
- `dashboard_teams_rows(payload)` -> one row per team (id, name, standing,
  division id, league id) — this is the new source of truth for "which
  teams does this account play on", replacing the single `team.team_id` in
  `apa_config.yaml`.
- `viewer_matches_rows(payload)` -> flatten every team's matches into rows
  shaped like `schedule_rows()`'s output, with a `team_id`/`team_name`
  column added so matches from different teams don't collide.

Fixtures + tests: mirror `tests/test_division_standings_fixture.py` --
sanitized JSON fixture (fabricated values, real field names, in
`tests/fixtures/`), a test file asserting the row-mapping is correct
including the 4-team case, and wire the result into `ingest_standings`/
`ingest_match` the same way `graphql_sync.py` already does.

### 2. `getEightBallStats` + `TeamStat` — the actual player match-history query

`global/global/getEightBallStats.json` and `global/global/TeamStat.json`.
**This is the "player match-history/statistics query" that's been an open
gap since early in this project.** Both are scoped by an `alias` id (a
member's per-league identity, not the same as `member.id` used elsewhere --
check `FormatsByMemberId.json` in this same capture for how alias/member
ids relate, and confirm which id `TEAM_ROSTER_QUERY`'s `roster[].member.id`
actually corresponds to before wiring this up, rather than assuming).

`getEightBallStats` returns real per-player stats: `matchesWon`,
`matchesPlayed`, `CLA`, `defensiveShotAvg`, `matchCountForLastTwoYrs`,
`lastPlayed`, split by `EightBallStats`/`NineBallStats`, plus a raw
`players` list with per-session `nineOnSnaps`, `nineBallBreakAndRuns`,
`miniSlams`, `skunks`.

`TeamStat` (paginated: `id`, `limit`, `offset` variables) returns
`pastTeams` + `currentTeams` per alias -- each with `matchesPlayed`,
`matchesWon`, `skillLevel`, `rank`, `nickName`, and which team/division/
session it was for. This is the cross-season history `PlayerMatch` doesn't
currently have any source for.

No PII concern in either of these two specifically (no names/emails in the
sanitized shapes) -- safe to use close to verbatim, still worth a second
look at the full non-sanitized query text before finalizing, same as every
other query in this file.

This likely needs a new ingestion path (or an extension of `PlayerMatch`)
since it's season-level aggregate stats, not a single match's scoresheet --
don't force it into the existing per-match `ingest_match_scores` path
without checking the shape actually fits.

### 3. Lower priority: `LeagueBox`

League-level branding/contact widget (logo, urls, phone, league officer
contacts). Requests the viewer's OWN name/email and contacts'
names/phones -- real PII, more than `DIVISION_CONTACTS_QUERY` already
covers for less value. Probably not worth wiring up; noted here so nobody
rediscovers it from scratch and wonders why it wasn't used.

## Everything else in this capture

`AliasSessionStatsDropdown`, `ComponentFeatureCheck`, `DisableCheck`,
`FeatureCheck`, `Header`, `HeaderCartQueryQuery`, `LiveStream`,
`MembershipBannerQuery`, `NationalNews`, `RaygunUserTracking` (third-party
error tracking, not APA data), `TournamentBannerQuery`,
`TournamentStatQuery`, `UseGetViewerQuery`, `ViewerEventQuery`,
`ViewerQuery`, `dashboard`, `dashboardBoxStats`, `dashboardMVP`,
`dashboardNews`, `getMemberStatsHeader`, `getMembershipHistory`,
`leagueEvents`, `login`, `newsLeagues`, `notificationBell`, `rules`,
`sidebar`, `viewerCountryQuery`, `viewerLeagues` -- UI chrome, navigation,
news, and account/session plumbing. Not APA score-tracking data. Skip
unless something specific turns up wanting one of them.

Already correctly captured and matching the existing implementation with no
changes needed: `teamPage`, `teamRoster`, `teamSchedule`, `DivisionContacts`,
`MatchPage` (see `team/`, `division/`, `match/` subdirectories here).
