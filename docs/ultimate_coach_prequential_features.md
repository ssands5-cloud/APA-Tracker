# Ultimate Coach prequential feature boundary

This slice creates descriptive pre-game feature snapshots for future chronological backtesting. It does **not** train a model or emit a matchup probability.

## Leakage boundary

For target game time `T`, a feature may use only trusted same-format games whose real timestamp is strictly less than `T`. Games at the same timestamp are deliberately excluded from one another's history. This fail-closed rule protects doubleheaders and cases where intra-night ordering is unavailable.

Only canonical `VERIFIED_UNIQUE` All Games rows are eligible. EIGHT and NINE are processed separately. Missing/invalid timestamps, incomplete target identities/outcomes, and unverified mirror evidence are excluded rather than filled.

Each target feature row preserves exact `prior_game_keys` and `direct_prior_game_keys` so an auditor can reproduce the evidence boundary.

## Current descriptive features

- prior games/wins/losses for each participant
- prior direct games and participant-A direct W/L
- prior shared-opponent ids/count

These are intentionally simple. No current career total, current skill snapshot, or other field that may contain information learned after the target game is admitted in this slice.

## Publication lock

Every output reports `probability_publication = FORBIDDEN`. There is no estimator, score, probability, calibration curve, threshold, or production activation path here.

## Claude audit challenge

Audit exact frozen SHA when CI is green. Try to falsify all of these:

1. A future game can never alter an earlier target's feature values.
2. Two games sharing the same timestamp cannot see each other.
3. NINE evidence cannot enter EIGHT features and vice versa.
4. `VERIFIED_COUNT_ONLY` and other unsafe evidence cannot enter history or targets.
5. Direct record and shared-opponent evidence are reproducible from exact source `game_key` lists.
6. No post-game/current aggregate is used as a historical feature.
7. No output can be interpreted as permission to publish odds.
