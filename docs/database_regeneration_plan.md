# Database regeneration plan

Regeneration is the supported response to a stale or incomplete APA Tracker
database. `Base.metadata.create_all()` can create missing tables but cannot add
columns to an existing table, and this project intentionally has no destructive
in-place migration for re-fetchable league facts.

## Safe sequence

1. Confirm the canonical repository root and origin, Python 3.12/3.13, pinned
   dependencies, and a valid `.env` without printing its contents.
2. Choose a new run directory and a new database path beneath it. Do not point
   the run at the old `data/apa_tracker.db` until validation has passed.
3. Run `python scraper/full_auto_scrape.py` (or the approved capture flow),
   complete login and consent, and verify that authenticated fixture buckets
   contain teams, schedules, matches, scoresheets, and alias TeamStat data.
4. Validate the fixture manifest: no auth-operation files, no empty entity
   walk, expected operation names, and no credentials in the tree.
5. Run the fixture pipeline with a temporary config whose database and export
   paths point to the run directory. It must ingest teams/rosters/standings/
   schedules, match scores, H2H, TeamStat history, matchups, H2H Advantage,
   and Player Trends in that order.
6. Inspect the schema with `database.engine.check_schema`. The regenerated
   database must contain all model tables and columns, including
   `player_team_history.team_external_id`, before any captain-first build.
7. Run the exporters and captain-first builder against the same database. The
   builder reads it read-only and must not migrate it.
8. Verify row counts, foreign keys, scope identity, evidence reconciliation,
   legality behavior, artifact hashes, workbook readability, and HTML safety.
9. Only after checks pass, copy or promote the run's database/artifacts using
   an explicit operator action. Retain the prior database as a recoverable
   backup; never delete it as part of an automatic demo step.

## Rebuild acceptance checks

- Every model table exists; `check_schema()` returns no missing columns.
- Foreign keys are enabled for every SQLite connection.
- TeamStat current rows key on immutable team ID plus division/session, not name.
- The selected team and every presented opponent are real schedule entities.
- A count of DIRECT/INDIRECT/UNKNOWN equals the feasible pair count by key.
- A complete Lineup Lab result has five assignments and a real 23-rule verdict;
  otherwise the page explains the partial/blocked result.
- No generated path escapes the run output directory.
- The manifest records the source capture and database/artifact hashes.

## Recovery

If authentication, fixture validation, schema checks, or exports fail, discard
only the new run directory after preserving its redacted log. Do not overwrite
the prior database and do not fall back to it for a production presentation.

