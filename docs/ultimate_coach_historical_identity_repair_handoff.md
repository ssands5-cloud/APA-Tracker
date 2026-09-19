# Ultimate Coach historical identity repair handoff

This slice provides an OFFLINE, dry-run-first repair for historical scoresheet
alias identities after the large authenticated archive crawl completes.

It does not query APA and it does not require another live scrape.

## Why a new repair is required

The older scripts/backfill_player_identity.py repair was designed for the
current-roster case. Two properties make that unsafe as the repair mechanism
for the Ultimate Coach historical archive:

1. historical PlayerTeamHistory rows are intentionally is_current=False;
2. the older repair builds one global alias Player.id -> canonical Player.id
   rewrite, even though a scoresheet alias id is not a stable global member
   identity and may appear in more than one team/session/match scope.

The new repair never creates a global alias rewrite.

## Resolution scope

Each candidate PlayerMatch is resolved independently by:

- alias Player.id
- exact Match.id
- exact PlayerMatch.team_id
- exact Match.session_name
- exact display name
- historical roster lookup with current_only=False

Display name is used only inside that exact team + session roster scope. There
is no unscoped name lookup.

## Collision gates

A rewrite is blocked when:

- more than one PlayerMatch row exists for the same alias player + match scope;
- the canonical player already has another PlayerMatch row in that match;
- multiple alias scopes in one match would collapse to the same canonical
  player;
- applying a scope mapping would turn any PlayerHeadToHead row into
  player == opponent.

The self-pairing gate blocks the entire source player/match scope. It does not
rewrite PlayerMatch while leaving the conflicting H2H row behind.

## H2H behavior

PlayerHeadToHead ids are rewritten only with the approved match-scoped mapping.
The same alias Player.id may therefore resolve to different canonical players
in different historical matches when exact team/session provenance proves that
is correct. That is the key safety difference from a global alias rewrite.

## Dry-run first

Default:

python scripts/repair_ultimate_coach_historical_identities.py --db data/ultimate_coach_staging.db --report data/ultimate_coach_identity_repair_dry_run.json

Nothing is changed.

Apply is deliberately separate:

python scripts/repair_ultimate_coach_historical_identities.py --db data/ultimate_coach_staging.db --apply --report data/ultimate_coach_identity_repair_applied.json

Do not apply to the live crawl staging database merely because this PR is
green. The dry-run report must be inspected and independently audited first.

## Residual limitation

The database currently stores canonical member ids and unresolved scoresheet
alias ids in the same Player.external_id namespace.

If two source id namespaces collide numerically during ingestion and are
already coalesced into the SAME Player row, an offline repair cannot assume it
can reconstruct the lost distinction. This script deliberately does not guess.

A separate post-crawl collision/coalescence audit should compare canonical
roster provenance with match-scoped participant team/session evidence and flag
suspect rows before the archive is trusted.

## Publication firewall

The report records:

- network_used = false
- identity_scope_rule = EXACT_TEAM_SESSION_MATCH_SCOPE
- probability_publication = FORBIDDEN

No model, calibration, probability, production promotion, or live APA action is
part of this repair.

## Claude adversarial audit challenge

Audit the exact frozen head for:

1. any remaining global alias rewrite;
2. historical roster lookup accidentally requiring is_current=True;
3. one alias used in two matches being smeared to one canonical player;
4. existing canonical PlayerMatch collision being overwritten;
5. two aliases collapsing into one canonical player/match;
6. self-pairing H2H being created or PlayerMatch being rewritten while that
   H2H conflict stays behind;
7. ambiguous same-name roster membership being guessed;
8. missing session/team scope being guessed;
9. dry-run mutating any database row;
10. H2H rewrites crossing match boundaries;
11. false claims that already-coalesced numeric namespace collisions are
    recoverable;
12. any live network, probability, or production side effect.

Green CI demonstrates execution of the tested contracts only. It does not
authorize applying repair to Paul's live staging database.
