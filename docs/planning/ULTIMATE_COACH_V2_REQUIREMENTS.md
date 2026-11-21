# Ultimate Coach V2: requirements and acceptance criteria

**Status: PENDING OWNER APPROVAL.** Blueprint only. No implementation, algorithm change, weight tuning, experiment, database change, Sunday-package change, merge or deployment is authorized by this document.

| Role | Responsibility |
|---|---|
| Owner (Paul) | Final decision authority on every requirement, threshold and phase gate |
| GPT | Product owner and independent reviewer |
| Claude | Technical lead: architecture, feasibility, validation, data integrity (author of this draft) |
| Copilot | Additional independent perspective |

**Objective:** the best possible APA captain decision-support system — helping a captain choose, sequence and understand match-night decisions that maximize **actual APA team points**, with every recommendation explained. A better single-game predictor is a means, not the goal.

**Inputs reviewed before drafting** (to avoid duplicate work):
- Research: `docs/research/FINAL_EVIDENCE_SUMMARY.md`, `docs/research/forensic/` (forensic report, night replay, focused impact, controlled re-tests), `docs/research/issue119/`, `docs/research/m3-validation/` (all on `claude/m3-validation-research`).
- Contracts: `docs/ultimate_coach/EVALUATION_EVIDENCE_CONTRACT.md` (probability publication FORBIDDEN until chronological evaluation and calibration gates pass), `docs/ULTIMATE_COACH_EVIDENCE_QUALITY_CONTRACT.md` (fail-closed evidence rules).
- Engine reviews: `docs/match_night_engine_review.md`, `docs/recommendation_philosophy_review.md`, `docs/captain_confidence_framework.md`, `docs/win_probability.md` (verified APA race charts), `docs/lineup_legality.md` (verified 23-Rule and 4/19 path).
- Captain Value: `docs/captain_value/` (acceptance matrix, current state, build-vs-connect, MVP plan) and PR #114 (Five check, Risk briefing, Player Form, What-If).
- Issues: #113 (21 baseline test failures), #115 CV-003, #116 CV-004, #118 CV-005, #119 (recommendation explainability research).

## 1. Current capabilities (baseline to preserve)

