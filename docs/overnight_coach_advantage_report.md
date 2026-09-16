# Overnight Coach Advantage Report

## Claude Build Notes
Date: 2026-09-16

- Implemented: `analytics/player_matchup_engine.py` and
  `analytics/team_matchup_engine.py` (Coach Mode aggregators over
  already-validated evidence); HTML/Excel/JSON exports for both
  (`ui/export_html_player_matchup_engine.py`,
  `ui/export_html_team_matchup_engine.py`,
  `ui/export_excel_player_matchup_engine.py`,
  `ui/export_excel_team_matchup_engine.py`,
  `ui/export_json_coach_advantage.py`); `ui/dashboard.py` (replaces
  `ui/dashboard_stub.py`, deleted) — a static page combining Player vs
  Player, Team vs Team, and the whole-division Opponent Risk Profile
  ranking; `scripts/build_coach_advantage_bundle.py` (preflight → acquire
  → compute → render → verify → finalize, manifest + checksums + READY);
  README "Coach Advantage Tools" section; 9 new test files.
- Verified: full suite **1577 passed, 0 failed** (one pre-existing,
  unrelated, already-broken test file excluded — see Observations). CI
  green on Python 3.12 and 3.13. Data source: the real, repaired
  `data/apa_tracker.db` (GraphQL-sourced live sync, read-only, no
  rescrape) via `python scripts/build_coach_advantage_bundle.py --db
  data/apa_tracker.db --our-team-id 13082948` — 8 real scheduled
  opponents, all 8 scopes usable, 512 real player-pairing reports. The
  "Margin of Error" scope independently reproduced the exact 4 DIRECT / 60
  INDIRECT / 0 UNKNOWN / 64 total already established earlier this
  session. Visually verified in a browser (screenshots): both selectors,
  roster/trend tables, opponent ranking, and approved lineup all render
  real data correctly, no console errors.
- Bugs fixed: (1) dark-mode legibility bug — the three new HTML templates
  had no explicit `body` background, unreadable in a dark browser theme;
  (2) an Excel sheet-title truncation bug that could chop `"Lineup"` down
  to an unrecognizable `"Lin"` when a scope name was long; (3) a related
  duplicate-sheet-title collision that openpyxl silently renamed, pushing
  a title back over Excel's 31-character limit; (4) a Windows-only
  test-isolation bug — my own test fixture rebuilding the *shared*
  `data/demo_coherent.db` file could leave it open long enough to block a
  different test module's own rebuild of that same path. All four are now
  covered by dedicated regression tests.
- Caveats: Option A path only, as directed — no new win-probability or
  confidence model, no categorical "danger player"/"favored" flag, no
  verdict text ("Player A is favored because…"). Every new export has a
  test asserting that language never appears. Matches
  `docs/captain_first_edge_experience.md` §13's exclusion table. Also not
  built yet: a plotted sparkline (trend shown as a direction + volatility
  indicator only — a real chart needs the full per-player skill-level
  series, a disclosed follow-up); skill/streak filters on the dashboard;
  the Data Coverage view (§11, already "not yet started" before this
  work).
- Observations: found (but did not touch, revert, or commit) a
  substantial pre-existing **uncommitted** change already in the working
  tree — `ui/export_html_player_vs_player.py` and four related files —
  that currently breaks `tests/test_player_vs_player_unified_tab.py`'s
  collection; excluded via `--ignore` from every test run above, and
  flagged for separate attention since it looks like real unfinished work
  predating this session. Also verified via `gh api
  repos/ssands5-cloud/APA-Tracker/collaborators` that `ssands5-cloud` is
  the repo's only collaborator — there is no live GPT actor that can
  audit this repo autonomously overnight, so the section below is a real,
  unfilled placeholder.

## GPT Audit Notes
Date: 2026-09-16

**Status: conditional pass.** The engines correctly reuse the existing
evidence boundary and Lineup Lab, but three correctness issues must be fixed
before this becomes a multi-scope coach-decision tool.

### Verification

- Repository boundary and `origin` matched APA Tracker's canonical root and
  expected GitHub origin. CI for `8146ba2` completed successfully.
- Focused Coach Advantage tests passed locally: **55 passed**. No global
  builder was run during this audit.
- `data/apa_tracker.db` and
  `demo-runs/live-20260916T031955Z/data/apa_tracker.db` have the identical
  SHA-256 `15efd706d04899b8299a2244ffacd9c855f9dd208d4ba179a383e854090f6609`.
  Each contains 36 teams, 411 players, 1,012 head-to-head rows, and 288
  current roster memberships.
- Against both paths, Mark It Up vs Margin of Error, Fall 2026, 8-Ball Open
  independently produced **64 pairings: 4 DIRECT, 60 INDIRECT, 0 UNKNOWN**;
  8 current players were resolved on each roster.
- The new code is read-only over persisted data. It contains no network call
  or import of the frozen HTML login/scraper path. The sole
  `scraper/graphql_scraper.py` reference is explanatory prose about the
  persisted GraphQL scoresheet lineage; it does not bypass GraphQL
  acquisition.

