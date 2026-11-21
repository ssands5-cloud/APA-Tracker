# Captain Value: reuse-first audit and roadmap (plan only)

Author: Claude. Date: 2026-11-20. Scope: audit and plan. No UI change, no code change, no deployment, no merge. M3 and the Broadcast UI stay as they are. Contains no player or team names and no row-level data.

The 25-question acceptance matrix is in `CAPTAIN_ACCEPTANCE_MATRIX.md`.

## 0. Evidence rules the product must respect

From the M3 studies (branch `claude/m3-validation-research`):
- Player form (lifetime win rate, own and opponent) carries most game-level signal; the skill gap adds some in 8-Ball and little in 9-Ball. Last-10 form is redundant with lifetime form in 8-Ball and adds a small amount in 9-Ball.
- The team signal in M3 comes from who plays, not how they are paired. That supports building the roster-selection surface. It does **not** prove that choosing a different five improves results: the bench is unrecorded, so that is untestable on the archive.
- Probability publication is forbidden by project contract (`docs/ULTIMATE_COACH_EVIDENCE_QUALITY_CONTRACT.md`). No win probability, no "expected points", no claim of improved results in any of the features below.

## 1. Reuse-first capability audit

| Capability | What already exists | Data already available | Reusable now | Gaps | Redundant or misleading |
|---|---|---|---|---|---|
| **Player Trends** | `analytics/player_trends.py` (skill-level slope, volatility over last 20, HOT/COLD flag, min 5 observations), `analytics/trend_analyzer.py`, `analytics/skill_level_trends.py`, `scripts/build_player_trends.py`, `player_trends` table, Excel sheets, `ui/tabs/trends.py`, `ui/tabs/trend_analyzer.py`, tests `test_player_trends.py`, `test_trend_analyzer*.py` | `PlayerMatch.skill_level` per match with format and session | The whole SL-trend engine and its spec and thresholds | It tracks **skill level** movement, not winning. Its own docs say points and results are not inputs. Not shown in the Broadcast UI or the web app. HOT/COLD here means "SL rising", which captains may read as "playing well". | Three modules cover SL trend (`player_trends`, `trend_analyzer`, `skill_level_trends`); do not add a fourth. |
| **Captain's Edge** | `analytics/captains_edge.py` (static one-to-one ranking, Fij), `captains_edge_summary.py`, `ui/tabs/captains_edge.py`, Excel export, `docs/captains_edge.md` | Per-pairing scores from stored H2H and trends | Summary rollups (strongest pairings, danger matchups, anchors) as descriptive reference | Uses the September composite whose `matchup_score` was never validated. Not wired into the Broadcast UI. Matchup-centred, not roster-centred. | Superseded for live nights by M3 (kept as frozen reference); do not extend. |
| **Roster recommendations** | `analytics/lineup_lab.py` (skill-only "approved best lineup"), `lineup_optimizer.py`, `ui/tabs/tonights_match.py`, `scripts/build_captain_first_edge.py`; Broadcast UI: per-game picks from M3 with the cap enforced; Here/Out per player | Roster, skill levels, availability marks, evidence per pair | The cap-aware candidate generation and the Here/Out state in `ui/ultimate_coach_war_room.js` | Nothing answers "who is my best five tonight". Lineup Lab and M3 both assign opponents; neither compares fives. | Lineup Lab, Captain's Edge and M3 are three matchup assigners; the roster advisor must not be a fourth. |
| **Player form metrics** | `analytics/player_stats.py` (`summarize_player`, `recent_form` last-N W/L string), `analytics/ultimate_coach_player_profiles.py` (verified, format-isolated, as-of profiles: observed record, skill history, opponent history, provenance), `analytics/ultimate_coach_evidence_quality.py`; cockpit payload `career_stats` (league-scoped lifetime record per format scope) | `all_games` contract rows with dates, results and skill levels (`analytics/ultimate_coach_data_contract.py`); `player_matches`; archive 2011 to 2026 | Profiles and `recent_form` are the right bases; lifetime record already flows to the phone | `recent_form` is used by no UI (only `summarize_player` is, in exports). Profiles are consumed by no component. The Broadcast payload carries a count of all games, not per-player dated recent games. No hot/cold derived from results. | None; the pieces are unconnected, not duplicated. |
| **Availability tracking** | Broadcast: Here/Out per person per night, shared across 8-Ball and 9-Ball on the same date, opponent check-in, "availability unknown" flagged at the decision; `docs/captains_live_assistant.md` | Marks stored per scope and night in the war-room state | All of it | No whole-team readiness summary ("who is confirmed, who is unknown, who is out") at a glance; no persistence beyond the browser. | The earlier Bench section was removed as a duplicate of Here/Out; do not reintroduce. |
| **Risk scoring** | `analytics/lineup_risk.py` (per-lineup upset risk, anchor stability), `opponent_risk_profile.py`, `opponent_volatility.py`, `data_coverage.py` (coverage and what cannot be known), evidence quality gates, M3 fragility and cap-safety notes, "Unknown does not mean safe" wording | Coverage, evidence level per pair, SL volatility | Data Coverage report and evidence labels as the factual-alert backbone; M3 fragility and cap safety | No captain-facing roster-level briefing that merges missing availability, short histories, uncertain skill levels and cold streaks. `lineup_risk` rests on the unvalidated composite. | Do not reuse `lineup_risk` numbers as a headline; reuse only factual coverage items. |
| **23-rule validation** | `analytics/lineup_legality.py` (`check_lineup_legality`, `legal_completion_exists`, `assess_completion_options` including the 4-player/19 fallback), `docs/lineup_legality.md`, `tests/test_lineup_legality.py`, JS mirror in `ui/ultimate_coach_war_room.js` (`wrCapFor`), cap default 23 in Broadcast, roster table shows who is left | Skill levels (unknown handled as tri-state) | All of it, unchanged | A five-chooser UI that shows the verdict live while selecting; a "which swaps keep it legal" helper (the module answers per pool; no swap list). | None. |
| **Bench decision support** | M3 hold-backs and designated answers, "what the plan loses without them" in the web command board, Compare-all-options, cap slack | Plan outputs from M3 | Existing explanations of who is saved and why | Nothing for "who should I leave out of my five and what changes": the M3 outputs are per-game, not per-roster. | Do not rebuild the planner. Present roster-level evidence only. |

