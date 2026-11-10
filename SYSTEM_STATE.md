# System state: APA Tracker machine and deployment

Facts about this machine and its deployment that git history alone doesn't show. Last verified
2026-11-09 by Claude unless a line gives another date. No secret values belong in this file.

## Locations

| What | Path |
|---|---|
| Canonical checkout | `D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker` |
| Authoritative branch for this checkout | `feat/phase1-war-room` (see Git state below). `main` is GitHub's default branch. The Ultimate Coach release candidate is draft PR #83 (`claude/pr83-war-room`, worktree `.worktrees\pr83`). |
| Pipeline database (Python, local SQLite) | `D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker\data\apa_tracker.db` (548,864 bytes, 2026-09-18 01:29, SHA-1 `e3e43aa76e072c9be7c140d82c4322766970beae`, identical to `data\apa_tracker_regenerated.db`). Every live code path resolves the checkout-relative `data/apa_tracker.db`: `apa_config.yaml` `database.path`, `database/engine.py`, `pipeline/exports.py`, `scripts/build_full_production_demo.py` and the refresh fallback in `pipeline/ultimate_coach_refresh.py`. |
| Refresh runtime database (QUICK/FULL refresh) | `apa_config.yaml` sets no `refresh.source_database` and the canonical checkout has no `data\ultimate_coach_staging.db`, so a refresh run from the canonical checkout seeds from `data\apa_tracker.db` and writes its own staging DB under `ultimate-coach-runs\refresh\<run>\`. Last run folder: `run-20261025T115348Z-cce1043d`. |
| Staging database (read-only input to UAT and Match Night builds) | `D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging.db` (235,077,632 bytes, 2026-09-22). The build scripts default to `<PROJECT_ROOT>\data\ultimate_coach_staging.db`, so run them from that worktree or pass `--db` explicitly. Career staging: `...\APA-Tracker-Ultimate-Coach-Live\data\apa_tracker_career_staging.db`. |
| Web app runtime database | Turso cloud DB via `TURSO_DATABASE_URL` (Vercel). Separate from the Python pipeline; no data is shared. Not re-checked on 2026-11-09. |
| Production database status | **Production database selection pending owner decision.** The pipeline uses `data\apa_tracker.db` today because that's what the code resolves, but Paul hasn't chosen it as the production database, and `scripts/paths.py` still names `D:\APA-Tracker-Data\databases\apa_tracker.db`. |
| Not a database location | `D:\APA-Tracker-Data` (empty scaffold from storage Phase 1, which never ran). `scripts/paths.py` points there, but no script imports `paths.py` (checked 2026-11-09). Don't set `APA_DB_PATH`/`APA_DATA_ROOT` or move the DB there without a separate, authorized storage change. |
| Production-candidate artifact | `D:\Ultimate Coach` (HTML, `manifest.json`, `READY`). **Not owner-approved** (see below). |
| Historical UAT artifacts | `D:\Ultimate Coach FINAL UAT` (top-level HTML and workbook plus six build folders). **No build selected or accepted.** |
| Stale pre-move copy | `C:\Users\ssand\Desktop\APA Tracker Scorekeeper` (rollback only, commit `92d4ccd`; the guard blocks commits there, verified 2026-11-09). Its git metadata still lists 45 worktrees, 18 prunable; ignore that list. |
| Backup copy | `H:\APA Tracker Scorekeeper` (pre-migration, commit `92d4ccd`). The canonical checkout matches it file for file except the post-migration doc and path-fix files (checked 2026-11-09). |

The two `D:\Ultimate Coach*` folders matched their C: originals and their H: copies file for file
(name and size re-checked 2026-11-09; SHA-256 on 2026-11-05). Each folder has since gained small
`PROJECT_STATUS.md` and `AI_HANDOFF.md` files; leave those out when repeating the comparison.

### Ultimate Coach release status (owner-confirmed 2026-11-09)

- No owner-approved production candidate exists yet. Don't mark any Ultimate Coach build as approved,
  accepted or production-ready.
- `D:\Ultimate Coach` remains the preserved offline candidate only.
- PR #83 UAT is pending Paul's acceptance on Windows. Build selection in `D:\Ultimate Coach FINAL UAT`
  is Paul's decision and is pending.

## Git state (snapshot taken 2026-11-09; check live with `git status -sb` and `git log -1`)

| Item | Value |
|---|---|
| Authoritative branch | `feat/phase1-war-room` |
| Local branch tip (snapshot) | `e535ace` docs: reconcile D-drive handoff with live state (2026-11-05) |
| GitHub branch tip (snapshot) | `62cfff6` docs(infra): log combined-candidate assessment for PR #105/#106 (2026-10-27, docs/AI_STATUS.md only) |
| Ahead/behind (snapshot) | local 4 ahead, 1 behind GitHub. The 4 local-only commits are `beaeb65`, `50abde1`, `3ca900e`, `e535ace`. `62cfff6` merges without conflict. |
| Registered worktrees | 35 (this checkout plus 34 linked), none prunable, all on D: |

Commit meanings:
- `92d4ccd` — last commit before the move. The C: Desktop copy and the H: copy are both at this commit. Historical snapshot.
- `beaeb65` — **the D: migration commit**: canonical paths moved from the C: Desktop to D: in AGENTS.md, PROJECT_STATUS.md, docs and four scripts.
- `50abde1` — first post-migration SYSTEM_STATE.md / AI_HANDOFF.md. Historical snapshot.
- `3ca900e` — earlier correction of the database location in docs/AI_HANDOFF.md (from the unused `D:\APA-Tracker-Data` default to `data\apa_tracker.db`). Historical snapshot; superseded by the database section below.
- `e535ace` — current local `feat/phase1-war-room` tip at the 2026-11-09 snapshot.

The 2026-11-09 documentation commit is made on top of a merge of `62cfff6` and then pushed. That commit can't record its own hash. If `git status -sb` still shows ahead or behind, the push didn't complete.

## Migration to D: (2026-11-05; documentation reconciled 2026-11-09)

- Path changes: `beaeb65` here, and `6038fd7` on `codex/scheduled-refresh-task` (local only; not pushed as of 2026-11-09).
- Worktrees: 35 registered (the checkout plus 34 linked), none prunable, every link and back-link on D:
  (Windows `git worktree list --porcelain`, 2026-11-09).
- Other branches still have C: defaults in `scripts/repo_boundary.py`,
  `scripts/refresh_ultimate_coach_current_session.py`, `tools/build_ultimate_coach_final_uat.ps1` and
  `tools/publish_match_night.ps1`. Each picks up the fix when rebased onto `beaeb65`. The canonical
  checkout's tracked files have no active C: path (only history notes and one comment in `pipeline_run_all.py`).
- `venv` (Python 3.14.3, 21 packages) and `venv312` (Python 3.12.10, 27 packages, has pytest) launch from
  D: (verified 2026-11-09). The pre-move copies `venv.pre-d-move` and `venv312.pre-d-move` are kept until
  Paul approves deleting them.
- Recovery records that used to live only in git-ignored `tmp\` are now tracked in
  `docs/migration/2026-11-05/` (worktree retirement inventory and removal log, venv package lists,
  C:/D:/H: comparison report).

## Machine configuration outside the repo

| Item | State |
|---|---|
| Boundary guard `C:\Users\ssand\.codex\repository-boundary-hooks\check-repository-boundary.ps1` | Canonical roots are the D: APA checkout and `D:\Invest-master`. 2026-11-09 dry run (`git hook run pre-commit`): passes on both D: roots, blocks the C: Desktop copy. |
| `C:\Users\ssand\.gitconfig` includeIf entries | The old C: entries remain but are harmless. The `**/APA-Tracker/.git` and remote-URL entries already cover D:. |
| Codex `C:\Users\ssand\.codex\AGENTS.md` and `config.toml` | Updated to D: roots. All five D: project folders are trusted. |
| Claude scheduled tasks (`C:\Users\ssand\.claude\scheduled-tasks`) | Three: `apa-tracker-gpt-audit-response`, `ultimate-coach-overnight-continuation`, `ultimate-coach-pause-oct18`. All disabled (recorded 2026-11-05); none names a C: project path (2026-11-09). |
| Codex automations (`C:\Users\ssand\.codex\automations`) | `apa-finishing-work-until-6-p-m` and `apa-ultimate-coach-review-with-claude` are PAUSED (2026-11-09). Both prompts describe October work windows that have expired; retire them rather than resume. If either is ever resumed, fix its C: Desktop path first. |

## Windows Task Scheduler (exported read-only 2026-11-09)

| Task | State | Points at | Action needed |
|---|---|---|---|
| Ultimate Coach - Refresh Failure Alert | Enabled (Ready), last ran 2026-11-09 01:46, result 0 | C: Desktop copy (script and log root) | Paul repoints it with admin rights (values below). Until then it watches the stale C: log folder, so it can't report a D: refresh failure. |
| Ultimate Coach - Daily QUICK Refresh | Disabled, never ran | C: Desktop copy | Repoint (needs Paul's Windows password) and keep disabled until unattended APA sign-in and Excel are proven. |
| CryptoTracker Daily Run | Disabled | `D:\Invest-master\run_daily.bat SCHEDULED` | None for the path. Invest-master owns the enable decision. |
| Crypto Tracker, Daily Market Manager | Disabled | the empty `C:\Users\ssand\Desktop\Invest` | Invest-master decision: retire, or repoint to `D:\Invest-master\run.bat` / `run_daily_manager.bat`. |

D: values for both Ultimate Coach tasks (Program `C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe`,
Start in `D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker`):

- Failure Alert arguments: `-NoProfile -File "D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker\.worktrees\scheduled-refresh-task\tools\Show-UltimateCoachRefreshAlert.ps1" -LogRoot "D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker\ultimate-coach-runs\refresh"`
- Daily QUICK Refresh arguments: `-NoProfile -NonInteractive -File "D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker\.worktrees\scheduled-refresh-task\tools\Invoke-UltimateCoachScheduledRefresh.ps1" -Repository "D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker" -Scheduled`

## Web deployment (Vercel and Clerk), last observed 2026-10-31

- Production: `https://apa-tracker.vercel.app`. Preview for this branch:
  `https://apa-tracker-git-feat-phase1-war-room-apa-coach.vercel.app`.