| Area | Live today (Sunday Broadcast HTML + Excel) |
|---|---|
| Pairing evidence | Six confidence levels from direct record, career record (compared at 20+ games), shared opponents and a skill-changed flag (`analytics/ultimate_coach_confidence.py`, JS mirror) |
| Match-night planning | **M3**: exact minimax over alternating put-ups, cap 23 on both teams, holds, sacrifices, fragility, lead and response tables (`analytics/match_night_engine.py`, JS mirror) |
| Evidence ordering | Next Send ranking by direct record, shared-opponent group, unranked rest (`analytics/ultimate_coach_matchup_evidence.py`); War Room categories, blind send, live threats (`analytics/ultimate_coach_war_room.py`) |
| Match-night workflow | Here/Out per person per night, toss and put-up flow, "They threw" pairing, Send/Put up instead, concession labels, 8-Ball/9-Ball switch, cap default 23 |
| Captain Value MVP (PR #114, not merged) | Five check (skill total vs cap), Risk briefing (sourced facts), Player Form (recorded games), Swap what-if |
| Data | Identity-verified evidence for 13k+ players embedded offline; archive 2011-2026 |
| Correctness evidence | 392 engine/confidence/replay/mirror/evidence tests incl. independent game-tree and brute-force checks; Python/JS parity tests |

Legacy engines (Lineup Optimizer, Captain's Edge, win-probability composites, Lineup Lab skill-only term) remain in the repository but are not in the Sunday package.

## 2. Verified weaknesses (from the research; evidence in `FINAL_EVIDENCE_SUMMARY.md`)

| ID | Weakness | Evidence status | Severity |
|---|---|---|---|
| W1 | Unknown (no usable evidence) is scored as an even game at every skill gap; in 8-Ball the lower player wins 26-37% at gaps of 2+ levels | SUPPORTED (actual outcomes); 9-Ball approximately even | Potentially consequential (8-Ball) |
| W2 | Confidence levels are correctly ordered but their meaning shifts with skill gap in 8-Ball (Caution 28% at -3, 50% at +2) | SUPPORTED | Statistically meaningful |
| W3 | Skill level and recorded form carry predictive information beyond M3's levels in 8-Ball; the planner does not use it | SUPPORTED (8-Ball); 9-Ball skill: no consistent benefit | Potentially consequential |
| W4 | Ties: 35-37% of early leads, 78% of late leads and 21-23% of responses are exact ties broken silently by roster order; answer ties are undisclosed; tied options often differ in strategic value | SUPPORTED | Consequential to trust; per-night effect |
| W5 | The planner maximizes a sum of evidence points, not expected APA team points; actual APA scoring is not modelled | SUPPORTED (design) | Potentially consequential |
| W6 | The opponent is always assumed to pick the most damaging reply | Theoretical (put-up order unrecorded) | Unknown |
| W7 | Unknown labels do not say why (new player vs close records vs no shared evidence); no skill-gap context; Next Send and M3 can disagree on the same screen | SUPPORTED (code and scenarios) | Consequential to understanding |
| W8 | Data integrity: 388 duplicate head-to-head keys (160 conflicting) block the production replay; about a fifth of rostered players have under half their career captured; 21 stale baseline tests (#113) | SUPPORTED | Blocks reliable validation |
| W9 | No record of put-up order, availability (bench) or the captain's options, so strategic effectiveness cannot be measured from history | SUPPORTED | Blocks strategic validation |
| W10 | Legacy skill-only probability uses one 0.40-per-level rule for both formats (wrong for 9-Ball) | SUPPORTED | Legacy surfaces only |

Not weaknesses (CONTRADICTED by the research, do not "fix"): the 20-game threshold as the cause of the originating case; removing the threshold (does not improve projected decisions); the shared point scale in 9-Ball (cosmetic); the current tie-break losing value on average.

## 3. Desired capabilities

1. A **format-specific matchup assessment** for every possible pairing that combines direct history, shared opponents, recent and career form, skill levels and their history, with explicit evidence quality and uncertainty.
2. A **team-point-aware match-night planner** that respects APA rules (alternating put-ups, cap, 4/19 path, actual scoring) and optimizes the team's expected outcome over the whole night, with preservation and sacrifice reasoning.
3. **Full explainability** of every recommendation: why this player, why not others, evidence and gaps, viable alternatives, sensitivity and rest-of-night impact.
4. A **validation harness** that measures each layer separately (data, mathematics, prediction, calibration, stability, strategy, team points, parity, usability, performance, regression) against the M3 baseline.
5. **Prospective data capture** of put-up order, availability and decisions so strategy can eventually be validated on real nights.

## 4. Functional requirements

Priority: **M** must, **S** should, **C** could. Each requirement maps to acceptance gates in section 6.

### 4.1 Matchup intelligence

| ID | Requirement | Pri | Gates |
|---|---|---|---|
| FR-MI-1 | Use direct head-to-head history with meeting count, recency and skill levels at each meeting; never treat one meeting as strong evidence without saying so | M | AG-1, AG-3, AG-4 |
| FR-MI-2 | Use shared-opponent evidence with the number of common opponents and both players' records against them | M | AG-3 |
| FR-MI-3 | Use recent performance (last-N recorded games) separately from career performance, by format | M | AG-3 |
| FR-MI-4 | Use career performance from APA league career totals, with the archive-captured share disclosed | M | AG-1, AG-3 |
| FR-MI-5 | Use current skill levels and skill-level history (pre-match levels; verified that recorded levels are the level played at) | M | AG-1, AG-3 |
| FR-MI-6 | Produce, for every pairing, a calibrated estimate (internal) plus an evidence-quality grade and the reasons; probabilities remain unpublished to captains until the publication gates pass | M | AG-3, AG-4 |
| FR-MI-7 | Distinguish missing evidence by cause: genuinely new player, incomplete capture, no direct history with similar records, contradictory evidence | M | AG-1, AG-9 |
| FR-MI-8 | Treat contradictory evidence explicitly (e.g. favourable direct record vs weaker form) and show both sides | M | AG-9 |
| FR-MI-9 | Fail closed on unverified identities, duplicate or conflicting records, and missing skill levels, per the evidence-quality contract | M | AG-1 |

### 4.2 Format-specific intelligence

| ID | Requirement | Pri | Gates |
|---|---|---|---|
| FR-FMT-1 | Separate 8-Ball and 9-Ball everywhere: data, estimates, thresholds, calibration and validation; never pool | M | AG-3, AG-4 |
| FR-FMT-2 | Encode actual APA scoring per format from verified official rules (team points per individual match, including any bonus rules), with a cited source and tests; the archive's team-score totals (about 16 per 8-Ball match and 119 per 9-Ball match on average) must be reproduced from the encoded rules before use | M | AG-2, AG-7 |
| FR-FMT-3 | Use the verified race charts (8-Ball two-dimensional games-to-win; 9-Ball points by own level) as an input or a check, with the double-counting question tested before use | S | AG-3 |
| FR-FMT-4 | Translate per-game estimates into team-point implications for each format | M | AG-7 |
| FR-FMT-5 | Allow format-specific strategy (e.g. skill-gap handling matters in 8-Ball; form dominates in 9-Ball) only where validation shows it | S | AG-6 |

### 4.3 Match-night strategy

| ID | Requirement | Pri | Gates |
|---|---|---|---|
| FR-MN-1 | Opening player selection when we put up first, considering their plausible replies | M | AG-2, AG-6 |
| FR-MN-2 | Responses to the opponent's declared player | M | AG-2, AG-6 |
| FR-MN-3 | Player preservation: show what is saved for later and its value | M | AG-6, AG-9 |
| FR-MN-4 | Full-roster availability (Here/Out, opponent check-in) drives every plan | M | AG-2 |
| FR-MN-5 | Skill-cap compliance for both teams, including the verified 4-player/19 fallback | M | AG-2 |
| FR-MN-6 | Track remaining matchup opportunities and the cost of spending a player now | M | AG-6 |
| FR-MN-7 | Explicit sacrifice decisions with their expected cost and benefit | M | AG-6, AG-9 |
| FR-MN-8 | Live re-planning after every game, played or skipped, within the performance budget | M | AG-10 |
| FR-MN-9 | Objective = expected APA team points (with night-win as a reported secondary), not a sum of evidence labels | M | AG-6, AG-7 |
| FR-MN-10 | Opponent model is explicit and selectable (adversarial, observed tendencies when data exists); never hidden | S | AG-6 |
| FR-MN-11 | Ties and near-ties are surfaced as equally viable options with a disclosed tie rule | M | AG-5, AG-9 |

### 4.4 Explainability (every recommendation)

| ID | The captain can see | Pri | Gates |
|---|---|---|---|
| FR-EX-1 | Why this player: the deciding evidence in plain words | M | AG-9 |
| FR-EX-2 | Why not each eligible alternative, in the same terms | M | AG-9 |
| FR-EX-3 | The supporting evidence with sample sizes and dates | M | AG-9 |
| FR-EX-4 | What evidence is missing and why (new player, incomplete capture, no direct history, contradiction) | M | AG-9 |
| FR-EX-5 | Whether other choices are equally viable (ties and near-ties) | M | AG-5, AG-9 |
| FR-EX-6 | How sensitive the choice is (would one more loss, one level change or another assumption flip it?) | M | AG-5, AG-9 |
| FR-EX-7 | The impact on the rest of the night (what this choice saves or spends) | M | AG-9 |
| FR-EX-8 | Skill-gap context for the pairing, as recorded history, not a promise | S | AG-9 |
| FR-EX-9 | One consistent ordering across all screens (no conflicting rankings) | M | AG-9 |
| FR-EX-10 | Language rules: facts vs estimates vs strategy are labelled; no probabilities shown until publication gates pass | M | AG-4, AG-9 |

### 4.5 Data capture and integrity

| ID | Requirement | Pri | Gates |
|---|---|---|---|
| FR-DC-1 | Record put-up order, who declared, availability and the plan shown, per night (captain-entered, local, opt-in) | M | AG-6, AG-7 |
| FR-DC-2 | Resolve or quarantine duplicate and conflicting head-to-head rows; production replay must run without exclusions | M | AG-1 |
| FR-DC-3 | Report capture completeness per player (archive vs career) | S | AG-1 |

### 4.6 Baseline protection

| ID | Requirement | Pri | Gates |
|---|---|---|---|
| FR-BP-1 | Current M3 remains the production baseline and stays runnable unchanged | M | AG-11 |
| FR-BP-2 | Any candidate runs in shadow mode beside M3 (same inputs, both outputs recorded) before replacement is considered | M | AG-6, AG-7 |
| FR-BP-3 | Replacement requires passing every gate in section 6 and an explicit owner decision | M | all |
| FR-BP-4 | Statistically better predictions are never assumed to give better decisions; strategy and team-point gates must be passed separately | M | AG-6, AG-7 |

## 5. Technical constraints

- Local and GitHub only; no Vercel, preview or production deployment without owner approval; real APA data stays local and out of git.
- Offline single-file Broadcast HTML and Excel companion remain the delivery surfaces unless the owner decides otherwise.
- Probability publication stays FORBIDDEN (evaluation evidence contract) until chronological evaluation and calibration gates pass; estimates may be used internally.
- Python is the reference; any browser logic is a mirror with parity tests.
- Determinism: same inputs give the same plan; tie rules are explicit and stable.
- Fail-closed evidence rules (evidence-quality contract) apply to every new input.
- Phone performance budget (section 6, AG-10).
- No change to the existing Sunday package during V2 development.

## 6. Acceptance gates (measurable; proposed thresholds for owner approval)

| Gate | What must be shown | Proposed threshold | Evidence artifact |
|---|---|---|---|
| **AG-1 Data integrity** | Clean inputs | 0 unresolved duplicate/conflicting keys in the evaluation set; production replay runs without exclusions; identity-verified share reported; capture completeness per player reported; leakage probe 0 mismatches on 1,000+ sampled games per format | Integrity report + script |
| **AG-2 Mathematical correctness** | Planner and rules compute what they claim | Exact agreement with an independent game-tree search on 1,000+ random nights per format; 100% cap/4-19 compliance on all test nights; team-point scoring reproduces archive team scores exactly for 99%+ of complete matches | Test suite |
| **AG-3 Predictive accuracy** | Better single-game prediction than the M3-level baseline | Log-loss gain ≥ 0.005 with 95% CI above 0 on the frozen holdout and in ≥ 4 of 5 rolling blocks, **per format**; reported with Brier and AUC; fresh holdout not used in development | Evaluation bundle |
| **AG-4 Calibration** | Estimates mean what they say | Calibration slope 0.9-1.1, intercept within ±0.05, ECE ≤ 0.02 per format and within each skill-gap band with n ≥ 500; required before any probability is shown | Calibration report |
| **AG-5 Recommendation stability** | Choices are robust and ties honest | 100% of ties and near-ties (within a pre-registered margin) disclosed; plan invariant to roster display order; share of recommendations that flip under a one-result change reported and below an owner-set limit | Stability report |
| **AG-6 Strategic effectiveness** | Better decisions, not just predictions | Shadow mode over ≥ 1 full season with recorded put-up order and availability: candidate's recommended choices score higher than M3's under a pre-registered evaluator fitted on earlier data, CI above 0, per format; simulated results labelled as such | Shadow-mode log + analysis |
| **AG-7 APA team-point outcomes** | Real team points | Prospective comparison on nights where the captain followed each system's recommendation (or a pre-registered alternation), using actual team points; no claim of improvement until the CI excludes 0; sample size set in advance | Prospective study |
| **AG-8 Python/JavaScript parity** | Phone and reference agree | Identical plans and explanations on 1,000+ randomized nights per format | Parity suite |
| **AG-9 Captain usability** | Captains understand and can act | Moderated test with ≥ 5 captains on phone: core questions answered in ≤ 5 seconds; explanation comprehension ≥ 80% correct; no critical accessibility defects (CV-005, #118) | Usability report |
| **AG-10 Performance** | Fast on match night | Re-plan after a game ≤ 200 ms p95 and first load ≤ 3 s on a mid-range phone; Excel build time reported | Benchmark |
| **AG-11 Regression protection** | Nothing existing breaks | All existing suites green, including the 21 baseline failures resolved (#113); M3 baseline outputs unchanged on a frozen fixture set | CI-equivalent local run |

## 7. Dependencies

1. Owner-approved verified APA scoring rules per format (FR-FMT-2).
2. Duplicate and conflicting record resolution (FR-DC-2) and the 21 baseline test failures (#113).
3. Prospective capture of put-up order, availability and decisions (FR-DC-1) for AG-6 and AG-7.
4. A fresh, untouched holdout period (the 2025-09+ period has been reused in research).
5. PR #114 review outcome and CV-003/004/005 follow-ups (#115, #116, #118).
6. Decision on Excel parity for new features.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Better prediction does not improve decisions | Separate AG-6/AG-7 gates; shadow mode; M3 stays baseline |
| Overfitting to a reused holdout | Fresh holdout; pre-registration; rolling validation |
| Evaluator bias in counterfactual scoring | Two or more independent evaluators; prospective data |
| Opponent model wrong | Explicit, selectable model; sensitivity reporting |
| Complexity reduces captain trust | Explainability gates; usability testing |
| Probability leakage to captains | Contract lock; language rules; tests |
| Phone performance | Performance gate; exact search kept within budget |
| Data gaps (capture, identity) | Disclose per player; fail closed |
| Two engines diverge silently | Shadow mode logs both; parity and regression suites |

## 9. Proposed development phases (each ends at an owner gate)

| Phase | Scope | Exit criteria |
|---|---|---|
| P0 Foundations | Data integrity (duplicates, #113), verified APA scoring encoding, evaluation harness with frozen and fresh holdouts, prospective capture design | AG-1, AG-2 (scoring), AG-11 |
| P1 Explain the baseline | Disclose M3 ties and near-ties, Unknown causes, skill-gap context, one consistent ordering, rest-of-night impact; no algorithm change | AG-5 (disclosure), AG-8, AG-9 (initial) |
| P2 Matchup estimates (offline) | Format-specific calibrated pairing estimates and evidence grades, research-only | AG-3, AG-4 |
| P3 Team-point planner (shadow) | Planner on expected team points with explicit opponent model, run beside M3, both logged | AG-2, AG-5, AG-10, AG-6 (started) |
| P4 Field validation | One season of shadow mode with recorded put-ups; captain usability trials | AG-6, AG-7, AG-9 |
| P5 Replacement decision | Owner review of all gates | Every gate passed; explicit owner approval |

## 10. Outstanding owner decisions

1. Approve or amend the acceptance thresholds in section 6.
2. Objective: expected team points, night-win probability, or both (and which leads).
3. Whether probabilities may ever be shown to captains, and under which gate.
4. Opponent model default (adversarial vs observed tendencies) once data exists.
5. Prospective data capture: what captains enter on match night, and privacy handling.
6. Excel parity for V2 features.
7. Whether to fix the 21 baseline test failures (#113) before V2 starts, and the classic-page scope of the 23-cap and "everyone Here" defaults.
8. Fresh holdout period definition and who holds it.
9. Order of P1 (explain the baseline) relative to P0.
10. Disposition of PR #114 and the CV follow-ups.

## 11. Traceability

| Weakness | Requirements |
|---|---|
| W1, W2 | FR-MI-6, FR-MI-7, FR-FMT-1, FR-EX-4, FR-EX-8 |
| W3 | FR-MI-3..6, FR-FMT-5 |
| W4 | FR-MN-11, FR-EX-5, FR-EX-6, AG-5 |
| W5 | FR-FMT-2, FR-FMT-4, FR-MN-9, AG-7 |
| W6 | FR-MN-10 |
| W7 | FR-EX-1..10 |
| W8 | FR-DC-2, FR-DC-3, FR-MI-9, AG-1 |
| W9 | FR-DC-1, AG-6, AG-7 |
| W10 | FR-FMT-1 (legacy surfaces out of scope unless the owner decides otherwise) |
