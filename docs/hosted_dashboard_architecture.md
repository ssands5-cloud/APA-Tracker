# Ultimate Coach production web architecture and implementation plan

**Phase 1 synthetic pilot approved and implemented, 2026-10-20.** Paul's later instruction
supersedes the implementation pause below: the dedicated Next.js/TypeScript application is
`apps/ultimate-coach-web`, using invented data and authored example responses only. Its six
sections are Home, Match Night, Recommendations, Threats, Team Status and Summary. It has no
APA/database/refresh integration. Authentication, assigned-team access and admin implementation
are deferred to Phase 2; therefore only synthetic data may be published. The production design
below remains the gate before any real team information is connected. Build/typecheck and4
data/boundary tests pass; final local Chromium37/WebKit37 and hosted WebKit37 pass. Public URL
https://apa-tracker.vercel.app is live, READY, source5194609, deployment
dpl_8JZ6DKgAxR1aqxtazTyUxVvdRVP4. All19 uploaded app files match committed source. No root Python,
DB or APA data was uploaded. Phase 2 execution plan: apps/ultimate-coach-web/PHASE2.md.

2026-10-20. GPT self-audited design, source checkpoint 8b483823.
The remainder records the original production architecture proposal; the current synthetic
release is described above. Real-data/backend/auth/admin work below is still proposed, not enabled.
Paul confirmed Vercel access and directed a dedicated web frontend; do not deploy the repository root.
This plan supersedes the earlier static-only hosting proposal.

## 1. Decision

Create a dedicated Next.js/TypeScript application at `apps/ultimate-coach-web`.
Vercel hosts that application only. The existing Python engine remains the authority for
recommendations. The private refresh machine retains SQLite, captured APA responses,
interactive APA login, workbook generation and all APA credentials.

Phase 1 is a responsive, authenticated, read-only view of an immutable fixture snapshot.
It has a small server layer for session checks, team authorization and snapshot reads. It does
not recompute recommendations or contact APA. No hosted database is needed.

Phase 2 adds administration only after its private durable-state and authorization boundaries
are approved and tested. It does not move the APA database to Vercel.

## 2. Why the current deployment fails

The user reports `PYTHON_ENTRYPOINT_NOT_FOUND`. That is consistent with Vercel trying to deploy
this operational Python repository as a Python HTTP application, without a supported HTTP
entry point. Adding a dummy `app.py` would not turn the existing tools into the requested site.

Verified source evidence:

| Existing source | Actual responsibility | Hosting implication |
| --- | --- | --- |
| `FULL_APA_REFRESH.bat`, `QUICK_REFRESH.bat` | Call `tools/launch_apa_refresh.bat` with full/quick mode | Windows operator launchers, not web entry points |
| `pipeline/ultimate_coach_refresh.py:run_refresh` | Capture, ingest, derived analytics, verified payload, workbook/HTML, validation, completed-run pointer | Keep on trusted refresh machine |
| `scripts/build_match_night_package.py:main` | Command-line selected-fixture export and encryption | Reuse selection/export concepts, not an HTTP app |
| `ui/match_night.py:select_fixture`, `slim_payload` | Limit export to exact selected fixture/format and relevant evidence | Basis for minimized web snapshot |
| `analytics/ultimate_coach_cockpit_identity_bridge.py:build_verified_cockpit_payload` | Build identity-verified engine input | Reuse before web export |
| `analytics/ultimate_coach_war_room.py:next_send`, `live_threats` | Existing evidence lists and threat guidance | Compute once using existing rules |
| `analytics/match_night_engine.py:plan_for_war_room` | Existing M3 plan | Export same plan; no TypeScript reimplementation |

The searched production sources contain no FastAPI/Flask/Django HTTP application. No tracked
root frontend package/build manifest or Vercel configuration was found. The exact failed
project's preset/root/build log has not been inspected: the connected tool lists zero visible
projects in APA Coach, despite the user's confirmed Vercel repository access. Do not confuse
that visibility limitation or the earlier create-project403 with this new build error.

## 3. Production topology

