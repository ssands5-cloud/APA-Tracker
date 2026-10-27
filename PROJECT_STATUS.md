# Project status: Ultimate Coach (Captain's War Room)

This file is required by `.github/prompts/build.md`: update it whenever build, publish or pipeline behavior changes. Build-by-build provenance (commits, CI runs, artifact hashes, live deployments) is recorded in `docs/overnight_coach_advantage_report.md`, which is append-only. This file holds what stays true between builds.

## Status (2026-10-08)
- **PR #83** (`integration/ultimate-coach-pr81-pr82-reconciliation`) is a **DRAFT, not merged, not accepted.**
- Claude builds. GPT audits: issue #84 is the production readiness sprint, and draft PR #85 holds the audit report.
- **Visual, native-Excel, print and physical-device acceptance: PENDING PAUL REVIEW.**
- **Real Match Night publication:** waiting for GPT to close the publisher P1 (junction/reparse-path guard, fixed in `989aecf`). Only a synthetic DEMO package is live.

## What it is
One fixture-focused coaching tool, built from the verified staging SQLite snapshot, in two forms:
- **HTML cockpit** (`ui/ultimate_coach.py`, `ui/ultimate_coach_war_room.js`). Its sections:
  - Tonight, with "Who should I send next?", threats and risks;
  - War Room;
  - matrix, with Captain view and Evidence view;
  - Lineup Lab;
  - scouting cards, each with a Quick Read;
  - Player vs Player.
- **Excel workbook** (`ui/excel_war_room.py`, `ui/export_excel_ultimate_coach.py`). Its tabs:
  - START HERE;
  - Command Center, with "They put up:" and Next Send;
  - Match Day, War Room, Lineup Lab and Scouting Cards;
  - Captain Packet, for printing;
  - Coach Dashboard and Coach Notes.
- **Match Night web app**, for phones (`ui/match_night.py`):
  - one fixture per package, encrypted with AES-256-GCM and unlocked by a passphrase;
  - published on GitHub Pages (`gh-pages`, https://ssands5-cloud.github.io/APA-Tracker/);
  - works offline after the first unlock.
- **Shared logic** (`analytics/ultimate_coach_war_room.py`):
  - categories, the evidence ranking, `next_send`, `quick_read` and `captain_cell`;
  - the onboarding, match-night and Player-vs-Player status texts.
  - The HTML JavaScript mirrors this logic, and browser tests cross-check the two.

**Method.** Evidence comes from recorded results only. There are no thresholds, weights, odds or confidence scores. Historical win rates are descriptive, and no win probability is shown (NOT CALIBRATED).

## Pipeline commands
Run from the repository worktree:
```powershell
# Tests (CI runs the same on Python 3.12 and 3.13). Locally, keep pytest's temp files inside the canonical
# folder but outside the worktree (several tests treat tmp_path as 'outside the repository'):
python -m pytest -q --ignore=tests/test_player_vs_player_unified_tab.py --ignore=tmp -p no:cacheprovider -p no:warnings --basetemp=..\..\tmp\pytest-pr83

# UAT build: HTML + Excel from the staging DB (read-only; hash checked before/after), with UAT_MANIFEST.json.
# Default output: <worktree>\tmp\uat. scripts/repo_boundary.py checks canonical .git + origin and refuses any
# destination outside the canonical folder or reached through a symlink/junction, before the fetch and before
# every write.
.\tools\build_ultimate_coach_final_uat.ps1

# Match Night publish (fail-closed; see docs/match_night_deployment.md)
.\tools\publish_match_night.ps1 -Demo          # synthetic demo package
.\tools\publish_match_night.ps1                # real next fixture: prompts for the passphrase (Paul only)
```

### Working-folder boundary
- All work, scratch files, workbook copies, screenshots and build outputs stay inside the canonical folder `C:\Users\ssand\Desktop\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker`, whose origin is `https://github.com/ssands5-cloud/APA-Tracker.git`.
  - PR #83 is built in the linked worktree `.worktrees/pr83`.
  - Scratch goes in its `tmp/`, which is git-ignored.
- Before writing, verify that `git rev-parse --path-format=absolute --git-common-dir` is `<canonical>/.git` and that `git remote get-url origin` is the URL above.
- **Exception, read-only input:** the staging DB is read, never written, from `..\APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging.db`. That folder is a linked worktree of the same canonical `.git`. Builds check its SHA256 before and after.
- Builds made before the 2026-10-07 boundary transition remain in `Desktop\Ultimate Coach FINAL UAT\`. They are historical and are left untouched.

### Publisher safeguards (`scripts/publish_match_night.py`)
These checks run before anything is built, deleted, copied, fetched or checked out:
- the checkout is the canonical repository, with the expected origin;
- the build folder is exactly `<repo>/tmp/match_night_site`;
- the Pages checkout is the clean `.worktrees/gh-pages` worktree on `gh-pages`, holding only allowlisted files;
- no path component of any allowlisted source, cleanup target or destination is a symlink, junction or other reparse point. All of them are checked together, before any cleanup, after the build and right before copying (shared `scripts/repo_boundary.py`);
- the source is committed (and, for a real publish, already on origin).

It stages and commits only the allowlisted files and records `Source: <commit>` in the commit. Hooks are never bypassed and history is never force-pushed.

## Where things are
| What | Where |
|---|---|
| Deployment and security model | `docs/match_night_deployment.md` |
| Phase 4 plan and status (WP-A, WP-B, WP-D) | `docs/superpowers/plans/2026-10-07-phase4-decision-first.md` |
| Build and audit log, provenance | `docs/overnight_coach_advantage_report.md` |
| Workbook instructions | the START HERE tab (generated by `ui/excel_war_room.py`; text shared with the HTML "Start here" card) |

## Open items
- **GPT re-audit:**
  - publisher P1 (`989aecf`);
  - Next Send P2s (`ab42ef0`);
  - legacy-note preservation (`2a67d78`);
  - descriptive-vs-predicted Player vs Player banner.
- **Unordered/tied single-send outside the HTML Tonight panel:** the Excel Command Center, War Room top opportunities and packet best sends.
- **Native Excel test of the latest workbook:** separate session; results go to issue #84.
- **WebKit primed-offline reload:** fails in emulation. Physical iPhone and Android checks are PENDING PAUL REVIEW.
- **Preference:** whether the matrix opens in Evidence view (current) or Captain view. PENDING PAUL REVIEW.
