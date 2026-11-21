# Captain acceptance matrix (25 questions)

> Note (2026-11-20): see `CAPTAIN_VALUE_CURRENT_STATE.md` section 0, which corrects two statements here: dated per-player game rows are already embedded in the Broadcast payload, and the cockpit Lineup Lab already offers a Planned selection. Gap effort for Real Player Form, the Five Advisor and What-If is lower than stated below.

Baseline: `docs/captain_value/CAPTAIN_VALUE_AUDIT_AND_ROADMAP.md` (same branch). Audit and plan only: no UI, code, production, deployment or merge. Reuse-first: every "Missing" entry is only what the repository cannot already do. No player or team names.

Status rule: **Solved** = a shipped captain-facing screen answers it from recorded evidence today. **Partially** = the data or a module exists but the captain-facing answer is incomplete or unconnected. **Not Solved** = neither exists, or the project forbids the claim. Effort: Low = wiring or wording, Medium = a payload field plus a screen element, High = a new interactive surface or new data capture. Priority: P1 = the four highest-value gaps, P2 = finish or connect, P3 = keep, polish only, W = withhold (evidence rules).

Gap keys: **A** Real Player Form, **B** Tonight's Five Advisor, **C** Roster What-If, **D** Captain Risk Briefing.

## 1. Acceptance matrix

