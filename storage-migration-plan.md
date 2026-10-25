# APA Tracker — Storage Migration Plan
**Date**: 2026-10-25  
**Branch**: feat/phase1-war-room (593982b)  
**Goal**: Separate code (C:) from data (D:) for long-term growth; introduce `APA_DATA_ROOT` so no path is ever hardcoded.

---

## Executive Summary

The repo currently stores ~390 MB of runtime data (databases, refresh outputs, UAT artifacts) alongside source code on C:. Scripts resolve paths via `PROJECT_ROOT = Path(__file__).resolve().parent.parent` — no absolute drive paths appear in source code. Migration is safe and low-risk because all paths flow through a small number of default argument values; adding `APA_DATA_ROOT` and updating those defaults is a single-file change per affected script.

---

## 1. Current Storage Inventory

### Data directories in repo (C: drive)

| Path | Size | Category | Move to D? |
|------|------|----------|------------|
| `data/` | 5.4 MB | DATABASES + HISTORICAL DATA | **YES** |
| `ultimate-coach-runs/` | 20.8 MB | REFRESH DATA | **YES** |
| `demo-runs/` | 7.8 MB | EXPORTS | **YES** |
| `coach-advantage-runs/` | 6.6 MB | REFRESH DATA | **YES** |
| `tmp/` | 340 MB | TEMP + UAT artifacts | **YES** |
| `logs/` | 0 MB (empty) | LOGS | **YES** |
| `scripts/data/` | 40 KB | DATABASES | **YES** |
| `analytics/` | 1.1 MB | SOURCE CODE | NO |
| `venv/` | 199 MB | BUILD ARTIFACTS | NO |
| `venv312/` | 227 MB | BUILD ARTIFACTS | NO |
| `scripts/` | 0.9 MB | SOURCE CODE | NO |
| `apps/` | ~200 MB | SOURCE CODE | NO |
| `.worktrees/` | 15,759 MB | SOURCE CODE (worktrees) | NO |

### Breakdown of `data/`

| File | Size | Sub-category |
|------|------|--------------|
| `data/apa_tracker.db` | 536 KB | **Active production DB** |
| `data/apa_tracker_regenerated.db` | 536 KB | Refresh output DB |
| `data/apa_tracker.backup-*.db` (×3) | ~1.9 MB | Backups |
| `data/audit_backups/*.db` | 664 KB | Audit backups |
| `data/demo_coherent.db` | 112 KB | Demo DB |
| `data/demo_apa_tracker.db` | 96 KB | Demo DB |
| `data/ultimate_coach_historical_catalog_expanded.json` | 1.4 MB | Historical data |
| `data/ultimate_coach_historical_catalog.json` | 112 KB | Historical data |
| `data/ultimate_coach_history_graph_report.json` | 79 KB | Reports |

### Breakdown of `tmp/` (340 MB)

| Sub-path | Content |
|----------|---------|
| `tmp/duplicate-repair-candidate-*/` | One-off repair DB (~10 MB) |
| `tmp/audit-quick-refresh/` | Quick-refresh audit runs with xlsx + html |
| `tmp/uat/` | UAT acceptance runs with xlsx + html + PDFs |
| `tmp/pytest-pr83/` | PR #83 pytest fixtures (package.json clones) |
| `tmp/codex-issue84-log-review.jsonl` | Issue log review (389 KB) |

### Hardcoded drive paths in source code

**None found in Python scripts or TypeScript.** Path handling is already portable:
- Python scripts use `PROJECT_ROOT = Path(__file__).resolve().parent.parent`
- TypeScript/Next.js web app uses Turso cloud DB (no local path)
- `tools/apa-console-capture.js` line 212: `C:\path\to\apa-tracker` — this is a **documentation string** displayed to users in a help message, not a path the tool uses. Low risk; update for completeness.

---

## 2. Target Structure: D:\APA-Tracker-Data\

