# Decision engine validation: research report (read-only audit)

Author: Claude (independent auditor). Date: 2026-11-20. Nothing in this report changed production code, the database, the UI, any branch, or any deployment. M3 is untouched and remains the benchmark. All data stayed local; this file contains no player or team names.

## 0. Summary

1. **M3 verified as implemented** (section 1). Its only learned-from-history parameter set is six integer level points; its inputs are four record types plus one flag; its optimizer is an exact minimax over alternating put-ups under the cap.
2. **All three prior studies reproduced bit-for-bit** (the regenerated `results.json` files are byte-identical to the originals; seeded). No temporal leakage found in the designs. Two real design weaknesses and several limits are listed in section 3.
3. **The contradiction has a likely, now measured, explanation.** M3's predictive signal sits in *who plays* (player-form differences between the two teams), which does not change when you re-pair the same ten players. The part of M3 that depends on *how they are paired* has a coefficient of about zero (8-Ball 0.03 [-0.04, 0.10]; 9-Ball 0.00 [-0.09, 0.08] per SD), while the who-plays part is strong (0.39 [0.30, 0.48]; 0.30 [0.22, 0.38]). See section 4.
4. **Component attribution:** player form (own and opponent lifetime win rate) carries most of the out-of-sample signal in both formats. M3's level label adds nothing once its own inputs are in the model (8-Ball drop-one +0.00001 nats; 9-Ball -0.00013). A refit of M3's own inputs beats M3's fixed weights by a clear margin (section 5).
5. **Go / No-Go:** M3 No-Go as evidence of captain value (keep only as frozen benchmark); M4 conditional Go (offline research); M5 No-Go until a cheap headroom test passes; M6 No-Go until put-up order and bench data exist (section 8).

## 1. Phase 1: M3 verification

**Source, at repository HEAD `6d74dc8`** (worktree `uc-broadcast-ui`):

| File | sha256 (first 16) | Role | Last engine-relevant commit |
|---|---|---|---|
| `analytics/ultimate_coach_confidence.py` | `b8edf535d3bfe565` | level rule `pair_confidence`, `LEVEL_POINTS` | `8b48382` (2026-10-20) |
| `analytics/match_night_engine.py` | `5c3eb50ee70a7004` | exact minimax planner (`_Night`, `match_plan`, `_best_board`) | `8b48382` (2026-10-20) |
| `ui/ultimate_coach_war_room.js` | `6e71d5236ef74c3b` | JavaScript mirror (parity tested) | UI-only changes in November |
| `scripts/replay_confidence_levels.py` | `dfc24bad0acaa004` | chronological level replay used by all studies | `8b48382` |

M3 introduction: `29a4f78` (2026-10-18), skill cap on both teams `7cea29b`. The algorithm has not changed since 2026-10-20; November commits changed inputs and screens only.

**Inputs per pairing:** direct (wins, meetings); both players' overall (wins, games) in the format; shared-opponent record (our wins/games, their wins/games, common count); a flag for "skill levels changed since they last met". Recency and the skill-level gap are **not** inputs.

**Feature definitions (exact):** form = (w + 5)/(g + 10); a form edge counts once both players have 20 games; thresholds .05 (any), .15 (strong), shared edge .10 (Solid needs 3 common opponents); direct record is Strong at 5+ meetings and 70%+ or at 3+ meetings with a stronger form, Solid at 3+ meetings or stronger form, else Thin; unfavourable direct is Caution, or Conflicted when form disagrees; flag downgrades Strong/Solid one step.

**Weighting system:** `LEVEL_POINTS = Strong 6, Solid 3, Thin 1, Unknown 0, Conflicted 0, Caution -3`, scaled from a 15-year replay (8-Ball +18/+8/+3/0/-8 points over even, 9-Ball +11/+4/+1/0/-4), Thin = 1, rounded.

**Optimizer:** maximise the night's total level points over the remaining games with alternating put-ups; the opponent is assumed adversarial (minimax); the skill cap binds both teams; deterministic Python and JavaScript.

## 2. Reproduction of prior studies

| Study | Script | Reproduced? |
|---|---|---|
| M3 signal study | `m3-signal-study/m3_signal_study.py` | Yes, byte-identical `results.json` |
| Captain vs M3 | `m3-captain-study/captain_vs_m3.py` | Yes, byte-identical |
| Component study | `m3-component-study/component_study.py` | Yes, byte-identical |
| Historical validation (levels order next-game wins, 843k games) | `scripts/replay_confidence_levels.py` | Not rerun end to end here; its logic is the replay all three studies reuse, and the same ordering appears in my replay (the full-model single-group M3 term has gain in both formats). The 843k figure is the project's own and was not independently recounted. |

