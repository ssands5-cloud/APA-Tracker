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
