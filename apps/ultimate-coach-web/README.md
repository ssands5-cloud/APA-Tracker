# Ultimate Coach web · Phase 1

Dedicated Next.js/TypeScript dashboard. **Synthetic public demo only.** No sign-in, database,
APA login, refresh integration, real identities or production recommendation execution.
Authored sample responses demonstrate presentation; they do not change the Python engine.

Six routes: `/`, `/match-night`, `/recommendations`, `/threats`, `/team-status`, `/summary`.
The only state is the currently viewed opponent. There are no editing actions or stored marks.

## Local run

From this directory, with Node 24 and pnpm 11.25.0:

```sh
pnpm install --frozen-lockfile
pnpm test
pnpm run typecheck
pnpm run build
pnpm start
```

Local address: http://127.0.0.1:3000. `pnpm dev` runs development mode instead.

## Vercel

Use a dedicated project, Framework Preset **Next.js**, Node **24.x**, Root Directory
**apps/ultimate-coach-web** when importing Git. Keep Next.js output defaults; no root Python
build, database, environment variables or outside-root source access. For an explicit file
upload deploy only this app's reviewed source and lockfile, rooted at the app itself.
Never include node_modules, .next, .pnpm-store, .env files, repository captures or databases.

The demo may be publicly visible because it contains only invented data. Do not add real data
until Phase 2 authentication and team access have passed independent access-control tests.
Deployment status/URL must come from Vercel READY plus an HTTP/browser check, not a local build.

## Verification

`pnpm test`: invented fixture consistency and absence of external data/write/storage hooks.
`pnpm run typecheck` and `pnpm run build`: isolated app compatibility.
`tests/browser_smoke.py`: production-server browser checks at phone, tablet and desktop sizes;
run using an existing Python Playwright environment and `UC_WEB_BASE_URL` if not localhost.
Browser dimensions are emulation, not physical iPad acceptance.

The app intentionally has no broad app-wide script CSP until nonce/hash behavior is designed
for Next.js and future identity-provider scripts. Current headers prevent framing/object embeds,
limit referrer and device permissions, and disable indexing. These are not authentication.
