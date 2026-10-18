# Refresh Ultimate Coach

Double-click **FULL_APA_REFRESH.bat** for a complete rebuild, or **QUICK_REFRESH.bat** for the same source check with unchanged components reused. Sign in on the real APA website if prompted. No follow-up Python commands are required for an installed environment.

Both launchers open the completed workbook and HTML after validation. Use the paths printed at completion. Previous generations stay available; an already open older file does not update itself.

## Visible progress after login

After Member Services loads, return to the console and press Enter. The console immediately prints `ENTER RECEIVED`, reports login-browser closure, then starts authenticated API requests. Authentication is confirmed only when APA accepts the dashboard query. After Enter, there is no URL, page-element or network-idle wait; the browser closes and serial GraphQL HTTP requests capture the source fixtures.

Each request and blocking build/validation phase prints START, DONE (with elapsed time), or FAILED. Phases exceeding five seconds print STILL RUNNING every five seconds. STEP 1/8 through STEP 8/8 identify the current phase. The launcher prints its working folder and runs Python unbuffered. The same progress is written to REFRESH_STATUS.txt. Wait for ALL REFRESH TASKS COMPLETE before using the new outputs; browser closure alone is not completion.

The original login prompt could remain the last visible line during acquisition even though responses were being saved. A real diagnostic login now verified Enter receipt, browser closure and three accepted API requests, including standings. This live handoff check did not rebuild a real database; full/quick/output/recovery acceptance uses isolated synthetic fixtures.

The final APA REFRESH COMPLETE block lists the number of indexed response fixtures, unique current-roster teams and players processed, matchup/workbook/HTML rebuild or reuse results, validation, the exact output folder and total elapsed time (including login). These are processed counts, not a claim that every row changed. Quick mode reports zero teams/players updated when ingestion is skipped and states how many were checked; existing validated outputs are explicitly marked reused. Offline checks say OFFLINE VALIDATION and Fixtures Loaded. The summary appears only after the completed bundle becomes current and is also saved in REFRESH_STATUS.txt.

## Current and replacement workflows

The old local `run_apa_full_scrape.bat` runs only `scraper/full_auto_scrape.py`. Its `main()` attaches response capture, logs in, visits team/division/match routes, prints SCRAPE COMPLETE, then closes Chromium. `capture_graphql()` writes raw responses beneath `scraper/sanitized_fixtures/`. There is no database ingestion or output build in that script. `scrape_all()` visits at most 12 teams, 12 divisions and 40 discovered matches. The batch file also prints Finished without testing the exit code.

`pipeline_run_all.py` adds `python -m pipeline` and tests. That fixture pipeline calls `pipeline/ingest.py` and `pipeline/exports.py`; its legacy workbooks and JSON are not the Ultimate Coach workbook/HTML pair. `Refresh_APA_Cockpit.bat` uses the separate game-night Cockpit path and can promote the production database. Neither is the new Ultimate Coach refresh command.

The complete refresh entry point is now:

```text
FULL_APA_REFRESH.bat / QUICK_REFRESH.bat
  -> tools/launch_apa_refresh.bat
  -> python -m pipeline.ultimate_coach_refresh
     1 configuration, repository boundary, lock, dependency checks
     2 pipeline/refresh_sources.py: acquire_current_sources
       -> tools/run_ultimate_coach_browser.py: capture_access_token (only if needed)
       -> scraper/graphql_scraper.py: authenticated read-only APA queries
       -> scraper/historical_catalog.py: exact league/session context discovery
       -> private checksummed response fixtures
     3 replay_ingest (HTTP forbidden during replay)
       -> scheduler/graphql_sync.py: ingest_team_data, sync_division_wide
       -> database/ingest.py: existing canonical writes, including explicit division standings ingestion
       -> scripts/refresh_ultimate_coach_current_session.py: reconcile_match
       -> scraper/player_enrichment.py: enrich_all_players
     4 rebuild_database
       -> pipeline/ingest.py: rebuild_matchups, rebuild_analytics
       -> analytics/matchup_builder.py
       -> scripts/build_head_to_head.py, scripts/build_player_trends.py
     5 analytics/ultimate_coach_cockpit_identity_bridge.py
       -> existing identity manifest, namespace audit, data contract, match-day payload
     6 ui/export_excel_ultimate_coach.py, ui/excel_war_room.py
       -> pipeline/refresh_workbook.py: isolated native Excel recalculation/checks
     7 ui/ultimate_coach.py + ui/ultimate_coach_war_room.js
       -> pipeline/refresh_workbook.py: real Chromium startup/error/phone-overflow checks
     8 SQLite integrity/FK checks, source preservation, artifact checksums
       -> manifest.json + READY -> atomic CURRENT.json
       -> ALL REFRESH TASKS COMPLETE -> open workbook and HTML
```

