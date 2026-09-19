# Ultimate Coach — All-Player Enrichment Implementation Checkpoint

Status: builder-only, offline, not production-approved.

Parent frozen checkpoint: `6ad0f31b1616e8d6fba68ba6f9c685f294600298` (PR #51).

## Purpose

Stage the implementation boundary for deterministic, offline all-player enrichment using only preserved APA archive evidence. This checkpoint intentionally adds no predictions and requires no live APA login.

## Required implementation behavior

1. Accept only canonical player identities whose resolution state is `VERIFIED_UNIQUE`; ambiguous or unresolved identities fail closed.
2. Treat canonical player IDs as strict integers; reject booleans, strings, floats, nulls, and other aliases rather than relying on Python equality coercion.
3. Build 8-Ball and 9-Ball profiles independently. No aggregate may cross formats.
4. Preserve source provenance through every aggregate. Blank, duplicate, quarantined, or otherwise unverified provenance must never silently become verified profile evidence.
5. Historical `as_of` enrichment must be leakage-safe: only evidence strictly available before the requested decision instant may contribute. Events at the same instant are an atomic batch and cannot leak into one another.
6. Preserve missingness. No evidence is `None`/unavailable, not numeric zero. A real observed zero remains distinguishable from missing evidence.
7. Keep direct matchup evidence, shared-opponent evidence, and player-level descriptive archive summaries semantically separate.
8. Every exclusion must remain attributable by reason so the cockpit can expose evidence limitations rather than hide them.
9. Evidence-quality/confidence labels describe provenance/completeness only. They must never be emitted or consumed as predictive confidence.
10. Offline enrichment must be deterministic for identical archive bytes, configuration, format, identity mapping, and `as_of` instant.

## Mandatory safety output

Any enrichment/cockpit surface consuming this layer must retain:

- `matchup_probability = None`
- `predictive_confidence = None`
- `probability_publication = FORBIDDEN`

No builder checkpoint may weaken those values until chronological backtesting and calibration gates pass on real archive data and a separately audited promotion explicitly authorizes publication.

## Test plan before implementation can freeze

Adversarial tests must cover:

- ambiguous/unresolved player identity;
- bool/string/float/null ID aliases;
- 8-Ball/9-Ball contamination attempts;
- blank and duplicate provenance;
- quarantined evidence;
- missing-versus-observed-zero behavior;
- `as_of` future leakage;
- same-instant atomic batches including equivalent timezone offsets;
- deterministic ordering under shuffled input;
- direct-matchup versus shared-opponent labeling;
- empty and tiny histories;
- exclusion reason accounting;
- explicit probability-publication lock.

## Builder/audit boundary

This file is a staging checkpoint, not proof that enrichment is implemented or correct. CI success on this documentation-only commit is execution evidence only. Implementation must be added and tested on this branch or a child builder branch, then frozen at an exact green SHA and handed to Claude for adversarial audit. Do not merge, promote, or modify any frozen parent head.
