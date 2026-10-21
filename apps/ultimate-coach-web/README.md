# Ultimate Coach web

Public demo: https://apa-tracker.vercel.app

Public routes use entirely invented teams and records. The read-only historical dashboard is
under `/dashboard`; all six sections require server authorization before snapshot access.
Clerk setup and real login verification are still required. Do not call protected historical
access live or accepted until the configured-provider checks below pass.

## Access boundary

- Clerk verifies sign-in. The server freshly checks the provider session and user account.
- Only an active, non-revoked session belonging to a non-banned/non-locked account with an
  explicitly allowlisted verified email may read this pilot snapshot.
- `UC_AUTHORIZED_EMAILS` is a server-only list, initially one owner-approved viewer.
- The pilot grants one fixed historical snapshot scope, not arbitrary teams or path-selected files.
- Missing configuration, missing membership, provider failure and invalid ciphertext deny access.
- Unknown accounts go to Access Denied; anonymous requests go to sign-in.
- Private pages are dynamic and use private/no-store headers. No private JSON/download endpoint exists.
- Public pages and static browser JS contain no real historical identities or records.
- Only AES-256-GCM ciphertext is committed. Its key is server-only, separate from Git and artifacts.
- No APA credentials, cookies, production DB, refresh runner or private notes are deployed.

An authorized response necessarily sends the authorized display data to that viewer's browser.
It is not embedded in publicly downloadable JavaScript bundles or public pre-rendered pages.

## Provider setup (required before historical release)

Connect Clerk to the existing Vercel apa-tracker project. Select invitation-only registration;
invite only the approved viewer. Store `CLERK_SECRET_KEY` and
`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` through Vercel settings, never chat/Git.
Set server-only `UC_AUTHORIZED_EMAILS` and `UC_SNAPSHOT_KEY` for the intended environment.
Do not share production keys with previews by default. `.env.example` lists names only.

Before release verify: anonymous denial, unapproved verified account denial, approved verified
account access to all six sections, sign-out, revoked session denial, direct RSC requests,
private/no-store headers and absence of private data in public assets. Also test actual iPad use.
Synthetic policy tests and missing-provider denial are not substitutes for these provider checks.

## Local snapshot workflow

```text
reviewed historical HTML export (private, exact hash)
 -> scripts/build_historical_dashboard_snapshot.py
 -> ignored tmp/uat/protected-historical/snapshot.json (plaintext, private)
 -> scripts/protect_dashboard_snapshot.py (UC_SNAPSHOT_KEY supplied privately)
 -> apps/ultimate-coach-web/private-snapshots/historical.enc.json (ciphertext)
 -> validate public isolation and protected access
 -> commit/push reviewed app and ciphertext only
 -> Vercel build using private environment configuration
```

The exporter refuses plaintext outputs outside ignored tmp/. The encryption helper uses an
existing 32-byte random key provided privately as base64 in `UC_SNAPSHOT_KEY`; it never publishes
or prints the key. Keep the key in the deployment environment and private operator storage.
No automatic refresh or production database integration is connected.

Historical recommendations reuse the existing Python evidence/M3 engine. They are captured
results under simulated availability/cap assumptions, not a current live APA feed. Dates and
assumptions appear after authorization; there are no editing or write APIs.

## Validation

Node24 / pnpm11.25.0:

```sh
pnpm install --frozen-lockfile
pnpm test
pnpm run typecheck
pnpm run build
pnpm start
```

Python exporter/protection tests: `tests/test_historical_dashboard_snapshot.py` with a new
`--basetemp` under ignored tmp/. Local negative browser checks: `tests/private_access.py`.
`UC_WEB_BASE_URL` and `UC_WEB_BROWSER=chromium|webkit` select the test target. These checks
explicitly describe missing-provider behavior; they do not claim a real authenticated login.
Keep raw results and screenshots private.

Vercel root stays `apps/ultimate-coach-web`, framework Next.js, Node24, locked pnpm install.
Never deploy the repository root, environment files, plaintext snapshots or private tmp/.

## Previous exposure

A plaintext historical snapshot was previously pushed in commit83faa58. Deleting the current
file and encrypting later copies does not remove that public Git history. No history rewrite
was performed. See ../../docs/hosted_dashboard_exposure.md for the documented boundary.

Administration and team-access design: [PHASE2.md](PHASE2.md).
