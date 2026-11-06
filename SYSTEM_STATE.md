# APA Tracker system state — 2026-11-05
- Canonical Windows checkout: D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker. Origin: https://github.com/ssands5-cloud/APA-Tracker.git. Only this checkout and worktrees attached to its Git common directory are writable.
- The Windows commit guard must recognize the D: checkout and verify the repository identity and origin. Preserve the repository marker and configured hook path. The machine-level hook is maintained separately.
- D: virtual environments were rebuilt with Python 3.14.3 and 3.12.10. Select the project runtime deliberately. Prior copies remain preserved.
- The scheduled-refresh-task worktree has local D: migration changes. Its task installer and scripts must use the D: repository, worktree, and log paths. The enabled failure alert still references the old checkout. QUICK Refresh remains disabled pending unattended sign-in and Excel validation. The published branch changes documentation only.
- The D: Ultimate Coach and FINAL UAT folders contain preserved artifacts. The original artifacts passed copy verification. Confirm the intended build and UAT decision separately.
- Confirm the actual production database location before a refresh. Current full backup restoration remains unverified. Worktree deletion is frozen.

## Final documentation lock — 2026-11-05
- The checkout-local data/apa_tracker.db was present at audit. Confirm runtime selection before a refresh because the external default was absent.
- 35 registered worktrees include this documentation checkout. Preserve the scheduled refresh, publishing, UAT and open-PR worktrees. Worktree deletion remains frozen.
- To recover, stage a backup in a separate location. Confirm repository identity, Git refs, local and ignored data, and artifact checksums. GitHub cannot recover unpublished work or local databases. The current full-machine restore is unverified.
- The enabled failure alert and disabled QUICK Refresh still point to the old checkout. Keep QUICK Refresh disabled until unattended operation is validated. Do not copy credentials into handoff documentation.
