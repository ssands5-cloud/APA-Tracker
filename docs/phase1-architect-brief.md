# Phase 1 Architect's Brief
**Role**: Chief Architect (Claude)  
**Implementer**: GPT  
**Branch**: `feat/phase1-war-room`  
**Session window**: 2026-10-25, autonomous until 18:00  
**Review cadence**: every 90 minutes  

---

## Current State

### Storage (complete)
- `D:\APA-Tracker-Data\` created with 11 subdirectories
- `scripts/paths.py` — central `APA_DATA_ROOT` config, committed `70ea1a1`
- `tmp/` added to `.gitignore`
- Phase 1 (move backups/demo-runs to D:) and Phase 2 (active DB migration) **not yet done** — requires Paul's go-ahead

### Ultimate Coach web app — routes live
| Route | View | Status |
|-------|------|--------|
| `/` | Home — CaptainCommand | Working |
| `/match-night` | War Room — full decision flow | Working |
| `/summary` | Team Briefing — CaptainBriefing | Working |
| `/recommendations` | Opponent recommendations | Working |
| `/threats` | Threat scouting | Working |
| `/dashboard/[...section]` | Protected historical dashboard | Working |
| `/team-status` | Team status | Working |

### This session's improvements (committed)
- Cost parity: lead cost now appears in War Room aside (Home + Summary already had it)
- Mobile order: recommendation floats above explorer at ≤740px
- Threat bar label: now reads "Historical direct record rate" (probability_publication invariant)
- Numbered briefing badges (01–06) replace emoji icons
- Empty threat state added
- `decision-cost` styled with caution border
- WCAG AA fix: `command-kicker` contrast

---

## Phase 1 Feature Priorities

### 1. Tonight's Plan  
**What**: A pre-match summary page a captain opens before leaving for the venue.  
**Job**: Answers in 30 seconds: who we put up first, who we protect, what the biggest threat is, what to do if our lead isn't available.  
**Route**: `/match-night` already serves the live War Room. Tonight's Plan is a **print-friendly / share-friendly summary** of the same snapshot — static, no interactive selectors.  
**Architectural constraint**: Must be derivable from the same `Snapshot` type with zero new data. No new backend calls.  
**GPT task**: Add `/tonight` route OR a `?view=tonight` mode on `/match-night` that renders a single-card read-only plan. Reuse existing `CaptainCommand` data.

### 2. Match Night War Room  
**What**: Already exists at `/match-night`.  
**Remaining gaps** (from autonomous session 2026-10-24):
- Cost bar: show cost impact visually, not just text
- "If unavailable" fallback — what if the lead player doesn't show?
- Send/hold toggle: let captain mark a player as "sent" to filter the response explorer
**Architectural constraint**: All state is local (no persistence needed in Phase 1 demo). Cost display must never show a percentage bar without the "historical direct record rate" label — `probability_publication: FORBIDDEN` invariant applies.

### 3. Preservation Workflow  
**What**: The "save a player for a later match" decision flow.  
**Current state**: `plan.protect` array renders in CaptainCommand ("Who to protect" section). The cost of sending a protected player is surfaced.  
**Gap**: No interactive way to mark "we're protecting X tonight" and see the downstream effect on the response explorer.  
**Architectural constraint**: Preserve-decisions are match-night state, not persistent config. Must not invent new evidence or upgrade "Unknown" to a confidence level.

### 4. Opposition Dossiers  
**What**: Per-opponent scouting cards (already at `?view=dossiers`).  
**Remaining gaps**:  
- Dossier cards have no visual hierarchy distinguishing strong-evidence opponents from thin/unknown
- No "show all opponents" vs "show only tonight's relevant ones" filter
**Architectural constraint**: Evidence labels must use `evidenceLabel()` — no raw level strings in UI.

### 5. Briefing Consolidation  
**What**: Team briefing at `?view=briefing` — already works.  
**Gap**: Briefing and War Room show overlapping information. A captain using both pages has to reconcile them mentally.  
**Task**: Add a "share" or "print" action on the briefing that produces a clean single-page summary with no UI chrome.

---

## Architectural Non-Negotiables (for GPT)

1. **`probability_publication: FORBIDDEN`** — No win probability, predictive confidence, or percentage bars without the label "Historical direct record rate". No exceptions.
2. **Snapshot URL never reaches the browser** — Keep `NEXT_PUBLIC_` env vars out of snapshot paths.
3. **`evidenceLabel(level)`** — All evidence display goes through this function. Never raw `level` strings.
4. **`<aside>` before `<div.workspace>`** in `layout.tsx` — DOM order is load-bearing for mobile layout. Do not change it.
5. **No new data structures** — Phase 1 must work with the existing `Snapshot` type. If something isn't in the snapshot, it doesn't render.
6. **Tests must stay green** — Run `node --experimental-strip-types` test suite before any commit. The captain-command tests are the primary regression gate.
7. **`APA_DATA_ROOT` for any new file paths** — No hardcoded `C:\` or `D:\` paths in new code.

---

## Review Checklist (GPT handoff)

At each 90-minute review, check:
- [ ] Tests pass: `node --experimental-strip-types apps/ultimate-coach-web/tests/*.test.ts`
- [ ] No raw `level` strings in UI components (grep: `{answer.level}` without `evidenceLabel`)
- [ ] No new `NEXT_PUBLIC_` vars that expose internal paths
- [ ] DOM order in `layout.tsx` unchanged
- [ ] `probability_publication` invariant: grep for `%` near threat/matchup displays
- [ ] Commit messages follow `fix(web):` / `feat(web):` convention

---

## Handoff Notes

### 2026-10-25 session start
- Storage Phase 0 committed. Phase 1 (file moves) awaits Paul's go-ahead.
- `feat/phase1-war-room` is the active branch. All Phase 1 web work goes here.
- GPT/Jeeves may push to this branch — always `git pull` before pushing.
- PR #97 may be the next PR target; verify before opening a new one.

*Next review: ~90 min from session start*