```
D:\APA-Tracker-Data\
├── archive\               ← completed/superseded DB snapshots, old run outputs
├── backups\               ← DB backups (*.backup-*.db, audit_backups/)
├── databases\             ← active and regenerated DBs (apa_tracker.db, demo*.db)
├── exports\               ← demo-runs, coach-advantage-runs, Excel/HTML outputs
├── historical-seasons\    ← historical catalog JSON (apa_tracker_historical_catalog*.json)
├── logs\                  ← logs/ directory contents
├── refresh-data\          ← ultimate-coach-runs/, run-YYYYMMDD/ refresh outputs
├── reports\               ← JSON reports (history_graph_report.json, coverage reports)
├── scoresheets\           ← future: downloaded scoresheet source data
├── snapshots\             ← tmp/ UAT runs, audit snapshots
└── statistics\            ← future: season stats exports
```

**D:\APA-Tracker-Data\ was created** on 2026-10-25. All 11 subdirectories exist.

---

## 3. Items to Move

### Priority 1 — Safe to move now (no active runtime dependency during dev)

| Source (C:) | Destination (D:) | Size |
|-------------|-----------------|------|
| `data/audit_backups/` | `D:\APA-Tracker-Data\backups\audit_backups\` | 664 KB |
| `data/apa_tracker.backup-*.db` (×3) | `D:\APA-Tracker-Data\backups\` | ~1.9 MB |
| `data/ultimate_coach_historical_catalog*.json` | `D:\APA-Tracker-Data\historical-seasons\` | ~1.5 MB |
| `data/ultimate_coach_history_graph_report.json` | `D:\APA-Tracker-Data\reports\` | 79 KB |
| `demo-runs/` | `D:\APA-Tracker-Data\exports\demo-runs\` | 7.8 MB |
| `coach-advantage-runs/` | `D:\APA-Tracker-Data\exports\coach-advantage-runs\` | 6.6 MB |
| `logs/` | `D:\APA-Tracker-Data\logs\` | ~0 MB |

**Subtotal: ~18 MB**

### Priority 2 — Move after code change (scripts reference these as defaults)

| Source (C:) | Destination (D:) | Size | Blocker |
|-------------|-----------------|------|---------|
| `data/apa_tracker.db` | `D:\APA-Tracker-Data\databases\` | 536 KB | Default path in ~12 scripts |
| `data/apa_tracker_regenerated.db` | `D:\APA-Tracker-Data\databases\` | 536 KB | Refresh output path |
| `data/demo_coherent.db` | `D:\APA-Tracker-Data\databases\` | 112 KB | `build_coherent_demo.py` default |
| `data/demo_apa_tracker.db` | `D:\APA-Tracker-Data\databases\` | 96 KB | `scripts/data/demo_apa_tracker.db` |
| `scripts/data/demo_apa_tracker.db` | `D:\APA-Tracker-Data\databases\` | 40 KB | `run_game_night.py` default |
| `ultimate-coach-runs/` | `D:\APA-Tracker-Data\refresh-data\` | 20.8 MB | Refresh output dir default |

**Subtotal: ~22 MB**

### Priority 3 — Move after audit/confirmation (large, test artifacts)

| Source (C:) | Destination (D:) | Size | Blocker |
|-------------|-----------------|------|---------|
| `tmp/` | `D:\APA-Tracker-Data\snapshots\tmp\` | 340 MB | Active test output; needs test paths updated |

**Subtotal: 340 MB**

### Items to Leave on C: (never move)

| Item | Reason |
|------|--------|
| `apps/` | Source code + Next.js app |
| `scripts/*.py` | Source code |
| `analytics/`, `database/`, `pipeline/`, `scraper/`, `ui/` | Source code |
| `tests/` | Source code |
| `package.json`, `pnpm-lock.yaml`, `pyproject.toml` | Package manifests |
| `.env`, `.env.example` | Active configuration (will add `APA_DATA_ROOT` here) |
| `venv/`, `venv312/` | Regenerable Python environments |
| `.worktrees/` | Git worktrees (contain full source) |

---

## 4. Required Code Changes

### Step A — Introduce `scripts/paths.py` (new file)

```python
"""Central path configuration for APA Tracker data.

All scripts import this module for canonical data paths.
Set APA_DATA_ROOT to override the default D:\\APA-Tracker-Data.
"""
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data root: reads from environment, defaults to D:\APA-Tracker-Data
APA_DATA_ROOT = Path(os.environ.get("APA_DATA_ROOT", r"D:\APA-Tracker-Data"))

# Subdirectories
DATABASES_DIR = APA_DATA_ROOT / "databases"
BACKUPS_DIR   = APA_DATA_ROOT / "backups"
REFRESH_DIR   = APA_DATA_ROOT / "refresh-data"
EXPORTS_DIR   = APA_DATA_ROOT / "exports"
HISTORY_DIR   = APA_DATA_ROOT / "historical-seasons"
SNAPSHOTS_DIR = APA_DATA_ROOT / "snapshots"
REPORTS_DIR   = APA_DATA_ROOT / "reports"
LOGS_DIR      = APA_DATA_ROOT / "logs"

# Canonical active DB (overrideable via APA_DB_PATH)
APA_DB = Path(os.environ.get("APA_DB_PATH", str(DATABASES_DIR / "apa_tracker.db")))

# Kept for backward compat during migration — remove after all scripts updated
LEGACY_DATA_DIR = _PROJECT_ROOT / "data"
```

### Step B — Update `.env` and `.env.example`

Add to `.env.example`:
```
# Data storage root — set to override D:\APA-Tracker-Data
APA_DATA_ROOT=D:\APA-Tracker-Data

# Active production database (optional; defaults to $APA_DATA_ROOT/databases/apa_tracker.db)
# APA_DB_PATH=
```

### Step C — Update scripts that have hardcoded `data/` defaults

The scripts below default to `PROJECT_ROOT / "data" / "..."`. After `paths.py` exists, update each default:

| Script | Current default | New default |
|--------|----------------|-------------|
| `build_ultimate_coach_excel.py` | `PROJECT_ROOT / "data" / "ultimate_coach_staging.db"` | `paths.APA_DB` |
| `build_ultimate_coach_html.py` | `PROJECT_ROOT / "data" / "..."` | `paths.APA_DB` |
| `build_full_production_demo.py` | `PROJECT_ROOT / "data" / "apa_tracker_regenerated.db"` | `paths.DATABASES_DIR / "..."` |
| `build_coherent_demo.py` | `PROJECT_ROOT / "data" / "demo_coherent.db"` | `paths.DATABASES_DIR / "demo_coherent.db"` |
| `build_historical_catalog.py` | `PROJECT_ROOT / "data" / "..."` | `paths.HISTORY_DIR / "..."` |
| `refresh_ultimate_coach_current_session.py` | output `ultimate-coach-runs/` | `paths.REFRESH_DIR` |
| `run_game_night.py` | `PROJECT_ROOT / "data"` | `paths.APA_DB` / `paths.REFRESH_DIR` |
| `export_ultimate_coach_data.py` | various `data/` paths | `paths.*` equivalents |
| `protect_dashboard_snapshot.py` | `data/` | `paths.DATABASES_DIR` |
| `expand_ultimate_coach_history.py` | `data/` | `paths.HISTORY_DIR` |
| `build_historical_dashboard_snapshot.py` | `data/` | `paths.DATABASES_DIR` |
| `build_captains_edge.py` | `data/` | `paths.DATABASES_DIR` |

**Pattern for each update** (takes ~2 lines per script):
```python
# Before
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "apa_tracker.db"

# After
import sys; sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import APA_DB as DEFAULT_DB
```

### Step D — Update `tools/apa-console-capture.js` (documentation string only)

Line 212: change `C:\path\to\apa-tracker` to a generic placeholder like `path\to\apa-tracker` or use a variable. Low risk, no runtime impact.

---

## 5. Estimated Space Savings

| Action | Current (C:) | After Move | Savings |
|--------|-------------|------------|---------|
| Move `data/` | 5.4 MB | → D: | 5.4 MB |
| Move `ultimate-coach-runs/` | 20.8 MB | → D: | 20.8 MB |
| Move `demo-runs/`, `coach-advantage-runs/` | 14.4 MB | → D: | 14.4 MB |
| Move `tmp/` | 340 MB | → D: | 340 MB |
| **C: total freed** | | | **~380 MB** |

### Projected Growth (D: drive)

| Category | Current | Monthly growth | 12-month projection |
|----------|---------|----------------|---------------------|
| Refresh runs | 20.8 MB | ~5-10 MB/mo | ~80-140 MB |
| Databases | 5 MB | ~1 MB/mo (backups) | ~17 MB |
| UAT snapshots | 340 MB | ~20-40 MB/test cycle | varies |
| Historical data | 1.5 MB | ~0.5 MB/season | ~7 MB |
| **D: total in 12mo** | ~382 MB | | **~500-700 MB** |

D: holds ~22 GB of archived worktrees after the cleanup mission. The data migration adds <1 GB of runtime data — well within capacity.

---

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Script breaks because `data/` path not found | Medium | High | Keep `LEGACY_DATA_DIR` symlink or fallback in `paths.py` during transition |
| D: drive unavailable (e.g., external drive disconnected) | Low | High | `APA_DATA_ROOT` env var lets any path be substituted at runtime |
| Test suite breaks (tmp/ paths baked into test fixtures) | Medium | Medium | Move `tmp/` last; update test path helpers first |
| Refresh scheduled task writes to wrong path | Low | Medium | Scheduled task picks up `APA_DATA_ROOT` from env if set in task definition |
| Multiple worktrees with different `data/` states | Low | Low | Each worktree already uses its own `PROJECT_ROOT`; no cross-contamination |
| Git accidentally tracks D: path | Low | Low | Add `D:\APA-Tracker-Data` to `.gitignore` patterns |

---

## 7. Migration Checklist (ordered)

> **Do not move anything until all three gates are verified:**
> 1. Inventory complete ✅ (this document)
> 2. Backup verified — confirm `data/apa_tracker.db` has a recent backup before any move
> 3. New paths tested — run one script with `APA_DATA_ROOT=D:\APA-Tracker-Data` before moving live DB

### Phase 0 — Prepare (no moves yet)
- [x] Create `D:\APA-Tracker-Data\` structure
- [ ] Write `scripts/paths.py`
- [ ] Add `APA_DATA_ROOT` to `.env.example`
- [ ] Add `D:\APA-Tracker-Data` pattern to `.gitignore`
- [ ] Verify `data/apa_tracker.db` has a current backup in `data/` (it does: 3 backups exist)

### Phase 1 — Move Priority 1 (no code changes needed)
- [ ] Move `data/audit_backups/` → `D:\APA-Tracker-Data\backups\audit_backups\`
- [ ] Move `data/*.backup-*.db` → `D:\APA-Tracker-Data\backups\`
- [ ] Move `data/ultimate_coach_historical_catalog*.json` → `D:\APA-Tracker-Data\historical-seasons\`
- [ ] Move `data/ultimate_coach_history_graph_report.json` → `D:\APA-Tracker-Data\reports\`
- [ ] Move `demo-runs/` → `D:\APA-Tracker-Data\exports\demo-runs\`
- [ ] Move `coach-advantage-runs/` → `D:\APA-Tracker-Data\exports\coach-advantage-runs\`

### Phase 2 — Code changes + move active DBs
- [ ] Implement `scripts/paths.py`
- [ ] Update each script's defaults (see §4, Step C)
- [ ] Test one script end-to-end against D: paths
- [ ] Move `data/apa_tracker.db` → `D:\APA-Tracker-Data\databases\`
- [ ] Move `data/apa_tracker_regenerated.db` → `D:\APA-Tracker-Data\databases\`
- [ ] Move `data/demo*.db` → `D:\APA-Tracker-Data\databases\`
- [ ] Move `scripts/data/demo_apa_tracker.db` → `D:\APA-Tracker-Data\databases\`
- [ ] Move `ultimate-coach-runs/` → `D:\APA-Tracker-Data\refresh-data\`

### Phase 3 — Move test artifacts
- [ ] Update test helpers that write to `tmp/`
- [ ] Move `tmp/` → `D:\APA-Tracker-Data\snapshots\`
- [ ] Update CI / scheduled-task definitions to set `APA_DATA_ROOT`

---

## 8. Items Still on C: After Migration (significant)

| Item | Size | Why kept |
|------|------|----------|
| `venv/` | 199 MB | Python env (regenerable: `python -m venv venv && pip install -r requirements.txt`) |
| `venv312/` | 227 MB | Python env (regenerable) |
| `.worktrees/` | 15,759 MB | Git worktrees (source code) — handled by cleanup mission |
| `apps/` | ~200 MB with node_modules | Source + Next.js build cache |

The `venv` directories consume 426 MB and could be deleted and regenerated at any time if C: space becomes tight. They are not data — they do not need D: migration.

---

*Plan written 2026-10-25 from inventory on feat/phase1-war-room @ 593982b*
