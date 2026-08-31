# Copilot Instructions (Budget)

## Operating model
- Sonnet = implementer (write code and scripts).
- Opus = auditor (review, challenge, validate).
- Quick routing reference: see .github/copilot-index.md.

## Non-negotiables
- No silent changes. State what changed and why.
- Keep workflows deterministic: explicit paths, pinned interpreter, repeatable commands.
- Include verification steps with expected outcomes.
- If build/pipeline behavior changes, update both:
	- PROJECT_STATUS.md
	- Workbook Instructions tab
- "Pipeline" includes any change to: create_budget_full_script.py, bootstrap_*.ps1, build_*.ps1, tasks.json, or any file referenced by a VS Code task.

## Project defaults
- Prefer Python 3.11.x for Windows + Excel COM stability.
- Prefer PowerShell scripts that run from project root with explicit paths.
- Do not rely on machine-specific state unless explicitly documented.

## Delivery format
- Provide copy/paste-ready commands.
- Include error handling for file/dep/runtime failures.
- End with a short regression checklist.

### Superpowers skills (optional but supported)
If a user says “use superpowers”, load:
.github/skills/.Claude/superpowers/using-superpowers/SKILL.md
and quote the checklist before proceeding.

