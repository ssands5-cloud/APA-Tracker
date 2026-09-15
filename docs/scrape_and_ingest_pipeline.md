# Full APA scrape and ingest pipeline design

This document specifies a future production CLI for creating a fresh,
auditable APA Tracker snapshot. It is design-only. The command coordinates
existing authentication, scraper, parser, ingest, reconciliation, and
verification boundaries; it does not duplicate their logic.

## Command and modes

Proposed entry point:

```powershell
python scripts/scrape_and_ingest.py --live --auth token-env --token-env APA_TOKEN --config apa_config.yaml --out runs/2026-09-15
```

For deterministic rehearsal and CI:

```powershell
python scripts/scrape_and_ingest.py --fixtures tests/fixtures/sample_pipeline --config tests/fixtures/ci_pipeline_config.yaml --out runs/fixture
```

Exactly one acquisition mode is required:

- `--live` permits authenticated APA network requests;
- `--fixtures PATH` forbids network access and reads an approved fixture tree.

## CLI contract

| Flag | Purpose |
| --- | --- |
| `--config PATH` | Repository-local non-secret league/team configuration |
| `--out PATH` | New run directory inside the canonical repository |
| `--db PATH` | Optional database path inside the run directory; defaults to `apa.db` |
| `--live` | Explicit authorization for the production acquisition path |
| `--fixtures PATH` | Offline acquisition source; mutually exclusive with `--live` |
| `--auth token-env\|token-stdin\|credentials-env\|prompt\|browser` | Required live authentication mechanism; forbidden in fixture mode |
| `--token-env NAME` | With `--auth token-env`, read a short-lived token from the named environment variable |
| `--token-stdin` | With `--auth token-stdin`, read exactly one token line from standard input without echoing it |
| `--username-env NAME` | Environment variable containing the username |
| `--password-env NAME` | Environment variable containing the password |
| `--team-id ID` | Optional configured-team override, stored as text |
| `--opponent-team-id ID` | Optional scope restriction for rehearsal |
| `--format NAME` | Optional format restriction |
| `--session NAME` | Optional session restriction |
| `--dry-run` | Validate configuration/auth mechanism/output containment without login or writes |
| `--keep-raw` | Retain redacted raw captures in the run directory; off by default |
| `--stop-after capture\|ingest\|verify` | Stop cleanly after the named completed phase; defaults to `verify` |
| `--request-timeout-seconds N` | Live-request timeout from 5–120 seconds; defaults to 30 |
| `--max-retries N` | Eligible-read retries after the initial attempt, from 0–5; defaults to 2 |
| `--log PATH` | Optional redacted log path contained within `--out` |
| `--verbose` | Emit operation names/counts only, never response bodies or secrets |

Raw values such as `--token VALUE`, `--password VALUE`, or credentials embedded
in a URL are intentionally unsupported because process lists and shell history
can expose them. Authentication modes are mutually exclusive. An
environment-variable *name* may be logged; its value may not.

### Argument validation matrix

| Mode | Required | Allowed credential companions | Forbidden |
| --- | --- | --- | --- |
| `--live --auth token-env` | `--token-env NAME` | scope, timeout, retry, retention flags | `--token-stdin`, username/password flags, `--fixtures` |
| `--live --auth token-stdin` | `--token-stdin` and non-interactive stdin | scope, timeout, retry, retention flags | token/username/password environment flags, `--fixtures` |
| `--live --auth credentials-env` | `--username-env NAME` and `--password-env NAME` | scope, timeout, retry, retention flags | token flags, `--fixtures` |
| `--live --auth prompt` | interactive terminal | scope, timeout, retry, retention flags | all token/username/password flags, non-interactive execution |
| `--live --auth browser` | supported local browser/session manager | scope, timeout, retry, retention flags | all token/username/password flags, CI |
| `--fixtures PATH` | fixture manifest and `--config` | scope, `--stop-after`, `--log` | `--auth`, every credential flag, live timeout/retry flags, all network |
| `--dry-run` | otherwise valid mode/config/output arguments | path/config/auth-mechanism validation | login, network, output creation, secret reading |

`--stop-after capture` writes only the validated capture/fixture manifest and
redacted phase status. `--stop-after ingest` additionally writes the fresh
database but marks it ineligible for export because reconciliation and
verification have not run. Only `--stop-after verify` can produce a promotable
run. No mode resumes or appends to a previous run directory.

The command rejects a pre-existing non-empty output directory, a database
outside the run directory, a fixture/output path outside the canonical APA
Tracker boundary, an unrecognized origin, or a live request without `--live`.
It never repairs or appends to an old SQLite file. Numeric flags reject zero,
negative, non-integer, and out-of-policy values before authentication.

## End-to-end flow

```text
preflight
  → authenticate (live only)
  → scrape/copy fixtures
  → validate and hash capture manifest
  → parse to typed rows
  → create fresh SQLite schema
  → ingest in dependency order
  → rebuild analytics aggregates
  → reconcile identities and coverage
  → verify schema/data/artifacts
  → write redacted run manifest
```

