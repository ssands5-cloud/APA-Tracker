# Issue #119: controlled re-tests requested by independent review

Evidence only. No fixes, tuning, new models, production changes or deployment. The goal is to settle the experimental objections, not to defend earlier conclusions; where an earlier statement fails, it is marked CONTRADICTED.

- Script: `docs/research/forensic/focused_controls.py`. Outputs: `focused_controls_EIGHT_clean.json`, `focused_controls_NINE_clean.json` (aggregates only).
- Reproduce: `FOCUS_FORMAT=EIGHT python -I focused_controls.py --db <archive_snapshot.sqlite> --out <dir>` and the same with `NINE` (about 30 minutes each). The snapshot is built by `docs/research/m3-validation/make_snapshot.py`; its sha256 (`4f4c861b…`) is checked against `docs/research/m3-validation/snapshot_manifest.json` and recorded in each output (matched).
- Sources exercised unchanged: `analytics/ultimate_coach_confidence.py` (`pair_confidence`, `FORM_MIN_GAMES`), `analytics/match_night_engine.py` (`_Night`), `scripts/replay_confidence_levels.py` (`FORMATS`, `local_day`).

## Integrity controls

- **Identical paired populations:** every variant is compared with the production run on the same night, same ten players, same pairing evidence, same opponent policy and same evaluator.
- **Test nights:** 2025-09-01 onward, five players a side, five decided games, all skill levels present: 3,476 8-Ball and 3,132 9-Ball. Excluded test matches: 8-Ball 740 not five per side, 389 not ten decided rows, 322 missing a skill level; 9-Ball 618, 292, 255.
- **Incomplete simulations:** one 8-Ball night had no legal M3 move under the cap in every setup and is excluded from that format's paired results; none in 9-Ball.
- **Seeds:** random tie-breaks and bootstraps use SHA-256-derived seeds, stable across Python processes. **Bootstrap:** 1,000 resamples over nights for every interval.
- **Evaluators** (score unplayed games only): skill+evidence and skill-only logistic models fitted on 2013-2021, penalty chosen on 2022, never on the test period. Calibration on actual test games: slopes 1.04 / 1.00 (8-Ball), 1.07 / 0.81 (9-Ball).
- **Outcome language:** "expected games" are simulated expected individual game wins. "3 of 5" is a simulated probability, **not an APA team-point outcome or team win**.
- **Carried forward:** leakage probe 0 mismatches; duplicates handled by the clean policy (228 identical, 160 conflicting keys); the 2025-09+ holdout has been reused across studies, so differences below about 0.005 games are treated as noise; M3 points are never treated as probabilities.

## 1. Global 20-game threshold removal

**Regression control (reproduced case):** no direct record; own 5-2 in 7 games; opponent 691-393 in 1,084 games; smoothed difference 4.796 points. Production level **Unknown**; with the threshold removed globally **Unknown**. Passes.

**Difference from the earlier experiment:** the earlier run re-scored only pairings that were Unknown. This run re-scores **every** pairing with `FORM_MIN_GAMES = 0`, whatever its level, because removing the threshold also opens form comparisons for pairings that have a direct record (which can move Thin to Solid or Strong, or create Conflicted).

**Transition matrix, 2023+ games (one row per game), production level to level without the threshold:**

| From \ to (8-Ball, 66,361 games) | Strong | Solid | Thin | Unknown | Conflicted | Caution |
|---|---|---|---|---|---|---|
| Strong (2,448) | 2,448 | | | | | |
| Solid (12,306) | 452 | 11,590 | | | 3 | 261 |
| Thin (10,851) | 426 | 1,239 | 8,631 | | 215 | 340 |
| Unknown (15,214) | 741 | 2,462 | | 8,838 | | 3,173 |
| Conflicted (2,898) | | | | | 2,898 | |
| Caution (22,644) | 78 | 536 | | | 207 | 21,823 |

