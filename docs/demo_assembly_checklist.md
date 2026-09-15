# Production demo assembly checklist

## Repository and environment

- [ ] Confirm repository root and origin are the canonical APA Tracker values.
- [ ] Confirm no code, test, fixture, `BUILD_INFO`, or separately owned staged
      file is part of the documentation/demo commit.
- [ ] Use Python 3.12 or 3.13 and install the pinned requirements.
- [ ] Install/verify Playwright Chromium for live mode.
- [ ] Verify `.env` exists locally and is excluded from outputs.

## Data regeneration

- [ ] Choose either a verified fresh database or the optional guarded live
      flow in `scrape_and_ingest_pipeline.md`; CI uses fixtures only.
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
- [ ] Call `build_matrix_export` once and build the unified Player vs Player
      tab/Excel from the identical returned rows.
- [ ] Validate escaped `pvp-data` script JSON, Pair/Matrix route restoration,
      and pair-key selection.
- [ ] Verify the HTML delegates each explicit-pair detail to the existing pair
      renderer; keep optional matrix JSON as a parity oracle.
- [ ] Verify UNKNOWN visibility; distinct-match/game-count separation; and
      explicit innings, defense, break/run, and volatility gaps.
- [ ] Confirm self-contained HTML, no external requests, safe escaping, and
      visible provenance.
- [ ] Confirm matrix identity reconciliation and evidence percentages.
- [ ] Confirm Matrix HTML/Excel/JSON pair and game parity.
- [ ] Confirm each embedded explicit-pair detail matches its matrix row.
- [ ] Confirm Captain's Edge Opponent Risk Profile matches the selected pair,
      shows capture/availability state, and contains no Avoid/Target, danger,
      favorable, tier, traffic-light, or equivalent categorical field/style.
- [ ] Confirm any opponent ordering names one visible descriptive source field
      and direction, places missing values last, and uses canonical identity
      tie-breaks without a composite score.
- [ ] Confirm assigned/unassigned reconciliation and legality/blocked reason.
- [ ] Build Team Strength from the exact current roster/session and eligible
      finalized matches; verify all three components, raw denominators,
      fifth-player identity, composite null gate, HTML, and three Excel sheets.
- [ ] Build Trend Analyzer from the already-populated `PlayerTrend` rows and
      chronological observations; verify spans, delivered `trend_score`,
      canonical initial order, history view, and two-sheet workbook parity.
- [ ] Build Opponent Volatility from the exact opponent roster and scoped trend
      rows; verify transform, median inputs, coverage, complete null rows, and
      absence of legacy danger categories.
- [ ] Build one current-skill Match Difficulty cell per matrix pair; verify the
      fixed-bin HTML/text view and both Excel heatmap sheets use identical keys
      and raw values.
- [ ] Build the Live Assistant source/scenario document from reconciled module
      hashes; verify exact scenario selection, offline behavior, unassigned and
      UNKNOWN visibility, and no new blended score.
- [ ] Load every workbook with openpyxl without repair prompts.
- [ ] Run the Full Production Demo Builder in the selected mode and verify no
      component renderer was invoked outside its documented phase.
- [ ] Write and re-read the redacted manifest and checksums, then write READY
      last and verify its manifest hash.
- [ ] Run the Unified Launcher against that exact run; verify argument-array
      forwarding or `--no-build`, loopback-only serving, health-check identity,
      and no presentation before checksum validation.

## Rehearsal and release

- [ ] Follow `demo_walkthrough.md` end to end.
- [ ] Capture only approved screenshots and no secrets/raw teammate data.
- [ ] Record commit, capture time, test command, warnings, and Issue #14 link.
- [ ] Package only approved HTML, JSON, XLSX, manifest, and release notes.
- [ ] Retain the previous release for rollback; do not delete it automatically.
