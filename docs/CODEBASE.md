# APA Tracker — Codebase Map

## Repository root
`C:\Users\ssand\Desktop\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker`  
GitHub: `https://github.com/ssands5-cloud/APA-Tracker.git`  
Active branch for web work: `feat/phase1-war-room`  
PR #104 pending: `feat/apa-tactics-coach-skill` → main

---

## Top-level directory ownership

| Directory | Language | Owner responsibility |
|-----------|----------|----------------------|
| `scraper/` | Python | APA.com data acquisition (GraphQL + HTML scraping) |
| `database/` | Python | SQLAlchemy ORM models + engine construction |
| `pipeline/` | Python | Refresh orchestration, fixture management, ingest coordination |
| `analytics/` | Python | All statistical computation — matchup engines, evidence, scoring |
| `ui/` | Python | Excel / HTML rendering from analytics output |
| `scripts/` | Python | CLI entry points and one-off builders (the operator-facing layer) |
| `apps/ultimate-coach-web/` | TypeScript/Next.js | Production web app (Ultimate Coach) |
| `.github/skills/` | Markdown | Claude skills (YAML frontmatter + markdown body) |
| `docs/` | Markdown | Architectural docs, feature specs, this file |
| `tests/` | Python | `node:test`-backed tests + fixture data |
| `tools/` | JS | APA console capture utility |

---

## `auth/` — 4 files

Authentication layer for APA.com. Used by `scraper/` and `scheduler/` — not a public API.

| File | Role |
|------|------|
| `auth/login.py` | Authenticates against the APA portal; returns a `requests.Session` |
| `auth/graphql_client.py` | Thin HTTP client for the APA GraphQL API |
| `auth/session_manager.py` | Persists and reuses an authenticated `requests.Session` across scheduler runs to avoid logging in on every invocation |

---

## `parser/` — 4 files

Shared parsing utilities consumed by `scraper/`. Not called directly by scripts.

| File | Role |
|------|------|
| `parser/apa_graphql.py` | GraphQL query/mutation documents for the APA Member Services API |
| `parser/html_parser.py` | Generic HTML table/summary parsing helpers used by all scraper modules |
| `parser/apa_page_map.py` | APA page structure mapping |

---

## `scheduler/` — 4 files

Automated sync jobs that run on a schedule. Each imports from `auth/` and `pipeline/`.

| File | Role |
|------|------|
| `scheduler/daily_sync.py` | Daily job: pull latest team data (HTML scrape) and ingest |
| `scheduler/graphql_sync.py` | Live job: pull team data via APA GraphQL API and ingest (GraphQL counterpart to daily_sync) |
| `scheduler/weekly_refresh.py` | Weekly job: full re-pull of standings + roster + fresh Excel export |

---

## `scraper/` — 15 files, ~189 KB

Acquires data from APA.com. Never writes to the production database directly; writes raw fixture JSON consumed by the pipeline.

| File | Role |
|------|------|
| `graphql_scraper.py` | Fetch team/roster/schedule via APA GraphQL API (`fetch_team_data`, `team_row`, `roster_rows`) |
| `league_scraper.py` | Fetch standings HTML (`fetch_standings`) |
| `match_scraper.py` | Parse individual match HTML pages (`fetch_match_page`, `parse_match`) |
| `player_scraper.py` | Parse per-player stats pages (`fetch_player_stats`, `parse_player_stats`) |
| `team_scraper.py` | Parse team roster pages (`fetch_team_page`, `parse_team_roster`) |
| `historical_archive.py` | Build/resume the league-wide historical staging archive |
| `historical_catalog.py` | Discover historical seasons/divisions (`build_historical_catalog`) |
| `historical_graph.py` | GraphQL-backed historical data fetcher |
| `player_enrichment.py` | Enrich players with lifetime APA stats (`enrich_all_players`) |
| `auth_classification.py` | Confirm APA session scope; retry on denial (`call_with_confirmed_denial_retry`) |
| `full_apa_scrape.py` | Type-sanitized full scrape (replaces values with type names — safe to commit output) |
| `full_auto_scrape.py` | Automated discovery of teams/matches/entities |

---

## `database/` — 8 files, ~85 KB

SQLAlchemy ORM. Single SQLite file (path from `APA_DATA_ROOT`). No migrations — schema checked at startup.

| File | Role |
|------|------|
| `models.py` | ORM models: `Team`, `Player`, `Match`, `StandingsSnapshot`, `PlayerMatch`, `PlayerCareerStats`, `PlayerLeagueCareerStats` |
| `engine.py` | `create_db_engine(config)` — creates SQLite engine, checks schema (`StaleSchemaError`), enables FK constraints |
| `queries.py` | Read-only query helpers: `all_teams`, `all_matches`, `latest_standings`, `player_match_history`, etc. |
| `ingest.py` | Write path: `ingest_standings`, `upsert_team`, `upsert_player`, `ingest_match`, `upsert_roster` |

