# Ultimate Coach evaluation evidence contract

This checkpoint defines the evidence required before any later model-quality or calibration claim can be considered. It does not train, fit, tune, score, calibrate, or publish a model.

## Frozen parent

This work is stacked on frozen evaluation-plan head `1424056dcd51e69fefd3ab50ae79123598ddefca` (PR #43). The parent must not be modified.

## Evidence bundle requirements

A future evaluator must emit an immutable, reviewable bundle for each format independently. EIGHT and NINE evidence must never be pooled.

Each bundle must contain:

- exact evaluator code commit SHA
- exact source archive identity/digest
- format (`EIGHT` or `NINE`)
- exact evaluation-plan schema/version and policy
- every fold's train and holdout `game_key` provenance
- train-end, holdout-start, and holdout-end timestamps
- exclusion counts and reasons inherited from upstream evidence gates
- deterministic configuration sufficient to reproduce the run
- per-fold target counts and aggregate target count
- explicit execution status

A bundle is invalid if any required identity, provenance key, timestamp, configuration field, or exclusion reason is missing or ambiguous.

## Chronology invariant

For every fold:

`max(train target time) < min(holdout target time)`

Same-instant games are atomic. Train and holdout `game_key` sets must be disjoint. Evidence must fail closed if these properties cannot be demonstrated from the source archive.

## Publication lock

This contract does not authorize predictions. Every evidence bundle remains research-only until separate chronological evaluation and calibration gates pass on real archive data.

Required state at this checkpoint:

- `model_training_performed = false`
- `calibration_performed = false`
- `probability_publication = FORBIDDEN`

No placeholder metrics, synthetic outcomes, imputed games, neutral fills, or fabricated provenance are permitted.

## Claude audit handoff

Audit executable evidence, not source shape alone. Attempt to demonstrate that a future evidence bundle can:

1. omit its source archive identity or evaluator SHA and still be accepted
2. mix EIGHT and NINE provenance
3. contain duplicate or overlapping train/holdout `game_key` values
4. split equivalent same-instant timestamps across a fold boundary
5. accept an ambiguous/missing identity or timestamp
6. silently discard upstream exclusions
7. claim execution or calibration that did not occur
8. unlock matchup probability publication merely because an evaluation plan exists

Any successful bypass is a blocking defect. This document itself is only a contract and must not be treated as execution evidence.