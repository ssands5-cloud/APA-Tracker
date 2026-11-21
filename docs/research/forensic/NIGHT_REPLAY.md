# Historical match-night replay: current M3 vs skill+evidence planner

Research only. Nothing deployed, nothing tuned, no production code changed. Script `night_replay.py`, output `night_replay_clean.json` (aggregates only), snapshot sha256 `4f4c861b…` (matches the manifest).

## Setup

- **Identical nights:** every 2025-09+ match with five players a side and five decided games: 3,476 8-Ball and 3,132 9-Ball nights; the ten players who actually played, in production roster order; cap 23 both teams.
- **Planners:** the same production search (`analytics.match_night_engine._Night`). M3 uses its level points; the candidate uses the issue #119 skill+evidence probabilities (fitted 2023-01 to 2025-08, untouched). Each plays all five games, re-planning after every game.
- **Opponent:** identical for both planners, two behaviours: adversarial (best reply under the evaluator) and "top first" (puts up its highest-level legal player, answers greedily). Both first-leader orders are played.
- **Scoring:** unplayed pairings are never observed, so each game is scored by an evaluator fitted only on 2013-2022 games: skill+evidence and skill-only. Night win = at least 3 of 5 games, games assumed independent. **Every outcome below is model-dependent.** The skill+evidence evaluator shares the candidate's feature family, which favours the candidate; the skill-only evaluator does not.

## Results (candidate minus M3; 95% bootstrap over nights)

| Format | Evaluator / opponent | Expected games per night | Night-win probability | Candidate better / worse on |
|---|---|---|---|---|
| 8-Ball | skill+evidence, adversarial | +0.021 to +0.029 | +0.8 to +1.1 points | 68-73% / 24-27% of nights |
| 8-Ball | skill+evidence, top first | +0.031 to +0.032 | +1.2 points | 64-66% / 31% |
| 8-Ball | skill-only, adversarial | +0.013 to +0.017 | +0.5 to +0.6 points | 52-56% / 20-21% |
| 8-Ball | skill-only, top first | +0.022 to +0.029 | +0.8 to +1.1 points | 58-59% / 24-27% |
| 9-Ball | skill+evidence, both opponents | +0.011 to +0.013 | +0.4 to +0.5 points | 56-66% / 30-39% |
| 9-Ball | skill-only, both opponents | +0.007 to +0.009 | +0.3 points | 45-51% / 29-35% |

Ranges span the two first-leader orders; every interval excludes zero. Baseline M3 expected games 2.45-2.51 and night-win probability 0.48-0.50 per night. At 14 matches a season, +1 point of night-win probability is about 0.14 extra night wins.

| Measure | 8-Ball M3 / candidate | 9-Ball M3 / candidate |
|---|---|---|
| Cap compliance (both teams, every replayed night) | 100% / 100% | 100% / 100% |
| Preservation: game our highest-level player plays (mean) | 2.1-2.3 / 2.6-3.3 | 2.2-2.3 / 2.7-3.5 |
| Opening answer differs (they lead, adversarial) | 2,454 of 3,475 nights (71%) | 2,253 of 3,132 (72%) |
| Response quality: this game's evaluator chance vs the best legal answer, mean shortfall | 0.040-0.063 / 0.050-0.071 | 0.013-0.032 / 0.010-0.030 |
| Identical five-game board | 3-7% of nights | 2-6% |

The candidate gives up a little in the game being answered (higher same-game shortfall in 8-Ball) to save its strongest player for later; across the whole night it comes out ahead under every evaluator and opponent.

**Explainability (decisions across replayed nights):** M3's choice is an exact tie with the runner-up on 38% (8-Ball) and 37% (9-Ball) of decisions, broken by roster order. The candidate is rarely an exact tie (11%), but 46% (8-Ball) and 57% (9-Ball) of its choices are within 0.02 expected games of the runner-up, so many of its preferences are thin. Chosen pairings rest on a direct record 21% / 21% of the time in 8-Ball and 19% / 27% in 9-Ball; about 27-29% are Unknown pairings for both.

## What this does and does not show

- Under two independent pre-2023 evaluators and two opponent behaviours, the candidate's plans score consistently higher, mostly in 8-Ball: about +0.02 to +0.03 expected games and +0.5 to +1.2 points of night-win probability per night.
- It does not show more real team wins. Counterfactual boards were never played, the bench is unrecorded, games are treated as independent, and APA team-point scoring is simplified to "3 of 5 games".
- No tuning was done; no recommendation is made.
