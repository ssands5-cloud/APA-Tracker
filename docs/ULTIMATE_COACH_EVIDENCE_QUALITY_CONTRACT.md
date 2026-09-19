# Ultimate Coach Evidence-Quality Contract

Status: builder-only contract. This document does not authorize production promotion, model training, calibration, odds, or probability publication.

Parent checkpoint: frozen PR #45 head `abe4b66a02ae3a7b4cd399bec4d06a6f8441ff4f`.

## Purpose

Define a fail-closed data-quality and evidence-confidence boundary for offline Scout & Compare. Quality labels describe the evidence available for a displayed historical claim. They are not predictive confidence and must never be converted into matchup odds.

## Non-negotiable source rules

1. Use only actual APA source records already present in the verified archive path.
2. Never fabricate, impute, neutral-fill, interpolate, or infer a missing APA result.
3. Every admitted historical game must retain its canonical `game_key` provenance.
4. Ambiguous player identity is excluded, not guessed.
5. 8-Ball and 9-Ball evidence are evaluated and displayed independently. Cross-format substitution is forbidden.
6. Quarantined or non-`VERIFIED_UNIQUE` evidence cannot silently contribute to a displayed count, record, trend, or confidence label.
7. Historical/as-of views may use only evidence strictly available before the requested boundary under the existing temporal-integrity rules.

## Evidence dimensions

Evidence quality must be decomposed rather than collapsed into a model-like score. At minimum a future implementation should expose:

- **identity_integrity**: whether every displayed subject/opponent resolves to one canonical identity without ambiguity.
- **provenance_integrity**: whether every counted game has a unique nonblank `game_key` and traceable archive source.
- **temporal_integrity**: whether all evidence is valid for the requested as-of boundary and same-instant rules are preserved.
- **format_integrity**: whether the evidence is wholly within the selected APA format.
- **direct_evidence_depth**: count of verified direct meetings, reported as a count only.
- **shared_opponent_depth**: verified shared-opponent coverage, explicitly distinct from direct meetings.
- **archive_coverage**: admitted versus excluded evidence counts, with exclusion reasons preserved.

A missing dimension is `UNKNOWN`/unavailable. It must not become zero or a passing value.

## Presentation labels

A cockpit may present descriptive labels such as `INSUFFICIENT_EVIDENCE`, `LIMITED_EVIDENCE`, or `SUBSTANTIAL_EVIDENCE` only when thresholds are deterministic, documented, format-specific, and based solely on the dimensions above. These labels mean evidence quantity/integrity only.

Forbidden interpretations include:

- win probability;
- confidence that one player will beat another;
- expected race score;
- betting or wagering advice;
- a substitute for chronological calibration/backtest results.

The UI must pair any evidence-quality label with language equivalent to: **Evidence quality is not predictive confidence.**

## Fail-closed conditions

The evidence-quality result must be unavailable rather than degraded to a reassuring default when any required condition is ambiguous, including:

- unresolved or multiply resolved player identity;
- blank/duplicate provenance key among admitted evidence;
- selected format cannot be established;
- invalid/ambiguous timestamp for an as-of claim;
- winner/loser identity inconsistent with participants;
- evidence source is quarantined or not admitted by the verified archive boundary.

Exclusions must be countable and attributable by reason. An exclusion cannot silently disappear from coverage accounting.

## Scout & Compare boundary

For a selected format, offline Scout may summarize one canonical player's verified historical evidence. Compare may place two canonical players side-by-side and may show verified direct history and shared-opponent evidence as separate descriptive sections. It must not manufacture a head-to-head conclusion when direct history is absent.

No live APA login is required to render already archived evidence. If fresh APA data is required, the cockpit must report staleness/freshness limitations rather than attempting an unaudited login path.

## Probability publication lock

`probability_publication = FORBIDDEN`

This contract does not satisfy the chronological real-archive backtest/calibration gates. A future probability path requires separate executed evaluation evidence, calibration evidence, acceptance criteria, and audit approval. Green repository CI is not predictive validation.

## Claude adversarial audit handoff

Audit this contract and any future implementation for:

1. missing evidence converted to zero, neutral, average, or pass;
2. ambiguous identities admitted through aliases/name normalization;
3. 8-Ball evidence affecting 9-Ball labels or vice versa;
4. duplicate `game_key` records inflating depth/coverage;
5. quarantined evidence reaching displayed totals;
6. future games leaking into historical/as-of views;
7. shared-opponent evidence being represented as direct history;
8. evidence-quality wording that resembles model confidence;
9. exclusion counts that cannot be reconciled to source provenance;
10. any route that publishes matchup odds before chronological real-archive evaluation and calibration gates pass.

Any such finding is a blocker. Do not merge or promote this builder checkpoint.