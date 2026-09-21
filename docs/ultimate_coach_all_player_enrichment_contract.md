# Ultimate Coach all-player enrichment contract

Status: builder-only contract. This document authorizes no production promotion, live APA login, model training, calibration, odds, or probability publication.

## Purpose

Define the fail-closed boundary for enriching the verified historical archive into player-level factual profiles usable by the offline Scout & Compare cockpit and later leakage-safe evaluation infrastructure.

## Source-of-truth rules

1. Enrichment may consume only actual APA source records already preserved in the verified archive/evidence pipeline.
2. Missing fields remain missing. Do not fabricate, impute, infer a neutral value, or backfill from another player.
3. Every derived fact must retain attributable source provenance sufficient to identify the contributing archive records.
4. Quarantined, ambiguous, duplicate, malformed, or otherwise unverified records must not silently become verified enrichment evidence.
5. Identity resolution is fail closed. Only canonical, verified-unique player identities may receive a profile.

## Format isolation

8-Ball and 9-Ball are independent evidence domains. Profiles, counts, recency summaries, opponent history, skill-level observations, and derived factual aggregates must be computed separately by format. A record from one format must never satisfy an evidence requirement in the other.

## Temporal safety

Every factual observation must retain its source event time. Any historical `as_of` profile must include only evidence strictly available by that boundary under the archive's timezone and same-instant atomicity rules. Later evidence must not leak backward into an earlier profile.

## Profile outputs

A profile may expose descriptive, provenance-bearing facts such as verified match counts, observed skill-level history, dated opponent history, direct matchup evidence, and other factual aggregates supported by the archive. It must distinguish unavailable evidence from a numeric zero.

The profile must expose exclusions or quality defects when they materially limit the evidence. Evidence quality describes the evidence, not the probability of winning.

## Identity and provenance invariants

- canonical player IDs must pass the repository's strict identity boundary; Python bool aliases are not player IDs
- unresolved or ambiguous identities produce no verified player profile
- duplicate or blank game provenance must fail closed according to the evidence-quality layer
- self-comparison cannot create opponent evidence
- shared-opponent evidence must not be mislabeled as direct matchup history
- source record identity must survive aggregation so facts can be audited back to actual APA evidence

## Publication firewall

All-player enrichment is descriptive infrastructure only.

`probability_publication = FORBIDDEN`

No enrichment metric may be renamed, normalized, scored, ranked, or presented in a way that implies calibrated matchup probability or predictive confidence. Predictive publication remains locked until chronological backtesting/calibration gates pass on real archive data with the required execution evidence.

## Offline requirement

Building and rendering profiles from the preserved archive must not require Paul's live APA login. Any future refresh that requires authenticated APA access is a separate acquisition action and must not weaken offline fail-closed behavior.

## Required implementation tests

Before implementation can be frozen, adversarial tests should cover at minimum:

- ambiguous and unresolved player identities
- bool/string/float/null identity aliases
- 8-Ball/9-Ball cross-contamination attempts
- blank and duplicate provenance
- missing fields versus real numeric zero
- historical `as_of` boundaries and same-instant events
- later-record leakage into earlier profiles
- quarantined evidence
- direct-history versus shared-opponent labeling
- deterministic output for identical verified input
- empty and tiny histories
- preservation of the probability-publication lock

## Audit interpretation

Green CI proves that the implemented checks execute successfully on the tested head. It is not evidence of predictive validity, calibration, or readiness to publish matchup odds.
