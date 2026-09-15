# Demo entrypoint specification

The proposed implementation is `scripts/run_production_demo.py`. This is a
contract for a future implementation; this documentation change does not add
the script.

## Invocation

```text
python scripts/run_production_demo.py
  (--live | --fixtures FIXTURE_ROOT)
  [--config PATH]
  [--out-dir PATH]
  [--team-id TEAM_ID]
  [--serve]
  [--port PORT]
  [--skip-tests]
  [--keep-run]
  [--verbose]
```

Exactly one of `--live` and `--fixtures` is required. The default config is
`apa_config.yaml`; the default output is a unique directory under `demo-runs/`.
`--team-id` overrides only the display-side configured team and must be a real
team ID present in the regenerated database.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Build, verification, and manifest completed |
| 2 | Invalid arguments, config, or repository/output boundary |
| 3 | Authentication, fixture, or dependency acquisition failure |
| 4 | Ingest or stale-schema failure |
| 5 | Export or HTML build failure |
| 6 | Verification failure; artifacts must not be presented |
| 7 | Optional local server could not start |

## Observable output

Log lines use the stable form `PHASE status message`, where the message may
contain IDs and relative paths but never tokens or response bodies. The final
line reports the absolute path of `demo_manifest.json`, the selected scope
count, and the verified artifact count. A machine-readable `events.jsonl` is
optional but useful for CI.

## Manifest fields

The manifest contains `run_id`, UTC `started_at`/`finished_at`, repository
commit, mode, config hash, fixture root hash, database relative path, artifact
relative paths and hashes, row counts, scope/evidence counts, test command and
result, and a redacted list of warnings. It must identify a stale/unavailable
scope without embedding SQL text or secrets.

## Server behavior

`--serve` starts a local-only server bound to `127.0.0.1`; it never binds all
interfaces. The printed URL points to a generated `index.html` with links to
the captain-first page, analysis tabs, and downloadable artifacts. Without
`--serve`, the operator opens those files directly.

