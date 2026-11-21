# Ultimate Coach recommendation research: final evidence summary

Consolidation of the work since the SL3-vs-SL7 recommendation was reproduced (issue #119). No new experiments, fixes, tuning or production changes. Every number below comes from an earlier published run; the source file is named in each row.

**Verdicts:** SUPPORTED, CONTRADICTED, INCONCLUSIVE. Where an earlier statement of mine failed a stronger test, it is listed as CONTRADICTED.

**Sources** (branch `claude/m3-validation-research`):
- `docs/research/issue119/`: the main experiment (`issue119_experiment.py`, `results_clean.json`, `results_raw.json`) and `RED_TEAM_RESPONSE.md`.
- `docs/research/forensic/`:
  - `FORENSIC_REPORT.md`: engine inventory, claim checks, scenarios.
  - `NIGHT_REPLAY.md`: whole-night replay.
  - `FOCUSED_IMPACT.md`: ties, Unknown causes, format.
  - `FOCUSED_CONTROLS.md`: global threshold removal, lead/response isolation, dispositions.
- `docs/research/m3-validation/`: earlier M3 studies and the snapshot manifest.

**Data:** local archive snapshot, sha256 `4f4c861b…` (matches the manifest), clean record policy. 2023+ games for actual outcomes. Test nights from 2025-09-01: 3,476 8-Ball and 3,132 9-Ball (five players a side, five decided games).

**Simulated vs actual:** "expected games" and "3 of 5" are simulated with evaluators fitted only on 2013-2022 data. They are not APA team points or team wins.

## The originating case

M3 answered their SL7 with our SL3. Reproduced exactly from the captain file: the SL3 scored 0 (Unknown) and every teammate scored -3 (Caution) or +1 (Thin, for the SL6). The planner kept the SL6 for a better pairing later, giving totals of 0 and -1. The arithmetic is correct; no coding defect was found (`issue119` decision trace).

## 1. Unknown classification

| Original hypothesis | Investigation | Evidence | Verdict |
|---|---|---|---|
| Unknown represents an even game (documented as "a true coin flip") | Production replay of level outcomes; Unknown outcomes split by skill gap and format (`FORENSIC_REPORT.md` 3, `FOCUSED_IMPACT.md` 2.3) | Unknown wins exactly 50% overall, but only because the level is symmetric between the two players. 8-Ball, lower player: 26-37% at gaps of -2 or worse; higher player 55-65% at +1/+2. 9-Ball: 46-55% at every gap | **CONTRADICTED for 8-Ball, SUPPORTED for 9-Ball** |
| M3's levels order next-game outcomes as documented | Re-ran `scripts/replay_confidence_levels.py` (it refuses the archive's duplicate rows; ran with the 193 affected matches excluded) | 8-Ball 68.1 / 57.6 / 53.3 / 50.0 / 42.4%, 9-Ball 61.2 / 54.2 / 51.4 / 50.0 / 46.1%, within 0.1 point of the documented table | **SUPPORTED** (with the duplicate-row caveat) |
| Unknown overstates lower players against stronger ones in 8-Ball | Calibrated level model vs actual, lower player vs SL7, test period | Implied 46.4%, actual 34.3% (n = 855); SL3 vs SL7 actual 22.2% (n = 990, CI 19.7-24.9) | **SUPPORTED** |
| Unknown pairings drive many recommendations | Production plans on test nights | 26-27% of all cross pairings are Unknown; M3's answer to their top player is Unknown on 25-27% of nights | **SUPPORTED** |

## 2. 20-game threshold

| Original hypothesis | Investigation | Evidence | Verdict |
|---|---|---|---|
| The SL3 was Unknown because of the 20-game threshold (my earlier root cause) | Smoothed records; global threshold removal as a regression control (`FOCUSED_IMPACT.md` 2.1, `FOCUSED_CONTROLS.md` 1) | 58.82% vs 63.62%, a 4.796-point gap under the 5-point Caution line; still Unknown with the threshold removed | **CONTRADICTED** |
| The threshold causes about 71% of Unknowns | Counterfactual re-scoring with the threshold at 0 | 71% was association only. It causes 41.9% (8-Ball) / 38.3% (9-Ball) of Unknowns, and decides 15.3% / 14.4% of all pairings when removed globally | **CONTRADICTED** (corrected figures SUPPORTED) |
| The threshold mainly hides unfavourable evidence | Destination levels of threshold-caused Unknowns | It hides both directions: Caution about 50%, Solid about 39-40%, Strong about 10-12% | **CONTRADICTED** |
| Removing the threshold would improve recommendations | Paired whole-night replays, threshold removed globally and Unknown-only, two evaluators, 1,000 bootstraps | 8-Ball: worse under skill+evidence (-0.003 to -0.006 expected games, CIs below 0), neutral under skill-only. 9-Ball: worse under skill+evidence; slightly better in 1 of 4 skill-only setups | **CONTRADICTED (8-Ball), INCONCLUSIVE (9-Ball)** |
| Low-history players are mostly capture gaps, not new players | Current rosters: archive games vs APA career totals | 93% of players under 20 recorded games are genuinely new (8-Ball 275 of 296, 9-Ball 177 of 204) | **CONTRADICTED** |
| Incomplete capture thins other evidence | Same rosters | About a fifth of rostered players have less than half their career in the archive. The effect on individual recommendations was not isolated | **SUPPORTED** that it exists; **INCONCLUSIVE** on impact |

