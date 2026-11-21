# M3 validation research (read-only audit)

Pre-registrations, analysis scripts and aggregate results. No production code, UI, database or deployment is touched. No player or team names or row-level data are in this folder. Start with `DECISION_ENGINE_VALIDATION_REPORT.md`.

## Contents
| Path | What |
|---|---|
| `DECISION_ENGINE_VALIDATION_REPORT.md` | the research report and Go / No-Go calls |
| `signal-study/`, `captain-study/`, `component-study/` | pre-registration, script, `results.json` for each study (`captain-study/decomp.py` is the who-plays vs how-paired decomposition) |
| `research_common.py` | shared setup: `--db` / `UC_ARCHIVE_DB`, repository discovery |
| `make_snapshot.py` | builds the compact archive snapshot the studies read |
| `snapshot_manifest.json` | row counts, date range and sha256 of the snapshot used for the committed results |
| `requirements.txt` | dependencies |

## Dependencies
Python 3.11 or newer, `numpy`, `pandas` (see `requirements.txt`). The scripts import the repository's own `analytics/ultimate_coach_confidence.py` and `scripts/replay_confidence_levels.py`; they find the repository by walking up from this folder, so run them from a checkout. No network, no database writes (the archive is opened `mode=ro`).

## Reproduce
The snapshot holds real league data, so it is **not** in the repository. To rebuild it from your own archive and rerun everything:

```bash
python -I make_snapshot.py --source /path/to/ultimate_coach_staging.db --out ./snapshot
export UC_ARCHIVE_DB=./snapshot/archive_snapshot.sqlite      # PowerShell: $env:UC_ARCHIVE_DB = ".\snapshot\archive_snapshot.sqlite"
python -I signal-study/m3_signal_study.py     --out ./out/signal
python -I captain-study/captain_vs_m3.py      --out ./out/captain
python -I captain-study/decomp.py             --out ./out/decomp
python -I component-study/component_study.py  --out ./out/component
```

Each script writes its `results.json` to `--out`. Run time is about one to two minutes each. Compare against the committed `results.json` files and `snapshot_manifest.json` (the snapshot sha256 should match if your archive is the same).

## Reproducibility notes
- Seeded random numbers; input games are sorted by (match, player, opponent), so results do not depend on database row order. The snapshot and the original archive give identical results (verified with `cmp`).
- The committed `results.json` files are from this sorted, deterministic run. The first published report quoted an earlier unsorted run; point estimates agree and bootstrap intervals differ by at most 0.005 (headline conclusions unchanged).
- Studies use the schema columns listed in `make_snapshot.py` only.