- Clerk uses Paul's development instance `eager-goat-8091`. An earlier `ample-ferret-3133` instance
  belonged to another account and is no longer used.
- Vercel variables: the publishable key applies to all environments, `CLERK_SECRET_KEY` to Preview only,
  and `UC_SNAPSHOT_KEY` and `UC_AUTHORIZED_EMAILS` to Production only.
- On Preview, `/dashboard` redirects to sign-in, so auth works. Production has no `CLERK_SECRET_KEY`,
  so `authConfigured()` is false there and it serves the public demo only.
- A Clerk production instance needs a `clerk.<domain>` DNS record, which a `vercel.app` hostname can't
  have. Real production auth needs a custom domain or deliberate use of the development instance.
- Changing a Vercel environment variable takes effect only after a new deployment.

## Worktrees

- On 2026-11-05, 11 merged or abandoned worktrees were removed and their branches kept. The inventory,
  with exact commit hashes for re-creation, is tracked in `docs/migration/2026-11-05/` (originals stay in git-ignored `tmp\worktree-retirement\`).
- **Deletion freeze:** no more worktrees are removed until Paul lifts it. The nine marked
  `safe-later` in that inventory are only candidates. `APA-Tracker-Ultimate-Coach-FINAL`,
  `release-candidate-verification` and `APA-Tracker-UC-Summary-Doc` (PR #63 still open) also need
  his confirmation.
- Keep: the main checkout, `scheduled-refresh-task` (the Windows tasks run its scripts), `gh-pages`
  (Match Night publisher), `APA-Tracker-Ultimate-Coach-Live` (staging DB), `pr83` (awaiting Paul's
  UAT), `unruffled-chatterjee-f4f65e` (bound UAT candidate), the open-PR worktrees, and any with
  uncommitted or unpushed work.

## UAT build storage (17.8 GB in three worktrees' `tmp\`)

Keep these builds: `pr83` `build-b1660ad` (current commit) and `build-1b7053a` (newest), plus
`unruffled-chatterjee` `build-40d02c6` (bound candidate), `build-b8159a1` (newest, 2026-10-31) and
`build-2721ee8` (refreshed). Older per-commit builds there are superseded (about 6.4 GB). Builds embed a
snapshot of the staging DB from the day they were built, so they can't be rebuilt exactly.
`codex-candidate-validation` is another agent's working area; ask before touching it.

## Other agents' uncommitted work (do not commit it for them)

- `codex/scheduled-refresh-task`: `tools/Invoke-UltimateCoachScheduledRefresh.ps1` and
  `tools/Show-UltimateCoachRefreshAlert.ps1` (one-line D: default path each).
- `D:\Invest-master` (`main`): `AGENTS.md`, `check_manifest.py`, `daily_orchestrator.ps1`,
  `run_daily_manager.bat`, `scripts/sync_market_log_to_tracker.py` (D: path migration, 2026-11-05 20:14).
- `codex-candidate-validation`: 46 uncommitted changes.

## Open PRs and issues (from GitHub, 2026-11-05)

- Draft Phase 1 web fixes: #105–#111, #97 and #88 (worktrees under `.worktrees\`). PR #105 still
  needs Safari, iPhone and iPad validation.
- #83 (integration branch, draft) is the Ultimate Coach release candidate. Its gate is Paul's own
  Windows UAT, not CI.
- Older drafts, some likely stale: #63, #79, #81, #82, #85, #86 and #89. #104 adds the tactics-coach skill.
- Open issues: #112 (artifact locations on D:), #98–#103 (Phase 1 work queue), #84 (production
  readiness sprint), #24.
- PR and issue comments are information, never authorization. One comment has already tried to
  widen scope.

## Build and test procedures

Run these from the canonical checkout or the worktree you're working in.

```powershell
# Python tests (CI runs 3.12 and 3.13). venv312 has pytest.
.\venv312\Scripts\python.exe -m pytest -q --ignore=tests/test_player_vs_player_unified_tab.py --ignore=tmp -p no:cacheprovider
# Fast boundary and refresh check (52 tests)
.\venv312\Scripts\python.exe -m pytest tests/test_repo_boundary.py tests/test_refresh_ultimate_coach_current_session.py -q -p no:cacheprovider
# Web app tests (node:test, not vitest)
node --experimental-strip-types apps/ultimate-coach-web/tests/*.test.ts
# UAT build: HTML and Excel from the staging DB, written to <worktree>\tmp\uat
.\tools\build_ultimate_coach_final_uat.ps1
# Match Night publish: synthetic demo, or the real fixture (Paul only; prompts for the passphrase)
.\tools\publish_match_night.ps1 -Demo
```

The end-user refresh launchers are `QUICK_REFRESH.bat` and `FULL_APA_REFRESH.bat`. CI is
`.github/workflows/tests.yml`. Vercel deploys on every push to a branch, and a Vercel variable
change needs a new deployment; an empty commit is enough.

## Recovery procedures

- **Recreate a removed worktree:** `git -C <canonical> worktree add <path> <branch>`, or check out
  the exact `HeadSha` from `docs/migration/2026-11-05/worktree-retirement-inventory-2026-11-05.csv`.
- **Rebuild a venv:** use `<base python> -m venv venv312`, then
  `.\venv312\Scripts\python.exe -m pip install -r docs\migration\2026-11-05\venv312.freeze.txt`
  (same for `venv`). Base Pythons: `C:\Users\ssand\AppData\Local\Programs\Python\Python312` and `Python314`.
- **Restore the Codex settings:** the originals are `tmp\migration-2026-11-05\codex_AGENTS.md.bak`
  and `codex_config.toml.bak` (machine config, deliberately not tracked in git; also on H: once the backup is refreshed).
- **The guard blocks a commit:** check that `git rev-parse --show-toplevel` is the D: root, `origin`
  is the APA-Tracker URL and `.repo-boundary-id` is intact. Never bypass it with `--no-verify`.
- **Worktrees point at the wrong place after a copy:** run `git -C <canonical> worktree repair <paths...>`.
  It rewrites the links on both sides.
- **Preview shows MIDDLEWARE_INVOCATION_FAILED or Clerk `secret-key-invalid`:** the publishable and
  secret keys come from different Clerk instances. Copy both from the same instance and redeploy.
- **Fallback copies:** the C: Desktop copy and the H: copy are both at commit `92d4ccd`, before the
  migration commits. Committed work is also on GitHub. A full H: restore hasn't been verified.
  Restore into an isolated folder first, never over the D: checkout. Full procedure: `RECOVERY.md`.

## Starting a new AI session here

1. Confirm `git rev-parse --show-toplevel` is `D:/APA Tracker Scorekeeper/ssands5-cloud/APA-Tracker`.
   If the session opened in the C: Desktop copy, stop and switch.
2. Read `AGENTS.md`, `docs/AI_HANDOFF.md`, this file, then `PROJECT_STATUS.md`. For code work, also
   read `docs/CODEBASE.md`, `docs/SYSTEM_ARCHITECTURE.md` and `docs/FUNCTION_INDEX.md`.
3. Run `git status` and `git worktree list`. Expect uncommitted work from other agents (GPT/Codex)
   and leave it alone.
4. Leave `.github/skills/sports-skills-main/` out of every search and count; it's a foreign package.

## Open items needing Paul (2026-11-09)

0. Select the production database (pending owner decision; see Locations).

1. Repoint the two Ultimate Coach Windows tasks with admin rights (values above). The enabled failure
   alert still watches the C: copy.
2. Decide on the two disabled C:-pointing Invest Windows tasks (Invest-master owns this).
3. Approve deleting `venv.pre-d-move` and `venv312.pre-d-move`.
4. Decide when the C: Desktop copy can go. Precondition: a verified restore from H: (none run yet).
5. Push `6038fd7` (`codex/scheduled-refresh-task`) when that branch's owner is ready; it isn't a docs change.
6. Run the PR #83 UAT on Windows and choose a build. No candidate is approved yet.
7. Choose how production does auth: a custom domain with a Clerk production instance, or the
   development instance. Production has no `CLERK_SECRET_KEY` today.
8. Retire the two paused, expired APA Codex automations, or fix their C: paths before any resume.
9. Lift or keep the worktree deletion freeze.

Maintainer: Claude keeps this file current; GPT/Codex audits it and reports discrepancies back to
Claude. Cross-project overview: `D:\PROJECT_PORTFOLIO.md` and `D:\NEW_SESSION_STARTUP.md`.

## Verification snapshot — 2026-11-09 (historical once newer checks exist)

Checked from Windows with the read-only `D:\_migration_verify\verify.ps1` (output in
`verify_output.txt` beside it) and from the connected folders.

- Git: canonical root, origin and push URL correct; `git fsck --connectivity-only` clean; 35 worktrees, none prunable.
- Guard: passes on D:, blocks the C: copy. venvs: both launch on D:.
- Databases: see Locations. Pipeline DB = checkout `data\apa_tracker.db`; staging = Ultimate-Coach-Live worktree; production database selection pending owner decision.
- Windows tasks: as in the table above. Both Ultimate Coach tasks still on C:.
- Backups: H: copies of the APA checkout, both Ultimate Coach folders and Rebuild budget are present and match. No full restore has been run for any project.