Sample sizes (test period 2025-09-01 onward): signal and captain studies 8-Ball 3,469 matches, 9-Ball 3,126 (train 6,526 / 5,759); component study 23,648 8-Ball and 20,769 9-Ball games (fit 2023-01..2025-02, validation 2025-03..2025-08, test after). Intervals: 95% bootstrap by match (B = 1000; B = 300 in the component study). Train/test: chronological; SL-pair win tables and all coefficients fitted on train only; model selection (lambda, greedy forward selection) used only the validation window.

## 3. Audit findings

| Check | Finding | Severity |
|---|---|---|
| Temporal leakage | None found. All features computed from days strictly before; all of a day's games evaluated before history updates; SL-pair tables train-only; test never used for selection. | OK |
| Inclusion filter uses post-match info | Matches must have 10 decided games and two five-player rosters. Not outcome-dependent: included vs excluded home-win rate 47.7% vs 48.2% (8-Ball), 48.4% vs 49.0% (9-Ball); tie rate 7.7% vs 6.6% and 3.3% vs 2.3%. | Low |
| Selection bias | 76% of 8-Ball and 78% of 9-Ball scored non-bye matches since 2023 are included. Only boards captains actually played are observed; the opponent chose half of each. | Medium (stated) |
| Survivorship / partial capture | "Overall" records are only what the archive captured, not lifetime records; new and partly captured players read as Unknown. 27-28% of test pairings are Unknown, 32% Caution, only about 3% Strong. | Medium |
| Correlated features | Team M3 vs skill-level difference r = 0.45 (8-Ball) and 0.19 (9-Ball). Level labels are deterministic functions of form and direct inputs. | Medium |
| Double counting | Each pairing's level uses both players' form, and a pairing is scored from each team's own side, so a form gap enters both teams' totals (a Strong for one side is usually a Caution for the other). A home-minus-away M3 counts a form difference about twice. | Medium |
| Missing-data artifacts | Caution is the largest level (32%); most Caution comes from "no direct history, weaker overall", i.e. a form signal rather than pairing evidence. Early-archive depth is thin. | Medium |
| Lineup legality | Counterfactual boards reuse the realized ten players, so the 23 cap is satisfied by construction. Real put-up alternation, the bench and the captain's true options are not represented. | **High** for any claim about decisions |
| Multiplicity | No correction across the many intervals reported. | Low |
| Design weakness found in my own earlier work | The captain-vs-M3 study measured distance from the M3 optimum, not an outcome comparison of optimal vs actual boards; the premise "M3-optimal boards do not outperform actual boards" is only indirectly supported (a flat dose-response). | Wording, not numbers |
| Design weakness | Team M3 beyond skill levels was tested against skill-only baselines, not against form; it likely proxies form. Confirmed by the component study. | Interpretive |

## 4. Phase 2: why M3 correlates with outcomes but M3-optimal boards show no advantage

Measured decomposition (test period; logistic on night win; coefficients per SD; AUC for night win). The board total is split into its mean over all 120 matchings (depends only on which players are on the table) and the deviation of the realized board from that mean (depends only on the pairing).

| | 8-Ball | 9-Ball |
|---|---|---|
| Who-plays part | 0.39 [0.30, 0.48] | 0.30 [0.22, 0.38] |
| How-paired part | 0.03 [-0.04, 0.10] | 0.00 [-0.09, 0.08] |
| AUC: skill only / + who-plays / + both | 0.577 / 0.620 / 0.620 | 0.549 / 0.579 / 0.577 |
| Correlation between the two parts | 0.04 | -0.01 |

Ranked explanations (likelihood from highest):

**1. The signal is between teams, not within a night's pairing (high confidence).** M3's score measures how strong a team's players are relative to the opponent's, which is fixed once the ten players are known; rearranging them cannot move it.
- Supports: the decomposition above; the how-paired coefficient is a precise null in 8-Ball; the dose-response of regret vs night win is flat (8-Ball +0.007 [-0.071, 0.079] logit per SD).
- Contradicts: nothing observed. The how-paired part is measured over all 120 matchings, not only the ones a captain could reach.
- Data to confirm: put-up order and bench, to restrict to reachable boards.

