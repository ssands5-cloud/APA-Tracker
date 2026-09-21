# Ultimate Coach all-player enrichment implementation handoff

This slice implements the descriptive profile contract defined in
docs/ultimate_coach_all_player_enrichment_contract.md.

## Files

- analytics/ultimate_coach_player_profiles.py
- tests/test_ultimate_coach_player_profiles.py

## Behavior

The builder consumes the canonical All Games rows plus explicit identity
records. It does not query APA, mutate SQLite, train a model, or publish odds.

A profile is created only when the supplied identity is VERIFIED_UNIQUE and
carries a real integer canonical player id. Python bool, strings, floats,
nulls, ambiguous identities, unresolved identities, and duplicate verified
identity declarations fail closed.

Profiles are isolated by EIGHT/NINE format and retain exact game_key
provenance for the observed record, each dated skill-level observation, and
each direct opponent summary.

Historical as_of profiles require an offset-aware timestamp and accept only
source events strictly earlier than that boundary. Same-instant events are
excluded from the historical snapshot, including equivalent instants expressed
with different timezone offsets.

Unsafe rows are reported rather than repaired:

- blank game keys
- duplicate game keys
- unverified mirror status
- missing, invalid, or timezone-naive event times
- invalid or self opponent identity
- incomplete or inconsistent outcomes

Missing skill levels remain None. No-recorded-history is represented as an
explicit evidence status with wins/losses unavailable rather than silently
presenting a 0-0 performance record.

## Publication firewall

Every profile and all-player bundle preserves:

- matchup_probability = None
- predictive_confidence = None
- probability_publication = FORBIDDEN
- requires_live_apa_login = False

## Claude audit challenge

Audit the exact frozen head for:

1. any path where bool, string, float, or null identity can become a profile;
2. duplicate identity declarations accidentally producing two profiles;
3. EIGHT/NINE contamination;
4. duplicate, blank, or unverified provenance entering verified aggregates;
5. timezone-naive or same-instant leakage across as_of;
6. future evidence changing an earlier historical profile;
7. missing skill level becoming numeric zero;
8. self-pairing or contradictory winner/loser evidence entering a profile;
9. nondeterministic output caused by input order;
10. any field that could be mistaken for calibrated predictive confidence or
    matchup probability.

Green CI is execution evidence only. It is not predictive validation or
authorization to publish odds.
