# Security Review — Ultimate Coach Web Platform (codex/web-platform-v1)

Reviewed: 2026-10-21  
Branch: `codex/web-platform-v1`  
Reviewer: Claude (automated + manual review of all files in scope)

---

## Scope

All files under `apps/ultimate-coach-web/` introduced or modified on this branch, covering:

- Database-backed authorization (`src/lib/server/authorization.ts`)
- DB layer (`src/lib/db/`)
- Admin system (`src/app/dashboard/admin/`)
- Snapshot pipeline (`src/lib/server/historical-snapshot.ts`, `snapshot-crypto.ts`)
- Configuration (`next.config.ts`, `.env.example`, `.gitignore`)

Not in scope: Match Night engine (`src/lib/engine/`), Clerk SDK internals, Turso server infrastructure.

---

## Findings

### PASS — Authorization model

| Check | Result |
|-------|--------|
| No `UC_AUTHORIZED_EMAILS` in any source file | PASS |
| Role check is server-side only; role value never in JS bundle | PASS |
| `/dashboard/admin` returns `notFound()` for non-ADMIN (404, not redirect) | PASS |
| `historicalAccess()` gated behind `authConfigured()` guard | PASS |
| Bootstrap seed replaced on first Clerk sign-in (id `bootstrap-seed` → real `user_xxx`) | PASS |
| New users default to `PENDING`; no access until admin approves | PASS |
| All DB and auth modules have `import 'server-only'` | PASS |
| Clerk session freshness verified via live provider read (not JWT cache alone) | PASS |
| `clerkUser.banned` and `clerkUser.locked` checked on every request | PASS |

### PASS — Snapshot pipeline

| Check | Result |
|-------|--------|
| `historical.enc.json` removed from git tracking (`git rm --cached`) | PASS |
| `private-snapshots/` excluded from git in `.gitignore` | PASS |
| `UC_SNAPSHOT_URL` env var used for storage; never forwarded to browser | PASS |
| AES-256-GCM key (32 bytes) validated at startup in production | PASS |
| Per-request key length check before decryption | PASS |
| Schema, mode, and label validation before returning snapshot | PASS |
| `cache: 'no-store'` on snapshot fetch | PASS |

### PASS — Admin system

| Check | Result |
|-------|--------|
| All server actions call `requireAdmin()` before mutating | PASS |
| `requireAdmin()` calls `historicalAccess()` → throws if not ADMIN | PASS |
| Audit log written before action completion on every mutation | PASS |
| Admin sign-in recorded in both `audit_log` and `user_activity` | PASS |
| Snapshot view recorded in `user_activity` | PASS |
| `revalidatePath('/dashboard/admin')` called after each mutation | PASS |
| `dynamic = 'force-dynamic'; revalidate = 0` on admin page | PASS |

### PASS — HTTP security headers

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `no-referrer` |
| `X-Frame-Options` | `DENY` |
| `Content-Security-Policy` | `frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'` |
| `X-Robots-Tag` | `noindex, nofollow` |
| `Cache-Control` on `/dashboard/*` | `private, no-store, max-age=0` |
| `poweredByHeader: false` | Enabled |

### PASS — Secrets hygiene

| Check | Result |
|-------|--------|
| No credentials in source files | PASS |
| `.env*` excluded by `.gitignore` (except `.env.example`) | PASS |
| `.env.example` contains no real values | PASS |
| `UC_AUTHORIZED_EMAILS` removed from `.env.example` with note | PASS |
| `probability_publication` remains FORBIDDEN (no probability model) | PASS — not present |

---

## Open items (deferred, not blocking merge of admin system)

### Phase 2: git history rewrite

`historical.enc.json` was removed from git tracking with `git rm --cached` (Phase 1). The file's history still exists in git objects. Phase 2 removes it from all history with `git filter-repo --path private-snapshots/historical.enc.json --invert-paths`. This requires Paul's explicit authorization and a coordinated push to all branches; deferred pending that authorization.

**Risk until Phase 2:** Anyone with full repo clone access can recover the encrypted file from git objects. The file is encrypted (AES-256-GCM). The key is never in the repo. Practical risk is low; completing Phase 2 is still recommended.

### Rate limiting

Admin actions are not rate-limited at the application level. Recommendation: Vercel WAF + a DB-backed rate table (one row per actor_id per action per minute). Not yet implemented. Mitigation: admin page is 404 to non-admins; only approved admins can reach the actions.

### `user_activity` table — `sign_in` logging granularity

Sign-in is currently logged on every authorized request (each server-rendered page load). Consider throttling to once per Clerk session to avoid activity table bloat. Not a security issue.

---

## Merge readiness checklist

**DO NOT open a PR until all items are checked by Paul.**

### Implementation complete
- [x] DB schema: `users`, `audit_log`, `user_activity`, `snapshots`
- [x] DB client (Turso HTTP, no extra npm dependency)
- [x] DB migration script (`src/lib/db/migrate.ts`)
- [x] `authorization.ts` — `UC_AUTHORIZED_EMAILS` removed, DB role lookup, bootstrap activation
- [x] `historical-snapshot.ts` — URL-based storage, per-request key check
- [x] `next.config.ts` — startup AES key validation, stale `outputFileTracingIncludes` removed
- [x] `/dashboard/admin` page — 404 for non-ADMIN, pending queue, all-users table, audit log
- [x] Admin server actions — approve, deny, promote, demote, suspend, remove
- [x] Audit logging — all role mutations write to `audit_log` before returning
- [x] Activity logging — sign-in, admin sign-in, snapshot view written to `user_activity`
- [x] `private-snapshots/historical.enc.json` removed from git tracking
- [x] `.gitignore` — `private-snapshots/` fully excluded
- [x] `.env.example` updated

### Paul's manual steps before deployment

- [ ] Create Turso database (free tier: `turso db create ultimate-coach`)
- [ ] Run migration: `TURSO_DATABASE_URL=libsql://... TURSO_AUTH_TOKEN=... node --experimental-strip-types src/lib/db/migrate.ts`
- [ ] Confirm seed row exists: `SELECT * FROM users WHERE id = 'bootstrap-seed';`
- [ ] Upload encrypted snapshot to Vercel Blob / R2 / S3; copy URL to `UC_SNAPSHOT_URL`
- [ ] Set all Vercel env vars: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `UC_SNAPSHOT_KEY`, `UC_SNAPSHOT_URL`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`
- [ ] Deploy to preview; sign in as `ssands5@comcast.net`
- [ ] Verify bootstrap activates (check DB: `SELECT id, role FROM users WHERE email = 'ssands5@comcast.net';` — id should be `user_xxx`, not `bootstrap-seed`)
- [ ] Visit `/dashboard/admin` — confirm it loads and shows admin UI
- [ ] Visit `/dashboard` — confirm snapshot loads and displays correctly
- [ ] Invite a second user; verify they appear as PENDING; approve them; confirm they can access dashboard
- [ ] Verify a non-authed request to `/dashboard/admin` returns 404

### Security sign-off

- [ ] Paul confirms no probability model, ranking model, or prediction output is present
- [ ] Paul confirms `UC_SNAPSHOT_KEY` and `TURSO_AUTH_TOKEN` are only in Vercel env vars, not committed anywhere
- [ ] Paul authorizes Phase 2 git history rewrite (or explicitly defers it)
- [ ] Paul's own browser test passes (UAT gate)

**Only after all boxes above are checked: open PR from `codex/web-platform-v1` → `main`.**
