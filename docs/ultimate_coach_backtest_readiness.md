# Ultimate Coach backtest-readiness boundary

This slice answers one question only: **does one format's verified historical archive contain enough leakage-safe evidence to justify designing/running a later held-out evaluation?**

It does not train a model, choose coefficients, calibrate probabilities, or approve odds publication.

## Inputs

The readiness report consumes the same `All Games` evidence already hardened by the temporal-integrity/prequential layer. Only rows admitted by that layer can contribute.

EIGHT and NINE are evaluated independently.

## Default readiness policy

A format remains `NOT_READY` until it has at least:

- 30 eligible chronological target games
- 8 distinct players represented in eligible targets
- 15 targets with at least one strictly earlier verified game
- 5 targets with strictly earlier direct history between the same two players

These are engineering readiness thresholds, not claims of statistical sufficiency. They may be revised before model evaluation, but may never be interpreted as calibration success.

`READY_FOR_EVALUATION_DESIGN` means only that a later audited evaluation may be attempted.

`probability_publication` remains `FORBIDDEN` in every status.

## Auditability

The report exposes:

- exact target `game_key` provenance
- counts of eligible targets and distinct players
- prior/direct/shared-opponent support counts
- exclusions inherited from the prequential integrity gate
- explicit readiness failures
- duplicate target provenance detection

No excluded source row is repaired or filled.

## Claude audit challenge

Audit the exact frozen SHA after CI passes and attempt to prove that:

1. unsafe mirror evidence cannot help satisfy a threshold
2. NINE rows cannot help EIGHT readiness or vice versa
3. same-instant games cannot create prior support
4. insufficient direct history cannot be masked by a large total archive
5. invalid/zero readiness thresholds fail closed
6. every admitted target is traceable by exact `game_key`
7. `READY_FOR_EVALUATION_DESIGN` cannot be confused in code with calibration/model approval
8. no probability publication path, estimator, coefficient fitting, or model training was introduced

A source-code inspection is not enough for PASS. Require executable evidence and adversarial cases.
