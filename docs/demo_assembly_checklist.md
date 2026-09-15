# Production demo assembly checklist

## Repository and environment

- [ ] Confirm repository root and origin are the canonical APA Tracker values.
- [ ] Confirm no code, test, fixture, `BUILD_INFO`, or separately owned staged
      file is part of the documentation/demo commit.
- [ ] Use Python 3.12 or 3.13 and install the pinned requirements.
- [ ] Install/verify Playwright Chromium for live mode.
- [ ] Verify `.env` exists locally and is excluded from outputs.

## Data regeneration

- [ ] Create a unique scratch run directory and database.
- [ ] Complete authenticated login and Member Services consent.
- [ ] Capture teams, schedules, divisions, scoresheets, and alias TeamStat.
- [ ] Validate fixture manifest and redact/exclude auth operations.
- [ ] Run ingest in dependency order and rebuild matchups, H2H Advantage, and
      Player Trends.
- [ ] Confirm all model columns, especially `team_external_id`, exist.

## Artifact build and verification

- [ ] Build `apa_data.json` and `apa_stats.xlsx`.
- [ ] Build Captain's Edge HTML/JSON/XLSX and optional `lineups.json`.
- [ ] Build `analysis_tabs.html`.
- [ ] Build `captain_first_edge.html` with Stage 3 Lineup Lab/Data Coverage.
- [ ] Build Player vs Player HTML/Excel from one enriched analytics document;
      keep the optional JSON as the parity oracle.
- [ ] Verify UNKNOWN visibility; distinct-match/game-count separation; and
      explicit innings, defense, break/run, and volatility gaps.
- [ ] Confirm self-contained HTML, no external requests, safe escaping, and
      visible provenance.
- [ ] Confirm matrix identity reconciliation and evidence percentages.
- [ ] Confirm Player vs Player HTML/Excel/JSON pair and game parity.
- [ ] Confirm assigned/unassigned reconciliation and legality/blocked reason.
- [ ] Load every workbook with openpyxl without repair prompts.
- [ ] Write and verify the redacted manifest and hashes.

## Rehearsal and release

- [ ] Follow `demo_walkthrough.md` end to end.
- [ ] Capture only approved screenshots and no secrets/raw teammate data.
- [ ] Record commit, capture time, test command, warnings, and Issue #14 link.
- [ ] Package only approved HTML, JSON, XLSX, manifest, and release notes.
- [ ] Retain the previous release for rollback; do not delete it automatically.
