# Architect Recommendations
**Date:** 2026-10-25  
**Role:** Repository Architect (Claude)  
**Scope:** Verified findings only. High-value only.

---

## RISK: Production database still on C: (Storage Migration Phase 1 not done)

**Severity:** High  
**File:** `data/apa_tracker.db` (C: drive, legacy location)

The storage migration Phase 0 created `D:\APA-Tracker-Data\` and `scripts/paths.py`, but no files have moved yet. The active production database is still at `data/apa_tracker.db` on C:, not at `D:\APA-Tracker-Data\databases\apa_tracker.db`.

Scripts that have not been updated to use `paths.py` still read `PROJECT_ROOT / "data" / "apa_tracker.db"`. This means:
- Phase 1 migration hasn't happened
- `APA_DB` in `scripts/paths.py` points to D: but the actual DB is on C:
- Running any updated script against the D: path will find an empty/missing database

**Verified:** `data/` exists at repo root with 5.4 MB of database files including backups.

**Recommendation:** Before Phase 1 can proceed, audit which scripts still use the `data/` path and whether `apa_tracker.db` on C: is the active production copy. Do not move files until this is confirmed. Candidate checklist is in `storage-migration-plan.md`.

---

## RISK: 37 stale worktrees consuming significant disk

**Severity:** Medium  
**Locations:** `.worktrees/` (19 internal) + sibling `APA-Tracker-*` directories (18)

Internal worktrees still present:
`captain-decision-first`, `captain-product-v1`, `claude-confidence`, `codex-candidate-validation`, `fix-excel-direct-games-type`, `fix-match-night-selector-tests`, `fix-safari-next-send`, `fix-safari-next-send-dom-compat`, `fix-snapshot-security-test-paths`, `fix-vercel-typescript-build`, `fix-web-typescript-compat`, `gh-pages`, `phase1-captain-clarity`, `pr83`, `release-candidate-verification`, `release-validation`, `scheduled-refresh-task`, `ux-match-night`

Prior cleanup report estimated ~22 GB total recoverable. Three require Paul's confirmation before deletion (noted in `D:\APA-Tracker-Archive\Cleanup-Logs\cleanup-report.md`).

**Recommendation:** Complete the cleanup mission. Safe removals (~633 MB) can proceed now. The three confirmation items need Paul's direct go-ahead.

---

## RISK: Foreign package pollutes file searches

**Severity:** Medium  
**Location:** `.github/skills/sports-skills-main/` (untracked, 116 Python files)

This is a `sports_skills` Python package dropped by GPT/Jeeves as untracked content. It will corrupt any AI agent's file-count analysis, grep results, or import tracing unless explicitly excluded.

**Recommendation:** Either `.gitignore` this directory or have Paul confirm it can be deleted. It is untracked so deletion has no git consequences. Until then, all agents must use `--exclude-dir=.github/skills/sports-skills-main` in searches.

---

## FINDING: `build_captain_first_edge.py` may be superseded

**Severity:** Low  
**Files:** `scripts/build_captain_first_edge.py` vs `scripts/build_captains_edge.py`

Both scripts exist and both have test files. `captain_first_edge` appears to be a "captain-first" deployment strategy variant of the standard captains edge builder. The distinction may be intentional — verify whether both are actively used in `run_game_night.py` or if one is dead.

**Recommendation:** Check `run_game_night.py` for which builder is called. If only one is used, flag the other for archival.

---

## FINDING: 5 analytics modules with no direct test file

**Severity:** Low  
These are tested indirectly and have lower risk:

| Module | Risk |
|--------|------|
| `analytics/captains_edge.py` | Low — covered by summary and build tests |
| `analytics/matchup_insights.py` | Medium — unclear coverage |
| `analytics/player_stats.py` | Low — covered by scaffolding fixture test |
| `analytics/ultimate_coach_confidence.py` | Medium — covered by `test_confidence_levels.py` |
| `analytics/ultimate_coach_payload.py` | Low — covered by cockpit/browser tests |

**Recommendation:** Add direct unit tests for `matchup_insights.py` and `ultimate_coach_confidence.py` — both are data-path functions, not browser-only, and a regression there would be silent under current coverage.

---

## FINDING: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is intentional and safe

**Severity:** None  
`auth-config.ts` uses `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` to detect whether Clerk is configured. This is expected — Clerk's publishable key is designed to be public (it's a pk_ prefixed key, not a secret). **No action needed.**

---

## FINDING: No client-side role checks detected

**Severity:** None (good)  
Scan of all `components/*.tsx` found zero calls to `historicalAccess`, `getUser`, or role-string comparisons. The role gate is clean. **No action needed.**

---

## FINDING: `tmp/` is 340 MB and growing

**Severity:** Low  
`tmp/` is correctly gitignored but is 340 MB of pytest/UAT scratch output on C:. It will continue growing with each test cycle.

**Recommendation:** Add `tmp/` cleanup to the weekly scheduler or to `run_game_night.py` as a pre-run step. One-liner: `shutil.rmtree("tmp", ignore_errors=True)` before building.

---

## DOCUMENTATION: Add TEST_MAP.md to AI_HANDOFF.md authoritative table

`docs/TEST_MAP.md` was created this session. It should be registered in the authoritative files table.

**Status:** Patched in this commit.

---

## Summary table

| Finding | Severity | Action |
|---------|----------|--------|
| Production DB still on C: (Phase 1 not done) | **High** | Audit before moving; see storage-migration-plan.md |
| 37 stale worktrees | **Medium** | Complete cleanup mission per cleanup-report.md |
| Foreign package in .github/skills/sports-skills-main/ | **Medium** | Gitignore or delete; exclude from all searches now |
| build_captain_first_edge vs build_captains_edge | Low | Verify which is active in run_game_night.py |
| matchup_insights.py + ultimate_coach_confidence.py untested | Low | Add direct unit tests |
| NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY | None | Intentional, safe |
| No client-side role checks | None | Clean — no action |
| tmp/ growing | Low | Add cleanup to scheduler or game-night script |