## 2. Reusable component inventory (files, APIs, data)

- **Python:** `analytics/lineup_legality.py`, `analytics/player_stats.py::recent_form`, `analytics/ultimate_coach_player_profiles.py::build_player_profile`, `analytics/data_coverage.py::build_report`, `analytics/ultimate_coach_evidence_quality.py`, `analytics/player_trends.py::hot_cold_flag` (SL only), `analytics/ultimate_coach_data_contract.py::build_contract` (`all_games`), `analytics/ultimate_coach_war_room.py` (payload builder; player rows carry `career_stats`).
- **JavaScript (Broadcast, phone):** `ui/ultimate_coach_war_room.js` (`wrSetAvail`, `wrAvail`, `wrRemaining`, `wrCapFor`, `WR_PLAN`), `ui/ultimate_coach_broadcast.py` (render, header, roster table).
- **Web app (Next.js):** `apps/ultimate-coach-web/src/lib/snapshot-types.ts` (`Player`, `Snapshot.simulation.cap`), `components/captain-command.tsx`, `team-status` page.
- **Tests:** `tests/test_lineup_legality.py`, `tests/test_player_trends.py`, `tests/test_ultimate_coach_player_profiles.py`, `tests/test_ultimate_coach_broadcast_browser.py`, `apps/ultimate-coach-web/tests/*`.
- **Data:** archive tables `matches`, `player_matches` (result, points, skill level, date), `player_head_to_head`; contract `all_games` with `event_time`; cockpit `career_stats`.

## 3. What is genuinely missing (and only that)

1. A per-player, per-format **results-based form** surface (record last 5 and 10, lifetime, trend, sample size, coverage). Data exists in `all_games`; nothing carries it to the captain.
2. A **roster-level** surface: choose five of the Here players, see the cap verdict, the form, the evidence coverage, and what is lost or gained by a swap.
3. A **briefing** that assembles factual alerts already computed elsewhere.

## 4. Roadmap for the four gaps

Order: Real Player Form (foundation), then Tonight's Five Advisor and Roster What-If (one shared panel, two modes), then Captain Risk Briefing. Each step is shippable on its own and keeps M3 untouched.

