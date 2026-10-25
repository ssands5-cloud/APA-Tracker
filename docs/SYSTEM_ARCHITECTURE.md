# APA Tracker — System Architecture

## What this system does

APA Tracker ingests league match data from APA.com, computes matchup analytics and lineup recommendations, and surfaces them in two delivery paths: (1) offline Excel/HTML artifacts the captain uses at the venue, and (2) a live Next.js web app (Ultimate Coach) backed by a Turso cloud database.

---

## Two distinct systems sharing one codebase

| System | Language | Database | Entry point | Audience |
|--------|----------|----------|-------------|----------|
| **Offline pipeline** | Python | SQLite on `D:\APA-Tracker-Data\databases\apa_tracker.db` | `scripts/run_game_night.py` | Captain at venue (Excel/HTML artifacts) |
| **Ultimate Coach web** | TypeScript/Next.js | Turso cloud SQLite (libsql HTTP) | `apps/ultimate-coach-web/` | Captain on mobile/browser |

These share analytics logic conceptually but **do not share a runtime DB**. The Python pipeline writes SQLite; the web app reads from Turso. Data flows into Turso only via an explicit migration/upload step.

---

## Python pipeline — data flow

```
APA.com (GraphQL + HTML)
    ↓
scraper/ — acquires raw data, writes fixture JSON to disk
    ↓
pipeline/refresh_sources.py — acquires or loads cached fixtures
    ↓
pipeline/ingest.py → database/ingest.py — writes to SQLite
    ↓  (database/models.py: Team, Player, Match, PlayerMatch, ...)
analytics/ — reads from SQLite Session, returns typed dataclasses
    ↓
ui/ — renders Excel (.xlsx) or HTML artifacts
    ↓
exports/ (gitignored) or ultimate-coach-runs/ (gitignored)
```

### Authoritative database
`D:\APA-Tracker-Data\databases\apa_tracker.db` (production)  
`D:\APA-Tracker-Data\databases\apa_tracker_regenerated.db` (refresh candidate)  
Path config: `scripts/paths.py` → `APA_DB`  
Override: env var `APA_DB_PATH`

### Authoritative config
`apa_config.yaml` — team external ID, division, session name  
`apa_config.local.yaml` — viewer identity (gitignored, machine-local)  
`.env` — `APA_USERNAME`, `APA_PASSWORD`

---

## Key data flow: game night

**Script**: `scripts/run_game_night.py`  
**Steps** (in order):
1. Acquire current session data from APA.com → `pipeline/refresh_sources.py`
2. Stage into a copy of the DB (never overwrites production)
3. Run analytics on the staged DB → `analytics/ultimate_coach_cockpit_identity_bridge.py`
4. Validate identity namespace → `analytics/ultimate_coach_identity_namespace_audit.py`
5. Build cockpit HTML → `ui/ultimate_coach.py`
6. Validate artifacts → `pipeline/refresh_workbook.py`
7. Promote to `ultimate-coach-runs/` when clean

**Output artifacts** (all in `ultimate-coach-runs/`, gitignored):
- `ultimate_coach.html` — interactive Scout & Compare
- `ultimate_coach.xlsx` — Excel companion
- `match_night_package/` — AES-256-GCM encrypted static site

---

## Key data flow: data acquisition

**Script**: `scripts/scrape_and_ingest.py`  
**What it does**: Full APA scrape (teams → roster → match history → standings → player career stats → team history). Writes SQLite directly. Requires APA credentials in `.env`.

**Historical archive**: `scripts/build_ultimate_coach_archive.py`  
Builds the league-wide historical staging DB from captured GraphQL fixtures. This is a separate DB from the active-session production DB.

---

## Ultimate Coach web app — data flow

```
Snapshot JSON (encrypted .enc.json or dynamic from API)
    ↓
apps/ultimate-coach-web/src/lib/server/historical-snapshot.ts
    authorizedSnapshot(userId, snapshotId) — server-side only
    decryptSnapshot(enc) — AES-256-GCM (UC_SNAPSHOT_KEY)
    ↓
React Server Components (app/ routes)
    ↓
Client components (components/*.tsx)
    — Snapshot passed as prop, never fetched from browser
```

### Auth layer
- **Provider**: Clerk (`@clerk/nextjs`)
- **Role system**: stored in Turso DB — ADMIN / COACH / REVIEWER / PENDING / SUSPENDED
- **Role gate**: `apps/ultimate-coach-web/src/lib/server/authorization.ts` → `historicalAccess(userId)`  
  — server-side only, NEVER in client components