```text
TRUSTED OPERATOR MACHINE
APA login -> capture -> guarded ingestion -> private SQLite
  -> derived matchups/trends -> verified payload -> existing evidence + M3
  -> workbook + local HTML + all existing validations
  -> proposed minimized web snapshot + private binding manifest
                           |
                    controlled release
                           v
VERCEL: apps/ultimate-coach-web only
Next.js server -> session + team authorization -> immutable server-only snapshot
                           |
                    authorized response
                           v
Mobile / tablet / desktop: six read-only sections
```

Only the reviewed fixture snapshot is hosted, never the DB, raw captures or APA session.
The same snapshot supplies all six sections so different requests cannot combine generations.
The snapshot is fixture-scoped and dated, not a live claim about availability or played marks.

## 4. Dedicated frontend and Vercel settings

Proposed files, **not yet created**:

```text
apps/ultimate-coach-web/
  package.json                   # real Node application manifest; pinned lockfile alongside
  next.config.ts                 # security headers and server bundle configuration
  tsconfig.json
  src/app/layout.tsx
  src/app/sign-in/[[...sign-in]]/page.tsx
  src/app/(dashboard)/page.tsx
  src/app/api/snapshot/[fixtureId]/route.ts  # authenticated GET only
  src/components/                 # six responsive views, view-only selectors
  src/lib/server/auth.ts         # managed identity SDK and team membership checks
  src/lib/server/snapshots.ts    # server-only validated snapshot loader
  src/lib/snapshot-schema.ts     # versioned display contract, no engine weights
  src/proxy.ts                   # auth routing; not sole authorization layer
  private-snapshots/              # ignored, injected release input; never public assets
  public/                        # generic icons/styles only; no team records or snapshots
  tests/
scripts/build_hosted_coach_snapshot.py  # proposed local exporter using existing engine
```

Vercel project Root Directory: `apps/ultimate-coach-web`; Framework Preset: **Next.js**.
Use that app's locked Node dependencies and `next build`, with Next.js default output handling.
Do not configure it as Python, run pip, start the scraper, or override output to the repo root.
Do not enable source access outside this root. Root Directory is a project setting, not a
`rootDirectory` key in `vercel.json`. Confirm actual framework/Node compatibility at implementation.

Deliver Next Send, Blind Send, Threats, Matchups, Team Status and Match Night Summary.
Use mobile-first cards/navigation, keyboard access and locally scrollable matrix tables.
Validate 390px phone and 768/1024px tablet layouts. No Sent buttons, notes, cap editing,
availability editing, admin links or refresh controls in Phase 1.

No recommendation calculations in React. View selectors only change the selected opponent or
section from the authorized snapshot. No ranking changes, predictions or confidence percentages.
Show explicit scope, capture time, unknown availability and omitted live state.

## 5. Snapshot and backend contract

The proposed exporter consumes a completed refresh run, not an arbitrary default DB. Reuse
fixture selection, identity checks and existing engine functions. Export only selected teams,
roster identities needed for display/authorization, format, records/counts, dates, skill context,
evidence confidence explanations, Next Send evidence, M3 lead/responses/holds/concessions/boards,
threats and summary. Keep source-file paths, raw responses and unrelated player histories private.

Contract includes schema version, source/engine revision, generated-at and data-as-of times,
fixture ID, authorized team scope and payload digest. The private release manifest also binds
run/READY/manifest/artifact hashes. A hash detects mismatches; it is not authorization or proof
that a compromised publisher is honest. Only the trusted release identity may supply snapshots.

The loader validates schema and scope and fails closed on missing, malformed or mismatched
snapshots. Use an explicit fixture allowlist/map, never filesystem paths assembled from user input.
Snapshot modules and files are server-only and must be included only in the server bundle.
They must not appear in public/, browser JavaScript, source maps or build-time static HTML.
Verify bundle/output contents rather than assuming folder names provide security.

Render protected data dynamically after authorization; disable static generation/ISR for these
routes. The API independently checks session and team scope on every GET, with private/no-store
responses and no shared tenant cache. Reject unsupported methods. No POST/PATCH/DELETE or Server
Action mutation is implemented in Phase 1. No Python process or DB connection exists in a Function.

