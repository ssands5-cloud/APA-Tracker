# Demo entrypoint specification

The proposed implementation is `scripts/run_production_demo.py`. This is a
contract for a future implementation; this documentation change does not add
the script.

## Invocation

```text
python scripts/run_production_demo.py
  (--live | --fixtures FIXTURE_ROOT | --verified-run RUN_ROOT)
  [--auth token-env|token-stdin|credentials-env|prompt|browser]
  [--token-env NAME | --token-stdin]
  [--username-env NAME --password-env NAME]
  [--config PATH]
  [--out PATH]
  [--team-id TEAM_ID]
  [--opponent-team-id TEAM_ID]
  [--format NAME]
  [--session NAME]
  [--keep-raw]
  [--fail-on-warning]
  [--serve]
  [--open]
  [--port PORT]
  [--no-build]
  [--keep-run]
  [--events PATH]
  [--log-level info|debug]
```

Exactly one data source is required. `--no-build` requires `--verified-run`;
`--open` requires `--serve`. Live authentication flags follow
`scrape_and_ingest_pipeline.md` and are forbidden in fixture/prior-run modes.
The default config is
`apa_config.yaml`; the default output is a unique directory under `demo-runs/`.
`--team-id` overrides only the display-side configured team and must be a real
team ID present in the regenerated database. Scope overrides are exact filters,
not labels applied after computation. `--keep-raw` is live-only and does not
authorize raw captures in a share package.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Build, verification, and manifest completed |
| 2 | Invalid arguments, config, or repository/output boundary |
| 3–9 | Preserved scrape/ingest/auth/reconciliation/verification/secret-safety categories |
| 10 | Analytics/document construction failure |
| 11 | Export or cross-renderer parity failure |
| 12 | Bundle finalization failure |
| 13 | Optional local server/browser presentation failure |
| 130 | Operator interruption; partial work is not presented |

## Observable output

Log lines use the stable redacted form documented in `demo_launcher.md`; a
message may contain IDs and relative paths but never tokens or response bodies.
When `--events` is supplied, the launcher writes a versioned JSONL stream. A
successful builder completion event carries the run ID, repository-contained
relative run path, manifest hash, selected scope count, and verified artifact
count. The launcher never parses ordinary log text to discover an artifact.

## Manifest fields

The manifest contains schema version, `run_id`, UTC
`started_at`/`finished_at`, repository commit, mode, config and source hashes,
database relative path/hash, selected scopes, formula versions, artifact
relative paths/hashes/row counts, scope/evidence/null counts, parity/security
gate results, promotable status, test command/result, and a redacted warning
list. It must identify a stale/unavailable scope without embedding SQL text,
absolute private paths, or secrets.

## Server behavior

`--serve` starts a local-only server bound to `127.0.0.1`; it never binds all
interfaces. The printed URL points to a generated `index.html` with links to
the captain-first page, analysis tabs, and downloadable artifacts. Without
`--serve`, the launcher reports the verified index path and does not open it.
`--open` launches only after a health check proves the served run ID and index
hash. The complete wrapper, logging, and safety contract is in
`demo_launcher.md`; builder phases are in `full_production_demo_builder.md`.
