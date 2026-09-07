# Reproducible Builds

How to install the exact environment that produced a given commit's test
results and exports, how to verify it, and what still isn't covered.

```
requirements.in / requirements-dev.in    hand-edited, with upper bounds
requirements.txt / requirements-dev.txt  pip-compile's fully pinned lock -- GENERATED, never hand-edited
scripts/reproducible_build.py            fresh venv -> install -> verify -> test -> pipeline -> manifest
tests/fixtures/sample_pipeline/          committed 2-team fixture tree for CI mode
tests/fixtures/ci_pipeline_config.yaml   redirects the CI-mode pipeline run into ci-build/
```

## Install the pinned environment

```bash
python -m venv .venv
.venv\Scripts\activate           # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

`requirements-dev.txt` already includes everything in `requirements.txt`
(it's compiled from `requirements-dev.in`, which starts with
`-r requirements.in`) -- one install, exact versions, including the
transitive dependencies (`numpy`, `greenlet`, `pyee`, ...) pip-compile
resolved alongside them. To actually run the scraper, also run
`playwright install chromium` once -- the Python package alone doesn't
carry the browser binary it drives.

### Why this exists

Before this pass, `requirements.txt` used lower bounds only
(`pandas>=2.0`) with no upper bound and no lockfile, and was missing two
packages entirely: `playwright` and `python-dotenv`, both real, direct
imports (`scraper/full_auto_scrape.py`; `env_loader.py`, which nearly
every entry point imports first). A fresh clone running
`pip install -r requirements.txt` could not actually run the scraper, and
nothing pinned *when* `pip install` ran to *what* got installed -- the
project was, at the time this was found, already running on `pandas==3.0.5`
(a major-version jump from the `>=2.0` floor) purely by chance of when it
happened to be installed.

### Updating a pinned version

Edit `requirements.in` (or `requirements-dev.in`), then regenerate:

```bash
pip install pip-tools
pip-compile --resolver=backtracking --strip-extras -o requirements.txt requirements.in
pip-compile --resolver=backtracking --strip-extras -o requirements-dev.txt requirements-dev.in
```

Never hand-edit `requirements.txt` / `requirements-dev.txt` directly --
the next `pip-compile` run will silently overwrite it, and a hand
edit that isn't reflected in the `.in` file is a change nobody can see
coming. Upper bounds cap at the next MAJOR version by default (a
minor/patch release is assumed backward-compatible per semver); tighten
any individual package to a minor-version cap in the `.in` file if its
real-world history says otherwise.

## Verify the pinned environment actually reproduces the tested state

```bash
python scripts/reproducible_build.py
```

Before these six steps, the script validates that the lock contains at
least one package and that every active line is one exact `name==version`
pin. Includes, ranges, URLs, environment markers, wildcard versions and
unsupported directives fail closed before an existing build environment
is removed or any install starts. This intentionally matches the current
flattened, no-hash `pip-compile` output; if that format changes, the parser
and its tests must be updated deliberately in the same change.

Six steps, any failure stops the build immediately:

1. Create a fresh virtual environment (`.build-venv/` by default --
   never the interpreter this script itself is running under).
2. Install `requirements-dev.txt` into it.
3. Check every lockfile pin against the venv's actual `pip freeze` --
   proves each locked application dependency was installed at its exact
   requested version, not "close enough".
4. Run the full test suite through that venv's own interpreter. This
   already includes the determinism check
   (`tests/test_full_pipeline_integration.py::TestFullPipelineDeterminism`)
   -- there's no separate ad hoc comparison here duplicating it.
5. Clear `ci-build/`, run the real pipeline against the committed sample
   tree (or the repository-local tree explicitly supplied with `--fixtures`),
   and confirm every declared artifact actually exists on disk. Ignored
   local scrape output is never selected implicitly, and stale files cannot
   satisfy the artifact check.
6. Write `dist/BUILD_INFO.json` -- see "Versioning artifacts" below.

The venv is deleted afterward unless `--keep-venv` is passed. Both
`.build-venv/` and `dist/` are gitignored. Build scratch paths are required
to remain below the repository root, the venv and manifest directories may
not overlap, and the script refuses unsupported Python versions before it
deletes or creates anything. An existing venv directory must also carry the
build marker. The standard `pyvenv.cfg` plus interpreter shape is accepted
only for the documented default `.build-venv/`, preserving older runs without
making an ordinary developer venv replaceable. Use Python 3.12 or 3.13.

To verify a different repository-local fixture tree without allowing local
state to change the default build:

```bash
python scripts/reproducible_build.py --fixtures scraper/sanitized_fixtures
```

Outputs still go to the isolated `ci-build/` directory; the selected fixture
path is recorded in `dist/BUILD_INFO.json`.

## CI mode

CI cannot scrape: step 1 of `pipeline_run_all.py` is a real login and
consent flow against a live third-party site (README-scraper.md), and
running that unattended would mean either flaky failures on a UI change or
credentials sitting in a CI secret for a browser-automation login flow --
neither is worth it for what this step needs to prove.

```bash
python pipeline_run_all.py --skip-scrape --skip-tests \
  --fixtures tests/fixtures/sample_pipeline \
  --config tests/fixtures/ci_pipeline_config.yaml
