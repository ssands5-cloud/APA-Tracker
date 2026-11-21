# Captain Value: what exists today (gap analysis, not a redesign)

Method: read the code on the Broadcast branch (`claude/uc-broadcast-ui` at `6d74dc8`, which contains everything on `main` and `feat/phase1-war-room`; no other branch holds an implementation of these features) and inspected the embedded data of the Sunday Broadcast file (counts only, no names). Audit only: no UI, code, production, deployment or merge. Contains no player or team names.

## 0. Corrections to my earlier audit and matrix

Two statements in `CAPTAIN_VALUE_AUDIT_AND_ROADMAP.md` and `CAPTAIN_ACCEPTANCE_MATRIX.md` were too pessimistic after this deeper read:

1. **"The Broadcast payload has no per-player dated games" is wrong.** The cockpit payload embeds an `evidence_index` of dated per-game results for every player (hundreds of thousands of rows, 2011 to 2026-11-17; fields `opponent_id, match_date, session_name, result, own_skill_level, opponent_skill_level, points_earned`; EIGHT and NINE only). The browser already has `rowsFor(playerId, format)` over it. Real Player Form needs **no payload change**.
2. **"Nothing lets a captain select a five" is wrong.** The cockpit's Lineup Lab (`id="lineup-lab"`, filed under the Team Status tab in Broadcast) already has per-player Availability and Lineup (Planned / Played) selects, a "Selected lineup" skill total, and a user-entered reference cap. What is missing is the live 23-Rule verdict on that selection.

Net effect: the four P1 items are mostly **connecting** work, not building.

## 1. Real Player Form

| | Today |
|---|---|
| **Existing files** | `analytics/ultimate_coach_payload.py` (players, `career_stats`, `team_history`, evidence rows), `analytics/ultimate_coach_data_contract.py` (`all_games`), `analytics/ultimate_coach_player_profiles.py`, `analytics/player_stats.py` (`recent_form`, `summarize_player`), `analytics/player_trends.py`, `trend_analyzer.py`, `skill_level_trends.py`, `analytics/ultimate_coach_war_room.py` (`sl_bucket_index`, `meetings_index`), `ui/ultimate_coach.py` (`rowsFor`, `oppMap`, `rosterTable`), `ui/ultimate_coach_war_room.js` (scouting cards), `ui/tabs/trends.py`, `ui/tabs/trend_analyzer.py`, `ui/export_excel*.py` |
| **Existing screens** | Broadcast Team Status roster table (SL, season team W-L, evidence-row count); Threats and Recommendations cards (lifetime record, sample size, vs-ours record); classic dashboard SL sparkline and trend filters; Streamlit Trends and Trend Analyzer tabs; Excel sheets Player Trends, Players, Sample_Sizes |
| **Existing APIs** | No HTTP API. Interfaces are the cockpit payload `ultimate-coach-verified-cockpit-v1` (compact v2), the in-browser `rowsFor`, Python `build_player_profile` and `build_contract` |
| **Existing data** | Dated per-game results with skill levels and points per player and format; `career_stats` per format (wins, played, last played, matches in last two years, break-and-runs, rackless, skunks); `team_history` per scope; identity-verified game counts and quarantined games in `trust` |
| **Existing calculations** | Lifetime and per-scope W-L; per-opponent and per-opponent-skill-level records; skill-level slope, volatility and HOT/COLD (skill movement only, minimum 5 observations); `recent_form` last-N W/L string and win percentage and average points (Python, wired only to exports) |
| **Missing** | Results-based last 5 and 10 in any captain screen; a stated, sample-guarded rule for any hot or cold wording; side-by-side 8-Ball and 9-Ball per player |
| **Already working** | Format-isolated, identity-verified data; lifetime and opponent records; skill-trend engine with spec and tests (`test_player_trends.py`); profiles with as-of boundary (`test_ultimate_coach_player_profiles.py`) |
| **Connect vs build** | **Connect:** a windowing function over the existing rows (JavaScript over `rowsFor`, mirrored or checked against Python `recent_form`) and one roster-table cell. **Build:** only the label rule and its wording. |

## 2. Captain Risk Briefing

| | Today |
|---|---|
| **Existing files** | `analytics/data_coverage.py`, `analytics/ultimate_coach_evidence_quality.py`, `ultimate_coach_data_contract.py` (coverage issues), `analytics/match_night_engine.py` (fragility, cap safety), `analytics/lineup_risk.py`, `opponent_risk_profile.py`, `opponent_volatility.py`, `ui/export_excel_data_coverage.py`, `ui/export_excel_ultimate_coach.py` (Data Trust sheet), `ui/ultimate_coach_war_room.js` (`mnCapSafety`, fragility text, `wrLiveThreats`) |
| **Existing screens** | Broadcast Summary tab (league table and results, plus `trust-section`); Threats tab (risks list, scouting cards, matchup notes); Match Night plan card (fragility rating, cap safety, "availability unknown" at the decision, thin pairings); Streamlit Data Coverage tab; Excel Data Trust sheet |
| **Existing APIs** | Payload `trust` block (verified identities, exclusions, quarantined games, source coverage issues, total game rows) and `match_day.coverage` (fixture counts, date status counts, missing locations, byes); plan JSON from the engine |
| **Existing data** | Those counts; current and per-scope skill levels; availability marks; per-pair evidence level and sample; stale-fixture facts |
| **Existing calculations** | Evidence levels; fragility rating and the player the plan leans on; cap slack and cheapest-rest; coverage report (direct, indirect, unknown counts; missing skill levels named); stale-snapshot sentence; skill-level volatility index |
| **Missing** | One consolidated list of factual alerts for tonight in the Broadcast (unconfirmed availability, short histories, unknown or recently changed skill level, partial coverage, stale data); per-player short-history flags (need the form function above) |
| **Already working** | Every ingredient above is built and tested; the Summary tab already carries the data-trust section |
| **Connect vs build** | **Connect:** gather existing values into one card. **Build:** the alert rules and the factual-versus-tentative styling. No new data. |