## 3. Tie-breaking

| Original hypothesis | Investigation | Evidence | Verdict |
|---|---|---|---|
| M3 recommendations are frequently exact ties | Every decision logged by type on test nights (`FOCUSED_CONTROLS.md` 2) | Ties on 35-37% of early leads, 78% of late leads, 21-23% of responses, both formats | **SUPPORTED** |
| Ties are broken silently | Code review plus planner output | Lead ties are disclosed ("first by roster order"); answer ties are not (only alternatives that lose later value are listed) | **SUPPORTED** for answers |
| The production tie-break (highest skill level first) systematically loses value | Decision-level comparison with a random tied pick; night-level paired replays | At the decision: within ±0.001 games. Across nights: random tie-breaks within noise, median 0 | **CONTRADICTED** |
| Tied candidates are strategically interchangeable | Evaluator value of each tied candidate at the same state | Early leads and responses: median spread 0.010-0.022 games, 95th percentile up to 0.08. Late leads: median 0 | **CONTRADICTED (early leads, responses), SUPPORTED (late leads)** |
| A better tie-break could recover value | Evaluator's best tied candidate vs the production pick | About 0.003-0.013 expected games per tied decision; worst single decision 0.13-0.32. Model-dependent | **SUPPORTED** (small) |

## 4. Roster order

| Original hypothesis | Investigation | Evidence | Verdict |
|---|---|---|---|
| Roster display order changes recommendations | Production vs reversed, player-id, random orders and random tie-break only, identical nights (`FOCUSED_IMPACT.md` 1, `FOCUSED_CONTROLS.md` 2) | First decision changes on 13-65% of nights, the five-game plan on 35-96%. Order acts only through ties: whole-order changes and tie-break-only randomization behave alike | **SUPPORTED** |
| Roster order changes average projected outcomes | Paired replays, two evaluators, two opponent policies, both lead orders | Means within ±0.004 expected games; the sign depends on the assumed opponent | **CONTRADICTED** |
| Roster order can swing single nights | Same | Worst single night -0.17 to -0.47 expected games; 5th-95th percentile about ±0.03-0.06 | **SUPPORTED** (model-dependent) |
| Roster order decides when our strongest player plays | Same | Reversed order moves the strongest player 1.3-1.65 games later on average | **SUPPORTED** |
| Roster order affects cap compliance | Same | 100% compliance in every variant | **CONTRADICTED** |

## 5. Skill level

| Original hypothesis | Investigation | Evidence | Verdict |
|---|---|---|---|
| Skill-level gaps carry outcome signal | Actual skill-pair outcomes, all years (`issue119` tables) | 8-Ball lower player vs SL7: SL2 10.9%, SL3 22.2%, SL4 34.4%, SL5 34.3%, SL6 37.5%. 9-Ball: about 50% at every level | **SUPPORTED (8-Ball), CONTRADICTED (9-Ball)** |
| Skill levels add predictive value beyond M3's levels | Chronological backtest, rolling validation, leakage probe, clean vs raw records (`issue119`, `RED_TEAM_RESPONSE.md`) | 8-Ball: M3 levels plus skill beat M3 levels in every one of five rolling blocks (+0.0038 to +0.0067 log loss); skill+evidence +0.0094 to +0.0127. 9-Ball: skill adds nothing to M3 in any block | **SUPPORTED (8-Ball), CONTRADICTED (9-Ball)** |
| Recorded skill levels are pre-match values | Rise-after-win test | A rise follows a win on the next match (5.5% vs 0.7% after a loss), not the same match | **SUPPORTED** |
| The legacy skill-only win probability is well calibrated | Its 0.40-per-level rule vs archive rates (`FORENSIC_REPORT.md` 3) | Predicts SL3 vs SL7 at 16.8% in both formats; actual 22% (8-Ball) and 50% (9-Ball). +1 level predicted 60%, actual 56% / 49%. Used by legacy surfaces, not the Sunday file | **CONTRADICTED** |

## 6. 8-Ball vs 9-Ball