An immutable bundled JSON snapshot is a deployment artifact, not a hosted database. Its update
requires a new reviewed deployment; no filesystem writes or background refresh inside Vercel.
Use explicit Next.js server file tracing/bundling and a deployment test to prove the loader can
read it. A missing release snapshot must produce unavailable/demo mode, never silent real-data fallback.

## 6. Authentication and secret boundaries

Recommended application identity: managed, invite-only email sign-in using Clerk's supported
Next.js SDK, with explicit approved membership. Provider provisioning/cost and account model
remain approval/configuration gates; no provider has been installed. Do not implement custom
password storage, JWT signing, magic links or a shared password as user authentication.

Vercel Deployment Protection is additional perimeter protection for previews/operator releases,
not a substitute for application team authorization. If a temporary Vercel-member-only pilot is
chosen instead, verify protection covers every environment, domain and direct asset URL before
any upload; it cannot be assumed from default preview protection. The final captain account
model has not been selected by Paul.

Public: generic UI assets and intentionally public identity-provider publishable configuration.
Server only: identity-provider secret and future narrowly scoped private-service credential.
Never on Vercel: APA password, capture bearer token, cookies/browser profile, config credentials,
SQLite DB, raw fixtures, workbook or unrestricted full HTML export.
Never prefix private secrets with `NEXT_PUBLIC_`; never log request tokens or snapshot bodies.
Use provider-managed Secure/HttpOnly session handling, enforced invitation/team membership,
revocation checks, MFA for admins, bounded inputs and restrictive CSP. Escape all display data.
No analytics sending player data, offline service worker or remembered decryption key in Phase 1.
The older encrypted/offline export is a separate workflow; do not deploy it unchanged as this app.

An authorized viewer can retain information they have seen. Sign-out cannot erase downloaded
or already rendered data; no instant-erasure claim is made. Apply the same authorization to
server-rendered HTML, React server responses, APIs, downloads and every direct deployment alias.

## 7. Refresh workflow integration

Current workflow is unchanged:

```text
FULL_APA_REFRESH.bat or QUICK_REFRESH.bat
 -> tools/launch_apa_refresh.bat
 -> pipeline/ultimate_coach_refresh.py
 -> local run: candidate DB + Ultimate_Coach.xlsx + ultimate_coach.html
 -> validations + manifest.json + READY + completed-run pointer
```

The coordinator currently does **not** build or publish a hosted dashboard. Proposed extension:

1. Verify successful completed run, coverage, identity safeguards, READY and artifact hashes.
2. Select the explicit viewer/team/fixture from that run and export the minimized web snapshot.
3. Validate snapshot schema, engine equality, scope and sensitive-data exclusion.
4. Inject that snapshot into a private web release staging directory, outside Git; build the
   dedicated frontend using its lockfile. No APA/network credentials are needed for this build.
5. Deploy a protected preview from the allowlisted frontend build. Validate anonymous denial,
   correct/incorrect team access, six sections and artifact/source binding.
6. Promote the exact tested deployment under release authority. Retain the previous good
   deployment for rollback. Never rebuild a different artifact and call it the reviewed preview.

Code-only Git previews use synthetic data exclusively. Private snapshots never enter GitHub.
Production uses a controlled local or trusted private release job that has the completed run.
Do not connect root-repo Git deployment and assume it can access the operator's local data.
Deployment credentials are operator/CI secrets, separate from APA credentials and app runtime.

Quick refresh may reuse web data only when exact scope, payload, engine/renderer/schema versions,
time-sensitive inputs and artifact hashes still agree. Auth/security changes still require tests.
If publication fails, report LOCAL REFRESH COMPLETE / HOSTED UPDATE FAILED and keep the previous
site timestamp. Neither failed ingestion nor failed validation advances the hosted generation.
Keep workbook, local HTML and hosted data source hashes aligned; publish a single snapshot generation.

## 8. Phase 2 admin architecture: design only

