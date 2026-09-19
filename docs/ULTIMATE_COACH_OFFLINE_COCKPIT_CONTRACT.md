# Ultimate Coach Offline Scout & Compare Cockpit Contract

## Status

Research-only builder checkpoint. This contract does not authorize production promotion, live APA access, model training, calibration, matchup odds, or probability publication.

`probability_publication = FORBIDDEN`

## Purpose

Define the fail-closed offline presentation boundary for Scout & Compare before any predictive layer is allowed. The cockpit may summarize only already-ingested, provenance-bearing APA evidence. It must never turn missing, ambiguous, quarantined, or future-derived evidence into a value.

## Source boundary

The cockpit consumes repository-produced archive/enrichment artifacts only. It does not log in to APA, scrape live pages, or mutate source evidence.

Every displayed evidence bundle must carry:

- source archive identity/digest when available from the upstream artifact;
- exact player identity keys used by the archive;
- format (`EIGHT` or `NINE`);
- source `game_key` provenance for historical game-derived claims;
- evidence-quality/exclusion state supplied by the upstream quality layer;
- artifact generation/evaluator identity where supplied upstream.

If required provenance is absent, duplicated, contradictory, or cannot be tied unambiguously to one player and one format, the affected panel fails closed as `EVIDENCE_UNAVAILABLE` rather than filling a gap.

## Identity rules

- Player matching is by canonical archive identity, never display-name guessing.
- Ambiguous identities are not auto-resolved.
- A player must never compare against themselves.
- Aliases may be shown only when an upstream canonical identity mapping explicitly supports them.
- Unknown or conflicting identity evidence is quarantined from comparison statistics.

## Format isolation

8-Ball and 9-Ball are independent evidence domains.

- No cross-format games may enter a statistic, trend, shared-opponent summary, direct-history summary, or readiness state.
- The UI must label the active format visibly.
- Switching formats rebuilds the evidence view from that format's provenance rather than reusing cached values from the other format.

## Scout view

For one unambiguous player and one format, the offline Scout view may show descriptive, provenance-backed fields already supported by archive/enrichment artifacts, such as:

- verified historical record/counts;
- chronology/trend summaries derived only from verified games;
- opponent history and shared-opponent evidence;
- evidence coverage and exclusions;
- data freshness/archive boundary information.

A field with insufficient safe evidence is shown as unavailable with its reason. Zero is displayed only when the evidence proves zero.

## Compare view

For two distinct, unambiguous players in one format, Compare may show side-by-side descriptive evidence and verified direct/shared-opponent history.

Compare must not show:

- matchup win probability;
- implied odds or betting-style language;
- calibrated confidence presented as a probability;
- fabricated head-to-head history;
- neutral-filled values for missing evidence;
- rankings that silently mix 8-Ball and 9-Ball.

Until chronological real-archive evaluation and calibration gates are independently passed, any predictive surface must remain absent or explicitly locked.

## Temporal safety

When a historical as-of boundary is requested, every game-derived value must use evidence strictly available before that boundary under the upstream temporal-integrity rules. Same-instant games remain atomic. Current career totals must not be projected backward into historical views unless the upstream artifact proves they are as-of-safe.

## Evidence confidence

Confidence labels describe evidence quality/coverage only. They are not predictive confidence.

Allowed states should be explicit and machine-readable, for example:

- `VERIFIED_EVIDENCE`
- `PARTIAL_VERIFIED_EVIDENCE`
- `EVIDENCE_UNAVAILABLE`
- `AMBIGUOUS_IDENTITY`
- `QUARANTINED_EVIDENCE`

The cockpit must expose why evidence was excluded rather than hiding exclusions behind a score.

## Offline behavior

A complete offline render must require no APA credentials or network fetch. If an expected local artifact is absent or invalid, the cockpit fails closed and identifies the missing dependency. It must not fetch replacement data automatically.

## Audit invariants

Claude should adversarially verify that an implementation cannot:

1. leak 9-Ball evidence into an 8-Ball view or vice versa;
2. merge two people because their display names resemble each other;
3. convert missing evidence to zero;
4. use quarantined/reverse-only/mirror-invalid evidence as verified history;
5. reuse current totals in a historical as-of view without temporal provenance;
6. split same-instant historical evidence across an as-of boundary;
7. invent direct history when only shared-opponent evidence exists;
8. emit matchup odds, probabilities, or probability-like confidence while publication is forbidden;
9. hide exclusion reasons or provenance needed to reproduce a displayed claim;
10. require a live APA login for an offline cockpit render.

## Exit criteria for a later implementation slice

A future implementation may be frozen only after tests prove format isolation, ambiguous-identity failure, missing-data failure, provenance traceability, temporal safety, deterministic offline rendering, and the probability-publication lock on the exact CI-tested head.
