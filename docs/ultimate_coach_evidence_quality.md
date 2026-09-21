# Ultimate Coach evidence-quality gate

This layer sits between the canonical `All Games` contract and future coaching/model outputs. It does not predict outcomes.

## Rules

- 8-Ball and 9-Ball are separate scopes.
- Every factual direct record returns the exact `game_key` values supporting it.
- Shared-opponent comparisons return exact source keys for both players.
- Only `VERIFIED_UNIQUE` All Games rows are trusted for recommendation-grade factual summaries.
- `VERIFIED_COUNT_ONLY`, `MISSING_REVERSE`, `MIRROR_MISMATCH`, and `REVERSE_ONLY` fail closed as `INSUFFICIENT_EVIDENCE`.
- Missing history is `NO_RECORDED_HISTORY`, never a neutral record and never a synthetic probability.
- An unsafe shared-opponent comparison is quarantined without discarding other independently verified common opponents.

## Why VERIFIED_COUNT_ONLY is not recommendation-grade

The canonical contract can prove the count of repeated same-player games when both directional multisets reconcile, but the persisted schema no longer contains the original source position needed to pair those repeated directional rows one-for-one. That is useful audit evidence, but not enough to silently promote each occurrence to a uniquely reconciled game.

## Model boundary

This module must not expose matchup odds. Chronological held-out calibration on real archived APA games remains a separate gate. Until that gate passes, downstream UI should show factual records/evidence confidence and `NOT CALIBRATED` for probability.

## Claude audit challenge

Try to break these invariants:

1. Reverse participant orientation and prove W/L remains correct.
2. Mix EIGHT and NINE rows and prove no cross-format contamination.
3. Inject each non-unique mirror status and prove no W/L summary is emitted from it.
4. Give one unsafe and one safe shared opponent and prove only the unsafe comparison is quarantined.
5. Verify every emitted factual record can be traced to exact `All Games.game_key` values.
6. Verify no code path in this layer invents a probability, fills a missing game, or converts unknown evidence into a loss/win.
