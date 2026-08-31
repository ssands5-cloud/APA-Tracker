# Skill: Refactor

## Trigger phrases
- "refactor this"
- "clean this up"
- "improve readability"
- "restructure this"
- "no behavior change refactor"

## Use when
Code structure needs cleanup in Python/PowerShell automation without changing outputs.

## Preconditions
- Target file must exist and be readable. If missing, report the error and stop.

## Rules
- No behavior changes.
- Preserve interfaces, file paths, and command contracts.
- Keep deterministic ordering and outputs.
- Logging changes must be non-functional (no data-path side effects).

## Actions
- Rename variables/functions for clarity.
- Extract repeated logic into helpers.
- Simplify control flow.

## Output
- Refactored files.
- Risk notes (what was intentionally not changed).
- Quick regression commands.
