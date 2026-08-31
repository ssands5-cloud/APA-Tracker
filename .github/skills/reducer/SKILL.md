# Skill: Reducer

## Trigger phrases
- "reduce this file"
- "minify this python"
- "prepare for qr export"
- "strip comments"
- "make this smaller"

## Use when
You need smaller Python source for transfer (including QR export), without changing behavior.

## Preconditions
- Target file must exist and be readable. If missing, report the error and stop.

## Rules
- Output must be deterministic: same input always produces same output.
- No behavior changes.

## Actions
- Remove comment-only lines.
- Remove docstrings safely.
- Collapse repeated blank lines.
- Preserve runtime logic and ordering.
- If a stripped docstring leaves an empty body, insert pass.

## Output
- Reduced file path.
- Size delta (lines/chars/%).
- Syntax check: `python -m py_compile <reduced_file>`.
- Behavior equivalence: confirm original and reduced produce identical stdout/stderr on a representative run, or compare output SHA256.