```mermaid
flowchart TD
    A[Parse CLI and verify repository boundary] --> B{Acquisition mode}
    B -->|--live| C[Load credential through env, stdin, prompt, or browser]
    B -->|--fixtures| D[Install network-deny guard and verify fixture manifest]
    C --> E[Authenticated scrape]
    D --> F[Read approved fixtures]
    E --> G[Hash and validate captures]
    F --> G
    G --> H[Parse through existing contracts]
    H --> I[Create fresh SQLite]
    I --> J[Ingest in dependency order]
    J --> K[Rebuild shared analytics]
    K --> L[Reconcile identities, matrix, and assignments]
    L --> M[Verify schema, data, redaction, and hashes]
    M --> N[Promote verified run for demo exports]
```

```mermaid
flowchart LR
    P[Phase starts] --> Q{Phase passes?}
    Q -->|Yes| R[Commit phase and continue]
    Q -->|No| S[Roll back phase]
    S --> T[Write redacted failure category]
    T --> U[Stop: no export or stale fallback]
```

```mermaid
flowchart TD
    A[Live request is prepared] --> B{HTTPS host and operation allowlisted?}
    B -->|No| Z[Stop: acquisition safety failure]
    B -->|Yes| C[Send with TLS verification and bounded timeout]
    C --> D{Result}
    D -->|2xx and valid contract| E[Hash capture and continue]
    D -->|401/403 or consent required| F[Stop: authentication failure]
    D -->|429 or eligible 5xx read| G{Retry budget remains?}
    D -->|redirect outside allowlist, malformed body, other 4xx| Z
    G -->|Yes| H[Honor bounded Retry-After or deterministic backoff]
    H --> C
    G -->|No| I[Stop: acquisition failure]
```

### 1. Preflight

Verify canonical repository root/origin, Python/dependencies, config schema,
mode exclusivity, contained output paths, free space, and expected parser
operation contracts. Create a unique run directory only after all read-only
checks pass.

### 2. Authenticate and scrape

Live mode delegates credentials/session state to `auth/` and acquisition to the
existing full scraper. The operator completes any guarded consent step. The CLI
records operation name, source entity IDs, HTTP/result status, byte count,
capture time, and SHA-256—not response bodies—in its normal log.

Live transport accepts HTTPS only and an audited APA hostname/operation
allowlist from repository configuration. TLS verification cannot be disabled.
Redirects are revalidated before following; cross-host redirects fail. Every
request has a bounded timeout and response-size ceiling. Retries apply only to
idempotent reads after 429 or eligible transient 5xx responses. The retry count
is finite, `Retry-After` is honored only within the configured cap, and the
fallback backoff/jitter schedule is deterministic under test. Authentication,
authorization, consent, parse, and contract errors are never retried as if they
were transient.

Fixture mode copies or reads only the selected approved fixture tree, verifies
its manifest/hashes, and installs a transport guard that fails any attempted
network call.

### 3. Parse and ingest

All captured payloads pass through existing parser contracts. The CLI creates a
new SQLite database from `database/models.py` and delegates writes to
`database/ingest.py`/`pipeline.ingest`. Dependency order is teams, current
rosters/team history, standings/schedules, scoresheets and pair history,
career/matchup aggregates, then H2H Advantage and Player Trends.

One database transaction is used per defined ingest phase. A failure rolls back
that phase and stops later phases. There is no silent partial-success demo.

### 4. Reconcile

Reconciliation verifies:

- external IDs are stable and unique within entity type;
- current `PlayerTeamHistory` rows include `team_external_id`;
- selected team/opponent/format/session scopes resolve unambiguously;
- scoresheet players and matches reference persisted identities;
- Stage 1 expected pair keys equal the current roster cross-product;
- DIRECT/INDIRECT/UNKNOWN counts sum to total feasible pairs;
- recognized W/L arithmetic and Lineup Lab assigned/unassigned counts reconcile;
- duplicate/conflicting same-match facts are reported, never arbitrarily won by
  insertion order.

### 5. Verify and finalize

Run schema, foreign-key, row-count, nullability, source-manifest, sensitive-data,
and focused analytics tests against the new database. Record the Git commit,
configuration hash, capture range, database hash, phase results, warnings, and
tool versions in a redacted manifest. Only a fully verified run is eligible for
demo export generation.

Stable exit-code categories should distinguish preflight, authentication,
acquisition, parse, ingest, reconciliation, verification, and secret-safety
failures. Logs name the category and remediation without exposing payloads.

## Credential and data safety

- Secrets are read at the last responsible moment, kept in memory, and removed
  from subprocess environments when no longer needed.
- Log/exception redaction covers tokens, cookies, authorization headers,
  usernames, passwords, query parameters, response snippets, and browser-state
  paths.
- Subprocesses receive argument lists, not interpolated shell strings.
- Live requests use HTTPS, certificate verification, an APA host/operation
  allowlist, bounded timeouts, bounded response sizes, and bounded eligible-read
  retries. Proxy and certificate overrides from the ambient environment are
  rejected unless an operator-approved deployment profile explicitly owns
  them.
- Raw authenticated payloads, cookies, profiles, and `.env` never enter Git or
  a public demo bundle.
