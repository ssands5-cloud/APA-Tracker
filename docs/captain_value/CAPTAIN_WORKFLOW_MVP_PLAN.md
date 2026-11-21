# Captain workflow MVP: implementation plan (for review, no code yet)

Scope: the smallest demonstrable captain workflow built from existing data and logic. Priorities as approved: (1) Five Advisor verdict, (2) Risk Briefing, (3) Real Player Form, (4) What-If. No M4/M5/M6, no new algorithm research, no probabilities, no redesign, no Python analytics changes, no Excel changes. No player or team names. **Stop here for review.**

## 0. The workflow being demonstrated

1. Captain opens the Broadcast file and confirms who is Here on Home (existing Here/Out; everyone Here by default).
2. On **Team Status**, the roster tables now show each player's recent results (item 3). The captain marks five players **Planned** in the existing Lineup Lab.
3. Directly under the Lineup Lab tables, a **Five check** says whether the five fits under the cap and who is left out (item 1).
4. Under it, the **Risk Briefing** lists factual alerts about this five and pool (item 2).
5. The captain picks a **swap** (a Planned player out, a left-out player in) and sees exactly what changes, without touching the real marks (item 4).
6. Confirming the five is the existing step: marks stay as they are and the Match Night flow uses them as before.

Everything lives in code shared by the classic cockpit and the Broadcast page, so both get it; Broadcast filing uses the existing tab tags (Team Status already holds `#lineup-lab` and `#team-rosters`).

## 1. Cross-cutting rules (decisions for reviewers marked **D**)

- **Wording contract.** The Lineup Lab and the Excel War Room deliberately say the selected-lineup line is "not a lineup-legality check" (reference arithmetic; required sends and other match constraints are not verified), and tests assert that text in Python, Excel and browser. The plan keeps that row **unchanged** and adds new elements beside it, so those tests do not move. New text says "skill total" and "reference", never "legal lineup". **D1:** if you want the verdict to say "legal", that is a deliberate change to a tested contract and needs the Excel formulas and three tests updated; the plan does not assume it.
- **No probability or outcome wording.** No "will win", odds, expected points, scores or rankings.
- **Mirror contract.** `tests/test_war_room_js_mirror.py` guards the evidence-text functions. New functions are pure JavaScript with a `window.__uc...` test hook (the existing pattern, e.g. `__ucMatchPlan`) and are cross-checked in the browser against the Python reference, not added to the Excel mirror. **D2:** Excel parity for these features is out of scope.
- **Shared page.** `ui/ultimate_coach.py` and `ui/ultimate_coach_war_room.js` render the classic page too; changes show there. Nothing is hidden behind a flag.
- **Sunday artifact.** Code changes need the existing splice step to produce a new HTML file; not part of this plan, only after approval and review.

## 2. Priority 1: Five Advisor verdict

**What.** A pure function `wrFiveCheck(w, ck, cap)` and one new block `#ll-five-check` inside the Lineup Lab render (rendered next to, not inside, the Snapshot list).

**Behaviour.**
- Selected = players whose lineup mark is Planned or Played (existing `wrLineup`). Cap from existing `wrCapFor(ta)` (default 23 for 8-Ball and 9-Ball; typed value overrides; blank turns the check off).
- Five selected, all skill levels captured: "Skill total T of 23: within the cap" or "T is N over 23". With the existing reference caveat ("required sends and other match rules not verified").
- Five selected, a skill level missing: "Cannot verify: k selected player(s) have no captured skill level".
- Fewer than five: "k of 5 chosen, total T, R left under 23" (known values only, missing named). More than five: "More than five marked".
- A selected player marked Out: named as a conflict.
- Left out: Here players not selected; Out players listed separately.
- 4-player/19 fallback: not shown in the MVP (existing classic Match Night logic covers it); a one-line pointer only when five is impossible and five-player options are exhausted (**D3**: include or defer).

**Files touched.**
- `ui/ultimate_coach_war_room.js`: add `wrFiveCheck` beside `wrPlan` (around line 433), call it from the Lineup Lab render (around line 1610), add hook `window.__ucFiveCheck`.
- `ui/ultimate_coach_broadcast.py`: CSS for the new block only.

**Screens affected.** Team Status tab (Broadcast) and the Lineup Lab card on the classic page.

**Tests.**
- Browser (`tests/test_ultimate_coach_war_room_browser.py`, extending the Lineup Lab test; one Broadcast flow case in `tests/test_ultimate_coach_broadcast_browser.py`): within, over, unknown skill, four selected, six selected, cap overridden, cap off, selected-but-Out conflict, left-out list correctness; existing Snapshot text unchanged.
- Reference cross-check: a table of complete fives evaluated by `__ucFiveCheck` and by `analytics/lineup_legality.check_lineup_legality`; verdicts must agree on within, over and unknown.
- Unchanged and must still pass: `tests/test_excel_war_room_formulas.py`, `tests/test_lineup_legality.py`, `tests/test_war_room_js_mirror.py`.

## 3. Priority 2: Risk Briefing

