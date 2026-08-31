# Skill: Validator

## Trigger phrases
- "validate this"
- "run checks"
- "prove it works"
- "verify this works"
- "test this"

## Use when
You need deterministic verification for Python/PowerShell scripts, Excel COM automation, or QR transfer flow.

## Preconditions
- Target file must exist and be readable. If missing, report the error and stop.

## Rules
- All checks must be reproducible from project root.

## Actions
- Provide exact commands from project root.
- State prerequisites (Python version, packages, file paths).
- Define expected success output and failure signatures.
- Include targeted checks (for example: chunk count, SHA256 match, workbook write success).
- If the change touches pipeline files, verify PROJECT_STATUS.md and workbook Instructions tab were updated.

## Output
- Short runbook: Run -> Verify -> Troubleshoot.
- PASS/FAIL criteria that are machine-checkable.
