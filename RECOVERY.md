# APA Tracker recovery

Written 2026-11-10 (Claude). Hashes and commits below are dated snapshots. Nothing here authorizes a restore,
a delete or a push; ask Paul first.

## What exists only on this machine (not on GitHub)

- Databases: `data\apa_tracker.db` (pipeline) and `APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging.db` (staging),
  plus `data\*.backup-*.db`, `demo_*.db` and `apa_tracker_career_staging.db`.
- Refresh runs `ultimate-coach-runs\`, UAT builds in worktree `tmp\` folders (17.8 GB), `.session_cache\`.
- `.env` (APA credentials; never copy its values into docs, chats or commits).
- Local-only branches and commits: `codex/scheduled-refresh-task` (`6038fd7`, not on GitHub as of 2026-11-10), any
  worktree branch without a remote, and `feat/phase1-war-room` commits until the 2026-11-09 docs push succeeds.
- Other agents' uncommitted work (listed in `SYSTEM_STATE.md`).

## Backup locations

| Location | Contents | State |
|---|---|---|
| GitHub `ssands5-cloud/APA-Tracker` | Pushed branches only | `feat/phase1-war-room` GitHub tip `62cfff6` at the 2026-11-09 snapshot |
| `H:\APA Tracker Scorekeeper` | Full pre-migration tree, commit `92d4ccd`, including worktrees, venvs and data | Present. Includes three worktree folders removed on D: (`APA-Tracker-cockpit-bridge`, `-scoresheet-gate-fix`, `-viewer-revalidation-fix`) |
| `C:\Users\ssand\Desktop\APA Tracker Scorekeeper` | Pre-migration rollback copy, commit `92d4ccd` | Present. Boundary guard blocks commits there. Its 51 branch tips and 4 stashes are also on D: |
| `docs/migration/2026-11-05/` (this repo) | Worktree inventory with exact HEAD SHAs, removal log, venv package lists, C:/D:/H: comparison | Tracked in git |

## Prerequisites

- Windows Git and `gh` signed in as `ssands5-cloud`.
- Base Pythons `C:\Users\ssand\AppData\Local\Programs\Python\Python314` (3.14.3) and `Python312` (3.12.10).
- Boundary guard hooks in `C:\Users\ssand\.codex\repository-boundary-hooks` (canonical roots: this checkout and `D:\Invest-master`).
- Node (for `apps/ultimate-coach-web`) only if web work is needed.
- Enough free space on D: for an isolated copy (the APA parent folder is about 30 GB).

## Restore order

1. Copy the backup into an **isolated** folder (for example `D:\_restore_test\APA Tracker Scorekeeper`). Never restore over the live checkout.
2. Git: `git -C <copy> fsck --connectivity-only`, `git branch -a`, `git stash list`. Compare branch tips with the live checkout.
3. Worktrees: `git -C <copy>\ssands5-cloud\APA-Tracker worktree repair <paths...>`, then `git worktree list --porcelain` (expect no `prunable`).
4. Databases: compare hashes (table below) before using any restored DB.
5. venvs: `<base python> -m venv venv312` then `pip install -r docs\migration\2026-11-05\venv312.freeze.txt` (same for `venv` with Python 3.14).
6. Fast check: `.\venv312\Scripts\python.exe -m pytest tests/test_repo_boundary.py tests/test_refresh_ultimate_coach_current_session.py -q -p no:cacheprovider` (52 tests at last count).
7. Only after Paul approves: swap the restored copy in, then re-run the boundary-guard dry run (`git hook run pre-commit`).

## Validation reference (SHA-1)

| File | SHA-1 | Checked |
|---|---|---|
| `APA-Tracker\data\apa_tracker.db` (548,864 B) | `e3e43aa76e072c9be7c140d82c4322766970beae` | D: and H: match, 2026-11-10 |
| `APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging.db` (235,077,632 B) | `9799128652976d55e58f52d367d05d36b5f37467` | D: and H: match, 2026-11-10 |

## Verified

- C: → D: copy: file counts and sizes, 2026-11-05 (`docs/migration/2026-11-05/verify_report.json`).
- D: checkout vs H: copy: same files except the post-migration docs and path-fix files, 2026-11-09.
- Both databases above match between D: and H: by SHA-1, 2026-11-10.
- Worktree links (35, none prunable), venv launch, and guard behaviour, 2026-11-09.

## Not verified

- No restore from H: or C: has been run end to end.
- The H: copy predates `beaeb65`; restoring it needs the migration commits from D: or GitHub.
- Turso (web DB), Vercel and Clerk settings have no backup procedure here.
- UAT build folders on H: were not hashed.