**What.** A pure function `wrBriefing(w, ck, ta, five)` returning a list of `{kind, text, source}` and one block `#ll-briefing` under the Five check. MVP alerts are **facts only**:
1. Players marked Out (names).
2. Selected players without a captured skill level.
3. Short recorded history: players in the five with fewer than a stated minimum of recorded games in this format (uses the evidence-row count already shown in the roster table; threshold constant stated on the page, **D4**: proposed 10, following the project's existing "small sample" idiom).
4. Cap position: slack under the cap, or over by N (from the Five check).
5. Opponent roster: players without a captured skill level; opponent players marked absent (existing opponent marks).
6. Data trust: quarantined games and source coverage issue counts from the existing payload `trust` block; omitted when zero.
Each line names its source field. No numeric score, no ranking. Tentative interpretations (cold streak) are **not** in the MVP; the factual/tentative distinction is built into the data shape so Form labels could use it later.
- Empty state: "Checked: availability, skill levels, recorded games, cap, opponent marks, data trust. Nothing flagged."

**Files touched.** `ui/ultimate_coach_war_room.js` (function, render, hook `__ucBriefing`), `ui/ultimate_coach_broadcast.py` (CSS).

**Screens affected.** Team Status tab and classic Lineup Lab card.

**Tests.** Browser: each alert appears and clears as marks, skill levels or cap change; every alert shows its source; empty-state text; no score or probability wording anywhere in the block; Out and unknown-skill cases reuse the Five check fixtures. No Python test needed (no Python change).

## 4. Priority 3: Real Player Form

**What.** A helper `formFor(pid, fmt)` in the shared page script and two new roster-table columns.

**Behaviour.**
- Uses `rowsFor(pid, fmt)` (dated per-game results already in the page), sorted by `match_date` first because the index order is not guaranteed; same-date games keep their stored order.
- Output: last 5 as a W/L strip with the count of games shown, last-10 win rate with n, recorded-games win rate with n. Fewer than 5 games: "not enough games (n)". Format-isolated: switching 8-Ball and 9-Ball changes the figures; never pooled.
- Labelled "recorded games" (archive-captured, not lifetime). No hot or cold label, no trend arrow, no "form" score. The skill-level trend is not relabelled.
- Also adds a "Last 5" column to the Lineup Lab table for our players so the choice of five sees it.

**Files touched.**
- `ui/ultimate_coach.py`: `formFor` next to `rowsFor` (around line 1013); two columns in `rosterTable` (around line 1256); hook `window.__ucForm`.
- `ui/ultimate_coach_war_room.js`: the extra Lineup Lab column.

**Screens affected.** Team Status roster tables for both teams, Lineup Lab, classic page roster cards.

**Tests.** Browser plus reference cross-check: the same rows through `__ucForm` and through `analytics/player_stats.recent_form` give the same W/L string; sorting regardless of input order; minimum-sample text; format isolation; opponent table renders the same columns. Existing roster-table assertions updated only for the added columns.

## 5. Priority 4: What-If

**What.** A pure function `wrSwapDiff(w, ck, cap, outId, inId)` and a small control in the Lineup Lab: choose a Planned player to swap out and a left-out Here player to swap in; the result shows beside the current Five check.

**Behaviour.** Exact difference only: who comes in and out, skill total before and after, within or over the cap and cannot-verify state, the Risk Briefing lines that appear or disappear, and both players' last 5. A Reset button clears the comparison. **It never changes a mark**; the real selection changes only if the captain then changes the Lineup selects as today. No planner call and no outcome claim in the MVP (**D5**: whether to add a labelled M3 planner summary for the swapped five later).

**Files touched.** `ui/ultimate_coach_war_room.js` (function, control, hook `__ucSwapDiff`), `ui/ultimate_coach_broadcast.py` (CSS).

**Screens affected.** Team Status tab and classic Lineup Lab card.

**Tests.** Browser: swap diff arithmetic exact; swap into an over-cap total flagged; unknown-skill swap; reversible via Reset; marks and evidence unchanged after any swap (assert the stored marks before and after); swap controls disabled when no valid pair exists.

## 6. Files touched (all four)

| File | Change |
|---|---|
| `ui/ultimate_coach_war_room.js` | `wrFiveCheck`, `wrBriefing`, `wrSwapDiff`, Lineup Lab render additions, three test hooks |
| `ui/ultimate_coach.py` | `formFor`, two roster-table columns, one test hook |
| `ui/ultimate_coach_broadcast.py` | CSS for the new blocks and columns |
| `tests/test_ultimate_coach_war_room_browser.py` | Five check, briefing, form, swap cases |
| `tests/test_ultimate_coach_broadcast_browser.py` | one end-to-end flow case for Team Status |

Not touched: `analytics/*`, `analytics/match_night_engine.py` (M3), the payload builders, Excel exporters, the web app, the archive or any database.

## 7. Test strategy summary

- All new behaviour is covered by browser tests on the existing synthetic all-categories fixture (no real data in tests).
- Three reference cross-checks against existing Python (legality verdicts, W/L strip) so the JavaScript arithmetic cannot drift.
- Regression gate before review: the three existing suites (404 tests at `6d74dc8`) plus `tests/test_lineup_legality.py`, `tests/test_excel_war_room_formulas.py`, `tests/test_war_room_js_mirror.py` must pass unchanged except the roster-column assertions.
- Visual check on phone width in the built-in browser, light and dark, using the existing screenshot routine.

## 8. Expected size and order of work

About 310 lines of product code and 380 of tests (from the build-versus-connect assessment). Order: Five check, then Briefing (reuses its fixtures), then Form, then What-If; each lands as its own commit so any can be dropped.

## 9. Open decisions for review

D1 verdict wording versus the "not a lineup-legality check" contract; D2 Excel parity out of scope; D3 4-player/19 pointer now or later; D4 short-history threshold (proposed 10 recorded games); D5 optional planner summary in What-If. Also: confirm placement on Team Status rather than Home, and that a new Sunday file is built only after review.