| Original hypothesis | Investigation | Evidence | Verdict |
|---|---|---|---|
| The formats behave differently for skill gaps | Actual outcomes and APA race charts | 8-Ball: a strong, non-linear effect (two-dimensional race chart). 9-Ball: near even (each player's target depends only on their own level) | **SUPPORTED** |
| M3's levels mean the same thing across skill gaps | Level outcomes by gap and format (`FOCUSED_IMPACT.md` 3) | Ordered in both formats. In 8-Ball meaning shifts with gap (Caution 28% at -3, 50% at +2). Roughly stable in 9-Ball | **CONTRADICTED (8-Ball), SUPPORTED (9-Ball)** |
| The single shared point scale distorts 9-Ball recommendations | 9-Ball scored with 9-Ball-derived ratios | 4-9% of first decisions change; no projected effect | **CONTRADICTED** |
| Better-informed planning helps more in 8-Ball | Night replay by format | +0.013 to +0.032 expected games (8-Ball) vs +0.007 to +0.013 (9-Ball). Model-dependent | **SUPPORTED** |
| Optimal captain strategy differs by format | Not tested directly | Different win rates alone do not establish different optimal strategies | **INCONCLUSIVE** |

## 7. Match-night replay

| Original hypothesis | Investigation | Evidence | Verdict |
|---|---|---|---|
| Better single-game prediction also predicts night results better | Realized boards, test nights (`RED_TEAM_RESPONSE.md` 8) | Night-win AUC 8-Ball M3 levels 0.591 vs skill+evidence 0.625; 9-Ball 0.547 vs 0.586 (actual outcomes) | **SUPPORTED** |
| The skill+evidence planner makes better whole-night plans than M3 | Same production search, identical nights, two opponent policies, both lead orders, two pre-2023 evaluators (`NIGHT_REPLAY.md`) | Higher in every setup. 8-Ball +0.013 to +0.032 expected games and +0.5 to +1.2 points of simulated 3-of-5 probability. 9-Ball +0.007 to +0.013. All CIs above 0 | **SUPPORTED** (simulated, model-dependent) |
| That planner wins more real APA team matches | Same | Unplayed boards are never observed, the bench is unrecorded, games are treated as independent, APA team points are not simulated | **INCONCLUSIVE** |
| Both planners respect the cap | Same | 100% for both | **SUPPORTED** |
| The candidate preserves strong players differently | Same | Our strongest player plays at game 2.6-3.5 vs 2.1-2.3 for M3; it gives up a little in the game being answered | **SUPPORTED** |
| Past captains' boards match M3's preferences | Captain-vs-M3 study (`m3-validation`) | Realized boards sit at chance relative to M3's optimum (3.4% vs 3.4% null) | **CONTRADICTED** |

## 8. Explainability

| Original hypothesis | Investigation | Evidence | Verdict |
|---|---|---|---|
| A captain can see why a player was chosen over the alternatives | Code and output review; decision logs | The reason text names the level and evidence; the cost of rejected alternatives is shown only when they lose later value; answer ties are not disclosed | **CONTRADICTED** for tied answers; **SUPPORTED** otherwise |
| Unknown tells the captain why evidence is missing | Reason texts | "No direct history and no clear overall or shared-opponent edge" is the same whether the player is new or the records are close | **CONTRADICTED** |
| Skill-level context is shown with each recommendation | Screens and payload | No skill-gap reference accompanies a level; an Unknown SL3 vs SL7 reads like an Unknown SL5 vs SL5 | **CONTRADICTED** |
| The live orderings agree with each other | Scenario test (`FORENSIC_REPORT.md` 5) | Next Send ranks a 2-0 above a 9-1 that M3 calls Strong; small samples are labelled | **CONTRADICTED** |
| Recommendations are robust to small assumption changes | Margin and sensitivity analyses | M3's game-one answer ties its runner-up on 35-36% of nights and is within 1 point on 59%; one-point changes flip the originating case | **CONTRADICTED** |

## Consolidated conclusion

1. **M3 works as designed.** The engine, cap logic and Python/JavaScript parity are correct (392 tests, independent game-tree and brute-force checks). The originating SL3-vs-SL7 pick is a consequence of the scoring design, not a bug.
2. **The core weakness is how no-evidence pairings are valued in 8-Ball.** Unknown scores as even at every skill gap. In 8-Ball that is wrong at gaps of two or more levels; in 9-Ball it is approximately right.
3. **The 20-game threshold is not the cause I first claimed.** It causes 38-42% of Unknowns, it did not cause the originating case, and removing it does not improve projected decisions.
4. **Ties and roster order matter for explanation and for individual nights, not on average.** Ties are frequent and often not strategically equal, but the current tie-break neither helps nor hurts on average.
5. **Skill levels and recorded form add real predictive information in 8-Ball, consistently over time.** In 9-Ball, form helps and skill level does not.
6. **A planner using that information scores better in simulation,** mostly in 8-Ball (about +0.02 to +0.03 expected games per night). Whether it wins more real APA team matches cannot be determined from the archive.
7. **The main explainability gaps are disclosable:** undisclosed answer ties, an Unknown label that does not say why, and no skill-gap context.

**Open integrity caveats:**
- Duplicate head-to-head rows block the production replay script.
- The 2025-09+ holdout has been reused across studies; differences under about 0.005 should be treated as noise.
- All counterfactual results depend on the evaluators.
- The replay builds records from archive games while the live product uses APA career totals.

No fixes, tuning, production changes or new investigations follow from this summary.
