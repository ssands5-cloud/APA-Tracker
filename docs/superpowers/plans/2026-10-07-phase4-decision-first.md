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
- [x] A1 Evaluator: `OR`/`AND` propagate argument errors like Excel (faithful oracle). Run → red on the
      Inspect formulas (and anything else). Fix guards (error-proof the guard expressions).
- [x] A2 Conditional fills: dxf fills carry `bgColor` (Excel paints conditional fills from it). Test
      asserts bgColor on every CF fill. Packet card names readable without any fill (dark text).
- [x] A3 Packet page 5: no clipped second line (font/row height within the page budget).
- [x] A4 Polish: hide helper columns/rows (matrix category grid, Coach Dashboard pair key); START HERE
      lines never truncated (heights from text length).
- [x] A5 Truthful limits: "no calibrated/predicted win probability"; historical rates are descriptive.
- [x] A6 HTML: matrix header spacing; Player vs Player readable dates + format names; page title.
- [x] A7 Coach-note migration runs once (cleared notes stay cleared); regression migrate→clear→reload.
- [~] A8 Rebuilt (7b78fa6, CI green). Real-Excel recapture of the fixed views PENDING (needs a screen takeover Paul must allow).

## WP-B — Decision support
- [x] B1 Shared `analytics.next_send()` / `next_send_lines()` (`092254f`), mirrored in JS and cross-checked
      line-for-line via `window.__ucNextSend` (all opponents × marks). Medals only for ordered direct
      candidates (favorable, then even); equal evidence shares a medal and names the tie; shared-only
      candidates one unordered "≈" group; Avoid worst first; Unknown "not weak"; "consider saving".
- [x] B2 HTML **Who should I send next?** at the top of Tonight (`092254f`, `f4eb60b`, `3751d22`, `8a841d9`):
      chips for unplayed opponents, medals with reasons and a one-tap "✓ Sent" (Played marks), the rest
      folded into one line that still names every player, the opponent's coach note as opinion.
      First screen: fits a Home Screen launch (844px) with room to spare and a wide-font approximation;
      in Safari's browser view (664px) Next Send + threats + risks fit and "Best sends now" follows.
- [x] B3 Threats: right after Next Send on phones (CSS order), with coach notes (`d805f0b`).
- [x] B4 **Quick read** on every scouting card, HTML + Excel (`f4eb60b`); `analytics.quick_read`,
      cross-checked; Excel `Scouting_Table[Quick Read]`, first card row. Also fixed clipped card values
      on phones (regression test red before the fix).
- [x] B5 **Captain view / Evidence view** (`ddf7e16`): shared `captain_cell`; HTML remembered toggle;
      Excel War Room "View" dropdown switching the matrix text. *Deviation:* a dropdown over the one
      matrix instead of a second grid above it, to keep one matrix, one set of colours and one place to
      tap/inspect. Default stays Evidence view — **which default Paul prefers is PENDING PAUL REVIEW.**
- [x] B6 Excel Command Center opens with "They put up:" + WHO SHOULD I SEND NEXT? (`9ab97fb`); Captain
      Packet page 1 is decision first: best sends → risks → rosters (`d805f0b`, same print geometry).
- [~] B7 Coach notes: Next Send (HTML + Excel), threats (HTML + Excel War Room), cards and packet cards.
      Not added to the packet's one-line "Dangerous" rows (fixed-height print rows).
- Excel tie/consider-saving wording ("tied (same evidence)", "…vs another unplayed opponent") is shorter
  than the HTML's (which names the tied players and the opponent); the medals and order are the same.
- Native Excel look of the new Command Center card, View dropdown and packet page 1: **PENDING PAUL REVIEW**.

## Verification per package
Focused red→green tests; full suite (`--ignore=tmp`); commit (explicit pathspec, Sonnet 5 footer); push;
CI 3.12/3.13 at that head; rebuild artifacts and verify hashes/DB; real-data browser check; real-Excel
recapture where Excel rendering is involved; report + #84 with provenance; visual acceptance
PENDING PAUL REVIEW.

## WP-D — Match Night Deployment Mode (Phase 4D, added 2026-10-07)
- [x] Slim one-fixture package, AES-256-GCM (PBKDF2-SHA256 600k), lock screen, remember (non-extractable
      key), service worker offline, manifest + icons, decision-first Tonight, START HERE mobile guide.
- [x] gh-pages via `.worktrees/gh-pages`; Pages live with a SYNTHETIC demo package; live checks on WebKit
      iPhone 13, Chromium Pixel 7 and desktop.
- [ ] Real package: Paul runs `tools/publish_match_night.ps1` (passphrase prompt) — PENDING PAUL.
- [ ] Real-device Add to Home Screen + match-night use — PENDING PAUL REVIEW.
