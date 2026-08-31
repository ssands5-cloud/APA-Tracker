---
mode: "sonnet"
---
# Standard Workflows

## 1. Implement a Feature

**Agent**: Sonnet (implementer)
**Skill**: n/a — direct implementation

Steps:
1. State what will change and why.
2. Write code/script with explicit paths and deterministic behavior.
3. Include error handling for file/dep/runtime failures.
4. If pipeline file changed, call out required doc updates.

Expected outputs:
- Modified files listed.
- Copy/paste run command.
- Verification step with expected output.

Verification:
```powershell
python "<changed_script>.py"
# Expected: ExitCode=0, no unexpected output
```

Doc update required if any of these changed:
`create_budget_full_script.py`, `bootstrap_*.ps1`, `build_*.ps1`, `tasks.json`
→ Update `PROJECT_STATUS.md` and workbook Instructions tab.

---

## 2. Audit a Change

**Agent**: Opus (auditor)
**Skill**: `.github/skills/validator.md` (trigger: "validate this")
**Prompt**: `.github/prompts/audit.md`

Steps:
1. Read the changed files and the validator skill.
2. Check correctness, determinism, edge cases, and failure paths.
3. Verify pipeline doc updates exist if required.

Expected outputs:
- PASS or FAIL verdict.
- Evidence (exact commands + outputs).
- Findings ranked by severity.
- Exact remediation steps for each FAIL.

Verification:
```powershell
# Run audit checks from project root
python "<script>.py"
# Expected: ExitCode=0, SHA256/count/output matches known-good baseline
```

---

## 3. Reduce a Script for QR Export

**Agent**: Sonnet (implementer)
**Skill**: `.github/skills/reducer.md` (trigger: "reduce this file")

Steps:
1. Confirm target file exists and is readable.
2. Run `py_reducer.py` against the target.
3. Syntax-check the output.
4. Run behavior-equivalence check.

Commands:
```powershell
python py_reducer.py create_budget_full_script.py
python -m py_compile create_budget_full_script_reduced.py
```

Expected outputs:
- `<source>_reduced.py` written beside the source.
- Size delta printed (lines/chars/%).
- `py_compile`: no output (success).

Behavior equivalence:
```powershell
python -c "exec(open('create_budget_full_script_reduced.py').read())"
# Must match stdout/stderr of the original run, or produce no new errors.
```

Then export to QR:
```powershell
python qr_create_budget_full_script.py
# Expected: 30/30 chunks, all SHA256 OK
```

---

## 4. Validate a Script Before Execution

**Agent**: Sonnet (implementer) or Opus (auditor) depending on context
**Skill**: `.github/skills/validator.md` (trigger: "validate this")

Steps:
1. Confirm target file exists and is readable.
2. Syntax-check.
3. Dependency check.
4. Dry-run or unit test if available.

Commands:
```powershell
python -m py_compile <script>.py              # syntax
python -c "import <module>"                   # import check
python <script>.py --dry-run                  # if supported
```

Expected outputs:
- `py_compile`: no output = PASS.
- Import check: no `ModuleNotFoundError`.
- Dry-run: ExitCode=0 with expected summary line.

Pipeline-file pre-flight:
```powershell
python "create_budget_full_script.py"
# Expected: ExitCode=0, workbook written, audit scripts pass
```

If validation fails:
1. Check missing deps: `pip install --user <package>`.
2. Check Python version: `python --version` must be 3.11.x.
3. Check file paths are absolute and exist on disk.