| # | Question | Status | Existing files / components | Existing data | Reusable | Missing | Effort | Acceptance criteria | Priority |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Who should be in my five tonight? | Not Solved | Broadcast per-game picks (`ui/ultimate_coach_broadcast.py`, `ui/ultimate_coach_war_room.js`); Lineup Lab (`analytics/lineup_lab.py`) assigns opponents, not fives | Roster, skill levels, Here/Out | Here/Out state, `lineup_legality`, roster table | A five-selection panel (no ranking by predicted win) | High | Captain picks five of the Here players; panel shows cap verdict, form and coverage; no odds or "will win" wording | P1 (B) |
| 2 | Who is actually available tonight? | Solved | Here/Out per person per night, shared across 8-Ball and 9-Ball, opponent check-in (`wrSetAvail`, `wrAvail`, `wrRemaining`) | Captain-entered marks | All | Team-wide readiness summary; persistence beyond the browser | Low | Everyone Here by default; Out marks recompute plans; unknown availability named at the decision | P3 (feeds D) |
| 3 | Who is playing their best pool right now? | Partially | `player_stats.recent_form`; profiles (`ultimate_coach_player_profiles.py`); lifetime record in cockpit `career_stats` | `all_games` dated results; `player_matches` | Profiles, `recent_form` | Results-based last 5/10 and lifetime form carried to the phone | Medium | Last 5/10 and lifetime per player per format, n shown, tied to game keys; below minimum games shows "not enough games" | P1 (A) |
| 4 | Who is slumping? | Not Solved | `player_trends.py` HOT/COLD is skill-level movement, not results | `all_games` | Sample-size rules from `player_trends` | A results-based, sample-guarded cold label (tentative wording); the SL flag must not be relabelled as slump | Medium | Label only above a stated minimum sample, tentative style, rule shown; SL trend never called form | P1 (A) |
| 5 | Which players are improving fastest? | Partially | `player_trends.py`, `trend_analyzer.py`, `skill_level_trends.py`, Player Trends Excel sheets, `ui/tabs/trends.py` | `PlayerMatch.skill_level` per match | Entire SL-trend engine | Not in Broadcast; SL movement is not performance; a results-based trend is missing | Medium | Show SL change and results form separately and labelled; sorted view by captain choice | P2 (A) |
| 6 | Who performs well against stronger opponents? | Partially | `sl_bucket_index` in `analytics/ultimate_coach_war_room.py` (record by opponent skill level); "vs SL" evidence text in `ui/ultimate_coach_war_room.js` | `player_head_to_head` by opponent SL | Bucket index and its renderer | Surface it for our own players on the roster view; sample sizes | Low to Medium | Per-player record vs higher-SL opponents with n; empty buckets say "no games" | P2 (A) |
| 7 | Who should sit tonight, and why? | Partially | M3 hold-backs and designated answers ("saved for X"), cap slack | M3 plan outputs | In-night "why saved" explanations | Pre-night roster-level view of who is left out of the five and what changes | Medium | Left-out list from the chosen five with factual reasons (form, cap, availability); no outcome claim | P1 (B) |
| 8 | Can my selected five satisfy the 23-Rule? | Partially | `analytics/lineup_legality.py` (`check_lineup_legality`, `legal_completion_exists`, `assess_completion_options`, 4-player/19 path), `wrCapFor`, cap default 23, `tests/test_lineup_legality.py` | Skill levels (unknown is tri-state) | All logic and tests | A live verdict while selecting a five | Low once B exists | Exact total vs 23 shown; unknown skill level gives "cannot verify"; 4-player/19 path explained | P1 (B) |
| 9 | What happens if one of my players doesn't show? | Solved | Mark Out in Here/Out recomputes the plan; remaining-slot and cap check | Marks | All | Optional one-click "if X is out" comparison | Low | Marking Out updates plan and cap immediately and reversibly | P3 |
| 10 | Is my team improving or getting worse? | Partially | Summary tab league table and recent results (`ui/ultimate_coach_broadcast.py`), `analytics/season_projection.py` (standings trend), `team_strength.py` | `matches`, 40 standings snapshots | League table; `season_projection` trend | Team results-form trend (last N matches) in the Broadcast; standings history is thin | Medium | Last-N team record and direction with n; states data limits; no projection claims | P2 |
| 11 | What are my biggest risks tonight? | Partially | M3 fragility and cap safety, data coverage (`analytics/data_coverage.py`), evidence labels, "Unknown does not mean safe" | Coverage, evidence level, availability marks | All as alert sources | One consolidated briefing of factual alerts | Low to Medium | Alerts name their source field; factual vs tentative visually distinct; no numeric risk score | P1 (D) |
| 12 | Which teammates are the most dependable? | Not Solved | `player_trends.volatility` (skill level spread), not results consistency | `all_games` | Volatility code as a pattern only | A results-based consistency measure with sample guard | Medium | Defined, documented measure with n; labelled descriptive; not named "dependable" without a stated rule | P2 (A) |
| 13 | What skill levels are recorded for my players? | Solved | Roster table and cap display in Broadcast; `Player.skill` in the web snapshot | `player_matches.skill_level` | All | Skill-change date | Low | Recorded SL per player per format; unknown shown as unknown | P3 |
| 14 | Who are we playing and what is their history? | Solved | Opponent roster and records, Summary tab league cards, war-room team cards (`team_record`, `lifetime`, `sample`) | Cockpit payload, `matches` | All | None material | Low | Opponent roster with recorded records and coverage note | P3 |
| 15 | Have we played these opponents before, and what happened? | Solved | Direct "Winning record vs", `met_list`, `vs_ours` cards, evidence levels | `player_head_to_head` | All | None | Low | Direct record and meeting count per pair; "no direct record" stated | P3 |
| 16 | Which opponent players should concern me most? | Solved | Threats and concerning lists in the war-room payload; command board threat tile | Evidence per pair | All | Notes that threat order is descriptive, not predictive | Low | Threat list names the recorded concern and its sample | P3 |
| 17 | Who should I put up first? | Solved (as planner evidence) | M3 lead pick, put-up cards, toss flow | M3 plan | All | Validation: no outcome evidence supports the pick; keep the labelled-evidence wording | Low | Lead pick shown with evidence level and alternatives; no claim of improved results | P3 (frozen M3) |
| 18 | Who should I save for later? | Solved (as planner evidence) | M3 hold-backs, designated answers, "why saved" | M3 plan | All | Same validation caveat | Low | Each hold names the opponent it covers | P3 (frozen M3) |
| 19 | How many points will each player contribute tonight? | Not Solved (withhold) | Descriptive `summarize_player.avg_points` only; probabilities forbidden by `docs/ULTIMATE_COACH_EVIDENCE_QUALITY_CONTRACT.md` | `player_matches.points_earned` | `summarize_player` for a descriptive average | A validated predictor; none exists | n/a | Show only recorded average points per match with n; never a forecast | W |
| 20 | Is a teammate stronger in 8-Ball or 9-Ball? | Partially | Header switch 8-Ball / 9-Ball in Broadcast; `career_stats` per format; profiles are format-isolated | Format-scoped records | Format isolation, `career_stats` | Side-by-side per-player comparison with n | Low to Medium | Both formats shown side by side with n, never pooled | P2 (A) |
| 21 | Who can handle a difficult opponent matchup? | Partially | Evidence levels, direct records, record vs SL buckets, M3 "Strong" label | Pair and SL-bucket records | All | Roster-level "record vs tougher opponents" view (same as Q6) | Low to Medium | Per-player record vs higher-SL opponents with n; no inference beyond records | P2 (A) |
| 22 | How much can I trust the data? | Partially | `analytics/data_coverage.py`, evidence labels, stale-data notices, `ultimate_coach_evidence_quality.py` | Coverage counts, refresh times | All | One trust summary in the Broadcast (what is missing and how stale) | Low to Medium | Briefing lists coverage gaps and stale fixtures; Unknown never read as safe | P1 (D) |
| 23 | What are my best alternative groups of five? | Not Solved | None for fives (Lineup Lab and M3 assign opponents) | Roster, SL, form (after A) | Cap logic to enumerate legal fives | Enumerate legal fives and compare factually; no win ranking | High | Legal fives listed with factual columns the captain sorts; no "best" claim | P1 (B/C) |
| 24 | What happens if I swap one player for another? | Partially | Out/Here marks recompute plan; cap check | Marks, SL | Plan recompute, cap check | Swap diff of two fives (cap, form, coverage, legality) | Medium | Exact reversible diff; optional M3 summary labelled planner view; no outcome claim | P1 (C) |
| 25 | How could tonight affect our playoff or qualification chances? | Not Solved (withhold) | `analytics/season_projection.py` (remaining schedule, standings trend; states it does not model qualification) | 40 standings snapshots; no playoff flag | Standings trend only | Qualification rules and playoff results are not in the archive | n/a | Show standings and schedule facts only; no qualification claim | W |

