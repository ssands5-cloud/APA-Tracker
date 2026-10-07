# HTML Onboarding, Command Center and Coach Notes — Implementation Plan

> Written with `.github/skills/writing-plans/SKILL.md` before implementation (2026-10-07). Executed in the
> same session (no subagents). Design source: Paul's written "captain's weapon" directive and his
> 2026-10-07 follow-up (approved scope; `brainstorming` question round not repeated — see Deviations).

**Goal:** Bring the Excel START HERE, Captain Command Center and Coach Notes to the HTML cockpit, from one
shared source so both artifacts say the same thing.

**Architecture:** Onboarding text (what it does, limitations), the coach-tag list, the build version and the
worked example move into `analytics/ultimate_coach_war_room.py`; Excel (`ui/excel_war_room.py`,
`ui/export_excel_ultimate_coach.py`) and HTML (`ui/ultimate_coach.py` + `ui/ultimate_coach_war_room.js`)
both read them. The HTML Tonight panel becomes the Command Center by adding the same counts Excel shows.
Coach notes in HTML become durable per player (browser only), with tags.

**Tech stack:** Python 3.12/3.13, openpyxl, plain JS in the generated page, pytest + Playwright, the repo's
formula evaluator. No COM, no macros.

---

## File map
- `analytics/ultimate_coach_war_room.py` — add `ONBOARDING_WHAT`, `ONBOARDING_LIMITS`, `COACH_TAGS`,
  `build_version()`, `worked_example()`.
- `ui/export_excel_ultimate_coach.py` — use `worked_example()` / `build_version()` (remove inline copies).
- `ui/excel_war_room.py` — START HERE and Coach Notes read the shared lists.
- `ui/ultimate_coach.py` — server-rendered "Start here" card + `DATA.coach_tags` (open on first visit, remembered closed).
- `ui/ultimate_coach_war_room.js` — Command Center counts in Tonight; coach tags + observation per player.
- Tests: `tests/test_ultimate_coach_war_room.py`, `tests/test_ultimate_coach_war_room_browser.py`,
  `tests/test_excel_war_room_formulas.py`.

## Tasks
- [x] 1. Failing tests: HTML Start-here card content/links/build info/example; Tonight shows availability,
      evidence counts (same wording as Excel) and opponent missing-info; coach tags + note on a card,
      durable across fixtures and reload, printed as "Coach: …", evidence unchanged. Run → red.
- [x] 2. Shared module constants + `worked_example()`; Excel switched to it; Excel tests still green.
- [x] 3. HTML Start-here card. Run task-1 tests for onboarding → green.
- [x] 4. Tonight Command Center counts → green.
- [x] 5. Coach tags/notes per player (migrate earlier per-team notes) → green.
- [x] 6. Full suite; commit; push; CI 3.12/3.13; rebuild; verify hashes, real data, no script errors.
- [ ] 7. Report + #84 with provenance; visual acceptance PENDING PAUL REVIEW.

## Deviations (justified)
- `brainstorming` hard gate (present design, get approval): the design is Paul's approved written spec and
  he authorized proceeding unattended; no new question round. This plan file is the recorded design.
- `writing-plans` header asks for subagent execution: executed directly in this session to keep one
  implementation session, as Paul instructed.
- HTML coach notes live in the browser (localStorage) and Excel coach notes in the workbook; there is no
  shared store between the two artifacts (no server by design).