| From \ to (9-Ball, 57,785 games) | Strong | Solid | Thin | Unknown | Conflicted | Caution |
|---|---|---|---|---|---|---|
| Strong (1,736) | 1,736 | | | | | |
| Solid (10,562) | 419 | 9,920 | | | 3 | 220 |
| Thin (9,930) | 314 | 1,036 | 8,068 | | 182 | 330 |
| Unknown (13,293) | 507 | 2,056 | | 8,196 | | 2,534 |
| Conflicted (2,723) | | | | | 2,723 | |
| Caution (19,541) | 65 | 428 | | | 203 | 18,845 |

- Globally the threshold determines the level of **15.3%** (8-Ball) and **14.4%** (9-Ball) of all pairings. 3,757 and 3,200 of those changes are pairings that were **not** Unknown.
- Of Unknown pairings, 41.9% (8-Ball) and 38.3% (9-Ball) change: identical to the Unknown-only experiment, as expected.

**Effect on decisions (paired nights, expected-games difference vs production; mean [95% CI], median, 5th-95th percentile, worst):**

| Format, evaluator | Threshold removed globally | Removed for Unknown pairings only | Plan changed (global / Unknown-only) |
|---|---|---|---|
| 8-Ball, skill+evidence | -0.0034 to -0.0055, all CIs below 0; median 0; p05 -0.06 to -0.10, p95 +0.05 to +0.09; worst -0.33 | -0.0026 to -0.0049, all CIs below 0 | 56-62% / 48-54% |
| 8-Ball, skill-only | -0.0002 to +0.0010, all CIs include 0 | -0.0001 to +0.0010, all include 0 | 55-63% / 48-54% |
| 9-Ball, skill+evidence | -0.0009 to -0.0024, all CIs below 0; worst -0.44 | -0.0008 to -0.0021, all below 0 | 55-59% / 47-51% |
| 9-Ball, skill-only | +0.0001 to +0.0010; one of four setups above 0 | +0.0002 to +0.0009; one above 0 | 55-60% / 47-51% |

Ranges cover both opponent policies and both first-leader orders. Cap compliance 100% throughout.

## 2. Lead and response decisions, isolated

Every individual M3 decision was logged as LEAD (we put up) or RESPONSE (we answer their player). Measurements below are taken at the decision itself: the evaluator value of each tied candidate given the same state, so later divergence cannot contaminate them. Skill+evidence evaluator, adversarial opponent; "early leads" are leads in games 1, 3 and 5 (we lead first), "late leads" in games 2 and 4 (they lead first).

| | 8-Ball early LEAD | 8-Ball late LEAD | 8-Ball RESPONSE | 9-Ball early LEAD | 9-Ball late LEAD | 9-Ball RESPONSE |
|---|---|---|---|---|---|---|
| Decisions | 10,425 | 6,950 | 17,375 | 9,396 | 6,264 | 15,660 |
| Tie share | 36.7% | 78.3% | 21.7-23.2% | 35.3% | 78.0% | 21.3-22.5% |
| Evaluator spread among tied (mean / median / 95th pct) | 0.029 / 0.022 / 0.082 | 0.009 / 0.000 / 0.045 | 0.023-0.025 / 0.017-0.018 / 0.069-0.072 | 0.018 / 0.013 / 0.051 | 0.006 / 0.000 / 0.028 | 0.015 / 0.010-0.012 / 0.041 |
| Production tie-break minus a random tied pick, mean [95% CI] | +0.0004 [-0.0002, +0.0009] | -0.0003 [-0.0005, -0.0000] | +0.0001 to +0.0009 | -0.0004 [-0.0009, +0.0000] | -0.0002 [-0.0004, -0.0000] | -0.0004 to +0.0003 |
| Production tie-break minus the evaluator's best tied pick (mean / worst) | -0.013 / -0.14 | -0.004 / -0.15 | -0.011 to -0.012 / -0.15 | -0.009 / -0.15 | -0.003 / -0.13 | -0.007 to -0.008 / -0.32 |
| Our strongest player chosen when available | 45.4% | 60.8% | 38.3-41.8% | 45.8% | 61.2% | 36.3-43.3% |

