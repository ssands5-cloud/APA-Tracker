# Unified Demo Launcher

The Unified Demo Launcher is the operator-facing wrapper around the Full
Production Demo Builder. Its planned entry point remains
`scripts/run_production_demo.py`, matching `demo_entrypoint_spec.md`. It selects
the build mode, streams redacted progress, verifies the result, and optionally
serves/opens the finished index. It contains no scraper, SQL, analytics, or
rendering formula.

## Invocation

```powershell
python scripts/run_production_demo.py --fixtures tests/fixtures/sample_pipeline --config tests/fixtures/ci_pipeline_config.yaml

python scripts/run_production_demo.py --live --auth token-env --token-env APA_TOKEN --config apa_config.yaml --serve --open

python scripts/run_production_demo.py --verified-run demo-runs/live-2026-09-15 --serve
```

The launcher forwards data/config/scope/auth flags as an argument list to
`scripts/build_full_production_demo.py`. It owns these presentation flags:

| Flag | Behavior |
| --- | --- |
| `--serve` | serve the verified run on loopback only |
| `--port N` | requested loopback port; default is an available ephemeral port |
| `--open` | open the verified index in the user's default browser after the server is ready |
| `--no-build` | require `--verified-run`; revalidate and present without rebuilding |
| `--keep-run` | retain the completed run and exact temporary paths allowed by policy |
| `--log-level info\|debug` | redacted operator verbosity |
| `--events PATH` | optional contained JSONL event log for automation |

`--open` requires `--serve`. CI forbids `--live`, browser authentication,
`--serve`, and `--open`; it calls the builder in fixture mode directly.

Mode flags are mutually exclusive. `--no-build` is valid only with
`--verified-run` and forbids all acquisition/credential/config mutation flags.
Unknown flags fail; the launcher never forwards them speculatively. Paths are
resolved and boundary-checked before a child process starts, and repeated flags
use an explicit parser error rather than last-value-wins behavior.

## Current status and final integration surface

`scripts/run_production_demo.py` is not yet implemented. Existing batch files
or fixture-demo commands are not the unified launcher contract and must not be
used as its source of truth. The launcher is a thin process boundary around
`scripts/build_full_production_demo.py`; it contains no module-specific build
sequence and never imports scraper, database, analytics, or renderer code.

The final invocation mapping is:

| Launcher input | Builder forwarding | Launcher-only action |
| --- | --- | --- |
| `--live`, auth source, config, scope, output policy | forward unchanged as an argument array | stream redacted progress |
| `--fixtures`, config, scope, output policy | forward unchanged; force network-denied environment | stream redacted progress |
| `--verified-run` without `--no-build` | request a new verified rebuild directory | optionally serve/open the new run |
| `--verified-run --no-build` | do not invoke the builder | revalidate and present that exact immutable run |
| `--serve [--port]` | never forwarded | start loopback server after verification |
| `--open` | never forwarded | open the verified health-checked URL |
| `--events PATH` | configure launcher's own JSONL sink | write redacted versioned events only |

The builder must return the resolved run directory through a versioned,
redacted completion event; ordinary log text is never parsed for paths. The
launcher confirms that directory is under the canonical run root and that the
event's run ID/manifest hash match READY before presenting it. Unknown event
schema versions fail closed.

## Wrapper flow

```mermaid
sequenceDiagram
    participant O as Operator
    participant L as Launcher
    participant B as Full demo builder
    participant V as Verifier
    participant S as Loopback server/browser
    O->>L: choose live, fixture, or verified run
    L->>L: validate canonical root, flags, and paths
    L->>B: pass an explicit argument list
    B-->>L: redacted phase events and exit status
    L->>V: revalidate READY, manifest, checksums, and index
    alt verification fails
        V-->>L: failure
        L-->>O: stop with category; do not open
    else verification passes
        V-->>L: verified run
        L->>S: optional 127.0.0.1 server and browser open
        L-->>O: URL, run ID, capture time, artifact count
    end
```

## Logging behavior

Human log lines use:

```text
UTC_TIMESTAMP RUN_ID PHASE STATUS MESSAGE
```

Allowed message data includes operation name, non-secret entity ID, row count,
relative run path, duration, hash prefix, and remediation category. Forbidden
data includes tokens, passwords, cookies, authorization headers, authenticated
URLs/query strings, response bodies/snippets, browser-profile paths, environment
dumps, and absolute credential paths.

The optional JSONL stream uses a versioned schema:

```text
schema_version, timestamp, run_id, phase, status, code,
message_key, counts, relative_path, duration_ms
```

Free-form exception text is redacted before either stream. A redaction failure
uses the secret-safety exit category and suppresses the unsafe line. Debug mode
adds call/phase metadata only; it never relaxes content policy.

## Server and browser safety

- Bind only `127.0.0.1` or `::1`; never `0.0.0.0` or a LAN interface.
- Serve only the resolved verified run root with directory traversal, symlink,
  junction, and alternate-data-stream escapes rejected.
- Set `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, and a
  restrictive referrer policy. Do not add remote fonts/scripts/analytics.
- Use a random unprivileged port by default. A requested occupied/privileged
  port fails clearly rather than switching exposure silently.
- Open the browser only after a health check verifies the exact manifest run ID
  and index hash.
- Stop the server cleanly on Ctrl+C; cleanup targets only launcher-created
  process/session files, never the run bundle or repository root.

## Process and repository safety

Before builder invocation or presentation, the launcher verifies the canonical
repository root, expected origin, `.repo-boundary-id`, resolved output/run path,
and that no path crosses the repository boundary. Subprocesses receive argument
arrays, not interpolated shell commands. Live authentication is opt-in and
never retried as fixture or prior-run mode.

The launcher never changes source, database, exports, or `BUILD_INFO`. In
`--no-build` mode every artifact is read-only. A manifest/hash mismatch,
missing READY marker, stale schema, failed builder status, or absent index stops
presentation.

Builder exit codes pass through unchanged. Launcher-only presentation failure
uses code 13; operator interruption uses 130. A browser-open failure after the
verified loopback server starts reports code 13 and the still-valid manual URL,
but never changes the run's READY state.

## Builder integration contract

The launcher starts the builder as a child process with an argument array and a
minimal allowlisted environment. It consumes versioned redacted JSONL phase
events when requested and treats ordinary stdout as operator text, never as a
source of artifact paths. The child exit code, resolved run path, and manifest
identity must agree; disagreement is a presentation failure.

For a successful build or `--no-build` presentation, the launcher reads READY,
recomputes the manifest SHA-256, validates every required artifact checksum,
confirms `promotable=true`, and resolves `index.html` beneath the run root. Only
then may it bind a loopback server. The browser health check must return the
same run ID and index hash from the verified bundle. The launcher never marks a
run ready, repairs a manifest, rebuilds a missing export, or substitutes the
most recent run.

On shutdown, the launcher stops only its own loopback process and closes its
event stream. It does not delete the verified run, temporary directories owned
by a failed builder, or any source/database artifact. Retention and cleanup are
explicit builder/release-policy operations, never launcher side effects.

## Acceptance tests

- Flag/mode matrix and exact forwarding without shell interpolation.
- Builder exit-code propagation and no presentation after failure.
- Secret canaries removed from human/JSONL logs and exception paths.
- Loopback-only binding, traversal/symlink rejection, security headers, and
  occupied-port behavior.
- Health-check validation before browser open.
- Ctrl+C/server cleanup scoped to exact launcher-created resources.
- Fixture CI proof that no DNS, HTTP, browser, credential read, or live flag is
  used.
- Verified-run proof that no file content or mtime changes during presentation.
