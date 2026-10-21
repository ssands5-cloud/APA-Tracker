# Ultimate Coach web · historical league-night simulation

Live: https://apa-tracker.vercel.app

**REALISTIC DEMO USING HISTORICAL DATA** — Brunch Ballers vs Inglorious Poolsters,
8-Ball, eight captured players on each side. Recommendations are produced by the existing
Python evidence/M3 engine, not authored placeholders or a new frontend scoring model.

## What is real and what is simulated

- Real: captured roster names, captured skill levels, verified direct results, shared-opponent
  aggregates and overall-record context from an existing reviewed historical HTML export.
- Historical source: exported October 15, 2026; latest recorded result October 9; selected
  scheduled fixture October 18. This is a replay, not an assertion of a current/upcoming schedule.
- Simulated: all captured players available, none played, five games remaining, reference cap23
  applied to both teams. No winner, score, winning percentage or observed opponent order is invented.
- Conditional: lead, responses, holds/protection, concessions and boards from the existing engine.
  A hypothetical board is not a required lineup or a tournament legality check.

The six routes show Home, Match Night, Recommendations, Threats, Team Status and Summary.
Every page discloses the historical mode and dates. No editing or write API exists.

## Data boundary

Only `data/snapshot.json`, the deliberately public allowlisted display projection, is committed.
The operator's original HTML, full payload, APA identifiers/card numbers, notes, database,
credentials, cookies and raw capture files remain private. Both GitHub and this dashboard are
public; publishing names and aggregate records is deliberate under Paul's historical-demo request.
This is not authorization to publish an unrestricted production dataset or private coach notes.

Next.js imports the local JSON at build time. It never opens a DB or calls APA. The Python
exporter runs only on the operator machine, outside the Vercel app root. It verifies the exact
source HTML hash, reads its embedded export, selects the historically configured viewer's fixture,
uses existing evidence/M3 functions, and atomically writes only the display snapshot.

```text
reviewed historical HTML export (private)
 -> local scripts/build_historical_dashboard_snapshot.py
 -> apps/ultimate-coach-web/data/snapshot.json
 -> tests + Next.js build
 -> commit/push app and snapshot
 -> Git preview / reviewed production deployment
```

Local export from the repository root (replace placeholders with reviewed private inputs):

```sh
python scripts/build_historical_dashboard_snapshot.py --html <historical-export.html> --expected-sha256 <reviewed-html-sha256> --cap 23
```

This does not run a refresh or publish anything itself. The earlier proposed automatic
refresh-to-snapshot-to-production pipeline is not connected by this historical-demo task.
A branch push can produce a Git preview; production promotion/branch policy must be verified,
not inferred from a successful push. Do not merge branches or overwrite production data blindly.

## Build and validation

From this app directory, using Node24 and pnpm11.25.0:

```sh
pnpm install --frozen-lockfile
pnpm test
pnpm run typecheck
pnpm run build
pnpm start
```

Python exporter tests: `python -B -m pytest tests/test_historical_dashboard_snapshot.py` from
repo root. Browser checks: `tests/browser_smoke.py` using an existing Python Playwright setup;
`UC_WEB_BASE_URL` selects local/hosted URL and `UC_WEB_BROWSER=webkit` selects WebKit.
Evidence belongs in private tmp/, never the repository's public data directory.

Verified: thirteen exporter tests, five snapshot/frontend checks, production build/typecheck,
and79 Chromium +79 touch-enabled WebKit local browser checks. Physical iPad use is not claimed.

## Vercel

Existing project: apa-tracker. Root Directory: apps/ultimate-coach-web. Framework: Next.js.
Node24; locked pnpm install/build, Next.js output defaults. No source access outside the app root,
no Python runtime, environment secrets or database. Explicit file deployment must include only
reviewed app source/config/lockfile and data/snapshot.json, never repo root or private outputs.

Navigation uses ordinary page links after WebKit exposed unnecessary RSC prefetch errors in
Phase1. Opponent selection is local React view state; no participation or availability is saved.

Phase2 auth/team/admin security plan: [PHASE2.md](PHASE2.md).
