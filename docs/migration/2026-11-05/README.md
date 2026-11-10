# D: migration recovery records (2026-11-05, tracked 2026-11-09)

Copies of records that existed only in git-ignored `tmp\` folders. Originals stay where they were.

| File | What it is | Used for |
|---|---|---|
| `worktree-retirement-inventory-2026-11-05.csv` | Every worktree considered for retirement: phase, path, branch, exact `HeadSha`, PR, push state, size | Re-creating a removed worktree at its exact commit |
| `removal-log-2026-11-05.csv` | The 11 worktrees removed on 2026-11-05 (branches kept) | Knowing what was removed |
| `venv.freeze.txt`, `venv312.freeze.txt` | Package lists for `venv` (Python 3.14.3) and `venv312` (Python 3.12.10) | Rebuilding either venv |
| `verify_report.json` | C: vs D: (and H:) file-count/size comparison for the five project folders | Migration evidence |

The JSON inventory and the cache-cleanup list were left in `tmp\` (large, and the CSV holds the same recovery data).
Codex settings backups (`codex_AGENTS.md.bak`, `codex_config.toml.bak`) are machine configuration and stay out of git.
