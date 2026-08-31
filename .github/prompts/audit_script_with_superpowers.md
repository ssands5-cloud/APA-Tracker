# Audit Script Changes With Superpowers

Use this for **Opus audit** of changes to **Python (`.py`)** and **PowerShell (`.ps1`)** scripts.

```text
ROLE: AUDITOR (Opus) â€” DO NOT IMPLEMENT

Use Superpowers.

MANDATORY SKILL:
.github/skills/.Claude/superpowers/using-superpowers/SKILL.md

ALSO APPLY:
- .github/skills/.Claude/superpowers/receiving-code-review/SKILL.md
- .github/skills/.Claude/superpowers/verification-before-completion/SKILL.md

RULES (HARD):
1) Quote the checklist from using-superpowers/SKILL.md before auditing.
2) Audit only â€” do not rewrite anything.
3) Provide PASS/FAIL per section with evidence.
4) If FAIL: list exact minimal fixes required.
5) No â€œlooks goodâ€ claims without verification evidence.

TARGET FILE(S):
- <script.py and/or script.ps1>

AUDIT SCOPE:
- correctness + edge cases
- regressions
- Windows compatibility
- determinism / invariants / ordering
- docs / governance updates

INPUTS:
- changed files:
- commands run + outputs:
- known risks / uncertainties:

REQUIRED OUTPUT:
1) Checklist quoted
2) PASS/FAIL by section
3) Exact minimal fixes required (if any)
4) Final verdict: PASS / FAIL
```