- **Admin page**: returns 404 to non-admins (not a redirect)

### Turso DB
- URL: `TURSO_DATABASE_URL` (env)
- Token: `TURSO_AUTH_TOKEN` (env)
- Client: `apps/ultimate-coach-web/src/lib/db/client.ts` (`execute`, `executeBatch`)
- Tables: users, audit_log, activity_log (identity / access management only)
- **Not** the match data DB — match data lives in the encrypted snapshot

---

## Critical invariants (never violate)

| Invariant | What it means | Where enforced |
|-----------|---------------|----------------|
| `probability_publication: FORBIDDEN` | No win probability, predictive confidence, or % bars without label "Historical direct record rate" | All UI components |
| Snapshot URL never in browser | `NEXT_PUBLIC_` env vars must not expose snapshot paths | `middleware.ts`, server components |
| `evidenceLabel(level)` everywhere | Raw `level` strings never reach UI | `lib/evidence-label.ts` |
| `<aside>` before `<div.workspace>` | DOM order is load-bearing for mobile sidebar (position: fixed) | `app/layout.tsx` |
| Role check server-side only | `historicalAccess()` never called in client components | `lib/server/authorization.ts` |
| No `APA_DB_PATH` hardcoded | All scripts use `scripts/paths.py` or `APA_DB_PATH` env | `scripts/paths.py` |

---

## Snapshot type (the core data contract)

Defined in: `apps/ultimate-coach-web/src/lib/snapshot-types.ts`

```typescript
Snapshot {
  schema, mode, label
  provenance: { capturedAt, latestResult, fixtureWhen, notice }
  fixture: { team, opponent, format, when, venue, scope, source }
  players: Player[]        // { id, name, skill, availability }
  opponents: Player[]
  evidence: Record<ourPlayer, Record<theirPlayer, Evidence>>
  responses: Record<string, Response>   // coaching responses
  threats: { name, text, wins, meetings, playersMet }[]
  plan: {
    lead: { player, level, why, alternatives[] }
    holds: Hold[]
    protect: Hold[]
    sacrifices: Pairing[]
    bestBoard, safestBoard, ifWeLead, ifTheyLead: Pairing[]
    cap: { cap, used, cheapest_rest, slack, incomplete }
    fragility: { rating, player, thinPairings[] }
    strongest, weakest: Pairing
  }
  totals: { meetings, directPairs, possiblePairs, favorablePairs, concerningPairs }
}
```

Phase 1 constraint: **all new features must derive from this type — no new data structures**.

---

## Key integrations

| Integration | Direction | Config |
|-------------|-----------|--------|
| APA.com GraphQL | Outbound (scraper) | `APA_USERNAME` / `APA_PASSWORD` in `.env` |
| Turso cloud DB | Outbound (web app) | `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` |
| Clerk auth | Outbound (web app) | `CLERK_SECRET_KEY` / `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` |
| GitHub Pages | Outbound (publish) | `scripts/publish_match_night.py` (fail-closed) |

---

## Test runner

**Runtime**: Node v24.18.0 at  
`C:\Users\ssand\actions-runner-invest-excel\externals.2.336.0\node24\bin\node.exe`

**Framework**: Node built-in `node:test` (NOT vitest)

**Run command**:
```
node --experimental-strip-types apps/ultimate-coach-web/tests/*.test.ts
```

**Primary regression gate**: `captain-command.test.ts` — runs before every commit to `feat/phase1-war-room`

---

## Branch / PR landscape (as of 2026-10-25)

| Branch | PR | Status |
|--------|----|--------|
| `feat/phase1-war-room` | (next PR target) | Active — all Phase 1 web work here |
| `feat/apa-tactics-coach-skill` | #104 | Open, deployed, awaiting merge |
| `main` | — | Protected, no direct commits |

**GPT/Jeeves collaborator** also pushes to `feat/phase1-war-room`. Always `git pull` before pushing.

---

## Storage layout (D: drive)

`D:\APA-Tracker-Data\` (created by storage-migration Phase 0, commit `70ea1a1`)
```
databases/      ← apa_tracker.db (production), regenerated, demo DBs
backups/        ← DB backups
refresh-data/   ← pipeline refresh outputs
exports/        ← Excel/HTML exports
historical-seasons/
snapshots/
reports/
logs/
scoresheets/
statistics/
archive/
```

Scripts that haven't been updated yet still read from `PROJECT_ROOT/data/` (legacy path via `LEGACY_DATA_DIR` in `scripts/paths.py`). Phase 2 migration will update those scripts.
