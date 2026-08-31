# Copilot Starter Kit Index

Use this file to quickly choose the right prompt, agent, or skill.

## Fast routing

| If you need to... | Use | Notes |
|---|---|---|
| Build or fix code/scripts | `.github/prompts/build.md` | Uses Sonnet flow, deterministic commands, verification required |
| Audit a change before/after merge | `.github/prompts/audit.md` | Uses Opus flow, PASS/FAIL + evidence |
| Standard end-to-end workflows | `.github/prompts/workflow.md` | Implement / Audit / Reduce / Validate — all four in one place |
| QR export + rebuild (full pipeline) | `.github/prompts/qr_workflow.md` | Reduce → Export → Decode → Rebuild — source and target machine steps |
| Prepare a script for QR export | `.github/prompts/prepare_qr.md` | Reduce → validate syntax → verify AST match → `qr_export.py --file <filename>` |
| Implement directly | `.github/agents/sonnet.md` | Implementer role only |
| Review and challenge changes | `.github/agents/opus.md` | Auditor role only |

## Skills by trigger phrase

| Trigger phrase you can type naturally | Skill |
|---|---|
| "reduce this file", "minify this python", "prepare for qr export", "strip comments", "make this smaller" | `.github/skills/reducer.md` |
| "validate this", "run checks", "prove it works", "verify this works", "test this" | `.github/skills/validator.md` |
| "refactor this", "clean this up", "improve readability", "restructure this", "no behavior change refactor" | `.github/skills/refactor.md` |

## Project guardrails (always apply)

- No silent changes.
- Deterministic workflows only (explicit paths, repeatable commands).
- Include verification steps and expected outcomes.
- If build/pipeline behavior changes, update both:
  - `PROJECT_STATUS.md`
  - Workbook Instructions tab

Source of truth: `.github/copilot-instructions.md`

## Core Commands

### Build Full Pipeline
Use:
build full pipeline: <task description>

### QR Export
Use:
prepare for qr export: <file>

### Audit
Use:
Use Opus to audit <file/change> and return PASS/FAIL with evidence.

### Validate
Use:
validate this script: <file>


## Superpowers skills
- .github/skills/.Claude/superpowers/using-superpowers/SKILL.md


## Superpowers skill pack (nested)
- Entry point: .github/skills/.Claude/superpowers/using-superpowers/SKILL.md
- Common companions:
  - .github/skills/.Claude/superpowers/verification-before-completion/SKILL.md
  - .github/skills/.Claude/superpowers/systematic-debugging/SKILL.md
  - .github/skills/.Claude/superpowers/writing-plans/SKILL.md

Invocation pattern:
- "MANDATORY SKILL: .github/skills/.Claude/superpowers/using-superpowers/SKILL.md"
- "Quote the checklist before starting."


## Superpowers quick entry
- Prompt: .github/prompts/use_superpowers.md