---

## `pipeline/` — 7 files, ~85 KB

Orchestrates refresh runs end-to-end. Separates concerns: fixture I/O, ingest, progress reporting, workbook validation.

| File | Role |
|------|------|
| `ingest.py` | `run(db)` — calls ingest layer for teams/matches/history; rebuilds matchups and analytics |
| `refresh_sources.py` | `acquire_current_sources(config, seed_database)` — downloads or loads cached APA data |
| `ultimate_coach_refresh.py` | `replay_ingest(config, fixtures)` — reproduces the UC staging DB from captured fixtures |
| `exports.py` | `run(config)` — writes Excel/HTML output artifacts |
| `refresh_progress.py` | Progress reporting context manager |
| `refresh_workbook.py` | Excel workbook validation (`validate_structure`, `recalculate_and_validate`) |
| `fixtures.py` | `FixtureStore` — disk-backed fixture cache |

---

## `analytics/` — 56 files, ~567 KB

Pure computation; no I/O except reading from a `Session` arg. All functions return typed dataclasses or named tuples. This layer is the largest and most tested.

### Ultimate Coach sub-system (prefix `ultimate_coach_`)
| File | Role |
|------|------|
| `ultimate_coach_data_contract.py` | `build_contract(db)` — canonical data contract for UC |
| `ultimate_coach_identity_manifest.py` | `build_verified_identity_manifest(contract)` — VERIFIED_UNIQUE identity resolution |
| `ultimate_coach_cockpit_identity_bridge.py` | `build_verified_cockpit_payload(...)` — wires identity gate into HTML payload |
| `ultimate_coach_payload.py` | `build_ultimate_coach_payload(db)` — full UC payload (all pairings) |
| `ultimate_coach_war_room.py` | War Room display helpers (`date_label`, `category`, `cell_text`, `explanation`) |
| `ultimate_coach_match_day.py` | `load_match_day_settings`, `parse_match_date` — identity-backed schedule lookup |
| `ultimate_coach_matchup_evidence.py` | Display labels, player refs, record text |
| `ultimate_coach_evidence_quality.py` | `direct_evidence`, `shared_opponent_evidence` |
| `ultimate_coach_confidence.py` | `pair_confidence`, `overall_record` |
| `ultimate_coach_excel_payload.py` | Excel-specific payload builders |
| `ultimate_coach_scout_compare.py` | `build_scout_compare(...)` — head-to-head scout card |
| `ultimate_coach_player_profiles.py` | Player profile builders |

### Core matchup engines
| File | Role |
|------|------|
| `pairing_evidence.py` | `PairingEvidenceMatrix` — direct + shared evidence, `EvidenceLabel` enum |
| `match_night_engine.py` | `match_plan(ours, theirs)`, `plan_for_war_room(war_room)` — lineup recommendation engine |
| `lineup_optimizer.py` | `LineupSolution` — optimized lineup assignments with scores |
| `lineup_lab.py` | `LineupLabResult` — enumerate lineup options |
| `lineup_legality.py` | `check_lineup_legality`, `legal_completion_exists` |
| `lineup_risk.py` | `upset_risk_index`, `anchor_stability_score` |
| `head_to_head.py` | `win_loss`, `skill_only_win_probability`, `weighted_win_rate` |
| `matchups.py` | Low-level matchup aggregation functions |
| `captains_edge.py` | `matchup_score`, `risk_factor` |
| `captains_edge_summary.py` | `CaptainsEdgeSummary` — top pairings / danger matchups |

### Player analytics
| File | Role |
|------|------|
| `player_stats.py` | `summarize_player`, `recent_form` |
| `player_trends.py` | `PlayerTrendResult` — rolling window, regression slope, hot/cold flag |
| `player_vs_player.py` | `summarize(...)` — head-to-head summary with trend |
| `player_matchup_engine.py` | `build_player_matchup_report(...)` — skill trend + matchup card |
| `skill_level_trends.py` | `skill_level_changes`, `skill_level_trend`, `skill_level_volatility` |

### Team analytics
| File | Role |
|------|------|
| `team_stats.py` | `compute_trend`, `team_match_record`, `opponent_strength_index` |
| `team_strength.py` | `build_report(...)` — offense/defense/depth index |
| `team_matchup_engine.py` | `build_ranked_opponents(matrix)` — opponent ranking by evidence |
| `scouting_evidence.py` | `build_scouting_evidence(...)` — shared opponent cross-referenced records |