**2. The pairing-specific inputs are weak predictors (high).** What a rearrangement actually changes is direct head-to-head, shared opponents and skill-gap interactions; form (own and opponent) dominates.
- Supports: single-group gain over base rate, 8-Ball: form 0.0178, skill 0.0094, shared 0.0058, direct 0.0014; 9-Ball: form 0.0051, recent 0.0051, shared 0.0011, direct 0.0006. Drop-one for direct and shared is within noise in 8-Ball.
- Contradicts: in 9-Ball the direct term has a small but significant drop-one effect (+0.00016 [0.00006, 0.00025]), so pairing information is not exactly zero.
- Data: a larger sample of repeat pairings, or a pairing-level experiment.

**3. The counterfactual space is not the captain's real choice set (high).** Alternation means a captain controls half of each pairing; the opponent's put-ups, the bench and the cap shape what is reachable.
- Supports: realized boards sit at chance relative to M3 (optimal 3.4% vs 3.4% null; mean regret 0.51 vs about 0.50 expected from random pairing), which would be odd if boards were chosen for pairing quality alone.
- Contradicts: a flat result would still be expected if the how-paired part has no effect (explanation 1); this explanation and that one are not exclusive.
- Data: who declared each game, availability, the options at each put-up.

**4. Game outcomes are close to coin flips, so pairing effects are small relative to noise (medium-high).** APA handicaps aim at even games; five games per night swamp small edges.
- Supports: best full-model game AUC 0.609 (8-Ball) and 0.566 (9-Ball); skill alone has AUC 0.514 in 9-Ball.
- Contradicts: 8-Ball skill has a real gradient at the extremes (SL6/SL7 against SL3-5).
- Data: pairing-level effect sizes from a larger sample with cap-feasible alternatives.

**5. M3's currency is a trust label, not an expected-points estimate (medium).** Level points were calibrated to order next-game wins, and the project states levels are never probabilities. Summing them need not track expected team points, and nothing models APA point scoring.
- Supports: M3 alone recovers only 45% (8-Ball) and 28% (9-Ball) of the full refit's out-of-sample gain.
- Contradicts: levels do order games monotonically.
- Data: calibrated per-game probabilities (the M4 harness).

**6. Power in 9-Ball (medium).** The 9-Ball dose-response and AUC intervals are wide (ΔAUC -0.037 to +0.006 in the captain study), so a modest effect cannot be excluded there; this is the only format where the contradiction is not a precise null.
- Contradicts: 8-Ball is precise.
- Data: more seasons, or pooled across formats if justified.

**7. Captain private information and confounding (low-medium).** Captains may use style, practice and availability information that is not recorded, so realized boards already embed unrecorded signal, or strong captains may both pick good boards and win for other reasons.
- Supports: nothing direct.
- Contradicts: if captains used information correlated with M3, realized regret would fall below random; it does not.
- Data: captain identity, recorded declarations, bench.

## 5. Phase 3: component attribution (game level, test period)

Full refit (all groups): 8-Ball log-loss 0.6737 vs base rate 0.6931, gain 0.0195 [0.0170, 0.0220], AUC 0.609, accuracy 57.5%; 9-Ball gain 0.0071 [0.0055, 0.0087], AUC 0.566, accuracy 54.4%. For a linear model, SHAP values are coefficient times centred feature, so per-group mean |SHAP| and permutation importance (group columns permuted jointly) are reported.

| Group | 8-Ball single gain | 8-Ball drop-one [95%] | 8-Ball permutation | 9-Ball single gain | 9-Ball drop-one [95%] | 9-Ball permutation |
|---|---|---|---|---|---|---|
| Form (own and opponent) | 0.0178 | +0.0029 [0.0017, 0.0042] | 0.0198 | 0.0051 | +0.0012 [0.0004, 0.0020] | 0.0062 |
| Skill gap and own level | 0.0094 | +0.0007 [-0.00002, 0.0014] | 0.0026 | 0.0003 | +0.0008 [0.0004, 0.0014] | 0.0015 |
| Recent (last 10) | 0.0083 | -0.00004 [-0.0002, 0.0001] | 0.0002 | 0.0051 | +0.0009 [0.0004, 0.0015] | 0.0019 |
| Shared opponents | 0.0058 | -0.0001 [-0.0005, 0.0003] | 0.0012 | 0.0011 | +0.0001 [-0.0001, 0.0003] | 0.0001 |
| Team strength (own, opposing) | 0.0024 | +0.0001 [-0.0001, 0.0003] | 0.0003 | 0.0005 | -0.00002 [-0.0001, 0.0001] | -0.00003 |
| Direct head-to-head | 0.0014 | +0.0001 [-0.0001, 0.0003] | 0.0006 | 0.0006 | +0.0002 [0.0001, 0.0003] | 0.0002 |
| M3 level (6 indicators) | 0.0087 | +0.00001 [-0.0001, 0.0002] | 0.0001 | 0.0020 | -0.0001 [-0.0003, 0.0001] | 0.00001 |
| Home team | 0.00002 | +0.00002 | 0.0001 | -0.00002 | -0.00004 | 0.00002 |
| Skill changed since last meeting | -0.00004 | +0.00001 | 0.00001 | -0.00003 | 0.0 | 0.00001 |

