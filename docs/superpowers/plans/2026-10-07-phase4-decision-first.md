# Phase 4 — Decision-First Ultimate Coach — Implementation Plan

> Written with `.github/skills/writing-plans/SKILL.md` before implementation (2026-10-07). Design source:
> Paul's "Phase 4 review results" directive (approved design; `brainstorming` question round not repeated —
> same justified deviation as the previous plan). Executed directly in one session (no subagents).
> Bug work follows `.github/skills/systematic-debugging/SKILL.md`; every claim follows
> `.github/skills/verification-before-completion/SKILL.md` (red-green tests, real-Excel recapture for
> anything Excel renders, exact-head CI, rebuilt hashes). `red-team` is used to check every new
> decision label against "no invented thresholds / no hidden ranking".

**Goal:** answer first — *who should I send, who should I avoid, who is dangerous, what don't we know* —
then the explanation, then the supporting evidence; and remove every trust defect from the artifacts.

**Hierarchy rule (Paul):** Recommendation → Evidence → Detailed analysis. HTML = match-night command
center; Excel = power-user planning tool.

**Evidence rules that do not change:** recommendations use the existing reviewed ordering (direct record
first: favorable, then even; shared-opponent-only candidates are **not ordered among themselves**; ties
shown). No thresholds, weights, odds or confidence. Every label states the recorded fact behind it.
Coach notes are opinion, always labelled, never evidence.

## WP-A — Must fix before production (trust)
- [ ] A1 Evaluator: `OR`/`AND` propagate argument errors like Excel (faithful oracle). Run → red on the
      Inspect formulas (and anything else). Fix guards (error-proof the guard expressions).
- [ ] A2 Conditional fills: dxf fills carry `bgColor` (Excel paints conditional fills from it). Test
      asserts bgColor on every CF fill. Packet card names readable without any fill (dark text).
- [ ] A3 Packet page 5: no clipped second line (font/row height within the page budget).
- [ ] A4 Polish: hide helper columns/rows (matrix category grid, Coach Dashboard pair key); START HERE
      lines never truncated (heights from text length).
- [ ] A5 Truthful limits: "no calibrated/predicted win probability"; historical rates are descriptive.
- [ ] A6 HTML: matrix header spacing; Player vs Player readable dates + format names; page title.
- [ ] A7 Coach-note migration runs once (cleared notes stay cleared); regression migrate→clear→reload.
- [ ] A8 Rebuild; real-Excel recapture of the affected views; GPT notes.

## WP-B — Decision support
- [ ] B1 Shared Python `next_send()` (mirrored in JS, exact cross-check): for one opponent, among our
      remaining players → ordered direct candidates (favorable, then even; ties disclosed), then
      shared-only candidates explicitly *unordered*, then Avoid (concerning direct), Unknown count,
      the opponent's coach notes. Also "consider saving" (protected players).
- [ ] B2 HTML **Who should I send next?** card at the very top of Tonight: remaining-opponent chips
      (pick who they put up) → 🥇🥈🥉 for ordered candidates only, "≈ not ordered" group, ⚠ Avoid,
      ❓ unknown, 📝 coach notes; visible on the phone's first screen.
- [ ] B3 **Top threats** panel promoted next to it (winning recorded record vs our roster, + notes).
- [ ] B4 **Quick read** at the top of every scouting card (HTML + Excel), facts only.
- [ ] B5 **Captain view / Evidence view** toggle for the HTML matrix (symbols only vs current cells);
      Excel gets a compact Captain View grid above the evidence matrix.
- [ ] B6 Excel Command Center: Next Send section first (opponent picker), threats; Captain Packet page 1:
      decisions before rosters.
- [ ] B7 Coach notes surfaced in Next Send, threats, packet.

## Verification per package
Focused red→green tests; full suite (`--ignore=tmp`); commit (explicit pathspec, Sonnet 5 footer); push;
CI 3.12/3.13 at that head; rebuild artifacts and verify hashes/DB; real-data browser check; real-Excel
recapture where Excel rendering is involved; report + #84 with provenance; visual acceptance
PENDING PAUL REVIEW.
