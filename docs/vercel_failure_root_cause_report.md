# Vercel Failure Root Cause Report

**Scope:** APA Tracker Vercel deployments through 24 October 2026.  This report uses the retained Vercel build logs and local source history. It does not infer secret values or deployment settings that the logs do not expose.

## Finding

The first retained TypeScript deployment failure on `codex/web-platform-v1` was introduced by commit `3f4b6af` (`feat(web-platform): database-backed admin system, auth refactor, snapshot migration Phase 1`). It is a deployment-blocking compile failure, not an `UC_SNAPSHOT_KEY` failure.

The subsequent Match Night release candidate inherited those failures. A later candidate also contained a JSX syntax error. Both are corrected by this branch's commit `a9472f3`.

## Deployment timeline

| Date (MDT) | Commit / branch | Deployment | Result | Evidence |
| --- | --- | --- | --- | --- |
| Oct 20, 11:20 PM | production | `6oJyTJyAxfMEGqYjdAtUrFeoVC6n` | Ready | Last confirmed production-ready deployment |
| Oct 21, 7:18 PM | `82c3564` / `codex/captain-display-cleanup` | preview | Ready | Last confirmed git-backed preview before the web-platform change |
| Oct 21, 7:39 PM | `3f4b6af` / `codex/web-platform-v1` | `5WJvANekSgGALxqJRbdtLbbNZDXi` | Failed | First retained web-platform TypeScript failure |
| Later | `b5e3213` / `codex/ux-match-night` | `5irSpHCMAEA6tZBHYhv9reQ9eToZ` | Failed | Same inherited errors plus the admin action enum error |

`82c3564..3f4b6af` contains one commit: `3f4b6af`. `next.config.ts` did not change in that range. The deployment records show Preview deployments; there is no evidence of a deployment-target change.

The repository's `main` branch does not contain `apps/ultimate-coach-web`, so these Next.js TypeScript errors exist on the release-candidate branches, not on `main`.

## Exact Vercel TypeScript errors

### First failure: `3f4b6af`

- `src/lib/db/audit.ts(43,10)` — unsafe `Row[]` to `AuditEntry[]` conversion (TS2352).
- `src/lib/db/users.ts(19,10)`, `(24,10)`, `(31,10)` — unsafe `Row`/`Row[]` to `User`/`User[]` conversions (TS2352).
- `src/lib/server/historical-snapshot.ts(32,34)` — `unknown` passed where the encrypted snapshot frame was expected (TS2345).

### Inherited later failure: `b5e3213`

In addition to the preceding conversions:

- `src/lib/server/authorization.ts(72,36)` — `"admin_sign_in"` not assignable to `AdminAction`.

### Later local release-candidate failure

- `src/components/dashboard-pages.tsx` — typographic quotation marks in a JavaScript fallback string caused `TS1127` / `TS1381` parsing errors.

## Classification

| Failure | Classification | Production effect | Corrective action |
| --- | --- | --- | --- |
| TypeScript/JSX errors above | Production-impacting build blocker | Vercel cannot deploy the candidate | `a9472f3` fixes the errors; verify its Vercel build |
| `UC_SNAPSHOT_KEY` absent | Configuration-only runtime dependency | A deployed protected dashboard cannot decrypt a snapshot; build still succeeds | Set a base64 AES-256 key (32 decoded bytes) as a Vercel Secret in the intended environments |
| `UC_SNAPSHOT_URL` absent | Configuration-only runtime dependency | No external encrypted snapshot is available to the deployment | Configure the encrypted snapshot URL alongside its key |
| Turso runtime variables absent | Configuration-only runtime dependency | Database-backed authorization/activity functions cannot operate at runtime | Configure the required production Turso values before beta |
| Snapshot test-path failures | Test-only | CI red; production boundary guard behaves correctly | Update test fixtures to write only inside ignored repository `tmp/` paths; do not weaken the guard |
| Excel `Direct Games` string comparison | Test and export robustness defect | Workbook export can crash on nonnumeric sheet cells | Isolated in PR #92 |
| Safari `#next-send` off-screen | Production UI regression | iPhone captains cannot reach the recommended move without scrolling | Isolated in PR #90 |
| Stale page/test assertions | Test-only | CI red; no evidence of a production deploy failure | Update expectations after intentional product changes |

## What the logs prove about `UC_SNAPSHOT_KEY`

The build output says `UC_SNAPSHOT_KEY is not set — snapshot decryption will fail`, but compilation, TypeScript checking, and page generation complete when the key is absent. The failed Vercel logs instead stop on the TypeScript errors above. Therefore the missing key is a real runtime readiness requirement, but it is **not** the documented cause of the failed deployments.

## Minimum release sequence

1. Merge/rebase the build correction after Vercel verifies `a9472f3`.
2. Merge the isolated Safari fix (PR #90) after the targeted phone coverage passes in CI.
3. Merge the Excel robustness repair (PR #92) after its workbook test expectation is updated separately or verified against the current workbook contract.
4. Correct snapshot tests without relaxing path-security enforcement.
5. Add Vercel Preview and Production configuration for `UC_SNAPSHOT_KEY`, `UC_SNAPSHOT_URL`, and required database values; then exercise a real authorized historical-dashboard request.
6. Run the full test suite, build a Preview deployment, and perform iPhone/Safari and authorized-user smoke checks before an invite-only beta.
