# M3 score signal study: pre-registration (written before any result was computed)

Scope: does the *score itself* contain signal about team outcomes? It does **not** test whether following M3 wins more, and no result may be read that way.

## Data and unit
- Archive `ultimate_coach_staging.db`, opened read-only. Matches since 2023-01-01, scored, not a bye, 8-Ball Open or 9-Ball Open (analysed separately), with exactly five players per side in `player_matches` and five decided games in `player_head_to_head`, all pairings consistent with the two rosters.
- Official APA team points: `matches.home_score`, `matches.away_score`.
- Unit of analysis: the match (home minus away differences) for adjusted models; the team-night (two per match) for the plain correlation, with a cluster bootstrap by match.

## The M3 score
- For every historical pairing, the **production** rule `analytics.ultimate_coach_confidence.pair_confidence` run in a chronological replay: only results on strictly earlier local dates (same method as `scripts/replay_confidence_levels.py`), then `LEVEL_POINTS` (Strong 6, Solid 3, Thin 1, Unknown 0, Conflicted 0, Caution -3).
- A team's **M3 score** = the sum of level points over the five pairings it actually played (the board total). This is not the plan's minimax value, which needs put-up order and the bench, neither of which is recorded.

## Skill-level baselines
- ΔSL sum: home team's total skill levels minus the away team's.
- ΔSL expected: sum over games of an out-of-time skill-pair win rate, fitted on the training period only (empirical per-pair rate shrunk toward a fitted logistic gap slope, 25 pseudo-games). Difference home minus away.
- "Skill-only" = both together.

## Split
- Train: 2023-01-01 to 2025-08-31. Test (all headline numbers): 2025-09-01 onward. Models are fitted on train, evaluated on test.

## Outcomes
1. Points: home points minus away points (continuous); also each team's own points against its own M3 score.
2. Night win: home points > away points. Ties are excluded from the headline; sensitivity treats a tie as half a win.

## Statistics and uncertainty
- Team-level Pearson and Spearman correlation between a team's M3 score and its own points, and standardized effect per one SD.
- Adjusted: points difference by OLS and night win by logistic regression, on differences. Report the M3 coefficient per one SD of the home-minus-away M3 score.
- Incremental value: test-set ΔR² (points) and ΔAUC and Δlog-loss (night win) for skill-only + M3 versus skill-only.
- 95% intervals by bootstrapping test matches (B = 1000). Same-sign check on the train period.
- Also reported: share of matches where the home-minus-away M3 score is exactly zero (uninformative), and results restricted to |ΔM3| >= 3.

## Verdict rules (fixed now)
Practical thresholds: correlation r >= 0.05; incremental ΔR² >= 0.005; incremental ΔAUC >= 0.005.
- **SUPPORTED**: the 95% interval excludes zero in the positive direction **and** the point estimate meets the practical threshold.
- **PARTIALLY SUPPORTED**: the interval excludes zero in the positive direction but the estimate is below the threshold, or the result holds for only one of the two outcomes or only on the informative subset.
- **NOT SUPPORTED**: the interval includes zero and its upper bound is below the practical threshold, or the effect is significantly negative.
- **INCONCLUSIVE**: the interval includes zero and its upper bound reaches the threshold (not enough information to tell).

Verdicts are given separately for 8-Ball and 9-Ball and for each of the three questions. Six interval-based verdicts per outcome are reported without multiplicity adjustment, and I will say so.

## Limits stated in advance
- Observational. Captains chose these boards; unobserved information and team quality may drive both the board and the result.
- The score is evidence from history before each night, so it reflects a team's players' past form. Tracking outcomes is its purpose; the test says nothing about whether choosing a different board would change the night.
- Not tested against overall win percentage or other form measures; that is a different question.