**Night level, tie-break variants vs production (paired, expected games):**

- Random tie-break (3 seeds): plan changed on 61-62% (8-Ball) and 59-60% (9-Ball) of nights when we lead first, 78% when they lead first; the first divergence is a LEAD decision in most cases. Mean difference -0.0009 to +0.0008, every CI but one includes 0 (9-Ball seed 2, we lead first: +0.0008 [0.0000, +0.0017]); median 0; 5th-95th percentile about ±0.03 to ±0.06; worst -0.17 to -0.34.
- Reversed order: 8-Ball -0.0009 to -0.0018 (we lead first CI below 0); 9-Ball +0.0005 to +0.0008 (CIs include 0). Strongest player moves 1.4-1.65 games later.

## 3. Final disposition of disputed claims

| Claim | Disposition | Evidence | Severity |
|---|---|---|---|
| The reproduced SL3 pairing was Unknown because of the 20-game threshold | **CONTRADICTED** | Regression control: still Unknown with the threshold removed (4.796-point gap) | Corrects an earlier claim |
| 71% of Unknowns are caused by the threshold | **CONTRADICTED** | 71% was association; caused share 41.9% / 38.3%; globally the threshold decides 15.3% / 14.4% of all pairings | Statistically meaningful |
| Removing the threshold would improve recommendations | **CONTRADICTED** in 8-Ball; **INCONCLUSIVE** in 9-Ball | 8-Ball: worse under skill+evidence (CIs below 0), neutral under skill-only. 9-Ball: worse under skill+evidence, slightly better in one of four skill-only setups | Not consequential either way on average |
| Ties are frequent | **SUPPORTED** | 35-37% of early leads, 78% of late leads, 21-23% of responses, both formats | Consequential to explanation |
| Equally scored candidates are strategically interchangeable | **CONTRADICTED** for early leads and responses (median evaluator spread 0.010-0.022 games); **SUPPORTED** for late leads (median 0) | Decision-level evaluator spreads above | Statistically meaningful |
| The production tie-break (highest skill level first) systematically loses value | **CONTRADICTED** | At the decision: production minus random tied pick within ±0.001; at night level random tie-breaks within noise | Cosmetic on average |
| A better tie-break could recover value | **SUPPORTED** (model-dependent, small) | The evaluator's best tied pick is worth about 0.003-0.013 expected games more per tied decision; worst single decision 0.13-0.32 | Potentially consequential on some nights |
| Tie-breaks can swing individual nights | **SUPPORTED** (model-dependent) | Worst paired night -0.17 to -0.34 expected games; 5th-95th percentile about ±0.03-0.06 | Potentially consequential for that night |
| Answer ties are not disclosed to the captain | **SUPPORTED** (code) | `analytics/match_night_engine.py` lists only alternatives that lose later value; lead ties are disclosed | Consequential to trust |
| Unknown behaves like an even game in 9-Ball, not in 8-Ball | **SUPPORTED** (actual outcomes, `FOCUSED_IMPACT.md` section 2.3) | 9-Ball 46-55% at every gap; 8-Ball 26-37% at gaps of -2 or worse | Potentially consequential in 8-Ball |
| The shared point scale materially changes 9-Ball recommendations | **CONTRADICTED** (`FOCUSED_IMPACT.md` section 3) | 4-9% of first decisions change, no projected effect | Cosmetic |
| Cap compliance is affected by tie-breaks or the threshold | **CONTRADICTED** | 100% in every variant | None |

## Limitations

- Every counterfactual outcome depends on the evaluators; unplayed pairings are never observed, the bench is unrecorded, games are treated as independent, and the opponent policies are assumptions.
- The replay builds overall records from archive-captured games; the live product uses APA career totals (agreement on who is new is high on current rosters, `FOCUSED_IMPACT.md` 2.4).
- The test holdout has been looked at several times; small differences should be read conservatively.
- No fix, tuning or recommendation follows from this report.