**Findings (evidence of association, not of causation):**
- **Most valuable:** form (8-Ball, 9-Ball). In 9-Ball recent form and the skill gap also matter, and the skill gap helps only together with form (single gain 0.0003, drop-one +0.0008).
- **Least valuable:** home team and skill-changed flag (no signal either format).
- **Redundant:** M3 level (fully explained by its inputs: drop-one about 0, in both formats), shared opponents, team strength, direct (8-Ball), recent (8-Ball).
- **Potentially harmful:** none with a significant harm; M3 level, team strength and home in 9-Ball have negative drop-one point estimates with intervals including zero (no evidence of benefit or harm).
- **Correlation among components:** M3 level is a function of form, direct and shared; its single gain (0.0087 / 0.0020) is absorbed by form once form is included.
- **M3's fixed weights vs a refit of the same kind of inputs (test log-loss minus full):** M3 only +0.0108 [0.0085, 0.0128] (8-Ball), +0.0051 [0.0036, 0.0067] (9-Ball); skill only +0.0101 / +0.0068; skill + M3 +0.0059 / +0.0046; full model without M3 +0.00001 / -0.00013.
- **Can M3 be simplified?** Greedy selection picks form, skill, team (8-Ball) and form, recent, direct (9-Ball). Their test loss minus full: 8-Ball +0.00059 [-0.00007, 0.00118] (INCONCLUSIVE against the 0.0005 bound), 9-Ball +0.00066 [0.00006, 0.00120] (does not meet the bound strictly). A three-group model nearly matches the full model; M3 alone does not.
- **Is M3 the correct formula?** On game-level prediction, **NOT SUPPORTED** in both formats (M3 only loses 0.011 and 0.005 nats to a refit). This does not say a refit would improve lineups; that remains untestable here.

## 6. Phase 4: challenger designs (no implementation)

**M4: hierarchical Bayesian matchup predictor.**
- Inputs: game outcomes with date, format, both players, their skill levels, team, home flag, game number, match score state. Output: posterior win probability per pairing with interval.
- Structure: player strength with partial pooling (by team, division, skill level), a skill-gap term, a pair-specific random effect shrunk to zero, a slow time drift per player.
- Data: archive since 2011 (about 851k decided game rows) plus a held-out future season.
- Assumptions: additive latent strength on the logit scale; exchangeable pair effects; independence across games conditional on strengths.
- Strengths: calibrated uncertainty, handles new players honestly (wide intervals instead of Unknown), absorbs the form signal the component study found, produces probabilities that a team-outcome optimizer can consume.
- Weaknesses: needs fitting infrastructure (MCMC or variational), probabilities are currently project-forbidden to publish until gates pass; strength is learned only from partial-capture data.
- Validation: the common harness (section 7); calibration slope and intercept, log-loss and AUC on the frozen test windows.
- Cost: fitting hours on a laptop for one format using variational inference; per-night scoring milliseconds.

**M5: time-aware gradient boosted predictor.**
- Inputs: the nine feature groups here plus rolling windows, days since last game, SL history, team context.
- Data: same; roughly 24k test games per format is small for boosting.
- Assumptions: nonlinear interactions exist that logistic models miss.
- Strengths: automatic interactions, easy importance reporting.
- Weaknesses: the signal is weak (AUC 0.57 to 0.61) and sample sizes moderate, so overfit risk is real; probabilities need calibration; opaque for captains; the library is not installed here.
- Validation: same harness, walk-forward refits; first a headroom test against the regularised logistic model.
- Cost: minutes per fit on one CPU; cheap to run.

**M6: APA-rules-aware probabilistic team-outcome optimizer.**
- Inputs: calibrated per-pairing probabilities (from M4), the skill cap, alternating put-up structure, game race rules, APA team-point scoring, bench availability, score state.
- Output: distribution of team points and night-win probability under each decision policy; optimizer maximises expected match points (or win probability) under an opponent model.
- Assumptions: an opponent model (adversarial vs observed behaviour); independence of games given probabilities; known cap.
- Strengths: targets the real objective; can use score state; can evaluate APA scoring.
- Weaknesses: untestable on the archive because put-up order, the bench and alternatives are unrecorded; the opponent model cannot be validated; heaviest build.
- Validation: needs recorded declarations and availability for at least a season; offline policy evaluation with an explicit counterfactual model, kept separate from observed outcomes.
- Cost: moderate (the existing minimax search plus Monte Carlo over game outcomes); development cost is the highest.

