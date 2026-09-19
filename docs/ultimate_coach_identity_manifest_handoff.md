# Ultimate Coach roster-backed identity manifest handoff

This slice automates the canonical identity boundary needed by all-player
profiles without using display-name matching or trusting arbitrary scoresheet
ids.

## Source proof

The historical archive writes every real division-roster member into the
Players table and writes a PlayerTeamHistory row carrying the real team id,
division id, and session name before scoresheet identities are reconciled.

Unresolved scoresheet aliases may still exist as Player rows, but they do not
gain roster-backed PlayerTeamHistory provenance merely by appearing on a
scoresheet.

The manifest therefore treats complete roster provenance as the minimum
offline proof that a Player row is a canonical APA member identity.

## Verification requirements

A VERIFIED_UNIQUE manifest identity requires all of the following:

- canonical internal player_id is an integer and not a Python bool
- member_external_id is a numeric string from the source contract
- exactly one Player row exists for that internal player id
- the APA member id does not map to another internal Player row
- at least one PlayerTeamHistory row matches the exact member id
- that provenance row has nonblank team_external_id, division_id, and
  session_name
- no team-history row supplies a conflicting valid APA member id

Display names are metadata only. They are never used to resolve identity.

## Fail-closed exclusions

The manifest reports rather than repairs:

- malformed Player rows
- invalid internal player ids
- non-string or non-numeric APA member ids
- duplicate Player rows
- one APA member id mapped to multiple Player rows
- conflicting team-history member ids
- missing or incomplete roster provenance
- orphan or malformed team-history rows

Malformed history-member types do not get string-coerced into proof.

## Output

analytics/ultimate_coach_identity_manifest.py emits:

- verified identities directly compatible with the all-player profile builder
- exact roster-provenance scopes per identity
- identity exclusions
- structural history issues and counts
- name_matching_used = False
- requires_live_apa_login = False
- probability_publication = FORBIDDEN

## Claude audit challenge

Audit the exact frozen head for:

1. Python bool aliasing integer player ids;
2. integer/float/member-id coercion into a valid APA member id;
3. display-name matching anywhere in verification;
4. duplicate internal ids or member ids surviving as VERIFIED_UNIQUE;
5. orphan history creating a player;
6. blank team/division/session provenance satisfying verification;
7. malformed or conflicting history member ids being ignored unsafely;
8. unresolved scoresheet aliases receiving profiles without roster proof;
9. nondeterministic ordering or duplicated provenance scopes;
10. any live-login, model, calibration, confidence, or probability side effect.

Green CI is execution evidence only. It is not proof that every live archive
identity will resolve, and it does not authorize production promotion or odds.