```

`--fixtures` (forwarded to `python -m pipeline`) points the ingest at
`tests/fixtures/sample_pipeline/` -- a small, committed, synthetic
two-team/one-match tree in the scraper's real documented layout, not real
league data. `--config` points the database and every export at
`ci-build/` (gitignored) via `tests/fixtures/ci_pipeline_config.yaml`,
so this can never write into the real `data/` or `exports/`. This exact
command is what `.github/workflows/tests.yml` runs as a dedicated step,
proving `pipeline_run_all.py` itself works as a real subprocess -- not
just its orchestration logic (`tests/test_pipeline_run_all.py`, mocked)
or the ingest/export functions called directly in-process
(`tests/test_full_pipeline_integration.py`).

`pipeline.exports.configured_exports_dir` is what makes `--config` able to
redirect *every* artifact this way: previously only the workbook and demo
JSON honoured `config["export"]`, while Captain's Edge, the Lineup
Optimizer and the analysis tabs page always wrote to the real project's
`exports/` regardless of config. Setting `export.exports_dir` in a config
file now redirects all of them.

## Versioning artifacts

`scripts/reproducible_build.py`'s `dist/BUILD_INFO.json` is the answer to
"what produced this workbook": the project's own release version (see
[docs/versioning.md](versioning.md); `null` when no `VERSION` file exists
yet), the git commit (and whether the tree was dirty -- a build from
uncommitted changes says so, since nobody else can reproduce it), the
Python version and platform, every pinned dependency's exact resolved
version, which fixtures were used, and the list of artifacts written. This
is deliberately a manifest written alongside the
existing exports, not a new artifact-store or release-packaging system --
appropriate for what this project actually needs, not a general solution
for a much larger team.

To compare two builds: regenerate `BUILD_INFO.json` for each commit and
diff them. A different `dependencies` block for the same commit means the
lockfile changed (or wasn't actually used) between builds -- exactly the
drift this whole pass exists to catch.

## What this does not cover

- **Hashes are not pinned** (no `--generate-hashes` on the pip-compile
  invocations). Hash pinning adds real supply-chain protection (a
  compromised package version with the right version number but different
  contents would still install) at the cost of a much longer, harder-to-
  skim lockfile and more friction on every regeneration. Worth adding if
  that threat model matters more than it currently does for a solo
  project's own tooling.
- **Cross-platform verification**: `scripts/reproducible_build.py` was run
  end-to-end on Windows/Python 3.12 (this project's primary environment).
  `.github/workflows/tests.yml` installs the same `requirements-dev.txt`
  fresh and runs the full suite plus the CI-mode pipeline smoke test on
  Ubuntu across Python 3.12 and 3.13 on every push -- confirmed green on
  both after this pass (run
  [34043915386](https://github.com/ssands5-cloud/APA-Tracker/actions/runs/34043915386),
  commit `c88eb2e`), not an offline claim made here. That same CI check is
  also what caught two real hermeticity bugs this pass fixed
  (`tests/test_captains_decision.py` silently reading the real, gitignored
  `data/apa_tracker.db` and `exports/captains_edge.json` instead of a
  hermetic fixture) -- CI had actually been red since before this pass
  started (commit `2200380`), which nothing had checked until this pass
  specifically went looking.
- **The scraper itself has no automated integration test** -- see
  [docs/full_pipeline_integration.md](full_pipeline_integration.md)'s own
  "What this does NOT cover" for why, and for what full-pipeline coverage
  means separately from the reproducibility question this document covers.
