# Phase 2: authentication, team access and administration

Design only. Phase 1 is deployed at https://apa-tracker.vercel.app with synthetic data.
No real APA data may be added until the read-access gates below pass. Existing Vercel
protection of alternate deployment URLs is separate from application authentication.

## 1. Authentication

Propose invite-only managed email sign-in using a supported Next.js identity SDK, such as
Clerk. Select/configure the provider and confirm cost before provisioning. Do not build custom
password hashing, token signing or email-login infrastructure. Disable automatic access from
public registration; a verified identity alone does not grant access to team information.

Use server-verified SDK sessions. Enforce authentication in protected pages and every API/
Server Action, not only navigation or a request proxy. Keep provider secrets server-only,
require MFA for administrators, support revocation and use SDK-secured cookies. No identity
tokens in URLs, public source, analytics, logs or browser storage. Use nonce/hash-aware CSP
appropriate for Next.js and the chosen SDK before introducing sensitive data.

## 2. Team access

Roles: viewer, assigned captain, organization admin and refresh operator. Roles may overlap
only by explicit assignment. Default is no teams and no access. Bind verified identity to
server-controlled organization/team memberships; never accept roles from client fields.

| Actor | Allowed scope | Boundary |
| --- | --- | --- |
| Viewer | Assigned teams/fixtures | Read authorized snapshots only |
| Captain | Assigned team and active fixture | Availability and participation changes, when writes are authorized |
| Organization admin | Explicit organization teams | Membership and team administration |
| Refresh operator | Explicit refresh scope | Request allowlisted refresh jobs; no arbitrary execution |

Check organization/team/fixture authorization on every read and write, including JSON/download
routes, server-rendered responses and direct URLs. Do not put protected snapshots in public/,
static browser bundles or statically generated pages. Missing or invalid membership fails closed.
Avoid shared response caching for private data; prevent one team's cache entries serving another.
Old public synthetic deployment URLs stay synthetic. Never turn one into a private-data URL
without verifying every alias, preview and environment access boundary.

## 3. Read-only real-data gate

Reuse the existing Python engine and completed-run validations to produce a minimized immutable
fixture snapshot; do not port ranking logic into the web app. Real-data integration is a separate
authorized task. Before release prove authentication/authorization, selected-fixture identity,
scope and source hashes, missing-data disclosures, no public asset leaks, no credential logging,
and rollback. The retained two unresolved refresh identities must remain protected; do not guess.
No production DB or APA session is deployed to Vercel.

## 4. Admin panel

Design screens for team membership/rosters, availability, participation, recommendation review
and refresh status. Implement capabilities only after their write boundary and durable storage
are approved. Captain observations remain opinion, separate from APA evidence. No hidden
ranking adjustments. Display actor, target fixture and proposed change before a write.

Every mutation needs schema validation, team authorization, CSRF/origin checks, bounded size,
rate limits, idempotency and stale-revision rejection. Pair participation marks in one transaction.
Record immutable actor/team/action/time/result audit events without raw credentials or private
data in public logs. Define correction, backup/restore and retention behavior before enabling writes.

## 5. Private backend and refresh boundary

Vercel may provide a thin backend-for-frontend. A reliably available trusted private service
must own durable state, transactions and audit. Do not use a Function's local files as a database,
expose SQLite, open a desktop DB port or improvise a public tunnel. Connectivity, service hosting,
durable command transport and operating ownership need an explicit design decision; no new hosted
database is authorized by this plan.

Future refresh controls submit an allowlisted job to that private runner. APA login stays on
the operator machine. The web app never receives APA passwords, bearer tokens or browser cookies.
Support overlap prevention, progress, waiting-for-operator-login, timeouts and safe retries.
Publish only validated snapshots. Failed ingestion/build/upload must retain the last good site
and show separate local-refresh/hosted-release status. Do not connect the existing BAT files now.

## 6. Implementation order and acceptance

1. Select provider/account model; configure synthetic test identities and denied-by-default roles.
2. Implement sign-in, sign-out and protected reads using synthetic teams only.
3. Test anonymous, wrong-team, revoked, expired and forged-role access on all routes/aliases.
4. Design the private service's persistence/connectivity/audit and obtain authority before writes.
5. Add one admin capability at a time with transaction, revision and replay tests.
6. Separately authorize real snapshot export/integration; verify source binding and leak prevention.
7. Separately authorize refresh controls after private runner failure/recovery tests pass.

Required negative tests: cross-team ID substitution, direct asset/API access, CSRF, duplicate
commands, concurrent stale edits, removed players, unavailable operator machine, failed login,
partial ingestion, failed publication and rollback. Use physical iPad testing for final usability;
automated WebKit is evidence, not a claim of physical-device acceptance.

No Phase 2 feature is installed, provisioned or enabled by this document.