| Capability | Minimum authority | Required boundary |
| --- | --- | --- |
| Team management | Organization admin | Exact team membership; preserve historical identity/rosters |
| Availability | Captain assigned to team and fixture | Server-validated roster membership; Unknown distinct from absent |
| Match-night updates | Assigned captain | Atomic paired participation; revision checks and idempotency |
| Recommendation review | Authorized captain/reviewer | Opinion separate from APA facts; no hidden ranking overrides |
| Refresh controls | Operator | Allowlisted constrained job; no browser shell, SQL or APA credentials |

Before writes, establish a securely reachable private durable service owning the current data
store and audit log. The Next.js backend-for-frontend authenticates users and forwards only
allowlisted, authorized commands using a least-privilege service identity. The private service
independently checks caller/scopes/revisions. Do not expose SQLite, a desktop database port or
an arbitrary command endpoint. No hosted database, public tunnel or new state service is
provisioned under this plan.

The private runner must be reliably available; an offline desktop cannot process admin updates.
Remote job transport, private service hosting and durable command/audit storage are genuine
Phase 2 infrastructure decisions. Do not pretend a stateless Vercel Function solves them.
Implement read-only snapshot hosting first; admin remains disabled until these are resolved.

Mutations require CSRF/origin checks, validation, bounded requests, rate limits, stale-revision
rejection, idempotency, transaction boundaries and immutable actor/team/action/result audit events.
Test cross-team denial and revoked roles on every handler, not just hidden buttons.
A refresh action requests an allowlisted job with overlap prevention, status/progress and retry;
interactive APA authentication occurs only on the private operator machine. It must support
waiting-for-login status without asking for APA credentials in the web app. Validate before
publication, preserve the original DB and roll back failed releases.

No admin screen, write API, runner transport or remote refresh is implemented in Phase 1.

## 9. Implementation sequence and completion gates

1. Confirm actual Vercel project/team/root and authentication/account decision. Review failed log.
2. Add only the dedicated Next.js app, pinned dependencies, synthetic snapshot and schema.
   Verify its build succeeds without Python, source DB, APA access or root-repo dependencies.
3. Add managed authentication and team authorization. Prove denial for anonymous, wrong-team,
   expired/revoked users across HTML, server responses and API/direct URLs.
4. Build the Python snapshot exporter against the completed-run manifest, reusing the engine.
   Test every requested section against the same fixture outputs, including sample/cost warnings.
5. Integrate the read-only UI and validate phone/tablet, XSS/input boundaries, no write requests,
   no protected data in public assets, bundle tracing and correct timestamp/scope.
6. Deploy synthetic protected preview only after its release inputs and target are reviewed.
   Verify Vercel-side auth behavior independently of local tests.
7. Resolve completeness/release gates, stage the exact real snapshot privately, test, then promote
   under explicit real-data release authority. Exercise failed refresh/upload and rollback.
8. Begin admin implementation only after its role model, private connectivity, persistence and
   operational ownership are approved. Reuse identity and team authorization from Phase 1.

Current status: plan ready; dedicated frontend/exporter/API/auth not implemented. The earlier
untracked `ui/hosted_dashboard.py` is an unfinished static renderer prototype only, not the chosen
Next.js app, and is excluded from this documentation commit. No `--read-only` CLI flag exists.
The retained validation snapshot still has two protected unresolved refresh identities; never
bypass those or claim complete current data based on synthetic tests. No production deployment,
secret provisioning, DB migration or database publication was attempted in this architecture task.

## Official platform references

- [Next.js on Vercel](https://vercel.com/docs/frameworks/full-stack/nextjs)
- [Monorepo project roots](https://vercel.com/docs/monorepos)
- [Project configuration](https://vercel.com/docs/project-configuration/vercel-json)
- [Python HTTP entry points](https://vercel.com/docs/frameworks/backend/fastapi)
- [Deployment Protection](https://vercel.com/docs/deployment-protection)
- [Vercel environment variables](https://vercel.com/docs/environment-variables)
- [Clerk Next.js quickstart](https://clerk.com/docs/quickstarts/nextjs)
