# Demo CI plan

The current GitHub workflow (`.github/workflows/tests.yml`) is the baseline:
Python 3.12/3.13, pinned development requirements, the full pytest suite, and
a real-subprocess fixture pipeline smoke test that redirects outputs to
`ci-build/`. Future demo checks should extend this boundary without adding
credentials to CI.

## Pull request checks

- Run unit/contract tests for the future launcher and manifest.
- Run the existing sample fixture pipeline and assert JSON/XLSX/HTML artifact
  presence and readability.
- Build the captain-first page and assert that the sample's absent
  `PlayerTeamHistory` is reported as unavailable rather than treated as a
  current roster.
- Run deterministic-build comparison and HTML injection tests.
- Run a path audit proving all CI artifacts stay under `ci-build/`.

## Nightly checks

- Recreate the environment from the pinned lock file.
- Run the full fixture matrix, including stale-schema and hostile-input trees.
- If a secret-backed live smoke is approved later, run it in an isolated secret
  environment, redact logs, and never publish raw fixture responses.
- Compare row-count and evidence-coverage distributions against a retained,
  redacted baseline; alert on unexplained zeroing, not on expected league
  changes.

## CI evidence

Upload only test reports, redacted manifests, artifact hashes, and screenshots
with no teammate names unless the repository's privacy policy explicitly allows
them. Do not upload SQLite, raw fixtures, browser profiles, or `.env`.

## Auditability

The Stage 1–3 trail separates implementation, correction, and audit evidence:
Stage 1 findings were corrected; Stage 2 received scoped HTML/security audit
evidence; Stage 3 scoring was corrected to the validated skill-only path and
has green CI evidence. The independent Issue #14 review status must be quoted
accurately in each release note rather than inferred from a green test run.