## 3. Tonight's Five Advisor

| | Today |
|---|---|
| **Existing files** | `analytics/lineup_legality.py` (`check_lineup_legality`, `legal_completion_exists`, `assess_completion_options` with the 4-player/19 fallback), `analytics/lineup_lab.py` (skill-only assignment against an opponent), `analytics/match_night_engine.py` (`_Night.legal`, planner over the available pool), `ui/ultimate_coach_war_room.js` (`wrCapFor`, `wrAvail`, `wrLineup`, `wrRemaining`, `wrLineupBudget`, cap safety), `ui/ultimate_coach.py` (Lineup Lab block), `ui/dashboard.py` (Match Night legality mirror, "valid finish"), `ui/tabs/tonights_match.py` |
| **Existing screens** | Broadcast Home (Here/Out per person, cap default 23, toss and put-ups); Team Status (roster tables and **Lineup Lab** with Availability and Lineup selects, "Selected lineup" skill total, "Remaining skill total", "Roster flexibility"); classic dashboard Match Night ("compare your legal options", valid finish, 5/23 and 4/19 messages); Streamlit Tonight's Match matrix with availability checkboxes; Excel Lineup sheet |
| **Existing APIs** | `assess_completion_options(committed, available)` returning a tri-state for each path; JS mirror of the cap and legality logic; plan JSON |
| **Existing data** | Roster with current skill level per format (unknown handled as unknown), Here/Out and Planned/Played marks, cap, opponent roster, evidence per pair |
| **Existing calculations** | Exact five-player/23 verdict for a complete lineup; legal-completion existence for a partial one; cheapest remaining total and slack; planner choices from the remaining pool; skill-only Lineup Lab assignment |
| **Missing** | A **live legality verdict on the Planned selection** (the Lineup Lab shows a total against a user-entered, "not verified" cap, with no legal or illegal answer); a "who is left out" line; form and coverage columns beside the selection (from the form function) |
| **Already working** | Legality arithmetic and tests (`test_lineup_legality.py`), the Planned selection itself, availability, cap default, tri-state for unknown skill levels |
| **Connect vs build** | **Connect:** feed the Planned selection to the existing legality logic and show its verdict; add form and coverage columns. **Build:** nothing new in logic; a small verdict line and left-out list in the existing Lineup Lab. Comparing alternative fives is not built (see 4). |

## 4. Roster What-If

| | Today |
|---|---|
| **Existing files** | `ui/ultimate_coach_war_room.js` (`mnPlanFor` with memoised solves, `wrLineupBudget`, Send instead and Put up instead handling), `analytics/match_night_engine.py` (`match_plan`, response tables), `ui/ultimate_coach_broadcast.py` (render), web app `plan-board.tsx`, `captain-command.tsx` and the response and opening-cost pages with their tests |
| **Existing screens** | Broadcast Here/Out (mark someone out and the whole plan and cap recompute); "Compare all options and risks"; Send instead / Put up instead dropdowns; "They threw" one-tap pairing; web Match Night response explorer and opening cost |
| **Existing APIs** | Plan recompute from any availability state; after-send plan per candidate; cap slack after each send |
| **Existing data** | Same as the Five Advisor |
| **Existing calculations** | Plan from the remaining pool, response table per opponent put-up, cost of an opening choice, "sending keeps legal", fragility |
| **Missing** | A **five-level** swap view: the exact difference between two fives (cap total and slack, form, coverage, legality) and a reversible compare; no stored alternative fives |
| **Already working** | Absence what-ifs (mark Out) and per-game what-ifs (send or put up instead) are complete, memoised and browser-tested |
| **Connect vs build** | **Connect:** reuse the plan recompute and `wrLineupBudget` for a swapped five. **Build:** the two-five diff renderer (small), plus logging the pool and chosen five so a later study is possible. |

## 5. Connect versus build summary

| P1 item | Connect (existing, unlinked) | Truly new |
|---|---|---|
| Real Player Form | dated rows already embedded; `rowsFor`; `recent_form`; roster table | windowing function and label rule |
| Captain Risk Briefing | `trust`, `match_day.coverage`, fragility, cap safety, availability unknowns, evidence gates, stale notice | alert rules and card styling |
| Tonight's Five Advisor | Lineup Lab Planned selection, `lineup_legality`, JS cap logic, Here/Out | verdict line, left-out list, form columns |
| Roster What-If | plan recompute, `wrLineupBudget`, Out/Here toggles | two-five diff view and selection log |

## 6. What this does not change

- Evidence rules still apply: no probabilities, no expected points, no claim that a recommended five improves results (the bench is unrecorded, so that is untestable on the archive).
- Existing HOT/COLD means skill-level movement, not winning; it must not be presented as form.
- Estimates of effort in the matrix drop by roughly one step for these four items; the order stays Form, then Risk Briefing and Five Advisor, then What-If.