- `--keep-raw` retains captures only inside the run directory under documented
  access/retention controls; it does not make them shareable.
- Authentication failure stops the run. There is no fallback to an old database
  or fixture mode.
- Cleanup targets only the exact run-created temporary paths and never a
  repository root or broad parent directory.
- Output, database, log, manifest, fixture, and temporary paths are resolved
  before use. Symlinks/junctions, `..` traversal, alternate data streams, and
  case/short-name aliases cannot escape the canonical APA Tracker root or the
  exact new run directory.

## Exit codes and operator contract

The CLI returns one stable primary category. Detailed phase and operation
information belongs in the redacted manifest/log, not in an unstable fleet of
subcodes.

| Code | Category | Meaning |
| ---: | --- | --- |
| 0 | success | requested stop phase completed; manifest states whether the run is promotable |
| 2 | usage/preflight | invalid flags, environment, config, dependency, origin, or contained path |
| 3 | authentication | credential, consent, session, or authorization failure |
| 4 | acquisition | exhausted eligible retries, transport failure, rejected redirect, or capture-contract failure |
| 5 | parse | captured payload cannot be validated/converted by an existing parser contract |
| 6 | ingest | schema creation, transaction, constraint, or dependency-order failure |
| 7 | reconciliation | identity, pair-key, count, result, or assignment invariants disagree |
| 8 | verification | schema/data/focused-test/hash checks fail after reconciliation |
| 9 | secret safety | suspected secret exposure, unsafe path, redaction failure, or prohibited raw artifact |
| 130 | interrupted | operator interruption; partial work remains unpromotable |

The first terminal category wins except secret-safety detection, which upgrades
any in-progress failure to code 9. Normal output contains a run ID, completed
phase, manifest path when safely available, and remediation category. It never
echoes secrets, authenticated URLs, headers, cookies, response snippets, or
credential-file/browser-profile locations.

## CI policy

CI must always use `--fixtures`. A test harness removes credential variables,
installs a network-deny transport/socket guard, and fails on any attempted DNS,
HTTP, browser login, or APA endpoint access. Workflow definitions must not
contain production credentials, tokens, cookies, or persisted browser state.

The live path runs only as an operator-initiated production rehearsal in an
approved environment. Its result is documented by a redacted manifest and
artifact hashes, not by committing captured league data.

## Test strategy

### Unit tests

- argument/mode validation and stable exit codes;
- every row of the argument validation matrix, including `--dry-run` proving no
  secret read, directory creation, login, or network call;
- path containment and non-empty-output rejection;
- credential-source exclusivity, standard-input behavior, and redaction;
- manifest hashing/schema and deterministic warning order;
- phase rollback and fail-closed transitions.
- HTTPS/host/operation/redirect allowlists, TLS-required behavior, timeout and
  response-size bounds, and eligible-read-only retry classification;
- deterministic bounded backoff, capped `Retry-After`, exhausted retry budget,
  and non-retry of 401/403/consent/parse errors;
- symlink/junction/traversal/case/short-name path escape attempts and exact-path
  cleanup targeting.

### Mocked integration tests

- mock auth success, consent required, expiration, denial, rate limiting, and
  malformed GraphQL payloads;
- assert secrets never appear in captured logs/exceptions/subprocess arguments;
- verify scraper/parser/ingest calls and transaction order without live hits;
- simulate interruption and prove a partial database cannot be promoted.
- simulate external redirects, oversized responses, timeouts, 429/5xx retry
  exhaustion, and a redaction canary in every exception/log field;
- run every stop phase and assert capture-only/ingest-only outputs are marked
  unpromotable while a verified result alone becomes export-eligible.

### Fixture end-to-end tests

- ingest committed representative 8-ball/9-ball fixtures into a new temporary
  database;
- cover complete, missing-roster, UNKNOWN, duplicate/conflicting, stale-schema,
  hostile-text, and empty-history cases;
- rebuild Player vs Player Matrix, Pair View data, Lineup Lab, and Data Coverage;
- run twice and compare deterministic database facts/manifests after excluding
  explicitly variable run IDs/timestamps;
- assert the network guard observed zero live attempts.
- scan the run tree and logs with seeded secret canaries; assert none survive;
- validate exit code, phase ledger, source hashes, database hash, and
  promotability state against golden manifests.

### CI enforcement tests

- Start fixture jobs with credential variables removed and loopback/external
  networking denied at both transport and socket layers.
- Fail if `--live`, `--auth`, browser automation, DNS, HTTP, or an APA hostname
  appears in executed CI arguments or observed calls.
- Verify fixture hashes before parsing and reject unmanifested files.
- Run hostile-string HTML/script-JSON tests and workbook formula/link/macro
  scans on downstream demo artifacts built from the verified fixture database.
- Publish only redacted test reports; never publish raw captures, databases with
  private league data, browser profiles, or environment dumps.

### Live smoke test

Run manually with a short-lived credential, least-privilege account, unique
output directory, and approved retention window. Verify consent, scope counts,
reconciliation, redaction, manifest, and logout/session cleanup. This smoke test
is required for a production demo but is never part of CI.