These are function calls in one coordinator, not scripts the user must remember. The recommendation rules remain the existing engine; recommendations are recomputed in the shared payload and workbook/HTML views, not a separate invented recommendation table.

## Reading Next Send

Next Send presents recorded matchup options, not an overall player ranking. Its explanation appears before the direct-record list. Neutral Direct-record order labels retain the existing order and ties; exact meeting counts and small-sample labels are emphasized. Captured current team/session records appear separately under **Not used in this ordering**, with format/team/session scope and explicit missing-data labels. Those records are not automatically lifetime records. Meeting age, skill-level changes and Coach Observations do not adjust the ordering; availability filters candidates and budget warnings remain separate reference checks. The recommendation algorithm is unchanged. Run the usual refresh to build files with this presentation; an older open generation retains its original presentation.

## Precisely what is refreshed

Source scope is the signed-in viewer's current dashboard league/tournament divisions: all roster teams, team pages/current statistics, division standings, complete returned schedules (including future matches/byes), and **every scored non-bye scoresheet**. There is no first-N cap and no assumption that unchanged team totals mean unchanged player results. Historical catalog queries establish league context; resolvable numeric members receive the existing league-specific lifetime-stat query. Captured responses are replayed through the existing normalizers and reconciliation.

Explicit standings for every captured current division share one refresh timestamp after team fallback snapshots. The latest standings view must contain the entire captured set; a mismatch fails before the completed pointer advances. `STANDINGS VERIFIED` reports this check.

The candidate SQLite database updates `teams`, `players`, `standings_snapshots`, `matches`, `player_team_history`, `player_matches`, `player_head_to_head`, and resolvable `player_league_career_stats`. It rebuilds `player_matchups`, `player_h2h_advantage`, and `player_trends`. Current roster membership is reconciled with the existing resolved-roster protections. Corrected current scoresheets update results and remove obsolete pairings using the existing authoritative reconciliation. The derived H2H advantage table is cleared before rebuilding in the private candidate so removed pairings cannot survive an upsert-only pass.

Source limits remain explicit: historical games already in the seed are retained, **not recrawled across every older APA session**. Player team-history rows are updated for the current divisions; this does not run the recursive all-player historical backfill. Unresolvable career contexts are counted in the console and manifest; no missing result is invented. Coverage complete means the requested current division ingestion passed its reconciliation, not all of APA history is complete.

## Output locations

Everything is local under ignored `ultimate-coach-runs/refresh/` by default:

| File | Purpose |
| --- | --- |
| `REFRESH_STATUS.txt` | Latest run's clear step status; failure identifies its step |
| `CURRENT.json` | Pointer and bindings for the last complete DB/workbook/HTML generation |
| `run-<UTC>-<unique>/ultimate_coach_staging.db` | Updated database used by both outputs |
| `run-.../Ultimate_Coach.xlsx` | Newly built and natively recalculated workbook, or verified unchanged bytes in quick mode |
| `run-.../ultimate_coach.html` | Updated offline Ultimate Coach and recommendations |
| `run-.../fixtures/responses/*.json` | Private captured APA source responses; never credentials/headers |
| `run-.../fixtures/sources.json`, `scope.json` | Request/content checksums and exact requested scope |
| `run-.../catalog.json`, `career_refresh.json` | Context discovery and enrichment diagnostics when ingestion ran |
| `run-.../refresh_report.json` | Coverage, reconciliation and source limitations |
| `run-.../manifest.json`, `READY` | Artifact/dependency/validation bindings |
| `run-.../FAILED.json` | Failed step/type; failed generation does not become current |

