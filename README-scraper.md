# Scrape contract

`scraper/full_auto_scrape.py` is the canonical scraper. One run produces a
full, current league snapshot under `scraper/sanitized_fixtures/`. Everything
downstream should treat that directory as the interface and this file as the
contract describing it.

```bash
python scraper/full_auto_scrape.py     # scraper only
python pipeline_run_all.py             # step 1 is the scraper
```

See [docs/full_pipeline_integration.md](docs/full_pipeline_integration.md)
for what "the pipeline" means end-to-end, what's now actually verified by an
integration test with nothing stubbed (real fixtures through every real
export) plus a determinism check, and what real gaps remain (dependency
pinning; `pipeline_run_all.py` itself isn't run as a real subprocess in CI).

## Login flow

Three steps, in this order. Skipping any one of them yields a run that looks
successful and captures nothing useful.

1. **Login form** — `league.poolplayers.com/login`, which redirects to
   `accounts.poolplayers.com/login`. Loaded with `wait_until="networkidle"`,
   because the *Log In* button renders **disabled** until the form hydrates;
   the scraper waits for it to become enabled before clicking. It carries no
   `type="submit"` and its class is a hashed CSS-module name, so it is
   targeted by accessible role and name.

2. **Consent screen** — submitting credentials lands on
   `accounts.poolplayers.com/authorize`, showing *"Continue to Member
   Services"*. **Until its `Continue` is clicked the league domain never gets
   an authorized session**: `ViewerQuery` returns `{"viewer": null}`, the
   dashboard renders no teams, and every league route bounces back here.

   `complete_authorization()` clicks it only when **all four** hold:

   | Guard | Value |
   |---|---|
   | host | exactly `accounts.poolplayers.com` |
   | path | starts with `/authorize` |
   | body text | contains `Member Services` |
   | control | a button with accessible name `Continue` |

   Anything else logs and declines — it must never click a `Continue` on an
   arbitrary third-party prompt. The check re-runs on each league route,
   since a route can bounce back to consent mid-run.

   **The `/authorize` URL contains a live `deviceRefreshToken` JWT. Never log
   it.**

3. **Entity walk** — `scrape_all()` reads team, division and league ids out of
   the captured `dashboardTeams` payload and visits each route directly.
   It deliberately does **not** scrape `<a href>` tags: the app is a
   client-rendered SPA that emits no anchors for these routes, and a DOM-based
   pass found zero links on a fully authorized page. League routes load with
   `wait_until="domcontentloaded"` plus a settle delay — they hold connections
   open and never reach `networkidle`.

## Credentials

`.env` at the repo root, loaded by `env_loader` (imported first in every
credential-dependent module). `override=True`, so a stale Windows-level
`APA_USERNAME` cannot shadow it.

Responses in `AUTH_OPERATIONS` (`login`, `authorize`,
`GenerateAccessTokenMutation`, `RefreshAccessTokenMutation`, `logout`) are
**never written to disk** — they carry live tokens. A real run once wrote a
valid JWT into a file called "sanitized_fixtures", which it was not.

## Where fixtures land

```
scraper/sanitized_fixtures/<entity>/<id>/<OperationName>.json
```

Gitignored by design. The **root-level** `sanitized_fixtures/` is a stale,
empty duplicate — ignore it.

Files are overwritten in place, so a run refreshes rather than accumulates.

## Expected operations per bucket

Verified against a real run (4 teams, 4 divisions, 40 matches).

| Bucket | Id is | Operations |
|---|---|---|
| `global/global` | none | `ViewerQuery`, `UseGetViewerQuery`, `viewerLeagues`, `viewerCountryQuery`, `dashboard`, `dashboardTeams`, `dashboardBoxStats`, `dashboardMVP`, `dashboardNews`, `sidebar`, `Header`, `leagueEvents`, `LeagueInfo`, `LeagueBox`, `getMemberStatsHeader`, plus UI noise (`FeatureCheck`, `RaygunUserTracking`, banners) |
| `team/<team_id>` | real team id | `teamPage`, `teamRoster`, `teamSchedule` |
| `division/<division_id>` | real division id | `DivisionContacts` |
| `match/<match_id>` | real match id | `MatchPage` |
| `alias/<alias_id>` | **alias** id | `TeamStat`, `AliasSessionStats*`, `FormatsByMemberId` |

`dashboardTeams` is the entry point for the whole walk — it is the only
payload that lists every team id, division id and the league slug.

`DivisionContacts` appears in **both** `global/` and `division/`: the same
operation is issued with and without an id depending on the route.

Operation names come from the API and are inconsistently cased
(`teamPage` vs `TeamStat`); the classifier lowercases before matching.

## The `TeamStat` / alias trap

`TeamStat` returns `data.alias`, keyed on an **alias id** — a member's
identity within a league, the *second* id in a
`/member/<member_id>/<alias_id>/teams` URL. It is neither a team id nor the
member id.

It previously filed under `team/3224381`, sitting alongside genuine team ids
like `13082948`. **Fixed at the source**: it now routes to `alias/`. The
prefix table tests `alias` **before** `team`, because `"teamstat"` starts with
`"team"` and would otherwise be captured by the wrong rule. The stale
`team/3224381/` directory has been removed.

> **Downstream rule, regardless:** derive ids from the **payload**, never from
> the directory name. The directory is a convenience for humans reading the
> tree. Any future operation whose name does not match the prefix table will
> land in `global/` with its real id only inside the JSON, and a normalizer
> that trusts folder names will silently mis-key it.

## Two fixture schemas exist on disk

Anything reading fixtures must tolerate both:

```python
body = payload.get("response", payload)   # then body["data"][...]
```

- **This scraper** writes the raw GraphQL payload: `{"data": {...}}`.
- **`tools/capture_apa_graphql.py`** writes a schema-capture envelope:
  `{"operationName", "entityType", "entityId", "capturedAt", "variables",
  "query", "response"}`.

Match discovery read the wrong shape and reported 0 matches on a run that had
actually captured 56.

## Known gaps

- Resolved: `pipeline_run_all.py` now calls `python -m pipeline` directly for
  ingest and exports (the old audit finding C3 — five imaginary
  `pipeline/`/`demo/` files — no longer applies), and the duplicate
  `scraper/pipeline_run_all.py` has been removed. The root file is the single
  end-to-end entry point: scrape → ingest → exports → tests.
- Caps are `MAX_TEAMS=12`, `MAX_DIVISIONS=12`, `MAX_MATCHES=40`. Raise them
  for a full-season sweep.
- The Lineup Optimizer (`analytics/lineup_optimizer.py`) is a transparent
  decision aid, not a fitted probability model — it has not yet been
  evaluated against actual match outcomes. See
  [`docs/lineup_optimizer.md`](docs/lineup_optimizer.md#missing-data-and-current-limitations).
