# Ultimate Coach identity namespace collision audit handoff

This slice addresses the residual identity risk documented by the historical
repair: canonical APA member ids and unresolved scoresheet alias ids can occupy
the same Player.external_id namespace.

The audit is intentionally read-only. It does not claim it can reconstruct an
already-coalesced source identity from insufficient evidence.

## Inputs

The audit consumes:

- canonical Ultimate Coach data contract
- roster-backed identity manifest
- All Games participant ids/member ids/team ids/session
- Team Matches home/away team ids
- exact PlayerTeamHistory provenance preserved in the identity manifest

Display names are never used for identity resolution.

## Participant classifications

EXACT_ROSTER_SCOPE
- internal player id maps to one roster-backed canonical identity
- observed external member id equals that canonical APA member id
- game team + session exactly matches at least one roster provenance scope
- if Team Match teams are known, participant team belongs to that team match

SUSPECT
- external member id conflicts with the canonical member id
- game team conflicts with known roster team(s) in that same session
- no roster provenance exists for the game session
- participant team is not one of the Team Match teams
- member id is missing/malformed despite a roster-verified identity

A SUSPECT row is a conflict with available evidence. It is NOT automatically
declared a proven numeric namespace collision because historical roster
coverage can itself be incomplete.

INDETERMINATE
- invalid internal player id
- player is not roster-verified
- duplicate identity-manifest player id
- missing game team/session scope
- verified identity contains no usable roster scopes

## Game-level gates

A game enters identity_verified_game_keys only when:

- its game_key is unique and nonblank;
- it is not self-paired;
- both participants classify EXACT_ROSTER_SCOPE;
- All Games mirror_status is VERIFIED_UNIQUE.

Suspect games are added to quarantined_game_keys. Duplicate keys and
self-pairings are structural quarantine.

An unverified mirror does not become identity-verified, even if both participant
scope checks happen to reconcile.

## Command

After the live archive is complete:

python scripts/audit_ultimate_coach_identity_namespace.py

Default source:
data/ultimate_coach_staging.db

Default report:
data/ultimate_coach_identity_namespace_audit.json

The command opens the staging DB read-only in behavior: it builds the contract,
runs the audit, writes only the JSON report, and never commits DB changes.

## Publication firewall

The report explicitly records:

- audit_mode = READ_ONLY_FAIL_CLOSED
- database_mutated = false
- name_matching_used = false
- requires_live_apa_login = false
- matchup_probability = null
- probability_publication = FORBIDDEN

## Claude adversarial audit challenge

Audit the exact frozen head for:

1. display-name matching leaking into identity verification;
2. Python bool or string ids passing as canonical internal ids;
3. malformed member ids being coerced into source truth;
4. external-id mismatch failing to quarantine a game;
5. wrong-team same-session evidence being accepted;
6. missing-session provenance being silently treated as exact;
7. participant team outside the Team Match being accepted;
8. duplicate game keys entering the verified set;
9. self-pairings entering the verified set;
10. duplicate manifest player ids being trusted;
11. unverified mirror evidence entering identity_verified_game_keys;
12. deterministic-output drift based on input ordering;
13. database mutation, live APA access, model output, or probability publication.

The audit is a quarantine detector, not an automatic repair authority.
