# Ultimate Coach verification and Claude handoff — September 26, 2026

## Verified this session

- PR #83 is OPEN and DRAFT at `9b68c50458583e7d1282ef05dde8e0d33d49c0af`.
- GitHub reports both Python 3.12 and 3.13 test jobs successful.
- The linked integration worktree is clean and its HEAD matches the PR.
- Local Python 3.12 verification: **217 passed, 1 warning in 22.90s**. Selection: every `tests/test_ultimate_coach*.py`, plus `tests/test_build_ultimate_coach_production.py` and `tests/test_export_excel_ultimate_coach.py`. Includes fixture-based real-browser tests; does not replace Paul's full-size artifact acceptance.
- Warning: existing SQLAlchemy datetime.utcnow deprecation.
- Desktop HTML and XLSX hashes equal the corresponding files in `build-9b68c50`.
- HTML hash agrees with manifest and READY. Manifest hash agrees with READY.
- Current staging DB hash agrees with the build's recorded source hash. This is a current comparison, not a new before/after build measurement.
- No new build, database mutation, release replacement, merge, or push performed.

## Artifact evidence

Existing artifact folder: `C:\Users\ssand\Desktop\Ultimate Coach FINAL UAT`.

| Item | Bytes | SHA256 |
| --- | ---: | --- |
| Ultimate_Coach_FINAL_UAT.html | 84863499 | `13812b8253b652549a3e448391c17f1f7c47c552437947f92d4a05ed49a0cd76` |
| Ultimate_Coach_FINAL_UAT.xlsx | 26619044 | `de4038594be4fafb608f9ceab1ec3efd8fe796274d894ff4e8ea3d899f28e208` |
| build-9b68c50/manifest.json | 1239 | `34cca91d75c5564305e22e2deb324ec73cce43cbd6acecbb14948abc28d17baa` |

Source staging DB SHA256: `fb2b098d6b0537b5e0d847dcf83aab43567fd3a257933e38b3123c49d0a43145`.

Manifest counts: 15,180 players; 425,859 all-game records; 828,316 directional head-to-head rows. Directional rows should not be presented as unique matches. Trust counts include 414,158 identity-verified games, 4,218 identity exclusions, 11,820 indeterminate participants, and 227 source-coverage issues. These counts describe different categories and should not be added together.

## Engineering follow-up from code review

1. The saved production manifest and READY cover HTML only. Excel SHA256 and the source commit are printed by the PowerShell helper but not persisted in the manifest. Add a separate complete-package receipt with both artifact hashes, sizes, exact commit, source hashes, and validation results; preserve the existing HTML manifest contract.
2. HTML uses a private SQLite snapshot; the Excel entry point reads the live staging DB separately. The helper checks the main DB file hash before and after both builds. For stronger consistency, build both artifacts from one private snapshot and account for SQLite WAL state. This is a publication robustness gap, not evidence that the current artifacts differ.
3. The helper defaults to a Desktop folder outside the currently authorized repository/parent boundary. Any future changes or outputs must respect current AGENTS.md. Existing files were read only during this audit.
4. The helper deletes an existing same-commit build folder before replacing it. Prefer retaining immutable build directories and safely publishing a selected completed package; add failure-path coverage before changing publication behavior.

## Message for Claude

Codex verified PR #83 at 9b68c50: 217 local Ultimate Coach tests passed; both CI jobs are green; the Desktop artifact hashes match the archived build; the staging DB still matches its recorded hash. Please independently review the Excel companion for usability and correctness, especially player/team selectors, 8-Ball versus 9-Ball separation, evidence counts, and lineup constraints. Use a verified APA Tracker worktree and a separate branch for fixes. Do not overwrite the current FINAL UAT files or modify the staging database. Report findings, tests, and commits. Consider the release-record and shared-snapshot gaps documented above as follow-up work. Leave merging and Paul's hands-on acceptance pending.

## Human acceptance still required

Open the full-size HTML directly; type Billy quickly; select players and inspect direct/shared evidence; switch formats and opponent scope; exercise Team vs Team and lineup assistance. Open the Excel workbook and verify the same practical workflows. Confirm responsiveness and that old results clear when selections change. Automated fixture tests do not establish the experience on the full-size artifacts.
