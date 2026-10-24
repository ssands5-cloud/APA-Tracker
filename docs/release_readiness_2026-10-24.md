# APA Tracker — Release Readiness Handoff

**Date:** 2026-10-24  
**Branch:** `codex/web-platform-v1`  
**HEAD:** `43c3135`  
**Test run:** 92 collected · 73 passed · 19 failed  

---

## Verdicts

| Gate | Status |
|---|---|
| Safe to test (Paul UAT) | **PARTIAL** — auth verified; Vercel must be fixed first |
| Safe to merge to web-platform | **BLOCKED** — 19 pre-existing failures must be triaged |
| Safe to merge to main | **BLOCKED** — Vercel broken; Safari regression from PR #87 already on main |
| Auth / security gates | **VERIFIED PASS** |

---

## PR & Branch Status

| PR / Branch | State | Notes |
|---|---|---|
| `#87 codex/ux-match-night` | MERGED → main | Source of Safari/iPhone layout regression |
| `#88 codex/captain-product-v1` | OPEN DRAFT | Not reviewed this session |
| `#89 codex/web-platform-v1` | OPEN · CI FAILING | 19 pre-existing failures; Vercel config broken |
| **Middleware rename** | DONE | `proxy.ts → middleware.ts` committed in `21f291f` |
| **Auth verification** | PASS | All server-side role checks verified |
| **CI** | 19 FAILURES | All pre-existing; Claude's 3 commits introduced zero new failures |
| **Vercel** | FAILING | `UC_SNAPSHOT_KEY` env var must decode to exactly 32 bytes |

---

## Test Failure Matrix

All 19 failures are **FAILS_ONLY_ON_PR89** — all 4 test files were added in feature branches after main's current HEAD and do not exist on main.

| Test File | Failures | Root Cause |
|---|---|---|
| `test_export_excel_ultimate_coach` | 7 | `TypeError` in `excel_war_room.py:2362` — Direct Games read as str, compared to int |
| `test_historical_dashboard_snapshot` | 7 | `BoundaryRefused` instead of `ValueError` — `tmp_path` is outside repo root |
| `test_match_night` | 3 | Safari/iPhone `#next-send` at y=911 on 844px screen (regression from PR #87) |
| `test_ultimate_coach_browser` | 2 | Duplicate `<p class="muted">` in full-roster mode (regression from PR #87) |

---

## Findings Ranked by Severity

### HIGH — Safari/iPhone Layout Regression
- **Files:** `ui/match_night.py`, `ui/ultimate_coach.py`
- **Tests:** `test_match_night` (3), `test_ultimate_coach_browser` (2)
- **Source:** PR #87 (now merged to main)
- `#next-send` renders at y=911.8 on an 844px viewport, or y=−43.67 (above viewport). Full-roster mode shows wrong evidence summary text and a duplicate `<p class="muted">` element.
- **Fix required before merge to main.**

### MEDIUM — Excel Direct Games TypeError
- **File:** `ui/excel_war_room.py` lines 2352, 2362
- **Tests:** `test_export_excel_ultimate_coach` (7)
- `_deeper_records_worst()` compares `rec['Direct Games']` (string from sheet read) to int.
- **Fix:** `int(rec['Direct Games'] or 0)` at both locations.
- Does NOT affect the web app.

### MEDIUM — Vercel UC_SNAPSHOT_KEY Configuration
- **Not a code fix** — Paul must set `UC_SNAPSHOT_KEY` in Vercel project settings to a value that decodes to exactly 32 bytes.
- Build fails at next.config.ts validation.

### LOW — Security Test tmp_path Mismatch (Test-Only)
- **File:** `tests/test_historical_dashboard_snapshot.py`
- `write_snapshot()` calls `check_no_links()` first; `tmp_path` is outside repo root → `BoundaryRefused` fires before the forbidden-field check.
- Production security logic is correct. Tests should use `ROOT / 'tmp' / ...` instead of pytest's `tmp_path`.

---

## Authorization Verification (All Passed)

| Component | Check | Result |
|---|---|---|
| Admin page (`dashboard/admin/page.tsx`) | `historicalAccess()` → `notFound()` if not ADMIN | ✓ 404 not redirect |
| Admin server actions (`actions.ts`) | All 6 actions call `requireAdmin()` | ✓ Unauthorized throw |
| Authorization module (`authorization.ts`) | Fresh provider reads; DB role check | ✓ No JWT-only bypass |
| Middleware (`src/middleware.ts`) | Correctly named; matcher covers `/dashboard` | ✓ Rename committed |
| API routes | None exist | ✓ No attack surface |
| Role in JS bundle | Not shipped to client | ✓ Server-side only |
| Snapshot encryption | AES-256-GCM; 32-byte key validated at startup | ✓ |
| `.gitignore` | `.env.txt`, `token.txt`, `token.xlsx` excluded | ✓ Committed in `ada1f4c` |

---

## What Was Verified This Session

- Full test run on PR #89 HEAD: 92 collected, 73 passed, 19 failed
- Main baseline: `test_ultimate_coach_browser.py` (only test file on main) — 1 test PASSED
- Confirmed zero new failures from Claude's 3 commits (`ada1f4c`, `21f291f`, `43c3135`)
- Root cause identified for all 4 failure groups
- All admin authorization paths inspected

## What Remains Unverified

- PR #88 (`codex/captain-product-v1`) — not reviewed
- End-to-end Playwright against a live dev server
- Paul's UAT on his own Windows browser (the real gate per project memory)
- Vercel deployment (blocked by config — Paul must fix)

---

## Recommended Next Actions

1. **Fix Safari layout regression** in `ui/match_night.py` — unblocks test_match_night and test_ultimate_coach_browser test groups
2. **Fix Vercel UC_SNAPSHOT_KEY** — Paul sets correct 32-byte base64 key in Vercel project settings
3. **Cast Direct Games** — `int(rec['Direct Games'] or 0)` at `excel_war_room.py:2352,2362` — unblocks Excel test group
4. **Fix security test paths** — use `ROOT / 'tmp' / ...` instead of pytest `tmp_path` in `test_historical_dashboard_snapshot.py`
5. **Paul UAT** — after Vercel fix, test decision-first dashboard on Windows browser

---

*Generated 2026-10-24 · branch codex/web-platform-v1 · HEAD 43c3135*
