# Build versus connect assessment (four P1 items)

Basis: `CAPTAIN_VALUE_CURRENT_STATE.md` (same folder) and a read of the code on the Broadcast branch. Estimation only: no design, no UI or code change, no deployment, no merge. No player or team names.

**How the percentages were made.** Each feature is split into data and calculation plumbing, screens, and tests, then judged by remaining effort (lines of code and tests I expect, not features named). They are engineering estimates from reading the code, not measurements; treat them as plus or minus 10 points. "Implemented" means working today and tested; "wiring" means existing pieces that must be linked or rendered; "new" means logic or structure that does not exist.

## 1. Estimates

| P1 item | Already implemented | Integration / wiring | Truly new code | Expected size of the remaining work |
|---|---|---|---|---|
| Real Player Form | 75% | 15% | 10% | about 60 lines of JavaScript (window function, roster cell), about 100 lines of tests |
| Captain Risk Briefing | 70% | 15% | 15% | about 90 lines (alert rules, card), about 100 lines of tests |
| Tonight's Five Advisor | 70% | 20% | 10% | about 40 lines (verdict, left-out line, optional form columns), about 80 lines of tests |
| Roster What-If | 55% | 20% | 25% | about 120 lines (second selection, diff renderer), about 100 lines of tests; logging needs new architecture (section 4) |
| **Four together (effort-weighted)** | **about 68%** | **about 17%** | **about 15%** | roughly 310 lines of product code, 380 lines of tests |

## 2. Does the assessment hold?

**Confirmed, with two qualifications.** Most of the remaining work is integration. The data (dated per-game results with skill levels and points), the cap and legality logic, the availability and Planned marks, the trust and coverage numbers, and the plan recompute all exist and are tested. The truly new code is small: a window function, a verdict line, an alert list, a diff view.

Qualifications:
1. **Roster What-If is the least integration-heavy** (55 / 20 / 25) because a five-versus-five comparison is a new view, and storing alternative fives or a log of the chosen five is new architecture.
2. **Wording and rules are real work even when code is small.** Any hot or cold label needs a stated, sample-guarded rule, and every alert needs a source field. Those are decisions, not wiring.

## 3. Minimum files and fastest MVP

| Item | Minimum files | Fastest MVP |
|---|---|---|
| Real Player Form | `ui/ultimate_coach.py` (`rosterTable`, near `rowsFor`), `tests/test_ultimate_coach_broadcast_browser.py` (plus a small parity check against `analytics/player_stats.py::recent_form`); CSS in `ui/ultimate_coach_broadcast.py` if styled | Roster-table cell showing the last 5 results as a W/L strip, last 10 and lifetime win rate and the number of games, per format, descriptive only. Sort rows by `match_date` first (the index is not guaranteed ordered). No hot or cold label. |
| Captain Risk Briefing | `ui/ultimate_coach.py` or `ui/ultimate_coach_war_room.js` (one card renderer), `ui/ultimate_coach_broadcast.py` (place it under Home or Summary), one test file | Card of existing facts: players with unknown availability, players with few evidence rows (the count already in the roster table; no form function needed), players with no captured skill level, cap slack, the data-trust counts and stale-fixture sentence. Each line names its source. |
| Tonight's Five Advisor | `ui/ultimate_coach_war_room.js` (the Lineup Lab block that renders the Planned select and "Selected lineup"), one test file | When five players are marked Planned: show total versus 23 with legal, illegal or "cannot verify" (unknown skill level), and list who is left out. Cross-check the arithmetic against `analytics/lineup_legality.py`. The 4-player/19 note can follow. |
| Roster What-If | `ui/ultimate_coach_war_room.js`, one test file | Second selection of five beside the first; show the exact difference (who is in and out, cap total and slack, legality). Reuse the existing plan recompute for an optional planner summary, labelled as the planner view. |

All four live in code shared by the classic cockpit page and the Broadcast page, so each change appears on both unless filed to a tab with the existing `bc.tag` mechanism.

## 4. Ship immediately versus new architecture

**Can ship immediately (existing data and logic only):**
- Risk Briefing MVP (facts only).
- Player Form strip and rates (descriptive; no label).
- Five Advisor legal verdict and left-out line.
- What-If difference of two fives (cap, slack, legality, who changes).

**Needs new architecture or a decision first:**
- **Persistence of the pool and chosen five.** Marks live in the browser only (local storage). A prospective study of roster advice needs a durable log: a server or exported file. This is new architecture and a product decision.
- **Hot and cold labels.** Need a written rule, sample guard and validation before use; not code.
- **Web app and Excel parity.** The Next.js app and Excel companion do not run this JavaScript. Showing these features there means separate implementations or a shared payload field.
- **Ranking alternative fives** (as opposed to listing them with factual columns): would need an outcome model the evidence rules do not allow.
- **Playoff or qualification impact** and **points per player**: blocked by evidence rules and missing data, not by integration.

## 5. Order and dependencies

1. Five Advisor verdict and Risk Briefing MVP can start now in parallel (no dependency on the form cell).
2. Player Form cell next; once it exists, the Briefing can swap evidence-row count for the games-in-window flag and the Five Advisor can show form columns.
3. What-If after the Five Advisor (it reuses the same selection).
4. Logging and any label rules only after those ship and captains have used them.

## 6. Assumptions

- Effort figures assume one engineer who knows the code, existing browser-test harness (35 tests in the Broadcast browser suite, 404 across the three suites at `6d74dc8`) and no new dependencies.
- The shared cockpit script remains the single place for these features.
- No claim is made that any of these features improves match results.