## 7. Phase 5: common evaluation harness (specification)

1. **Cutoffs:** train through 2025-02-28; validation 2025-03-01 to 2025-08-31 (selection only); test 2025-09-01 to the end of the archive; additional rolling-origin folds with 6-month test blocks starting 2024-09-01 for stability. All models use identical cutoffs and identical game and match filters (those in sections 2 and 3).
2. **Chronology:** features computed from strictly earlier local days; walk-forward refits; no future information anywhere.
3. **Two separate result tables.** (A) *Observed outcomes:* game-level log-loss, AUC, calibration, and match-level night-win and points metrics on realized boards. (B) *Counterfactuals:* any statement about alternatives (regret, simulated policies) labelled model-dependent and never merged into (A).
4. **Uncertainty:** 95% bootstrap intervals clustering by match (resample matches), B at least 1000; paired differences between models; report no result without an interval; correct or flag multiplicity.
5. **Contestants:** actual captain boards (observed), the existing production predictor (September skill-only win-probability term), M3 (frozen), M4, M5, M6, and baselines: base rate, skill-gap logistic, form logistic, lifetime win rate difference, coin flip.
6. **Metrics:** game level: log-loss, Brier, AUC, calibration slope/intercept. Match level: AUC and log-loss for night win, RMSE for points difference. Decision level (only for models producing boards): regret against each contestant's own counterfactual space, always flagged model-dependent.
7. **Pass gates (preregistered per model):** beats the form-logistic baseline on paired log-loss with a CI excluding zero, calibration slope within 0.9 to 1.1, results positive in at least 4 of 5 rolling folds.
8. **Reproducibility:** seeded RNG; scripts and results stored with hashes; reruns must be byte-identical.

## 8. Go / No-Go

- **M3: No-Go as evidence of captain value or as a validated objective.** Keep it frozen as the benchmark. The game-level ordering of its levels is real, but its team-level signal comes from who plays, it is fully explained by its own inputs, a refit beats it on game prediction, and no outcome evidence supports its board-optimal choices.
- **M4: Conditional Go, offline research only.** The component study shows what to model (player form and skill, shrunk), and calibrated probabilities are a prerequisite for any serious optimizer. Gate: passes the harness gates in section 7.
- **M5: No-Go for now.** Run only the cheap headroom check first (boosted vs regularised logistic on identical features under the harness). Proceed only if it improves paired log-loss with a CI excluding zero.
- **M6: No-Go until the data exists.** It cannot be validated on the current archive. A Go on data capture (declarations, availability, options, outcomes, captain id) is the prerequisite; the engine work comes after.

## 9. Assumptions and statistical limitations

- Observational; the archive records boards captains chose with information we lack.
- The archive is partial capture; "overall" is not lifetime.
- Game-level prediction quality does not imply better lineups; the data cannot show that.
- No multiplicity correction; borderline results (e.g. 9-Ball direct drop-one) should be read as suggestive.
- The decomposition in section 4 uses all 120 matchings; reachable boards are a subset.
- Playoffs, tri-cup and season standings are not in the data; nothing here speaks to them.
- The 843k-game figure is the project's own and was not recounted.

## 10. Reproducibility

Folder: `tmp/ultimate-coach-release/claude-captain-workflow/`. Archive opened read-only (`?mode=ro`). Python with numpy and pandas; no other dependencies.

```bash
python -I m3-signal-study/m3_signal_study.py
python -I m3-captain-study/captain_vs_m3.py
python -I m3-component-study/component_study.py
python -I m3-captain-study/decomp.py
```

Run each from an empty working directory; each writes `results.json` (`decomp_results.json` for the last). The `repro/` folder holds the verification rerun; `cmp` confirms identical output. Pre-registrations are in each study folder.

## 11. Addendum (portability and rerun)
Scripts now take `--db` or `UC_ARCHIVE_DB` and need no hardcoded paths; see `README.md`. Inputs are sorted so results are independent of database row order. The reruns on the compact snapshot are identical to reruns on the original archive; versus the first run, bootstrap intervals moved by at most 0.005 and no verdict changed. The committed `results.json` files are the rerun. The snapshot itself (real data) stays local.
