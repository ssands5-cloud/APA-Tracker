# Claude → GPT Handoff · 2026-10-24

**Current Work:**
Phase 1 captain-mistake mapping complete. Creating `feat/phase1-war-room` branch off `fix/mobile-merge-both` (= `codex/web-platform-v1`). Implementing Phase 1 changes to the Next.js web platform (`apps/ultimate-coach-web`).

**Decisions Made:**
- COST source confirmed: `responses[threatOpponentId].cost` — human-readable string ("Spends the recorded answer against Zane.")
- ALTERNATIVE source: `plan.lead.alternatives[]` — already in snapshot type
- Preservation warning: making per-protect-option specific ("Quinn is designated for Xeno. Keep this designated answer until Xeno is put up.")
- Branch: `feat/phase1-war-room` off `codex/web-platform-v1`
- PR #97 content staged as the foundation — committing as base before Phase 1 additions

**Captain Mistakes Prevented (this session):**
1. Tonight's Plan: captain sends without knowing the spend ("Spends the recorded answer against Zane" now on Home screen)
2. Preservation: captain burns designated-protect player before target matchup appears (named warning now fires at Home and Match Night)
3. Briefing: cost of tonight's plan missing from the Opening briefing step

**Phase 1 Status:**
| Item | Before | After |
|---|---|---|
| Tonight's Plan — COST | Not on Home | Added to CommandReasoning |
| Tonight's Plan — ALTERNATIVE | Not on Home | Added to CommandReasoning |
| Match Night — COST weight | Buried in decision-cautions | Visual promotion pending |
| Preservation Workflow | Generic warning | Named per-player warning |
| Opposition Dossiers | Built (PR #97) | Verified link target |
| Briefing — cost in Opening | Missing | Added cost line |

**Recommendation For GPT:**
- Before proposing new UX changes to Home/Match Night: confirm whether the COST text from `responses[id].cost` is the right field to surface, or whether there's a better cost expression in the plan summary (`plan.summary`).
- The snapshot `plan.lead.alternatives[]` may be empty in some production snapshots — confirm with Paul whether alternatives should always be shown or only when non-empty.
- `probability_publication: FORBIDDEN` invariant still applies — COST text is descriptive ("Spends the recorded answer") not probabilistic. Verify GPT's any new workflow text does not introduce confidence language.
- PR #88 (`codex/captain-product-v1`) conflicts with PR #97 on hero removal — needs resolution before either merges to main.

**Architecture Boundaries (don't cross):**
- Snapshot URL never reaches the browser
- Role never shipped in JS bundle
- No win probability / confidence scores in any UI element
- All plan data is descriptive (historical record), not predictive

**Next Action (Claude):**
Implement COST + ALTERNATIVE on Home screen in `captain-command.tsx`, specific preservation warning, cost line in `CaptainBriefing`. Then typecheck + run 16 unit tests.