### Gap A: Real Player Form (effort: Medium)
- **Reuse:** `ultimate_coach_data_contract.build_contract` `all_games`; `player_stats.recent_form`; `ultimate_coach_player_profiles` (format isolation, as-of boundary, provenance); `evidence_quality` fail-closed rules.
- **New (minimal):** one pure function that turns a player's dated `all_games` into form rows (last 5, last 10, lifetime, direction, n, coverage flag) and a compact `form` field added to each cockpit player row (proposed file `analytics/ultimate_coach_player_form.py`; payload change in `analytics/ultimate_coach_war_room.py`). Labels such as hot or cold only with a stated rule and a minimum sample; otherwise "not enough games".
- **Data dependencies:** `all_games` rows with dates; format separation EIGHT and NINE; archive coverage gaps disclosed per player (partial capture).
- **Components:** roster-table form cell (last 5 as a W/L strip, last 10 rate, lifetime rate, n) in the existing Broadcast roster table; no new screen.
- **Acceptance:** (1) every number traces to listed game keys; (2) 8-Ball and 9-Ball never mixed; (3) fewer than the minimum games shows "not enough games", never a trend; (4) coverage gap named when history is partial; (5) no probability or "expected" wording; (6) existing SL-trend labels are not relabelled as form; (7) figures strictly before the viewed date when browsing past nights.
- **Tests:** unit tests for window math, ties and forfeits, minimum sample, format isolation, as-of boundary; Python versus JS parity if any computation is mirrored; Broadcast browser test for the cell; reconciliation check that dated results sum to `career_stats`.
- **Evidence note:** lifetime form is the strongest game-level signal measured; last-10 adds little in 8-Ball. Present recent form as description, not as a stronger predictor.

### Gap B: Tonight's Five Advisor (effort: Medium to High)
- **Reuse:** Here/Out state (`wrAvail`, `wrRemaining`), `lineup_legality` verdicts and the JS `wrCapFor`, roster table, Gap A form cells, evidence labels.
- **New (minimal):** a five-selection panel inside the Broadcast Home/Match Night setup: pick five of the Here players; live cap total and verdict; per-player form and evidence coverage; "who is left out". No ranking by predicted win. Suggestions only as factual sorts the captain controls (by form, by skill level, by availability).
- **Data dependencies:** skill levels (tri-state for unknown), Here/Out marks, Gap A form fields.
- **Acceptance:** (1) an illegal five is flagged immediately with the exact total and the cap; (2) unknown skill levels give "cannot verify", not "legal"; (3) the 4-player/19 path is explained when five is impossible; (4) the panel never says a five "will win" or shows odds; (5) the chosen five can be handed to the existing night flow without retyping.
- **Tests:** reuse `test_lineup_legality.py` cases through the JS mirror; browser tests for select, swap, over-cap, unknown-skill and fewer-than-five-available cases.

### Gap C: Roster What-If (effort: Medium; builds on B)
- **Reuse:** the same panel and `lineup_legality`.
- **New (minimal):** swap one player and show only what changes factually: cap total and slack, form cells, evidence coverage, whether the five stays legal; optionally the M3 plan summary for the new five as reference, labelled as the planner's view, not a result forecast.
- **Acceptance:** (1) the diff between the two fives is exact and reversible; (2) no outcome claims; (3) when M3 output is shown, it carries the existing evidence wording and the frozen-benchmark label.
- **Tests:** browser tests for swap, undo, illegal swap; deterministic diff unit test.
- **Caution:** whether better-looking fives win more is untestable on the archive (bench unrecorded). The feature should log the available pool and the chosen five so a prospective study becomes possible.

### Gap D: Captain Risk Briefing (effort: Low to Medium)
- **Reuse:** `data_coverage` report, evidence-quality gates, M3 fragility and cap-safety text, Here/Out unknowns, `skill_level_trends` volatility, Gap A short-history flags.
- **New (minimal):** one pre-match briefing card listing factual alerts only: unconfirmed availability, players below the minimum sample, unknown or recently changed skill levels, cap slack, partial-history coverage. Interpretations (cold streak) are labelled tentative and shown only above the minimum sample.
- **Acceptance:** (1) every alert names its source field; (2) factual and tentative alerts are visually distinct; (3) no numeric risk score; (4) the empty state says what was checked.
- **Tests:** unit tests for each alert rule with fixtures; browser test for factual versus tentative styling; no-alert and many-alert states.

### Measurement (no outcome claims)
Captain Value Scorecard as proposed: time to a legal five, availability errors caught, five-second comprehension, captain feedback. Add a prospective log (pool, chosen five, result) from the start; it is the only route to a later test of roster-advice value.

## 5. Captain review matrix (25 questions)

Completed in `docs/captain_value/CAPTAIN_ACCEPTANCE_MATRIX.md` (matrix, dependency map, four gaps, order, risks).

## 6. Frozen
M3, M4/M5/M6, matchup weights, ESPN visual standards (no redesign), production, deployment, merges.
