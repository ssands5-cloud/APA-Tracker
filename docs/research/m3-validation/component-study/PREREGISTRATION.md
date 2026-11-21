# M3 component study: pre-registration (written before any code ran)

Scope: which of the inputs behind M3 carry out-of-sample signal about the outcome of a single game, whether they are redundant, whether any hurt, and whether a smaller model matches the full one. Evidence only: no change to M3, no new objective is proposed or implemented (standing freeze).

## Unit and outcome
One decided game from `player_head_to_head` (8-Ball and 9-Ball separately), one random-but-fixed orientation per game (hash of match and player ids). Outcome: the oriented player wins. Games since 2023-01-01 whose match has a known home/away. Features are computed as of strictly earlier local days (same replay discipline as the M3 level replay; all games of a day use history before that day).

## Chronological split
- Fit: 2023-01-01 to 2025-02-28. Validation (model selection only): 2025-03-01 to 2025-08-31. Final fit for evaluation: 2023-01-01 to 2025-08-31. Test (all headline numbers, never used for selection): 2025-09-01 onward.

## Feature groups (the components of M3, plus other candidates)
1. DIRECT: shrunk head-to-head win rate minus 0.5, log(1+meetings), and whether any meeting exists.
2. SKILL: skill-level gap as clipped (-4..+4) one-hot (captures non-linearity), plus own skill level.
3. FORM_OVERALL: both players' shrunk lifetime-in-archive win rates (own and opponent separately), log games played.
4. RECENT: each player's last-10-game win rate (shrunk), own and opponent.
5. SHARED: shared-opponent record difference and count of common opponents.
6. SLCHG: skill level changed since last meeting (production flag).
7. HOME: the player's team is the home team.
8. TEAM: own team's and opposing team's prior game win rate in that format (shrunk), separately.
9. M3: the production level (Strong/Solid/Thin/Unknown/Conflicted/Caution) as six indicators (not forced to its point values).
Opponent strength = the opponent terms in FORM_OVERALL, RECENT and TEAM.

## Models and importance
Regularised logistic regression (L2, lambda chosen on validation), continuous features standardised on the fit period. For a linear model, SHAP values are exactly coefficient times centred feature, so the mean |SHAP| per group is reported along with:
- Permutation importance per group on test (group columns permuted jointly, 5 repeats): rise in test log-loss.
- Drop-one-group: test log-loss of full model without the group minus full model.
- Single-group models and M3-only model, test log-loss and AUC.
Metrics: test log-loss (primary), AUC, accuracy. Log-loss gains are in nats per game against a base-rate model; 95% CIs by bootstrap resampling matches (B = 300).

## Questions and decision rules
1. Signal: a group has signal if the single-group model beats base rate AND drop-one hurts (CI of the loss increase excludes 0).
2. Redundant: single-group beats base rate but drop-one is within noise (CI includes 0) of zero.
3. Hurts: the group's permutation importance is negative or dropping it lowers test log-loss with a CI that excludes 0.
4. Simplification: greedy forward selection by validation log-loss (stop when the gain < 0.0002 nats); the selected model is evaluated once on test. "M3 can be simplified" if the selected model's test log-loss is within 0.0005 nats of the full model's (CI of the difference includes that bound).
5. Rankings: by permutation importance, separately by format.
6. Is M3 the right formula? Compare on test (a) M3-only, (b) skill-only, (c) full refit weights. Verdict per format: M3-only SUPPORTED as adequate if its log-loss is within 0.0005 of the full model; otherwise NOT SUPPORTED; INCONCLUSIVE if the CI straddles the bound.

## Limits
Game-level prediction only. Whether a model that predicts single games better would choose better lineups is a separate, untestable-here question (no put-up order, bench or unplayed alternatives). Home/team features cannot enter a lineup decision when they do not vary across the options; they matter only for calibration. Features using only partial-capture archive history.