The original source DB is read-only and never replaced. First-run seed selection is `refresh.source_database` in the existing local configuration if supplied; otherwise `data/ultimate_coach_staging.db`, then `data/apa_tracker.db`, otherwise an empty candidate. An empty seed does not provide older history. Later refreshes use the last verified complete DB when the configured base has not changed. A missing/modified completed DB fails for review instead of silently discarding its accumulated history.

**Not updated:** the production `data/apa_tracker.db` or other original seed; legacy `exports/`/`output/` files; previously generated review workbooks/HTML; the old Coach Cockpit; published websites; recursive historical archives; old browser tabs; existing workbook planning inputs. Previous workbook edits remain in their original generation and are not merged into a newly generated workbook. This refresh is a coherent local DB/workbook/HTML bundle, not release installation, production DB promotion or publication.

## Quick refresh rules

Quick still checks live APA responses, including all scored sheets. Without a trustworthy APA change feed, skipping those checks would miss corrected individual results with unchanged team totals.

It verifies every captured response against its index, then compares source content, scope, base DB and ingestion/engine code signatures. If unchanged, ingestion and derived rebuilds are skipped. Each output is checked separately against payload/settings/date, exporter/runtime dependencies and its actual file checksum. Missing/damaged HTML rebuilds HTML; missing/damaged workbook rebuilds the workbook. HTML-only runtime changes do not rebuild the workbook. Reused validated bytes retain their original build label; the manifest records the latest source check time. Full mode always ingests/reconciles/rebuilds.

## Setup, verification and troubleshooting

Windows, desktop Excel, Python 3.12/3.13, the application dependencies plus `requirements-refresh.txt`, and installed Playwright Chromium are prerequisites. The launcher prefers a compatible `venv` Python, then the Python launcher. Dependency/Excel registration errors stop before acquisition; failures later still preserve the prior completed bundle. No credentials are embedded in the launchers or response fixtures. Raw responses and generated artifacts stay private.

Expected full completion:

```text
SCRAPE COMPLETE
DATABASE UPDATED
MATCHUPS REBUILT
TRENDS REBUILT
RECOMMENDATIONS UPDATED
WORKBOOK REBUILT
HTML REBUILT
ALL REFRESH TASKS COMPLETE
```

Quick prints UP TO DATE for skipped components. Offline fixture verification is explicitly labeled OFFLINE VALIDATION and cannot replace an existing live current bundle. A failed step returns a nonzero exit code and does not advance CURRENT.json. If a prior process was interrupted, verify it is stopped before reviewing its REFRESH.lock; the launcher never guesses that another refresh is dead or deletes someone else's lock.

Developer verification from the repository root: `python -B -m pytest tests/test_refresh_sources.py tests/test_graphql_client_errors.py tests/test_ultimate_coach_refresh.py -q --basetemp=tmp/uat/<new-unique-folder>`. Portable tests run actual SQLite ingestion and exporters with synthetic responses; native Excel/browser launcher acceptance is a separate Windows check, not a live APA acceptance claim.

## Legacy batch review (recommendations only)

Reviewed project launchers in the canonical root and builder; dependency/vendor launchers are not application workflows. No files are deleted or renamed by this task.

| Existing batch file | Recommendation | Source-based reason |
| --- | --- | --- |
| `run_apa_full_scrape.bat` (local) | RENAME to `CAPTURE_APA_FIXTURES_ONLY.bat` after owner review | Calls only full_auto_scrape.py; does not ingest/build; Finished banner ignores return code |
| `Refresh_APA_Cockpit.bat` | KEEP | Explicitly named older Coach Cockpit workflow, separate outputs/promotion behavior |
| `run_demo.bat` (local) | RENAME to `BUILD_DEMO_ONLY.bat` if retained | Machine-specific synthetic demo, not a live refresh |
| `run_full_demo.bat` (local) | REMOVE only after owner review/replacement | Duplicate demo chain; build_data_coverage.py is called without its required scope arguments |
| literal `fullscrape.bat` | No action | Not present in inspected project launchers |
| `FULL_APA_REFRESH.bat`, `QUICK_REFRESH.bat` | KEEP | Complete Ultimate Coach entry points |
| `tools/launch_apa_refresh.bat` | KEEP | Shared interpreter selection/exit-code handling, called by both entry points |

Build/audit execution evidence and release gates remain in the single `docs/overnight_coach_advantage_report.md`; this document is the durable user runbook and source call map.
