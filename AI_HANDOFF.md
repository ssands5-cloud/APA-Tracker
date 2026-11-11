# APA Tracker AI handoff
Updated 2026-11-09. Canonical checkout: D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker, authoritative branch feat/phase1-war-room. 35 registered worktrees, all under a deletion freeze.

Read, in order: AGENTS.md, SYSTEM_STATE.md, PROJECT_STATUS.md, RECOVERY.md, docs/AI_HANDOFF.md. Cross-project: D:\PROJECT_PORTFOLIO.md and D:\NEW_SESSION_STARTUP.md.

- Git: Repository synchronized with GitHub at ea7efea as of the documentation reconciliation (verified 2026-11-10); later docs-only commits sit on top. beaeb65 = D: migration commit. 3ca900e = earlier DB-location doc fix (historical). Run git status -sb and git log -1 for live state.
- Historical snapshot (2026-11-09, before the reconciliation push, no longer current): local tip e535ace, GitHub tip 62cfff6, 4 ahead / 1 behind.
- Databases: pipeline = data\apa_tracker.db in this checkout. Staging = APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging.db. Web app = Turso. Production database selection pending owner decision. D:\APA-Tracker-Data is an unused empty scaffold.
- Ultimate Coach: no owner-approved candidate. D:\Ultimate Coach is the preserved offline candidate. PR #83 UAT and the FINAL UAT build choice are pending Paul. Never mark a build approved, accepted or production-ready.
- Windows tasks: both Ultimate Coach tasks still point at the C: Desktop copy. Repointing needs Paul's admin rights.
- Recovery: RECOVERY.md; records in docs/migration/2026-11-05/.
- Leave other agents' uncommitted work alone. Never bypass the boundary guard. Don't delete worktrees or data.

## Local development and deployment boundary (2026-11-10)
- Use local worktrees and GitHub for coordination. Push only when the update is verified to skip Vercel. Preview and production deployments require Paul's explicit approval. Pushes of `6a5ce06` and `ea7efea` triggered previews. Vercel returned zero deployments for `cff8212` and `9f7223c` after their branch opt-outs.
- Claude's ESPN-style showcase is in the linked worktree on `claude/espn-broadcast-dashboard` at `9f7223c` on GitHub. See PROJECT_STATUS.md for validation and scope. Keep real exports under git-ignored `private-snapshots/`; keep real names and records out of GitHub updates.
- Draft PR #83 is at `15b342e`. The preserved `b1660ad` UAT build is 229 commits behind that head. Build and verify the exact head before Windows acceptance, and leave selection and approval to Paul.
- Use GitHub issue #84 for meaningful coordination updates. Claude's 30-minute check is session-scoped. Review the shared docs and exact branch heads whenever work resumes.
