# Ultimate Coach V2 candidate — intelligence and contradiction audit (living document)

Branch `claude/uc-v2-candidate`, draft PR #120. Real player data stays local; this file holds counts, code
locations and rules only. Tools: `docs/v2/contradiction_audit.py` (cross-screen invariants),
`docs/v2/data_reconcile.py` (page vs source records), `docs/v2/strategy_sweep.py` (policy behaviour).

## Status
| Phase | State |
|---|---|
| 1 Inventory (V2-relevant surfaces, engine used, legacy logic) | done for Match Night, Command Board, plans, trace, comparison, Team Status features; classic-only cards listed below |
| 2 Data integrity | owner fixture done (16 players, 64 direct pairings); division-wide not yet |
| 3 Contradiction detector | v1 division run complete (72 pairs, 360 states, 2 contradictions -> S7 fixed; 29 quantified strategic exceptions); harness v2 + 31 seeded-fault tests; final v2 run against e22310e in progress |
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
| D1 | High (preliminary, GA-03) | Package evidence not reproducible from any database on disk (12/16 players' totals differ vs newest catch-up DB, both directions; one newcomer's 7 games in no DB) | open — needs a build manifest with source path + hash |
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


## GPT acceptance gates (PR #120, owner-approved)
| ID | Sev | Requirement | Status |
|---|---|---|---|
| GA-01 | High | Harness must not false-pass: per-invariant checked/skipped/failed counts, nonzero coverage, requested team/format validated, missing outputs = failure, no-answer states separated; EIGHT+NINE, both toss orders, played 0-4, both sides' availability, no-feasible-five; I7 with prior spend, uniqueness, unknown SL never zero; stable IDs; rendered advice checked; absent engine answer never becomes a legacy Send | open — current division run predates this; results reported as preliminary |
| GA-02 | High | Seeded negative/mutation tests for each fault class plus a positive control; coverage + build hashes in aggregate output | open (first seeded case: GPT-004 regression test fails on the old code, passes on the fix) |
| GA-03 | High | D1-D3 are preliminary: reconcile raw -> verified eligible game keys -> compact HTML on stable identities and the same snapshot/cutoff; raw vs filtered separately; reuse the production build manifest/hash for V2 builds; no record changes on preliminary counts | open; D1-D3 reclassified preliminary |
| GA-04 | High | Recheck GPT-004/006/007/008/009/010/011/013/014 | see rows below |
| GPT-004 | High | later long shot classified at the root state | fixed 6b2d952; regression test fails on old code |
| GPT-006 | Medium | unknown skill level | documented: V2 uses the average skill-pair effect (never a made-up pair); cap check marked incomplete; harness never counts unknown SL as zero |
| GPT-007 | Medium | shortened lineup / 4-player 19 fallback | open: V2 plays min(5, rosters) games (inherited); the APA 4/19 fallback is not modelled |
| GPT-008 | High | silent broadcast fallback to M3 | fixed e55b45f: red badge when V2 has no model for the format |
| GPT-009 | High | reported holdout metrics were single-orientation, app uses symmetrized p | fixed: fit reports symmetrized holdout (8-Ball log loss 0.6720, slope 0.958; 9-Ball 0.6846, slope 0.963); on-page check uses them; coefficients unchanged |
| GPT-010/011 | Medium | verified mirror/finalization and train/live feature parity | partly: Python/JS parity to 1e-12 and fit/module feature identity tested; live inputs come from compact page evidence (no match ids, D2) while training used the clean archive - parity not yet verified (GA-03) |
| GPT-013 | Low | opponent cap assumption | documented: same cap assumed for them; dropped if they have no legal lineup (inherited) |
| GPT-014 | Medium | model uncertainty | open: no uncertainty ranges on win chances; only 1-point tie and 0.02 equal-plan tolerances |

Notes: APA team-point optimisation remains an unmet requirement (P1). Model-dependent rollout gains are not observed wins.

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