### Calibration / validation (research, not production path)
`win_probability.py`, `prediction_validation.py`, `calibration_metrics.py`, `baseline_evaluation.py`, `season_projection.py`, `matchup_candidate_model.py`

---

## `ui/` — 35 files, ~692 KB

Renders analytics output to Excel (`openpyxl`) or HTML (Jinja2/f-strings). Each file exports one or two public functions: `build_workbook(...)` and/or `write_workbook(...)` for Excel, `render(...)` for HTML tabs.

| Subdirectory/file | Renders |
|-------------------|---------|
| `ui/export_excel_ultimate_coach.py` | Ultimate Coach Excel workbook |
| `ui/export_excel_team_matchup_engine.py` | Team matchup Excel |
| `ui/export_excel_player_matchup_engine.py` | Player matchup Excel |
| `ui/excel_war_room.py` | War Room Excel with dynamic formulas |
| `ui/ultimate_coach.py` | `_browser_payload(...)` — UC HTML artifact |
| `ui/match_night.py` | `write_site(out)` — AES-GCM encrypted Match Night static site |
| `ui/dashboard.py` | Dashboard HTML renderer |
| `ui/coach_cockpit.py` | Coach Cockpit HTML |
| `ui/tabs/tonights_match.py` | Tonight's Match tab |
| `ui/tabs/matchups.py` | Matchups tab |
| `ui/tabs/captains_edge.py` | Captain's Edge tab |
| `ui/tabs/lineup_optimizer.py` | Lineup Optimizer tab |
| `ui/tabs/trends.py` | Player Trends tab |

---

## `scripts/` — 49 files, ~536 KB

Operator-facing CLI entry points. Each has `def main(argv=None)`. No hardcoded drive paths — all use `PROJECT_ROOT = Path(__file__).resolve().parent.parent` or `scripts/paths.py`.

### Key orchestrators
| Script | Purpose |
|--------|---------|
| `run_game_night.py` | **Primary game-night workflow**: stage DB → build cockpit → validate → promote |
| `scrape_and_ingest.py` | Full APA scrape + ingest (teams, matches, standings, career stats) |
| `refresh_ultimate_coach_current_session.py` | Refresh current session results into a copy of the UC staging DB |
| `build_ultimate_coach_production.py` | Read-only publication boundary — builds verified UC production candidate |
| `build_ultimate_coach_excel.py` | Builds the standalone offline UC Excel companion |
| `build_ultimate_coach_html.py` | Builds the standalone offline UC Scout & Compare HTML |
| `build_match_night_package.py` | AES-GCM encrypted Match Night static site |
| `publish_match_night.py` | Fail-closed publish to gh-pages branch |

### Central config
| Script | Purpose |
|--------|---------|
| `scripts/paths.py` | `APA_DATA_ROOT`, `DATABASES_DIR`, `APA_DB`, `REFRESH_DIR`, etc. Import instead of constructing paths |
| `scripts/repo_boundary.py` | Repository boundary guards (used by publisher + UAT) |

---

## `apps/ultimate-coach-web/` — Next.js App Router

### `src/app/` — routes
| Route | Component | Access |
|-------|-----------|--------|
| `/` | `CaptainCommand` | Authenticated |
| `/match-night` | War Room decision flow | Authenticated |
| `/summary` | `CaptainBriefing` | Authenticated |
| `/recommendations` | Opponent recommendations | Authenticated |
| `/threats` | Threat scouting | Authenticated |
| `/team-status` | Team status | Authenticated |
| `/dashboard/[...section]` | Historical dashboard | ADMIN/COACH only |
| `/dashboard/admin` | User management | ADMIN only |
| `(auth)/sign-in` | Clerk sign-in | Public |

### `src/lib/` — shared utilities
| File | Exports |
|------|---------|
| `snapshot-types.ts` | `Snapshot`, `Player`, `Evidence`, `Pairing`, `Hold`, `Response` types |
| `evidence-label.ts` | `evidenceLabel(level)` — Strong/Solid/Thin → "X Evidence" |
| `access-policy.ts` | `isAuthorized(identity, resource)` |
| `auth-config.ts` | `authConfigured()` |
| `demo.ts` | Static demo fixture (no backend call) |
| `db/client.ts` | `execute(sql, args)`, `executeBatch(stmts)` — Turso HTTP client |
| `db/users.ts` | `getUser`, `getUserByEmail` — Role: ADMIN/COACH/REVIEWER/PENDING/SUSPENDED |
| `db/audit.ts` | `appendAuditLog`, `listAuditLog` |
| `server/authorization.ts` | `historicalAccess(userId)` — server-only role gate |
| `server/historical-snapshot.ts` | `authorizedSnapshot(userId, snapshotId)` |
| `server/snapshot-crypto.ts` | `decryptSnapshot(enc)` — AES-256-GCM |

