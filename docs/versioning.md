# Versioning

`VERSION` at the repo root holds the project's current release version as
plain text (currently `1.0.0-rc1`) -- nothing else reads its meaning into
the number; this file is the single source of truth.

`scripts/reproducible_build.py` reads it (`read_version()`) and reports it
as `apa_tracker_version` in `dist/BUILD_INFO.json`, alongside the git
commit, dependency versions and artifacts that manifest already records --
see [docs/reproducible_builds.md](reproducible_builds.md). A missing
`VERSION` file is not a build error: `apa_tracker_version` is simply `null`
in the manifest, the same "real data or a real null, never a fabricated
value" convention this project uses everywhere else.

## Scheme

Semantic versioning, `MAJOR.MINOR.PATCH` with an optional pre-release
suffix (`-rc1`, `-beta`, ...):

| Bump | When |
|---|---|
| Major | A schema change, or a change to pipeline/export behavior that isn't backward compatible (a column renamed or removed, an export's shape changed) |
| Minor | A new analytics engine, exporter, or validation layer, added without changing existing output |
| Patch | A bug fix, a CI fix, or a documentation update |

## Updating it

Edit `VERSION` directly (a single line, no `v` prefix, no trailing
whitespace beyond the newline) and commit it as its own change or alongside
the change it describes -- there is no script that bumps it automatically,
so a version bump is always a deliberate, reviewable line in a diff rather
than something that happens as a side effect of another change.

## What this does not cover

This is the versioning primitive only: a single source of truth for "what
version is this," read into the build manifest. It does not, by itself,
define a release-packaging process, a changelog, or a distribution
mechanism -- those are real, separate, larger decisions (what a "release"
bundle contains, whether/how it's distributed) that this file does not
make on its own.
