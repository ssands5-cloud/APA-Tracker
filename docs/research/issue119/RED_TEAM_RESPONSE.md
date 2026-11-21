# Response to the red-team review (issue #119)

All figures are from `results_clean.json` unless marked raw, produced by `issue119_experiment.py` on snapshot sha256 `4f4c861b…` (matches the manifest). Nothing in production was changed.

## 1. Publish the exact experiment scripts — done
`issue119_experiment.py` is the one script behind every number; `case_trace.py` reproduces the single-recommendation trace. The earlier prototypes are superseded: running the published script with `--policy raw` reproduces the first summary's log-loss gains to four decimals (8-Ball B +0.0012, C1 +0.0053, C2 +0.0113; 9-Ball B -0.0014, C1 +0.0008, C2 +0.0059).

## 2. Fully reproducible run — done
Portable arguments, fixed seeds, sorted inputs, snapshot hash recorded and checked against the committed manifest; commands in `README.md`. Both policies were run end to end from the repository copy of the script.

## 3. Duplicate records — resolved by policy and shown not to matter
- 388 repeated (match, player, opponent) keys: 228 identical repeats, 160 conflicting (158 with opposite results, 2 with different skill levels). No key repeats more than twice.
- Mirror check: every decided row has its mirrored row with the opposite result and swapped skill levels (0 exceptions); 48 rows have no result.
- Clean policy drops identical repeats and both rows of conflicting keys (548 rows of 851,766). Headline gains under clean vs raw are identical to four decimals (8-Ball C2 +0.0113 both; 9-Ball C2 +0.0059 both).

## 4. Skill levels are pre-match values — verified
If a recorded level reflected the result of the match it is attached to, wins would line up with rises on the same match. They do not:

| | Rise recorded on the same match | Rise recorded on the next match |
|---|---|---|
| 8-Ball after a win | 2.6% | **5.5%** |
| 8-Ball after a loss | 3.7% | 0.7% |
| 9-Ball after a win | 2.4% | **5.0%** |
| 9-Ball after a loss | 3.4% | 0.7% |

(463k 8-Ball and 341k 9-Ball player-match transitions.) Rises follow wins on the next match, so a match's recorded level is the level it was played at.

## 5. Chronological separation — verified
- Every feature uses results from strictly earlier local dates; same-day games never see each other.
- Leakage probe: 400 random test games per format, features recomputed directly from rows dated before each game: 0 mismatches (own record, opponent record, direct record, last-10).
- No match is in both train and test; last training day 2025-08-31, first test day 2025-09-01. Penalties were chosen on 2025-03 to 2025-08 only; the test period was evaluated once.

## 6. Re-run on a clean dataset — done
Clean policy, test 2025-09 onward (23,620 8-Ball and 20,740 9-Ball games):

| Model | 8-Ball LL / AUC | gain vs A [95% CI] | 9-Ball LL / AUC | gain vs A [95% CI] |
|---|---|---|---|---|
| A M3 levels | 0.6842 / 0.573 | - | 0.6913 / 0.538 | - |
| B skill pair | 0.6830 / 0.576 | +0.0012 [-0.0005, +0.0031] | 0.6927 / 0.520 | -0.0014 [-0.0026, -0.0001] |
| C1 M3 + skill | 0.6789 / 0.594 | +0.0053 [+0.0039, +0.0066] | 0.6905 / 0.546 | +0.0008 [+0.0001, +0.0016] |
| C2 skill + evidence | 0.6729 / 0.613 | +0.0113 [+0.0094, +0.0135] | 0.6854 / 0.570 | +0.0059 [+0.0043, +0.0075] |

Independent re-estimation with plain empirical rates matches the logistic fits (8-Ball A 0.6842 vs 0.6842, B 0.6829 vs 0.6830; 9-Ball A 0.6913 vs 0.6913, B 0.6924 vs 0.6927).

## 7. Rolling-period validation — done
Gain in log loss vs A for each 6-month test block (3-year training window before each):

| Block | 8-Ball C1 | 8-Ball C2 | 9-Ball C1 | 9-Ball C2 |
|---|---|---|---|---|
| 2024-03 | +0.0051 [+0.0027, +0.0075] | +0.0124 [+0.0089, +0.0158] | +0.0002 [-0.0012, +0.0017] | +0.0049 [+0.0014, +0.0079] |
| 2024-09 | +0.0050 [+0.0029, +0.0073] | +0.0116 [+0.0083, +0.0153] | +0.0002 [-0.0011, +0.0015] | +0.0033 [+0.0004, +0.0059] |
| 2025-03 | +0.0058 [+0.0032, +0.0078] | +0.0125 [+0.0094, +0.0158] | -0.0011 [-0.0022, +0.0002] | +0.0058 [+0.0039, +0.0085] |
| 2025-09 | +0.0038 [+0.0017, +0.0060] | +0.0094 [+0.0050, +0.0137] | +0.0012 [-0.0002, +0.0023] | +0.0054 [+0.0028, +0.0080] |
| 2026-03 | +0.0067 [+0.0054, +0.0084] | +0.0127 [+0.0099, +0.0151] | +0.0006 [-0.0005, +0.0015] | +0.0063 [+0.0042, +0.0081] |

8-Ball: M3 + skill beats M3 in all five blocks; skill + evidence beats M3 in all five blocks in both formats. 9-Ball: skill levels add nothing to M3 in any block; skill alone is worse than M3 in every block.

## 8. All reported metrics recalculated — done
Calibration (clean, test): intercept/slope/ECE 8-Ball A 0.023/1.083/0.006, B 0.019/1.025/0.009, C1 0.022/1.025/0.008, C2 0.016/0.929/0.009; 9-Ball A 0.046/0.812/0.015, B 0.042/0.707/0.013, C1 0.048/0.832/0.015, C2 0.047/0.893/0.012.

Night level (realized boards, test nights 3,476 8-Ball / 3,132 9-Ball; correlation of expected with actual games won; night-win AUC): 8-Ball A 0.18 / 0.591, B 0.18 / 0.577, C1 0.22 / 0.604, C2 0.26 / 0.625; 9-Ball A 0.10 / 0.547, B 0.06 / 0.539, C1 0.12 / 0.565, C2 0.16 / 0.586.

Game-one planner comparison (model-dependent; unplayed pairings are never observed; bench unrecorded): the same M3 planner fed C2 probabilities picks a different answer to their top player on 2,394 of 3,476 8-Ball nights; under two evaluators fitted only on pre-2023 data, its choice is worth +0.015 [+0.013, +0.017] and +0.014 [+0.012, +0.015] expected games (8-Ball), +0.006 and +0.007 (9-Ball). These are small and depend on the evaluators; they are not evidence of more nights won.

Explainability (game-one answers, 8-Ball / 9-Ball): M3's answer ties its runner-up on 36% / 35% of nights and is within 1 point on 59% / 59%; it rests on a direct record on 27% / 26% and is a 20-game Unknown on 21% / 18%.

## Conclusions unchanged
Skill level adds out-of-sample information to M3's levels in 8-Ball, consistently across time; not in 9-Ball. Recorded evidence (form) helps in both. Decision-level benefit remains unproven. Recommendation stays **INVESTIGATE FURTHER**.