### `src/components/` — UI
| Component | Renders |
|-----------|---------|
| `captain-command.tsx` | Home page — tonight's lead, protect list, threats |
| `captain-decisions.tsx` | `ThreatDossiers`, `CaptainBriefing` |
| `dashboard-pages.tsx` | `HomePage`, `MatchNightPage`, `RecommendationsPage`, `ThreatsPage` |
| `plan-board.tsx` | `PlanBoard` — tactical board |
| `opponent-view.tsx` | Per-opponent scouting card |
| `decision-brief.tsx` | `DecisionBrief` — send/hold decision block |
| `navigation.tsx` | Sidebar nav |
| `ui.tsx` | `PageTitle`, `Card`, `Notice` — primitives |

---

## `tools/` — operator utilities

| File | Role |
|------|------|
| `tools/capture_apa_graphql.py` | Captures APA GraphQL traffic from a browser session — replaces the DevTools → HAR → PowerShell dance |
| `tools/run_ultimate_coach_browser.py` | Runs the Ultimate Coach live build using browser-based auth (browser is an auth bridge only; credentials never touch the script) |

---

## Root-level utility files

| File | Role |
|------|------|
| `env_loader.py` | Environment variable loading helper used by scripts that need `.env` |
| `pipeline_run_all.py` | Top-level pipeline runner — orchestrates the full pipeline in one command |
| `apa_full_scrape.py` | Gitignored superseded Playwright scrape draft — **not source, do not modify** |
| `playwright_login_scrape.py` | Playwright-based login scrape draft — experimental, not part of the canonical pipeline |

---

## `tests/` — 171 files

Node built-in `node:test` (TypeScript) + pytest (Python). Every analytics module has a corresponding test file.

**Key test files for AI agents modifying analytics:**

| Test file | Covers |
|-----------|--------|
| `tests/test_match_night_engine.py` | `analytics/match_night_engine.py` |
| `tests/test_lineup_legality.py` | `analytics/lineup_legality.py` |
| `tests/test_lineup_optimizer.py` | `analytics/lineup_optimizer.py` |
| `tests/test_pairing_evidence.py` | `analytics/pairing_evidence.py` |
| `tests/test_ultimate_coach_cockpit_identity_bridge.py` | Identity bridge |
| `tests/test_ultimate_coach_data_contract.py` | Data contract |
| `tests/test_ultimate_coach_identity_manifest.py` | Identity manifest |
| `tests/test_match_night.py` | `ui/match_night.py` encryption |
| `tests/test_publish_match_night.py` | `scripts/publish_match_night.py` boundary guards |
| `tests/test_repo_boundary.py` | `scripts/repo_boundary.py` |
| `apps/ultimate-coach-web/tests/` | TypeScript — captain-command (primary CI gate), browser smoke, private access |

**Run Python tests:** `pytest tests/`  
**Run TS tests:** `node --experimental-strip-types apps/ultimate-coach-web/tests/*.test.ts`

---

## IGNORE FOR APA TRACKER ANALYSIS

```
.github/skills/sports-skills-main/
```

**This is an external package, not part of APA Tracker production code.**  
Reason: GPT/Jeeves dropped a `sports_skills` Python package (116 files) here as untracked content.  
It has nothing to do with APA pool league analytics.

**Exclude from:**
- File counts and directory listings
- Architecture analysis
- Code searches (grep, glob)
- Import tracing
- Coverage calculations

Unless the user explicitly asks about it, treat this directory as absent.  
Recommended grep/glob exclusion: `--exclude-dir=.github/skills/sports-skills-main`

---

## Config files

| File | Purpose |
|------|---------|
| `.env` / `.env.example` | `APA_USERNAME`, `APA_PASSWORD`, `APA_DATA_ROOT`, `APA_DB_PATH` |
| `apa_config.yaml` | Team ID, division, session config for scripts |
| `apa_config.local.yaml` | Machine-local overrides (viewer identity, gitignored) |
| `apps/ultimate-coach-web/.env.local` | `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `CLERK_*`, `UC_SNAPSHOT_KEY` |
| `scripts/paths.py` | Central data-path config (import this, don't construct paths) |

---

## What is gitignored (important)

`data/`, `exports/`, `logs/`, `tmp/` (340 MB pytest scratch), `demo-runs/`, `coach-advantage-runs/`, `ultimate-coach-runs/`, `venv*/`, `.env.*`, `token.txt`, `token.xlsx`, `apa_config.local.yaml`, `dashboard*.html`, `apps/ultimate-coach-web/data/`, `apps/ultimate-coach-web/private-snapshots/*` (except `historical.enc.json`)
