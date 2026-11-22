# Ultimate Coach V2 candidate — intelligence and contradiction audit (living document)

Branch `claude/uc-v2-candidate`, draft PR #120. Real player data stays local; this file holds counts, code
locations and rules only. Tools: `docs/v2/contradiction_audit.py` (cross-screen invariants),
`docs/v2/data_reconcile.py` (page vs source records), `docs/v2/strategy_sweep.py` (policy behaviour).

## Status
| Phase | State |
|---|---|
| 1 Inventory (V2-relevant surfaces, engine used, legacy logic) | done for Match Night, Command Board, plans, trace, comparison, Team Status features; classic-only cards listed below |
| 2 Data integrity | owner fixture done (16 players, 64 direct pairings); division-wide not yet |
| 3 Contradiction detector | harness-v2 run on e22310e stopped for the owner's restart at 7/72 pairs (84 states); its 13 contradictions (shards 3-4) all diagnosed as GPT-008 (send card fell back to the recorded ranking when V2's answer had no recorded category) and re-verified clean on 424b9e0 (2 pairs x 12 states); final re-run pending; v1 division run complete (72 pairs, 360 states, 2 contradictions -> S7 fixed; 29 quantified strategic exceptions); harness v2 + 31 seeded-fault tests; final v2 run against e22310e in progress |
| 4 Strategic audit | sweep done at 539408f (576 put-ups); rerun pending on the latest policy |

## Phase 1 — where each screen's logic comes from (V2 build)
| Surface | Function (ui/ultimate_coach_war_room.js unless noted) | Engine / source | Tests |
|---|---|---|---|
| Send card answer, role, concession note | `wrBroadcastModel` → `mnPlanFor(...,"v2")` → `v2ApplyOptions` | V2 executed policy | test_uc_v2_candidate (owner scenario, rollout, roles) |
| Decision trace ("Every option") | `wrV2Trace`, `wrV2TraceHtml` | V2 policy rollout, M3 + benchmark scored on same terms | trace fields, rollout consistency |
| M3 vs V2 table | `wrEngineCompare`, `wrEngineCompareHtml` | both engines' own policies, scored with V2 estimates | rollout + role consistency |
| Lead / put-up options | `v2ApplyOptions` (lead, `lead_options`), `wrLeadOptions` | V2 policy | rollout consistency |
| Game plans, totals, holds, fragility | `v2ApplyOptions` (lazy holds/fragility) | V2 policy | rollout consistency |
| Captain Command Board | `wrCommandV2` (V2), `wrCommand` (M3 builds) | V2 plan | harness I2–I4, I8 |
| Send instead picker | `wrSendScenarios` | V2 bands + estimate | harness I8 |
| Alternatives / risks on send card | `wrBroadcastModel` (V2 reorder), broadcast `renderNight` | V2 estimate order; records shown as facts | legacy-notes test |
| Next Send direct-record list (classic) | `wrNextSend`, `wrNextSendCard` | **recorded head-to-head categories (M3-era)** — labelled as recorded results | existing classic tests |
| Blind send card (classic Tonight) | `wrBlindSend`, `wrBlindSendCard` | **recorded categories (M3-era)** | existing classic tests |
| Send cost text | `wrSendCost`, `wrCostText` | **recorded categories**; suppressed on V2 send cards since a0bf857, still on classic cards | — |
| Threat panel, matrix, opportunities, risks (classic War Room) | `wrLiveThreats`, `renderWarRoom`, `wrPlan` | recorded records (facts) | existing |
| Team Status: Player Form, Five check, Risk briefing, Swap what-if | `ui/ultimate_coach.py formFor`, `wrFiveCore`, `wrBriefingCore`, `wrSwapCore` | facts / arithmetic (no engine) | existing MVP tests |
| Engine badge | `ucEngineBadge` | build flag; never remembered | reopen test |
| Excel workbook | `ui/excel_war_room.py` | **M3 only** (no V2) | Excel suites |


