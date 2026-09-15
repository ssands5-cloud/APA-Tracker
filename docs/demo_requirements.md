# Production demo requirements

This document is the acceptance contract for a rich, authenticated demo. A
fixture-mode run is useful for CI, but it is not a substitute for the fresh
league snapshot required for a production presentation.

## Required software and environment

- Python 3.12 or 3.13. Python 3.14 is excluded because the documented Windows
  `asyncio.run()` failure breaks the Playwright path.
- A clean install from `requirements-dev.txt`, including SQLAlchemy, pandas,
  openpyxl, PyYAML, pytest, and Playwright; Chromium must be installed for a
  live scrape.
- A repository-local `apa_config.yaml` with the league/team identifiers and
  scratch database/export paths. Secrets do not belong in this file.
- Live mode requires a valid `.env` (`APA_USERNAME`, `APA_PASSWORD`) or a
  supported short-lived access token. The operator must be able to complete
  the guarded consent flow.
- A writable scratch output directory inside the APA Tracker repository, with
  enough space for raw fixtures, SQLite, HTML, JSON, XLSX, and a manifest.

For a full production run, the optional acquisition phase follows
`scrape_and_ingest_pipeline.md`: the operator explicitly selects live mode and
supplies credentials through environment, prompt, browser session, or token
standard input. CI always selects fixture mode and must be network-denied.

## Required data

The database must contain, or explicitly report why it does not contain:

- the configured team and its canonical current roster;
- every real scheduled opponent scope (team ID, format, session, and match);
- current opponent roster membership for each selected scope;
- current skill levels when an INDIRECT probability or a legality calculation
  needs them;
- scored, finalized, non-bye matches and per-game scoresheets for DIRECT
  evidence;
- TeamStat rows carrying immutable `team_external_id`, division, session, and
  `is_current` membership state;
- enough rows to make the displayed trend/career statistics meaningful.

There is no minimum evidence count that may be invented for a “better” demo.
The page must show the real DIRECT/INDIRECT/UNKNOWN mix and the Data Coverage
view must name missing fields. A database created before the
`player_team_history.team_external_id` column is present is a hard blocker, not
a prompt to apply an ad-hoc migration.

## Required artifacts

The run is complete only when the selected output directory contains a manifest
and the requested artifacts that have real source data:

- `captain_first_edge.html` (Tonight's Match, Opponent Risk Profile, Lineup Lab,
  Data Coverage);
- `player_vs_player.html` and `player_vs_player.xlsx` for the unified Player vs
  Player tab's Matrix/Pair data, plus optional script-JSON parity data;
- `analysis_tabs.html` (Captain's Edge/Lineup Optimizer where available,
  Head-to-Head, Player Trends);
- `apa_data.json` and `apa_stats.xlsx`;
- `captains_edge.html`, `captains_edge.json`, and `captains_edge.xlsx`;
- `lineups.json` when the legacy builder has usable rows;
- a regenerated SQLite database and a machine-readable run manifest.

An optional artifact may be absent only when its builder reports a genuine
missing-data condition. The manifest must say why; an empty placeholder file is
not a successful deliverable.

## Safety and evidence requirements

- No raw authenticated response, token, cookie, password, or teammate data is
  copied into a commit, screenshot bundle, or public share.
- HTML is self-contained, offline-openable, and escapes captured names/IDs.
- The demo names the database capture time and source manifest, not “updated
  today” unless a real persisted timestamp supports that statement.
- The walkthrough distinguishes observed rates from modeled probabilities and
  identifies excluded analytics that are not approved captain advice.
- The unified Player vs Player tab restores Pair/Matrix route state, consumes
  only the embedded escaped JSON snapshot, and makes no runtime network call.
- Captain's Edge identifies its Opponent Risk Profile as a build-time snapshot,
  shows availability status, and keeps Avoid/Target flags unavailable unless a
  versioned threshold has passed audit.

## Human acceptance

Before release, a reviewer must be able to select a real scheduled scope,
change player availability, observe evidence counts reconcile, inspect at least
one DIRECT/INDIRECT/UNKNOWN row when the snapshot contains them, view Lineup
Lab unassigned lists, open the unified Player vs Player tab, switch between
Matrix View and Pair View without losing UNKNOWN rows, review the Captain's
Edge Opponent Risk Profile/flag status, and open all requested workbooks without
repair prompts.