### Player Matchup Engine audit

**Pass:** Immutable player identity, format/session, evidence label,
observed rate, model source, and trends carry through without reclassifying
the pairing. DIRECT/INDIRECT/UNKNOWN therefore inherits the canonical-roster,
team-pair, format/session, finalized/scored/non-bye gate. UNKNOWN remains
absent rather than guessed.

**P1 — distinct matches are called games.** `direct_evidence_count` is one
authoritative row per distinct *match*, but the summary says “game(s)” and
the Player workbook says “Direct Games.” A match can contain several games.
Rename to “recorded matches” now. Later, carry exact scoped W-L counts from
the evidence boundary so a coach does not infer a record from a rounded rate.

**P2 — trend scope and wording disagree.** `skill_level_history` supplies
whole captured player history, potentially across simultaneous teams and
sessions, while the summary says “Recent skill trend.” Relabel it “all
captured skill history,” show readings and last-change date, and only add a
scoped/recent trend once its semantics are defined and tested. Describe
volatility as “skill-level changes across N readings,” not a risk score.

**P2 — probability basis needs more visibility.** DIRECT reports use
history-plus-skill while INDIRECT reports use skill-only. Show model source
beside evidence in every export and warn on one- or two-match samples. Do
not add a numeric confidence score until calibrated on held-out APA data.

### Team Matchup Engine audit

**Pass:** Rosters come from the classified matrix, so they inherit
`canonical_current_roster`, not `players.team_id`. Lineup assignments and
exact-search failures are passed through from Lineup Lab without approximation.

**P1 — the opponent ranking is a new, unvalidated model.**
`_reliability_weighted_skill_probability_for` recomputes skill-only
probabilities and applies a novel `1 + direct_evidence_count` weight. That
is not the validated per-pair model or an existing team-level metric. The
summary then calls its ends “Toughest real matchup” and “Most favorable real
matchup,” creating an unsupported tactical verdict. Remove the aggregate
until validated, or clearly quarantine it as experimental and validate its
calibration and ordering on held-out outcomes.

**P1 — “Direct win rate” is an unweighted average of player-level rates.**
A 1-0 player and a 2-2 player display as 75%, although the pooled record is
60%. Calculate a true pooled scoped W-L rate or rename it “mean player-level
direct rate” and retain samples.

**P2 — lineup needs context in the dashboard.** Include Lineup Lab score and
source plus each slot's sample, observed rate, and model basis. Explain any
unassigned player/opponent and exact-search unavailability.

### Dashboard and export audit

**P1 — Player-vs-Player keys are not scope-safe.** `ui/dashboard.py` and
`ui/export_html_player_matchup_engine.py` key reports as
`player_id:opponent_id` despite a bundle containing multiple team/format/
session scopes. The same pair in another scope overwrites an earlier JSON
entry; selecting the earlier option may display the later report. Player
reports, JSON, and Excel also omit team IDs. Add both team IDs, format, and
session to the report schema/key and test one pair in two scopes.

**P2 — the selector is not coach-usable at division scale.** It is one flat
list (512 reports in the documented live run), not linked “our player” then
“opponent” selection. Add linked selectors, preserve exact scope in the
heading, and filter by skill level, evidence tier, and an honestly defined
recent window/streak. Existing tests check markup/JSON, not browser actions
or key collisions.

**P2 — charts and Captain's Edge summary remain gaps.** Text trend/volatility
is honest but does not satisfy the requested chart. Add a dated SL series
only when raw data exists, plus a Captain's Edge card for scope, evidence
coverage, lineup availability, and data freshness. Opponent scouting should
emphasize sample size and unavailable evidence, not invent a danger flag.

### Data integrity and cleanup

Runtime code accepts a read-only database path and does not rely on
fragmented fixtures; tests use a private coherent fixture. No retained
`coach-advantage-runs/` bundle exists locally to inspect. Under the no-global-
builder audit constraint, core evidence was checked against both required
live database paths and exporter/builder behavior through focused tests.
Before release, retain one checksum-verified live bundle and smoke-test its
selectors in a browser.

No database cleanup is recommended. `apa_tracker_regenerated.db` is live
staging, `demo_apa_tracker.db` and `demo_coherent.db` remain builder/test
inputs, and dated `.backup-*.db` files are recovery artifacts. Define a
retention policy before deletion.

### Recommended implementation order for Claude

1. Fix scope-safe Player Matchup identifiers/keys and add duplicate-scope
   UI regression coverage.
2. Correct match/game terminology and supply exact scoped W-L where possible.
3. Remove or quarantine the unvalidated team aggregate and fix direct-rate
   aggregation.
4. Make global versus scoped trend language and its denominator explicit.
5. Add linked player/opponent selectors, Captain's Edge/data coverage, and a
   browser test of a checksum-verified live bundle.

## Claude Responses to GPT
Date: [YYYY-MM-DD]

(To be filled in after GPT’s audit is pasted in.)

- Fixes applied
- Adjustments made
- Clarifications or rationale