### Full screen inventory (Broadcast build, 7 tabs)
| Tab | Sections (DOM id / heading) | Source (function) | Logic | V2 build uses |
|---|---|---|---|---|
| Home | team pickers `#bc-team-a/b`, cap `#bc-cap`, Key Matchups list | broadcast `renderHome` from `wrBroadcastModel.rows` | plan answers per put-up | V2 policy |
| Schedule | Match Day `#match-day-card`, fixtures, viewer, coverage | `ui/ultimate_coach.py` Match Day | schedule facts | facts |
| Match Night | night board `#bc-night` (status, who's here, toss, chips, send card), decision trace `#bc-v2-trace`, M3 vs V2 `#bc-engine-compare`, Captain command board, Compare all options `#bc-compare` (player details, Alternatives, Risks I accept) | `wrBroadcastModel`, `wrV2Trace`, `wrEngineCompare`, `wrCommandV2`, `wrSendScenarios`, broadcast `renderNight`/`commandHtml` | V2 policy; recorded records shown as facts | V2 |
| Recommendations | Captain's War Room: `#wr-opportunities` (recorded options preview), `#wr-matrix`, `#team-comparison`, `#team-matchups` (evidence ranking per opponent) | `renderWarRoom`, `wrPlan`, `rankVsOpponent` | recorded head-to-head ordering (M3-era categories) | **recorded facts (not V2)** — L1 |
| Threats | `#wr-risks` (threats, losing records, open risks), `#scouting-cards`, coach notes | `wrLiveThreats`, `renderWarRoom`, scouting cards | recorded records; notes are opinions | facts (V2 relabel of losing-records heading, a111f46) |
| Team Status | `#team-rosters` (Player Form), `#lineup-lab` (marks, Five check, Risk briefing, Swap what-if, Snapshot, Recorded options now, unique winning records) | `formFor`, `wrFiveCore`, `wrBriefingCore`, `wrSwapCore`, `wrPlan` | facts / arithmetic; recorded-record lists | facts (V2 relabel of protected heading, a111f46) |
| Summary | League table, recent results, Start here (incl. limitations), Data trust | broadcast `renderLeague`, `ui/ultimate_coach.py` start-here, trust card | facts; limitations text | V2-specific limitation line (a111f46) |

Duplicated business logic / competing sources of truth found:
1. Recorded-record "categories" (G/E/R/I/X in `rankVsOpponent` / `wrCategory`) still drive the classic Next Send list,
   blind send card, send-cost text and War Room opportunities. In V2 builds these describe recorded facts, but
   they rank players differently from V2 — a source of apparent contradiction on the classic page.
2. Python mirror (`analytics/match_night_engine.py`) has no V2 policy; V2 exists only in JS
   (`analytics/uc_v2_pair_model.py` mirrors the pairing model, not the policy).
3. Excel prints M3's start-of-night plan.

## Findings (severity; status)
| ID | Sev | Finding | Status |
|---|---|---|---|
| S1 | Critical | Rebuilt V2 file opened on M3 when M3 had been chosen before (stored preference) | fixed e55b45f; reopen test |
| S2 | Critical | V2 tap latency on a throttled phone 23.9 s vs Sunday 16.1 s | fixed 942e77b (15.9 s) |
| S3 | High | Command Board used M3 categories: "avoid" Match Night's own answer; "save" for a 25% matchup; strongest responder graded C | fixed fc5b7ff; harness I2–I4 |
| S4 | High | Plans/totals/trace/comparison scored a different policy than the one recommended | fixed 11879db; GPT counterexample test |
| S5 | High | V2 send card listed its own answer under recorded "avoid" and showed M3-era "consider saving / spends our only favorable option" notes | fixed a0bf857; test + harness |
| S6 | High | Sacrifice accepted on a gain that held in only one opponent model (owner fixture +0.110 worst / +0.099 even) | fixed fc5b7ff: needs >= 0.10 under both |
| D1 | Medium (reclassified, GA-03) | The page matches its own verified source: the Sunday data is the v7 build (base refresh run `run-20261119T183918Z-1cdb65c6` + 8,440 catch-up pairs, cutoff 2026-11-19; Codex verification 0 differences over 549,936 pair records). The earlier comparison used unrelated databases. Open: the base run's input folder was not found on disk, so the private input is not retained for rebuilding. Original text: Package evidence not reproducible from any database on disk (12/16 players' totals differ vs newest catch-up DB, both directions; one newcomer's 7 games in no DB) | open — needs a build manifest with source path + hash |
| D2 | Medium (preliminary, GA-03) | Page evidence rows carry no match ids; 8 fully identical rows among 16 players cannot be told from same-day rematches; counted by V2 and record views | open |
| D3 | Medium (preliminary, GA-03) | 1 direct record differs page vs DB (pair absent in DB) | open (follows D1) |
| L1 | Medium | Classic-page Next Send list, blind send card and send-cost text still use recorded-record categories inside V2 builds | open (labelled as recorded facts; align or hide in V2) |
| P1 | Medium | APA team-point margins (8-Ball hill/shutout, 9-Ball ball points) not modelled; team points are a linear conversion that never changes a choice | open (requirement) |
| P2 | Medium | Base tap latency ~15 s on a 4x-throttled phone (shared with the Sunday build) | open, not V2-specific |
| X1 | Low | Excel has no V2 | open by scope |
| W1 | Low | Summary printed 0.099 as "+0.10" beside a 0.10 threshold | fixed a0bf857 (3 decimals) |
| S7 | Medium | Command Board: player graded B but labelled Not planned (2 of 360 states, division harness v1) | fixed e22310e: Backup role for players outside the planned five the plan still relies on |
| T1 | High | Start Here / Excel START HERE limits contradicted the product: "no skill cap is assumed", "Unknown availability is not Unavailable", "marks belong to one fixture"; V2 build also said no win-probability model exists | fixed a111f46 |
| T2 | Medium | War Room "Avoid records" and Lineup Lab "Protected players (consider saving)" read as instructions that can contradict the V2 plan | relabelled as recorded facts in V2 builds, a111f46 |



## Regression-lock matrix (owner-approved rules, PR #120)
Status rules: OPEN -> FIXED (pending verification) -> VERIFIED (targeted test + CI pass on the same code) -> LOCKED
(VERIFIED + independent review for High/Critical; Medium/Low lock on VERIFIED). REOPENED if evidence fails. CI: every
commit on the branch runs the whole `tests/` suite on Python 3.12 and 3.13 (`.github/workflows/tests.yml`); these
locked tests are part of that run. Latest green run covering every row: CI 44982036898 at bdc6c82 (rows added after
bdc6c82 are covered by the run on b2e549f, pending at writing).

| ID | Sev | Locked behaviour | Test node(s) | Fail-before evidence | Fix | Status |
|---|---|---|---|---|---|---|
| S1 | Critical | V2 file reopens on V2 after M3 was chosen / stored | `tests/test_uc_v2_candidate.py::test_rebuilt_v2_file_opens_on_v2_even_after_m3_was_chosen_before` + verifier on the owner file | not separable (badge introduced with the fix); real-file reopen check PASS | e55b45f | VERIFIED, awaiting independent review |
| S2 | Critical | V2 tap latency not worse than Sunday | none automated (measured 15.9 s vs 16.1 s at 4x throttle) | — | 942e77b | FIXED, **lock open** (needs a timing test) |
| S3 | High | Command Board built from the V2 plan (no avoid/save/grade contradictions) | `tests/test_uc_contradiction_audit.py::test_seeded_fault_is_detected` (I2/I3/I4 cases); real-data harness | detector cases fail on faulty states; real-data owner fixture 0 contradictions | fc5b7ff | VERIFIED, awaiting independent review |
| S4 | High | every V2 number = the executed policy | `tests/test_uc_v2_candidate.py::test_gpt_counterexample_every_reported_number_is_the_policy_v2_actually_plays`, `test_whole_night_rollout_is_consistent_on_every_surface` | fails on f628b13 (plan Xan->Bo) | 11879db | VERIFIED, awaiting independent review |
| S5 | High | no legacy save/spend notes on V2 send cards; answer never under avoid | `tests/test_uc_v2_candidate.py::test_v2_send_card_has_no_legacy_save_or_spend_notes_and_never_lists_its_answer_as_avoid` (strengthened b2e549f) | fails on 942e77b ('consider saving' present) | a0bf857 | VERIFIED, awaiting independent review |
| S6 | High | give up the strongest matchup only for >= 0.10 under both models | `tests/test_uc_v2_candidate.py::test_v2_keeps_the_strongest_matchup_when_saving_a_player_gains_too_little` | not demonstrated | fc5b7ff | VERIFIED, awaiting independent review; threshold provisional |
| S7 | Medium | no "graded B but Not planned" (Backup role) | `tests/test_uc_contradiction_audit.py::test_seeded_fault_is_detected[graded B but Not planned (S7)]`; real-data harness | detector case fails on the faulty state | e22310e | VERIFIED (real-data re-run pending) |
| S8 | High | rendered send card = V2 answer (no recorded-ranking fallback) — GPT-008 | `tests/test_uc_v2_candidate.py::test_absent_v2_answer_never_becomes_a_recorded_ranking_send`; harness I8 | fails on 82ab6a4; real data: 13 contradictions on e22310e (2 pairs, 24 states) -> 0 on 424b9e0 | 424b9e0 | VERIFIED, awaiting independent review |
| S9 | High | V2 risk list not overwritten by the recorded-record list | `tests/test_uc_v2_candidate.py::test_v2_risk_line_is_v2s_own_list_not_the_recorded_record_list` | fails on 82ab6a4 (['Eve Ellis'] vs []) | 424b9e0 | VERIFIED, awaiting independent review |
| GPT-004 | High | later long shot classified at its own step | `tests/test_uc_v2_candidate.py::test_later_long_shot_is_classified_at_its_own_step_of_the_night` | fails on the previous code | 6b2d952 | VERIFIED, awaiting independent review |
| GPT-009 | High | holdout metrics describe the symmetrized prediction | `tests/test_uc_v2_candidate.py::test_deployed_holdout_metrics_describe_the_symmetrized_prediction` | fails on b51988a | 4f27e6b | VERIFIED, awaiting independent review |
| T1 | High | Start Here limits match the product | `tests/test_uc_v2_candidate.py::test_start_here_limits_match_the_product_in_both_builds` | fails on ad4a0d2 | a111f46 | VERIFIED, awaiting independent review |
| GA-02 | High | detector catches seeded faults; empty runs never pass | `tests/test_uc_contradiction_audit.py::` (32 seeded faults + controls) | each seeded fault must fail its invariant | b51988a, 82ab6a4 | VERIFIED, awaiting independent review |
| AC2/AC8 etc. | High | model properties (missing evidence never even, JS/Python parity, symmetry) | `tests/test_uc_v2_candidate.py::test_missing_evidence_is_never_scored_as_even_and_skill_gaps_count_by_format`, `test_js_probabilities_match_python_exactly`, `test_probability_is_symmetric_and_bounded` | — | 82ef551 | VERIFIED, awaiting independent review |

Counts: LOCKED 0 (no independent review of these fixes yet) · VERIFIED 13 · FIXED with open lock 1 (S2) · REOPENED 0.

## GPT acceptance gates (PR #120, owner-approved)
| ID | Sev | Requirement | Status |
|---|---|---|---|
| GA-01 | High | Harness must not false-pass (counts, coverage gate, validated teams/format, missing outputs fail, both sides' availability, stable ids, prior-spend cap, unknown SL never zero, rendered advice, absent answer never a Send) | implemented: harness v2 + 33 seeded detector cases; states now cap 23/22/cleared, both toss orders, 1-4 played under BOTH toss orders, our/their player Out, no feasible five; 8-Ball and 9-Ball (format set and verified per state); final run done on 683d5f5 (8-Ball complete, 9-Ball sample): 1,536 states, 0 contradictions |
| GA-02 | High | Seeded negative/mutation tests for each fault class plus a positive control; coverage + build hashes in aggregate output | open (first seeded case: GPT-004 regression test fails on the old code, passes on the fix) |
| GA-03 | High | D1-D3 are preliminary: reconcile raw -> verified eligible game keys -> compact HTML on stable identities and the same snapshot/cutoff; raw vs filtered separately; reuse the production build manifest/hash for V2 builds; no record changes on preliminary counts | open; D1-D3 reclassified preliminary |
| GA-04 | High | Recheck GPT-004/006/007/008/009/010/011/013/014 | see rows below |
| GPT-004 | High | later long shot classified at the root state | fixed 6b2d952; regression test fails on old code |
| GPT-006 | Medium | unknown skill level | documented: V2 uses the average skill-pair effect (never a made-up pair); cap check marked incomplete; harness never counts unknown SL as zero |
| GPT-007 | Medium | shortened lineup / 4-player 19 fallback | open: V2 plays min(5, rosters) games (inherited); the APA 4/19 fallback is not modelled |
| GPT-008 | High | silent broadcast fallback to M3 | fixed e55b45f: red badge when V2 has no model for the format |
| GPT-009 | High | reported holdout metrics were single-orientation, app uses symmetrized p | fixed: fit reports symmetrized holdout (8-Ball log loss 0.6720, slope 0.958; 9-Ball 0.6846, slope 0.963); on-page check uses them; coefficients unchanged |
| GPT-010/011 | Medium | train/live parity | Python/JS parity (1e-12) and fit/module feature identity tested. Known difference: training dropped identical and conflicting duplicate rows (clean policy), but live page rows carry no match ids, so V2's live inputs cannot drop them (D2: 8 identical rows across the owner fixture's 16 players). Open; no records changed. Other definitions match: decided games only, per format, last 10 by date, recorded career = archive games, shared opponents only without a direct record |
| GPT-013 | Low | opponent cap assumption | documented: same cap assumed for them; dropped if they have no legal lineup (inherited) |
| GPT-014 | Medium | model uncertainty | open: no uncertainty ranges on win chances; only 1-point tie and 0.02 equal-plan tolerances |

Notes: APA team-point optimisation remains an unmet requirement (P1). Model-dependent rollout gains are not observed wins.



## Final harness-v2 audit on the exact candidate (683d5f5, review HTML sha256 46618509c44c...)
| Run | Scope | Pairs | States | Contradictions | Coverage | Strategic exceptions |
|---|---|---|---|---|---|---|
| 8-Ball | division 436647, COMPLETE (every ordered team pair) | 72/72 | 1,152 | 0 | ok | 116, all >= 0.10 expected wins under both opponent models |
| 9-Ball | division 436654, SAMPLE (first 24 of 182 ordered pairs) | 24 | 384 | 0 | ok | 0 |
States per pair: cap 23/22/cleared; toss us/them; 1-4 played under both toss orders; our player Out; their player Out;
no feasible five. Invariant checks (checked/skipped/failed): I0 3072/0/0, I1 12892/0/0, I2 9820/0/0, I3 12080/0/0,
I4 12080/0/0, I5 19640/0/0, I6 4608/0/0, I7 2880/96/0 (96 skipped: unknown skill level, never counted as zero),
I8 11356/0/0, I9 9820/0/0, I10 1715/0/0, I11 8/0/0. Not covered: other divisions, the remaining 158 9-Ball pairs,
Masters (stays on M3).

## Codex red-team audit (tmp/red-team-audit/RED_TEAM_AUDIT.md) — what it means for the V2 candidate
| ID | Sev | Codex finding | Applies to V2? | Status |
|---|---|---|---|---|
| RT-1 | High | 388 repeated (match, player, opponent) keys; key equality cannot tell an erroneous repeat from a legitimate repeated meeting (no event position in the snapshot); history replays update on every raw row | Yes. The V2 fit (`scripts/fit_uc_v2_pair_model.py`) uses the research "clean" policy: drops repeats of 228 identical keys and both rows of 160 conflicting keys, before any history update, so training history is not inflated by them; but some dropped rows may be legitimate meetings. Live V2 inputs come from page rows without match ids and are not de-duplicated (D2). | CONDITIONAL, open: whether the clean policy changes V2's fitted estimates materially is unmeasured; no records changed; no refit done |
| RT-2 | High | Preprocessing uses fit+validation rows (means, scales, non-constant columns) before choosing the penalty on validation; test outcomes not leaked; magnitude unmeasured | Yes. V2 fit standardizes on fit+validation (`mu, sd = X[train_m]`) then picks the penalty on the validation window. The reported 2025-09+ holdout numbers carry that exposure. The shipped coefficients are refit on all games with the chosen penalty (already disclosed). | CONDITIONAL, open: disclosed; not changed (changing it could change the penalty and therefore the shipped model, which needs a separate approved refit) |
| RT-3 | High | "Refit beats M3's fixed weights" is not what was tested: the "M3" model is a logistic fit on M3's six level indicators, not the fixed 6/3/1/0/0/-3 utility or the planner | V2 materials make no such claim (checked: PR #120, AUDIT_FINDINGS, model notes, page text). The only V2-vs-M3 numbers are each engine's own choices scored with V2's estimates, labelled model-dependent ("M3 has no probabilities of its own"). The research summary on `claude/m3-validation-research` uses "M3 levels" for the fitted level model; qualifier needed there. | V2: no misleading claim found. Research summary qualified in 04c201c on `claude/m3-validation-research` |
| RT-4 | Medium | Subgroup calibration: low SL vs SL7 predicted 46.4% vs 34.3% observed in an issue #119 model | V2's skill-pair terms give SL3 vs SL7 (8-Ball) about 25-30%, close to the archive's 220/990 (22%); subgroup calibration of V2 itself is not verified | open (GPT-014 uncertainty) |
| RT-5 | Medium | Karsten case: expected M3 behaviour, not proof of a wrong or right choice | Agreed; V2's different answer is a different policy, not proof of a better team outcome (no counterfactual outcomes) | documented |

## Owner fixture (sanitized), latest policy
Their SL7 (64% APA career) put up first; 8 of ours available, none played, no player excluded. Estimates
36.5% (SL6), 34.8% / 34.7% (two SL4s, practical tie), 30.3% (SL5), 28.0% (SL4), 25.3% (SL3 newcomer), 18.8%, 17.5%.
| Effective cap | V2 answer | Why |
|---|---|---|
| 23 | SL6, 36.5% (best available; every option a long shot) | saving him: +0.110 worst / +0.099 even — not >= 0.10 under both |
| 22 | SL6, 36.5% | +0.123 worst / +0.089 even — not under both |
| cleared | SL6, 36.5% | +0.076 worst / +0.108 even — not under both |
M3 answers with the SL3 newcomer in all three (Unknown scored as even).

## Phase 4 — strategy (sweep at 539408f; rerun pending on fc5b7ff+)
One 8-Ball division, 72 ordered team pairs, 576 put-ups, start of night, cap 23. Whole night, expected wins
(they put up first; worst case / even choices), each policy scored with V2 estimates under identical opponent
models: V2 executed 2.43 / 2.75; M3's choices 2.27 / 2.68; always strongest now 2.36 / 2.72; plain worst case
2.50 / 2.77 (benchmark 2.50). V2 gave up the strongest matchup in 19 of 576 put-ups (plain worst case: 357).
Skill-matched (strong vs strong) reference policy: added in fc5b7ff; numbers in the rerun.
All results are model-dependent (V2's own estimates); thresholds are provisional.
