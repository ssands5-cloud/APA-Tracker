# Repository Boundary

This repository is **APA Tracker only**.

- Canonical local root: `D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker`
- Expected GitHub origin: `https://github.com/ssands5-cloud/APA-Tracker.git`
- Keep source code, generated exports, databases, fixtures, tests, and worktrees for APA Tracker under this repository or its `APA Tracker Scorekeeper` parent.
- Do not create, clone, move, or save APA Tracker files under `D:\Invest`, `D:\Invest-master`, or any Invest-master worktree.
- Do not modify Invest-master while handling an APA Tracker task unless the user explicitly requests a cross-repository operation.
- Before making changes, verify that `git rev-parse --show-toplevel` resolves to the canonical root above and that `origin` is the expected APA-Tracker URL.
- Keep the tracked `.repo-boundary-id` file unchanged; it identifies this repository to the machine-level Git guard.
- Never bypass the repository boundary guard with `--no-verify` or by changing `core.hooksPath`.

## Session start (added 2026-11-09)

- Read `AI_HANDOFF.md`, `SYSTEM_STATE.md`, `PROJECT_STATUS.md` and `RECOVERY.md` before any change.
- Work on branch `feat/phase1-war-room` unless the task names another branch or worktree. Commit hashes in the docs are dated snapshots; check `git status -sb` and `git log -1`.
- The pipeline database is `data\apa_tracker.db` here; production database selection is pending Paul. Don't point scripts at `D:\APA-Tracker-Data`.
- The C: Desktop copy is rollback only. Worktrees and data are under a deletion freeze.
