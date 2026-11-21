# Issue #119 experiment: skill level vs M3 evidence levels

Read-only research. No production code, M3 weights or algorithms, Ultimate Coach recommendations, UI, Excel, database, Sunday file or deployment are changed. Results files hold aggregates only (no player or team identifiers).

| File | What |
|---|---|
| `issue119_experiment.py` | the single, deterministic experiment (every number in the issue #119 summaries) |
| `research_common.py` | `--db` / `UC_ARCHIVE_DB`, `--out`, `--policy`, snapshot hash check against the manifest |
| `case_trace.py` | reproduces one Match Night answer from a locally built captain file (prints names; keep output local) |
| `results_clean.json` | run with `--policy clean` (headline) |
| `results_raw.json` | run with `--policy raw` (sensitivity; reproduces the first issue #119 summary) |
| `RED_TEAM_RESPONSE.md` | point-by-point response to the review |

## Reproduce

Requires Python 3.11+, `numpy`, `pandas` (and `playwright` only for `case_trace.py`). The archive snapshot holds real league data and is not in the repository; build it with `docs/research/m3-validation/make_snapshot.py`. Its sha256 must equal `docs/research/m3-validation/snapshot_manifest.json` (`4f4c861b…`); each run records whether it does (`snapshot.matches_manifest`).

```bash
python -I docs/research/m3-validation/make_snapshot.py --source /path/to/ultimate_coach_staging.db --out ./snapshot
python -I docs/research/issue119/issue119_experiment.py --db ./snapshot/archive_snapshot.sqlite --out ./out --policy clean
python -I docs/research/issue119/issue119_experiment.py --db ./snapshot/archive_snapshot.sqlite --out ./out --policy raw
```

About 40 minutes per policy on a laptop. Seeds are fixed and inputs are sorted, so reruns on the same snapshot reproduce the committed JSON (bootstrap intervals use a fixed generator).

## Record policies

- `raw`: every decided head-to-head row.
- `dedup`: drops exact repeats of (match, player, opponent, skill levels, result): 228 keys.
- `clean` (headline): also drops both rows of the 160 keys that repeat with a different result or skill level (cannot tell which is right). Rows without a result (48) never count; rows without a skill level (15,592) count in history but are not modelled.

## What the experiment does

1. Data quality: duplicate keys, mirror consistency (every row has a mirrored row with the opposite result and swapped skill levels), rows per match, missing skill levels.
2. Pre-match skill level check (does a recorded level describe the match it was played at, or the result of it?).
3. Chronological replay: every feature and M3 level uses only results from strictly earlier local dates (same discipline as `scripts/replay_confidence_levels.py`); one fixed orientation per game.
4. Skill-pair outcome tables by format; Unknown-vs-Caution comparison.
5. Models (L2 logistic, penalty chosen on a validation window): A = M3's six levels (probability mapping fitted on training data, never raw points), B = skill pair, C1 = A + B, C2 = skill pair + direct, shared-opponent, last-10 and lifetime records. Main split: train 2023-01 to 2025-08, test 2025-09 onward. Log loss, Brier, AUC, calibration intercept/slope, ECE, 95% bootstrap by match.
6. Independent re-estimation of A and B with plain empirical rates; leakage probe recomputing features for 400 test games per format straight from the rows dated before each game.
7. Rolling-origin validation: five 6-month test blocks (2024-03 to 2026-09), each trained on the prior three years.
8. Night-level outcomes on realized boards; game-one planner comparison (M3 vs the same planner fed C2 probabilities, scored by two evaluators fitted only on pre-2023 data, model-dependent); decision-change counts; explainability metrics.
