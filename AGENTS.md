# Repository Boundary

This repository is **APA Tracker only**.

- Canonical local root: `C:\Users\ssand\Desktop\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker`
- Expected GitHub origin: `https://github.com/ssands5-cloud/APA-Tracker.git`
- Keep source code, generated exports, databases, fixtures, tests, and worktrees for APA Tracker under this repository or its `APA Tracker Scorekeeper` parent.
- Do not create, clone, move, or save APA Tracker files under `C:\Users\ssand\Desktop\Invest`, `C:\Users\ssand\Desktop\Invest-master`, or any Invest-master worktree.
- Do not modify Invest-master while handling an APA Tracker task unless the user explicitly requests a cross-repository operation.
- Before making changes, verify that `git rev-parse --show-toplevel` resolves to the canonical root above and that `origin` is the expected APA-Tracker URL.
- Keep the tracked `.repo-boundary-id` file unchanged; it identifies this repository to the machine-level Git guard.
- Never bypass the repository boundary guard with `--no-verify` or by changing `core.hooksPath`.
