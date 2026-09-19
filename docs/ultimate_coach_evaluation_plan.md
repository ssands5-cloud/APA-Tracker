# Ultimate Coach chronological evaluation plan

This slice designs deterministic expanding-window folds only. It does not fit a model, tune coefficients, calculate model performance, calibrate probabilities, or permit publication.

## Boundary

The planner consumes the same leakage-safe prequential rows and the existing backtest-readiness gate. A plan can be `PLAN_READY` only when the format independently passes `READY_FOR_EVALUATION_DESIGN` and at least one valid fold exists.

EIGHT and NINE remain independent.

## Same-instant rule

The atomic chronological unit is a unique instant, not a row. All games sharing the same real instant, including equivalent timestamps expressed with different UTC offsets, stay together. A fold must satisfy:

`max(train target time) < min(holdout target time)`

This prevents same-night/doubleheader evidence from leaking across a train/holdout boundary merely because rows have different `game_key` values.

## Provenance

Every fold exposes the exact training and holdout `game_key` lists plus its train-end, holdout-start and holdout-end timestamps. Train and holdout provenance may never overlap.

Unsafe mirror evidence, malformed chronology, duplicate provenance and wrong-format rows are already excluded by the upstream prequential/temporal gates and cannot re-enter here.

## Publication lock

Every result carries:

- `probability_publication = FORBIDDEN`
- `model_training_performed = false`
- `calibration_performed = false`
- `evaluation_executed = false`

`PLAN_READY` means only that an independently audited future evaluator has a leakage-safe fold design to execute.

## Claude audit challenge

Audit the exact frozen SHA after CI passes. Try to prove that:

1. a same-instant batch can be split across train and holdout
2. NINE evidence can enter an EIGHT fold or vice versa
3. unverified evidence can enter any fold
4. a fold can contain the same `game_key` on both sides
5. a training target can be simultaneous with or later than a holdout target
6. readiness failure can still produce `PLAN_READY`
7. zero/negative fold-policy values are accepted
8. `PLAN_READY` can unlock a probability, model-training, calibration, or publication path

Require executable evidence. Source inspection alone is not a PASS.