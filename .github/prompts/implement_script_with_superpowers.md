# Implement / Update Script With Superpowers

Use this for **new or updated Python (`.py`)** and **PowerShell (`.ps1`)** scripts.

```text
ROLE: IMPLEMENTER (Sonnet)

Use Superpowers.

MANDATORY SKILL:
.github/skills/.Claude/superpowers/using-superpowers/SKILL.md

ALSO APPLY:
- .github/skills/.Claude/superpowers/writing-plans/SKILL.md
- .github/skills/.Claude/superpowers/verification-before-completion/SKILL.md

RULES (HARD):
1) Quote the checklist from using-superpowers/SKILL.md before starting.
2) Quote the checklist from writing-plans/SKILL.md before coding.
3) Make minimal diffs only unless a larger refactor is explicitly approved.
4) End with VERIFICATION (commands run / outputs / expected results).
5) If files change: list files + summarize diffs.

TARGET FILE(S):
- <script.py and/or script.ps1>

TASK:
<describe the new feature or change>

CONSTRAINTS:
- Preserve existing behavior unless explicitly changing it.
- Keep Windows compatibility in mind.
- Keep layman-friendly docs updated if user-facing behavior changes.

DONE WHEN:
- change implemented
- docs updated if needed
- verification passes
```
