# Project status: Ultimate Coach (Captain's War Room)

This file is required by `.github/prompts/build.md`: update it whenever build, publish or pipeline behavior changes. Build-by-build provenance (commits, CI runs, artifact hashes, live deployments) is recorded in `docs/overnight_coach_advantage_report.md`, which is append-only. This file holds what stays true between builds.

## Cross-surface parity in progress (2026-10-17)

Loss cautions now share the existing Top Risks net-loss/meeting order across outputs; favorable,
even and shared-only sends retain their order. Workbook/Packet live threat flags follow the phone's
remaining-player and unplayed-opponent scope. Historical-only evidence is explicitly unknown, not
cleared. Full-roster Scouting/Quick Read are labeled historical; Packet preview limits and separate
phone/workbook marks are disclosed. Native Excel and focused browser/formula evidence is recorded
in the ONE report. Other owner-listed paper-warning findings remain in progress; no final auditor
clearance, primary installation or release is implied.

## Current evidence-strength presentation sprint (2026-10-17)

The HTML Next Send headline now names the existing first direct-record group with record, meeting
count and a prominent small-sample warning. When that group has one or two meetings, deeper remaining
direct records appear separately with their actual outcomes and counts; this is not a second ranking.
Blind Send explicitly labels total meetings. One-meeting threats/losses and future-save warnings state
Beat us once, Lost once and Only 1 meeting at the decision. Existing colors and sample threshold remain.
Quick Read's first/even/losing direct records and winning/losing skill-level buckets have explicit counts;
HTML emphasizes those counts and generated workbook data receives the same textual disclosures.
Engine functions, ranking/order, eligibility, evidence counts and storage are unchanged. No probabilities
or predictive model were added. This remains candidate work; source-bound checks are in the ONE report.

## Previous recommendation trust presentation (2026-10-17)

Ranking and evidence engines remain unchanged. HTML explicitly says first in direct-record order
does not mean better supported or the better practical send. Blind Send now shows the meetings
behind its existing pairing counts and identifies small-sample pairings. Threat/Avoid headings describe
winning/losing direct records; single-result cautions and sample badges distinguish history from advice.
Candidate budget warnings have stronger borders and weight, with existing reference-only limitations.
Quick Read uses First by direct record, Winning direct record and Losing direct records in both HTML
and generated workbook data. Broader records remain separately labeled Not used in this ordering.
Private synthetic browser/native acceptance and exact scope are recorded in the ONE report.
This is candidate presentation work; no production publication or successful live refresh is implied.

## Separate live validation blocker (2026-10-17)

Real primary APA full-refresh validation stopped at identity reconciliation before workbook/HTML builds.
A reproduced multi-division standings defect
was found: separate capture timestamps left only the final division in latest_standings(), despite all
rows being stored. The bounded correction groups explicit division standings under one timestamp after
team fallback snapshots and rejects completion unless the latest snapshot contains all captured rows.
The correction is still separate candidate work. Replay verified all 40 standings rows from four divisions;
17 scoresheets still have unresolved identities. No original database or completed bundle was replaced.
No recommendation, ranking, model, schema or architecture change is involved. Exact live outcomes and
source/artifact bindings belong in the ONE report; do not infer completion from source capture alone.

## Previous presentation boundary update (2026-10-17)

Paul subsequently authorized implementing presentation transparency, while preserving all ranking logic.
Next Send now identifies recorded matchup options and explains ordering before the list, uses neutral
Direct-record order labels, emphasizes meeting/sample counts, and shows a separate Not used in this
ordering section with captured team/session records (not mislabeled lifetime or universal overall records).
Missing records remain explicit. HTML and Command Center share these boundaries; onboarding copy matches.
Rank keys, evidence categories, ties, eligibility, availability, shared-only grouping, budget and save rules
are unchanged. See the ONE report's latest entry for actual browser, formula, table-parity and native checks.
Use the normal primary QUICK_REFRESH launcher to generate updated files; older generations remain frozen.
No live recrawl, release publication, legacy cleanup or unrelated audit is implied by this bounded task.

## Previous handoff (2026-10-17)

Paul requested transfer to Claude because GPT usage is nearly exhausted. Start from the primary
`codex/phase3-captain-audit` tree or current `codex/captain-display-cleanup` builder, with refresh source
`41a31f0d4d858d4f20fcfbbc3b69163aed6a896d` or its later documentation-only handoff commit.
The older Claude worktree predates the refresh and has not been overwritten or blindly merged.
Read CURRENT PRIORITIES / Claude handoff in `docs/overnight_coach_advantage_report.md` for the complete
source chain, private evidence pointers, test boundaries, remaining live operator verification and gates.
The local refresh/progress/summary work is delivered. A complete live-data source-to-output run remains
unclaimed; synthetic end-to-end and actual live login/API checks are distinct. No additional general
audit or recurring automation is requested. Legacy BAT files and local data remain preserved.

## Historical status (2026-10-08)
- **PR #83** (`integration/ultimate-coach-pr81-pr82-reconciliation`) is a **DRAFT, not merged, not accepted.**
- Claude builds. GPT audits: issue #84 is the production readiness sprint, and draft PR #85 holds the audit report.
- **Visual, native-Excel, print and physical-device acceptance: PENDING PAUL REVIEW.**
- **Real Match Night publication:** waiting for GPT to close the publisher P1 (junction/reparse-path guard, fixed in `989aecf`). Only a synthetic DEMO package is live.

## What it is
The verified refresh workflow is integrated into the primary working tree with explicit owner authorization.
Legacy launchers remain unchanged. Production database promotion and web publication are separate gates.
The end-user refresh entry points are `FULL_APA_REFRESH.bat` and `QUICK_REFRESH.bat`, both using
`pipeline.ultimate_coach_refresh`. The workflow captures current authenticated APA division sources into
private fixtures, replays existing ingestion and scoresheet reconciliation, rebuilds derived data, and
validates the Ultimate Coach workbook/HTML from one payload before moving a single local current pointer.
The console confirms Enter receipt and browser closure, validates authentication with APA, and logs every API request and blocking build/validation phase. Long phases print activity every five seconds; STEP 1/8 through STEP 8/8 and REFRESH_STATUS.txt expose progress. Python runs unbuffered. A final completion block reports captured fixture counts, unique current-roster teams/players processed, rebuild versus reuse results, output folder and total elapsed time; quick reuse is not described as new database updates.
Quick mode still checks live content; it reuses only matching dependency and artifact checksums. Outputs,
database, coverage, source limitations and `REFRESH_STATUS.txt` live under ignored `ultimate-coach-runs/refresh`.
This does not install a release, promote the production database, publish real data, or refresh every
historical APA season. Historical games in the configured seed are retained; current scope is explicit.

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