**Counts:** Solved 8 (Q2, 9, 13, 14, 15, 16, 17, 18). Partially 11 (Q3, 5, 6, 7, 8, 10, 11, 20, 21, 22, 24). Not Solved 6 (Q1, 4, 12, 19, 23, 25), two of which (Q19, Q25) are withheld by evidence rules. Q17 and Q18 are solved as features, not validated as outcome improvements.

## 2. Dependency map

```
all_games contract (analytics/ultimate_coach_data_contract.py)  [exists]
   -> Gap A: per-player form function + payload field  (analytics/ultimate_coach_war_room.py)  [new, small]
         -> roster-table form cell (ui/ultimate_coach_broadcast.py)            answers Q3 Q4 Q5 Q6 Q12 Q20 Q21
         -> short-history flags -> Gap D                                         answers Q11 Q22
         -> form columns -> Gap B                                                answers Q1 Q7 Q8 Q23
Here/Out state + lineup_legality + wrCapFor  [exist]
   -> Gap B five-selection panel (needs A for form columns; cap verdict needs only existing code)
         -> Gap C swap diff                                                      answers Q24 (and Q9 comparison)
Data coverage + evidence gates + M3 fragility/cap notes  [exist]
   -> Gap D briefing card                                                        answers Q11 Q22
Not buildable now: Q19 (validated predictor), Q25 (playoff data).
```

Shared prerequisites: format isolation (EIGHT and NINE), the as-of date boundary, and the minimum-sample rule, all already established in `ultimate_coach_player_profiles.py` and `player_trends.py`.

## 3. Four highest-value gaps (by questions unlocked)

1. **Real Player Form (A):** unlocks Q3, 4, 5, 6, 12, 20, 21 directly and feeds Q1, 7, 10, 11. Reuse: `all_games`, `recent_form`, profiles. Medium.
2. **Tonight's Five Advisor (B):** the headline captain question (Q1) plus Q7, Q8, Q23. Reuse: Here/Out, `lineup_legality`, roster table. High, but only the panel is new.
3. **Captain Risk Briefing (D):** Q11 and Q22 from existing coverage and evidence gates. Low to Medium; cheapest of the four.
4. **Roster What-If (C):** Q24 and the Q9 comparison. Medium; shares the B panel.

## 4. Recommended implementation order

1. **A** (foundation; no screen of its own beyond a roster-table cell).
2. **D** may run in parallel with B once A's short-history flags exist; it needs no new data.
3. **B** the five-selection panel with the live 23-Rule verdict (the cap verdict can ship first, form columns follow from A).
4. **C** the swap diff on the same panel.
5. P2 items (Q5, Q6, Q10, Q12, Q20, Q21) are columns and views on top of A.
6. Withhold Q19 and Q25 until evidence exists. Start logging the available pool and the chosen five from the first release so a later study of roster advice is possible.

## 5. Risks and assumptions

- **Form is not skill movement.** Existing HOT/COLD means skill-level movement; showing it as slump or improvement of play would mislead. Keep them separate and labelled.
- **Evidence limit.** Lifetime form is the strongest signal measured; last-10 adds little in 8-Ball. Present recent form as description.
- **Roster advice is unvalidated.** The archive has no bench record, so whether better-looking fives win more cannot be tested now. Do not claim it. The prospective log is the route to evidence.
- **Probability policy.** No forecasts, no expected points, no qualification odds. `season_projection` uses a probability formula internally; its output must not be surfaced as odds.
- **Partial-capture history.** Records reflect what the archive captured, not lifetime; coverage gaps must be named per player.
- **Payload size and staleness.** Adding per-player recent games enlarges the Broadcast payload and its snapshot age must be shown (reuse the existing stale-data notice).
- **Python and JS parity.** Any form arithmetic mirrored in JavaScript needs a parity test, as with the confidence and cap code.
- **Assumption:** the cockpit payload builder (`analytics/ultimate_coach_war_room.py`) can accept a new player field without breaking the Excel and web consumers; this must be checked in the first step.
- **Assumption:** effort ratings are from reading the code, not from prototyping.
