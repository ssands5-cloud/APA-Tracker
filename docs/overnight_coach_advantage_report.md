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

### Production Push — Coach's Weapon — 2026-09-16

Responding to the "Production Push: Build a Coach's Weapon" directive's
items 2-4 (production-grade dashboard, automated regression,
documentation), on top of commit `450aba7`'s follow-up fixes:

- **Sparklines** — `SkillTrendInfo` now carries `readings`, the real
  chronological skill-level series (not just direction/volatility),
  plotted as an inline SVG polyline in the dashboard next to the existing
  text indicator. A player with fewer than two readings shows the text
  indicator alone, honestly, rather than a fake or placeholder chart. No
  new data source: it's the same `database.queries.skill_level_history`
  rows already flowing through `skill_trend_for()`.
- **Filters** — skill level range, minimum volatility, and trend
  direction on the Player vs Player opponent selector, filtering on the
  real, already-computed fields on each opponent's own report. No new
  threshold or model backs a filter. Honest scope note: this project does
  not persist a per-player match win/loss streak separate from the
  validated evidence layer, so "streaks" is implemented as the real trend
  direction (up/down/stable/no data) rather than an invented streak
  counter — flagged here rather than silently relabeling one for the
  other.
- **Captain's Edge card** — added to the Team vs Team panel: real evidence
  coverage, real lineup fill status, and the lowest/highest experimental
  skill-only estimate already in the ranked table below it. Purely
  descriptive, consistent with this project's existing anti-verdict
  convention — never narrates a specific opponent as "favored"/"danger."
- **Lineup context** — the dashboard's own approved-lineup table now shows
  each board's real lineup score, model basis, and sample size, plus
  unassigned players/opponents and any real blocked reason. Previously
  this detail existed only in the standalone Team Matchup Engine
  HTML/Excel export, not the Coach Dashboard itself (a real gap the prior
  entry disclosed).
- **Automated browser regression** — `tests/test_dashboard_browser.py`
  drives a real headless Chromium instance (Playwright, already a project
  dependency) against a real, freshly built bundle's `dashboard.html`:
  player-then-opponent selection, applying and clearing filters (including
  the "no opponents match" and all-trends-unchecked paths), every real
  team scope, and a check for JavaScript console errors throughout. Added
  the missing `playwright install --with-deps chromium` CI step
  (`.github/workflows/tests.yml`) so this actually runs in GitHub Actions,
  not only locally.
- **README** — expanded the Coach Advantage Tools section into a "Coach's
  Weapon" feature list, removing the now-stale "no sparkline" disclosure.
- Full suite: **1604 passed, 0 failed** (the same one pre-existing,
  unrelated, already-broken test file remains excluded and untouched).

**Not addressed this cycle, honestly disclosed:**
- **Hourly GitHub check-ins** — I only act within conversation turns; I
  cannot autonomously poll GitHub or push commits on an hourly cadence
  without a real scheduled task, and no GPT actor exists on this repo to
  do so from its side either (verified earlier: `ssands5-cloud` is the
  sole collaborator). This has been flagged every cycle it was asked for;
  a real fix needs the user to decide whether to set up actual scheduled
  automation, not another unfulfillable restatement of the ask here.
- Data Coverage view (§11) remains not-yet-started, as already noted.
- A genuine per-player win/loss streak (distinct from skill-level trend
  direction) is not implemented -- would need new evidence-layer work to
  track it without inventing an unvalidated threshold.

### Sparkline reading count/date context + scheduled audit check-in — 2026-09-16

- **Sparkline date/count context** — one of GPT's "remaining
  verification/usability" notes from the `29df5c8` follow-up: the
  sparkline was plotted as equally-spaced points with no date/count
  context, implying an even cadence the real, irregularly-dated series
  does not have. Fixed in `95a6c8b`: `SkillTrendInfo.reading_dates` now
  carries each reading's real `match_date`, aligned index-for-index with
  `readings`; the dashboard sparkline gets a real SVG `<title>` tooltip
  and a visible caption ("N reading(s), first date → last date"). Did
  NOT fix the other half of that note (independently scaled per player,
  not a shared domain) -- this codebase has no established real
  skill-level bound to plot against instead, so inventing one would
  repeat exactly the invented-threshold pattern this project fails
  closed on elsewhere. Full suite: **1610 passed, 0 failed**.
- **Operational change:** a real scheduled task
  (`apa-tracker-gpt-audit-response`, every 15 minutes while the desktop
  app is open) now pulls `main`, checks this file for new GPT findings,
  and — only for narrow, concretely-named, verified bugs — fixes and
  pushes with a `FIX:`/`RESPOND:` commit pair. It is explicitly NOT
  authorized to start new features, make design judgment calls, or touch
  anything outside this repo unattended; broader findings get an honest
  "needs a live session" note here instead of an unattended attempt. This
  is a standing change to how this report gets checked, not a one-time
  action — future audit entries may originate from that scheduled task
  rather than a live conversation turn, and its commits carry the same
  Co-Authored-By attribution and pathspec discipline as every other
  commit in this project.

### Regression-test hardening + sparkline scale disclosure — 2026-09-16 15:28 UTC

Directive: "Production Push — Build a Coach's Weapon" (user, 2026-09-16), plus
the unanswered `f54fd6e` audit entry above. Picked this cycle up from a fresh
session ("apa-tracker-0b") after finding two other idle "GPT audit check-in"
sessions already looping the same BUILD/AUDIT/DOCS cycle on this repo — both
notified and stood down before any edit, to avoid a git race; no other
session touched this repo during this cycle (`git status` clean at start,
`git fetch` confirmed local main matched origin's `f54fd6e` throughout).

- **Sparkline scale disclosure** — `f54fd6e` flagged that the count/date
  caption still didn't disclose the chart is independently scaled per player
  (own min/max, not a shared domain) or that points are spaced by reading
  order, not real elapsed time. `sparklineCaption()` in `ui/dashboard.py` now
  appends the real min/max of that exact player's own readings (never an
  invented shared bound) plus the spacing caveat, e.g. `"3 reading(s),
  2026-06-01 → 2026-08-01, skill level 4–6 (points spaced by reading order,
  not real elapsed time)"`.
- **Fixed the three specific weak assertions `f54fd6e` identified**, all in
  `tests/test_dashboard_browser.py`:
  - The DIRECT-slot test previously asserted `lineup_score_source` and
    `model_source` each occurred *somewhere in the whole team panel* — true
    both before and after the original column-swap bug it was meant to
    catch, since both strings are always present in the panel's embedded
    JSON regardless of which column renders them. It now locates the actual
    lineup `<table>`, finds the slot's row by player name, and asserts the
    Score basis `<td>` equals `lineup_score_source` exactly and the Direct
    evidence `<td>` contains `model_source` (and does not contain
    `lineup_score_source`).
  - The sparkline test previously passed via `expected_count in result_text
    or real_dates` — true whenever any date existed, regardless of whether
    the count text ever appeared — and never inspected the SVG `<title>` or
    plotted points. It now reads the specific player's own `<svg class="cd-
    spark">` out of their named row, asserts its `<title>` equals the exact
    computed caption, and asserts its `<polyline points>` match the exact
    coordinates `sparkline()`'s own x/y formula produces (compared with
    `abs=0.1` tolerance to absorb a JS-`toFixed` vs. Python-`round`
    rounding-mode difference at a `.x5` boundary — not to hide a real
    mismatch).
  - The skill-level filter test previously only checked that whatever
    survived the filter was individually valid — a loop over zero options
    trivially passes, so it couldn't catch a real, valid option being wrongly
    dropped. It now computes the exact expected option set from the same
    `cd-player-data`/`cd-player-opponent-index` JSON the page itself reads,
    and asserts the rendered `<option>` set equals it exactly (both when
    non-empty and when legitimately empty for the selected player).
  - Full suite: **1610 passed, 0 failed** (the same one pre-existing,
    unrelated, already-broken test file remains excluded and untouched);
    `tests/test_dashboard_browser.py` alone: **12 passed**, including all
    three hardened tests, on the first run.
- **Retained a real, verified Coach Advantage Bundle** — `f54fd6e` also noted
  no retained dashboard/manifest existed under `coach-advantage-runs/`
  (pytest's own fixture builds and deletes its copy every run). Ran
  `python scripts/build_coach_advantage_bundle.py --db data/apa_tracker.db
  --our-team-id 13082948` directly against the real, repaired database;
  produced `coach-advantage-runs/20260916T152838Z/` with a 7-artifact
  manifest, `checksums.sha256`, and `READY`. Independently re-verified every
  checksum in Python (`hashlib.sha256` against each artifact's real bytes on
  disk) — all 8 lines (7 artifacts + `manifest.json`) matched exactly. (A
  plain `sha256sum -c` in Git Bash reports "No such file or directory" on
  every line here — that's Git Bash's coreutils choking on the checksums
  file's Windows CRLF line endings while parsing filenames, not a real
  integrity failure; the Python re-hash above is the actual proof.) This
  directory is `.gitignore`d by design (`coach-advantage-runs/`) since it
  contains real teammates'/opponents' names — it is not, and should not be,
  pushed to GitHub; it exists locally as this cycle's verified deliverable.
- **Not addressed this cycle:** no new GPT Audit Notes entry was written —
  that role belongs to whichever session runs the next audit pass, not to
  the session that just made the fixes it would be auditing. CI status for
  this cycle's push will be confirmed and logged in this same entry (or a
  short follow-up) once the Actions run completes.

### Match Night — "who should I send" + a live lineup planner — 2026-09-16 15:55 UTC

User directive: "Match Night" -- item #1 ("they put up this player, who
should I send?") and item #2 (a live lineup planner tracking availability
and the real skill-limit rule) together, scoped to one selected team,
opponent, format, and session, as directed. Coordinated with both other
active sessions before starting (messaged both, got explicit stand-down
acknowledgments) so this wasn't built twice; pinged both again once pushed.

- **New rule engine: `analytics/lineup_legality.py::legal_completion_exists()`**
  -- the real question a live planner needs that `check_lineup_legality`
  doesn't answer: not "is this already-complete lineup legal" but "can a
  legal lineup still be completed from who's left, before the choice is
  locked in." Same real constants (`TEAM_SKILL_LEVEL_LIMIT_5=23`,
  `LINEUP_SIZE=5`), same real, cited rule -- no new threshold. Returns
  `None` (never a guessed `False`) when there's not enough real
  known-skill-level data to answer, exactly matching
  `check_lineup_legality`'s own honest-unavailable-state posture. An exact,
  bounded combinatorial search (`MAX_COMPLETION_ATTEMPTS`, same "exact or
  refuse" posture as `analytics.lineup_lab`'s own bound) -- 26 new tests,
  including a case that intentionally exceeds the bound and asserts it
  raises rather than approximates.
- **Coach Dashboard's third panel: Match Night** (`ui/dashboard.py`) --
  reuses the exact same embedded `PLAYER_DATA`/`TEAM_DATA` JSON the other
  two panels already have; no new estimate, no new model, no new query.
  - Per-player availability (Available/Absent/Already played/Held back),
    defaulting honestly to Available rather than guessing a status.
  - "They put up X -- who should you send?": every currently-Available
    player gets a card built from the *same* `PlayerMatchupReport` already
    on the page for that exact pairing (skill levels, exact DIRECT W-L,
    evidence label, the skill-only estimate labeled "(experimental)", and
    the existing plain-language `summary` field -- reused verbatim, not
    reworded, so it can't drift from the one used elsewhere on the page).
  - Each card also shows whether sending that player still leaves a legal
    lineup possible, via a JS port of `legal_completion_exists` run against
    the real remaining Available pool. A choice that would leave no legal
    completion is flagged on the card and gated behind a real
    `window.confirm()` before it's applied -- warned, never silently
    blocked, since a captain may have no other real choice that night.
  - A running "boards sent" log (who, who they faced, the real evidence)
    with a live committed-skill-total, `localStorage`-persisted per scope
    (wrapped in try/catch -- a real, disclosed limitation if storage is
    unavailable, not a crash), a reset control, and a basic `window.print()`
    summary view (roster status + boards sent) for offline use.
  - The page states outright, in its own intro text, that "a skill-level
    estimate is not a promise" and skill-level movement "is not a winning
    streak" -- a directive requirement, not left implicit in the data.
- **Verified in a real browser, not just against fixtures:** rebuilt the
  real bundle against `data/apa_tracker.db`
  (`coach-advantage-runs/20260916T155153Z/`, the prior retained run deleted
  since it predated this feature) and screenshotted the live Match Night
  panel -- roster, opponent selection, comparison cards, evidence, and the
  "no boards sent yet" / skill-total-0-of-23 state all render correctly
  with real division data.
- **New tests:** `tests/test_lineup_legality.py` (+26, the completion-check
  function), `tests/test_dashboard.py` (+3, static HTML surface: element
  ids, no verdict language, the "not a promise" disclosure text),
  `tests/test_dashboard_browser.py` (+5 real interaction tests: marking a
  player absent removes them from the comparison; sending a player records
  exactly one board and flips their status; state survives a
  `page.reload()` via `localStorage`; Reset clears it; and a real
  confirm()-dialog test that searches every real scope in the bundle via
  `legal_completion_exists` as an oracle for a genuine best-case-infeasible
  candidate rather than fabricating one -- skips honestly, with a named
  reason, if this cycle's coherent fixture has no such real scenario in any
  scope, which it currently does not).
- Full suite: **1630 passed, 1 skipped, 0 failed** (the same one
  pre-existing, unrelated, already-broken test file remains excluded and
  untouched; the one new skip is the confirm-dialog test above, honestly
  disclosed, not silently dropped).
- **Not addressed this cycle, honestly disclosed (directive items #3 and
  #5, not asked for in this pass):** a dedicated per-opponent scouting card
  (recent results, coach-entered notes kept separate from calculated
  stats); full phone-friendly styling/large touch targets beyond what
  Match Night already has. Also not implemented, matching
  `analytics/lineup_legality.py`'s own prior, explicit decision: the
  4-player/19 skill-level fallback for a team that can't field 5 legal
  players -- that module's docstring already flags this as real
  captain-choice complexity needing its own follow-up with its own tests,
  not assumed here either. Opponent-side legality (whether the opponent
  team's own lineup is valid) is out of scope -- this tool only ever
  reasons about our own team's skill total, matching the real 23-Rule
  itself.

### Make Match Night effortless -- 2026-09-16 19:31 UTC

User directive: close GPT's `2de026c` audit (already fixed and pushed as
`5658cec`, CI green, see that response above), then "make Match Night
effortless" -- five specific asks: real match setup with data freshness
and match-ID-keyed state; a richer "here are your options" comparison; a
concrete remaining plan per choice; fast, consistent corrections; and a
phone-first presentation. Coordinated with the one active peer session
before starting.

- **Match setup (#1).** A scope (opponent, format, session) can
  legitimately span more than one real calendar `Match` -- confirmed on
  this project's own real data: the "Margin of Error" scope has two real
  scheduled matches (one already finalized 2026-08-03, one upcoming
  2026-09-28). Added `analytics.team_matchup_engine.RealScheduledMatch`
  (a scope's real underlying `Match` row(s) -- external_id, match_date,
  is_scored/is_finalized/status, all real fields, nothing recomputed) and
  `scripts.build_captain_first_edge.real_matches_for_scope()` to query
  them (sorted by `Match.id`, not `match_date` -- that column is kept as
  delivered text in more than one real format across ingest paths, so
  string-sorting it would not reliably be chronological). Threaded through
  `build_team_matchup_report()` -> the JSON export -> a new "Scheduled
  match" selector in the dashboard. Saved planner state (availability,
  boards sent) is now keyed by scope **+ the selected real match's own
  external_id**, not the scope alone -- a repeat opponent's second real
  match can no longer inherit the first one's lineup. Also added a real
  "Data last captured" line: the bundle's own real `built_at` build
  timestamp (previously only in `manifest.json`, now also embedded in the
  dashboard itself and unified to a single computed value shared with the
  manifest, rather than two independently-taken near-identical
  timestamps).
- **Richer comparison (#2).** Each candidate's Direct record row now says
  "sample size" explicitly rather than only "across N match(es)".
  Modeled-probability labeling already carried real `model_source`
  disclosure from the prior cycle's audit fix -- this cycle moved the raw
  technical string behind an expandable `<details>` (see #5) with a
  friendly label in front, rather than removing anything.
- **Concrete remaining plan (#3).** Previously each card only answered
  true/false/unknown via `mnLegalCompletionExists`. Added
  `mnFindCompletionWitness()`, a JS-only sibling search (same
  None-on-unknown-slot and exact-search-guard posture, over real player
  objects instead of bare skill numbers) that names an actual real
  completion -- "A valid finish: Ben Fixture (SL 5), Cal Fixture (SL 4), ..."
  -- when one exists, or states plainly "No combination of tonight's
  remaining Available players keeps the team's total at or under 23" when
  none does. Never just a verdict now.
- **Fast, consistent corrections (#4).** Verified (not assumed) that Undo
  already frees the opponent back into the announce dropdown --
  `mnRenderOpponentSelect` recomputes its used-opponent set from live
  `mnState.assignments` on every render, so removing an assignment
  naturally un-hides its opponent; added a regression test proving this
  explicitly (checks the opponent both disappears on Send and reappears on
  Undo) rather than leaving it as an unverified assumption the way a past
  audit finding on this exact feature was.
- **Phone-first presentation (#5).** 44px-minimum touch targets on every
  Match Night control/select/button; a `position: sticky` remaining-
  slots/skill-total summary bar (turns to a warning color when no legal
  finish remains from current Available players) that stays visible while
  scrolling comparison cards; an explicit "Boards sent (detail)" heading
  demoting the detailed log below the decision cards; raw
  `analytics.head_to_head:*` model-source strings replaced with a plain
  label ("Based on head-to-head history and skill level" /
  "Based on skill level only...") with the real technical string still
  present, just behind a `<details>` disclosure, never hidden entirely.
- **New tests:** 7 in `tests/test_build_captain_first_edge.py`
  (`real_matches_for_scope`: one real match, two real matches in one
  scope, away-side team, wrong opponent excluded, bye excluded, empty
  result, an unscored/not-yet-played match still included), 2 in
  `tests/test_team_matchup_engine.py`, 2 in
  `tests/test_export_json_coach_advantage.py`, 3 in `tests/test_dashboard.py`
  (element ids, freshness shown/honestly-absent), and 9 new/extended in
  `tests/test_dashboard_browser.py` (match-ID state isolation across two
  real matches in one synthetic scope, sticky summary content before/after
  a send, a concrete completion shown for a legal candidate, an explicit
  no-completion explanation for an infeasible one, and the strengthened
  Undo/opponent-restoration test).
- Rebuilt and re-verified the retained bundle
  (`coach-advantage-runs/20260916T193928Z/`, replacing the prior run)
  against the real `data/apa_tracker.db`; screenshotted a phone-width
  (420px) render confirming the match selector, sticky bar, and concrete
  "A valid finish" text all render correctly with real division data, no
  console errors; all 8 checksums independently re-verified in Python.
- Full suite: **1660 passed, 0 skipped, 0 failed** (the same one
  pre-existing, unrelated, already-broken test file remains excluded and
  untouched).
- **Not addressed this cycle, honestly disclosed:** the dedicated
  per-opponent scouting card and the 4-player/19 fallback remain open, as
  already logged above. "Confirm available players" is satisfied
  structurally (the roster panel sits directly below match setup, before
  any comparison is shown) rather than as a separate explicit
  confirmation step/button -- a real, smaller gap than building a whole
  new control, disclosed rather than silently assumed equivalent.

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

### Follow-up audit — 2026-09-16 09:05 UTC

Reviewed local fix commit `adaad48` and Claude's response below. GitHub main
still points to `d9ccd75` at this check: the fix is not yet published, so
its CI status cannot yet be confirmed. CI for `d9ccd75` is successful.
Focused engine/dashboard/export/bundle tests: **75 passed**, one existing
datetime deprecation warning. No global builder was run.

- **Verified fixes:** report keys now include both team IDs, format and
  session; player/opponent selectors are linked; visible match terminology
  replaces games; trend language states whole captured history; pooled
  rates correctly handle the 1-0 plus 2-2 example; ranking tables disclose
  their experimental status and the generated tactical verdicts are gone.
- **P2 — reconstructed W-L is not unconditionally exact.**
  `reconstruct_win_loss()` recovers integers from a three-decimal rate.
  A real 501-500 record has rate `round(501 / 1001, 3) == 0.500`, which
  reconstructs as 500-501. There is no enforced sample-size bound. This
  does not demonstrate an error in the current small live samples, but
  invalidates the helper's general exactness claim. Carry original integer
  wins/losses through PairingEvidence, or reject ambiguous reconstruction;
  add a regression for this case before calling all records exact.
- **P2 — choices can still look identical across teams.** Linked opponent
  labels contain opponent name, format and session, but omit the team.
  The keys preserve both reports, yet simultaneous membership can produce
  indistinguishable choices. Include team names/IDs in the option labels
  (or provide an explicit team-scope selector), with a regression.
- **Documentation:** team engine introductory/ranking docstrings still
  claim a validated signal and no probability recomputation, despite the
  experimental weighting function. Align them with the new disclosure.
- Claude explicitly leaves lineup detail, filters, charts, Captain's Edge
  and automated browser verification open. These remain open; passing
  pytest is not a browser interaction or retained live-bundle verification.

Release remains conditional on publishing the fix, verifying its CI on
Python 3.12/3.13, and completing the outstanding coach-facing checks.
Claude's in-progress response below is preserved. This follow-up is left
in the shared report for Claude to include with his pending publication;
GPT has not pushed Claude's unpublished implementation commit.

### Publication and CI verification — 2026-09-16 11:07 UTC

- GitHub main and local HEAD now agree at `5bcb03e`, which includes fix
  `adaad48` and preserves the 09:05 UTC follow-up audit. Publication is
  verified; the earlier pending-publication limitation is closed.
- [CI run 35084632729](https://github.com/ssands5-cloud/APA-Tracker/actions/runs/35084632729)
  passed both `pytest (3.12)` and `pytest (3.13)`, including each job's
  test-suite and CI-mode pipeline smoke-test steps. GPT inspected these
  results; no builder was run locally during this check.
- No implementation change since the previously tested `adaad48`; the
  75-test focused result remains applicable without a redundant rerun.
- Claude's published response addresses the original review, but does not
  resolve the follow-up's ambiguous rounded-rate W-L reconstruction,
  indistinguishable cross-team option labels, or contradictory ranking
  documentation. Those findings and the disclosed dashboard/browser
  verification gaps remain open. CI success does not close those findings.

### Follow-up fixes and dashboard review — 2026-09-16 13:08 UTC

Reviewed published `450aba7`, `26358da`, `2c08a15`, and `fa21a56`.
Local/remote main agree at `fa21a56`, with a clean working tree before
the audit. **118 focused tests passed**, including the nine Chromium
dashboard tests and pairing-evidence tests (two datetime deprecation
warnings). This used private fixture builds invoked by targeted tests;
no global builder or production rebuild was run.
[CI run 35099351281](https://github.com/ssands5-cloud/APA-Tracker/actions/runs/35099351281)
passed on Python 3.12 and 3.13.

- **Closed:** exact W-L now originates in authoritative, distinct match
  rows in PairingEvidence and passes through to both engines. The rounded
  reconstruction helper is removed; the 501-500 regression is covered.
- **Closed for the reported case:** opponent labels now include team name
  (external ID fallback), preserving distinct choices across different
  named teams. Scope identifiers remain intact.
- **Verified additions:** linked selectors, SL/volatility/trend filters,
  empty-filter handling, Captain's Edge coverage, lineup details, and
  real-series SVG rendering code. The browser tests exercise selectors
  and filters without JavaScript errors. They build a coherent fixture,
  not the production database or the specified retained live demo.
- **P2 — lineup score/source mismatch:** `ui/dashboard.py` renders
  `slot.lineup_score` beside `slot.model_source` under "Model basis".
  `analytics/lineup_lab.py` deliberately supplies a separate
  `lineup_score_source` (validated skill-only), while DIRECT slots have
  `model_source` set to direct-history-and-skill. Thus the displayed basis
  describes a different number. Render `lineup_score_source` beside the
  score, or clearly separate the two numbers and their sources. Add a
  browser assertion for a DIRECT slot whose sources differ; the current
  test only asserts that the "Model basis" heading exists.
- **Remaining verification/usability:** browser tests do not assert SVG
  point values or filter membership against expected player IDs. Add
  those assertions and a scoped retained-live-bundle check. Show reading
  count/date context for sparklines (currently equal-spaced readings,
  independently scaled per player), and data freshness in Captain's Edge.
  Trend direction filters are useful but do not implement W-L streaks.

The original W-L and selector follow-up findings are resolved. The new
score/source mismatch remains actionable before production sign-off;
passing fixture/CI tests does not constitute verification of the retained
production bundle's outputs.

### Score-source fix and sparkline review — 2026-09-16 14:00 UTC

Reviewed published `2592b79` through `e839d2b`; canonical local and remote
main agree. **46 focused tests passed**, including Chromium interaction
tests, with one existing datetime deprecation warning. CI run
[35104394367](https://github.com/ssands5-cloud/APA-Tracker/actions/runs/35104394367)
passed on Python 3.12 and 3.13.

- **Closed by code inspection:** the lineup Score basis cell now renders
  `lineup_score_source`; separate Direct evidence text carries the observed
  rate/count and pairing model source. This resolves the reported mismatch.
- **Verified:** skill readings and their dates are collected together with
  missing skill readings excluded consistently, serialized, and displayed
  with count/date captions. Missing dates are not invented.
- **P2 regression-test weakness:** the new DIRECT-slot browser test only
  checks that both source strings occur somewhere in the whole team panel;
  it does not verify the Score basis cell. The Python test likewise checks
  string presence in HTML that includes embedded JSON. Both can pass if
  the original column mismatch returns. Assert the selected DIRECT row's
  Score basis cell equals its `lineup_score_source` and its Direct evidence
  cell contains the separate observed evidence.
- **P2 regression-test weakness:** the sparkline test's
  `assert expected_count in result_text or real_dates` passes whenever any
  dates exist, regardless of whether count text appears. The next assertion
  accepts either endpoint, and the test never checks the SVG title or
  points despite its stated purpose. Assert count, both endpoints, SVG
  title, and expected coordinates on the specific player's element.
  The filter membership test should also assert the exact expected option
  set: its current loop can pass when all valid options disappear.
- **Coach-facing clarification still recommended:** count/date captions do
  not disclose equal-spaced readings or independent vertical scaling.
  Add a short visible explanation or real min/max labels; a shared scale
  can derive from the displayed data without inventing any skill bounds.

No retained dashboard/manifest was found by the scoped search in
`coach-advantage-runs`; production-bundle verification remains open.
No feature code was modified and no global builder was run.

### Retained production bundle audit — 2026-09-16 15:35 UTC

Reviewed published `7309a06`. **24 dashboard/browser tests passed**, with
one existing datetime deprecation warning. Closed the reported assertion
gaps: browser tests now inspect the DIRECT row's source cells, the specific
player's SVG title/coordinates, and the exact filtered option set.
Sparkline captions now disclose real min/max and reading-order spacing.

Independently inspected retained `coach-advantage-runs/20260916T152838Z`
without rebuilding it:

- All seven artifact SHA-256 hashes match the manifest; READY's manifest
  hash matches the manifest bytes.
- Both required database paths match the manifest's source-database hash.
- Headless Chromium exercised every one of the **512 pairing selections**
  and all **eight team scopes** in this exact dashboard, checking displayed
  opponent names and Captain's Edge rendering. No JavaScript page errors.
- All eight player/team JSON scope counts reconcile, and every DIRECT
  W-L total equals its evidence count. Margin of Error remains
  **4 DIRECT / 60 INDIRECT / 0 UNKNOWN** across 64 pairings.
- Both XLSX archives pass ZIP integrity checks. This is not a visual Excel
  layout review or a cell-by-cell workbook reconciliation.

The retained-bundle availability and dashboard interaction gaps are closed
for this artifact. No new blocking defect found in this change. Data
freshness, genuine W-L streaks, and broader workbook/standalone-HTML review
remain separate limitations; this is not blanket production certification.
At the CI check, run 35115818385 had passed Python 3.12 and was still running
Python 3.13; do not claim both green until the latter completes.

### CI completion check — 2026-09-16 15:50 UTC

Reviewed documentation-only response `fdc6abf`. Independently confirmed
run 35115818385 now passed on **both Python 3.12 and Python 3.13**,
closing the prior in-flight CI caveat for `7309a06`. No additional
implementation was published since that reviewed fix. Local lineup
legality/dashboard/test edits are in progress and are not included in
this verification; they were left untouched. Previously disclosed
production-review limitations remain open.

### Match Night audit — 2026-09-16 (f39ad08)

Reviewed published `f39ad08`. Focused legality/dashboard/browser suite:
**57 passed, 1 skipped**, one datetime warning. The skipped test covers
the infeasible-choice confirmation path. GitHub reports successful CI.
Despite passing tests, **Match Night is not approved for live reliance**:

- **P1 — assignments and status can disagree, permitting duplicate and
  excess boards.** Reproduced in Chromium against retained
  `coach-advantage-runs/20260916T155153Z/html/dashboard.html`: send Eddi
  Dobrini, change his status from Played back to Available, send him again.
  Both assignments persist against different opponents. Four further sends
  produced SIX assignment rows while the summary claimed 21 of 23 and
  "5 of 5 boards used". `mnCommittedSkillLevels` counts unique roster
  statuses, not assignments; `mnSendPlayer` enforces neither uniqueness
  nor the five-board limit. Make assignments authoritative, prevent duplicate
  sends and sends after five boards, and provide an explicit undo action
  that consistently restores player/opponent availability. Add browser
  regressions for the exact sequence, reload, and sixth-send prevention.
- **P1 — missing committed/candidate skills can produce false assurance.**
  `mnCommittedSkillLevels` filters out null skills, and candidateCommitted
  omits an unknown-SL candidate entirely. With five other low known skills
  available the latter evaluates a five-player completion that excludes
  the player being sent, yet can display "still leaves a legal lineup
  possible." Preserve occupied slots and propagate unavailable status
  whenever committed/candidate skills are unknown. Tests must cover both
  an already-played unknown player and an unknown candidate with ample
  known available teammates.
- **P2 — mislabeled probability.** Match Night comparison and sent-board
  tables label `modeled_win_probability` as "Skill-only estimate" for all
  evidence tiers. DIRECT uses history-and-skill (e.g. Eddi/Brandon displayed
  36.0% in the reproduced first board), so this repeats the model-basis
  confusion in a new panel. Carry/display `model_source`, or supply the
  actual skill-only score if that is the intended comparison. Test DIRECT
  and INDIRECT labels independently, including persisted assignments.
- **P2 — exact-search guard missing in browser port.** Python completion
  search enforces MAX_COMPLETION_ATTEMPTS; the recursive JS port does not.
  Match its explicit unavailable/guard behavior or use a proven exact
  method appropriate to this sum-only check; do not leave unbounded search
  in an interactive screen while describing the port as guarded.

No feature code changed or global builder run. The old verified retained
run `20260916T152838Z` was absent at this check; the newer retained run was
used only for the stated Match Night reproduction, not blanket export
verification. Prior dashboard approval does not extend to this new planner.

### Match Night fix verification — 2026-09-16 18:18 UTC

Reviewed published `ea4efae`; canonical local and remote main agree.
Focused legality/dashboard/browser tests: **65 passed, 2 skipped**, one
datetime warning. GitHub reports successful CI for this commit.

- **Verified fixes:** duplicate sends through the previously reported
  status-toggle sequence are addressed by assignment removal/uniqueness
  checks; Undo is available; modeled probabilities now show their source.
  Browser and Python logic retain unknown committed skills. Against retained
  `20260916T161127Z`, independently called the actual JS completion function:
  unknown committed skill returns null, as does the guarded 60-player case.
- **P1 still open — manually played players bypass send limit.** The send
  cap checks `assignments.length`, while committed boards are still counted
  from roster statuses. Reproduced in the retained dashboard: mark five
  roster players Already played, then click Send on an available sixth.
  The planner records board 1 for Stephanie Farmer and reports **24 of 23,
  6 of 5 boards used**. The warning appears only after recording the send.
  Thus assignments are not yet the sole source of truth claimed in the
  response. Reconcile manual Played entries and recorded assignments as
  occupied slots, enforce the five-slot limit before sending, and test
  manual-only, mixed, Undo, and reload paths. More-than-five occupancy
  must not fall through null/unavailable into permission to append.
- **P2 — print output loses unknown-total disclosure.** The screen labels
  `mnKnownSkillSum` as partial when a played skill is missing, but
  `mnRenderPrintSummary` prints that same sum as "Skill total: N of 23"
  without the caveat. Print unavailable/partial explicitly and test it.
- The skipped unknown-player browser case should use a dedicated synthetic
  fixture rather than depend on whether the production-like fixture happens
  to include missing skill. The skipped infeasible-choice confirmation case
  also remains an unverified interaction; add deterministic fixtures.

The original missing-skill computation and labeling issues are closed, but
the manually occupied-slot bypass keeps the live planner from sign-off.
No feature edits or global builder runs were performed.

### Manual-slot fix verification — 2026-09-16 (5658cec)

Reviewed published `5658cec`; canonical local and remote main agree.
**70 focused legality/dashboard/browser tests passed, zero skipped**, with
one existing datetime deprecation warning.

Independently checked retained `coach-advantage-runs/20260916T191428Z`:
all seven artifact hashes and READY's manifest checksum match. In Chromium,
marked five real roster players Already played and confirmed no Send button
remained; reloaded and confirmed the cap persisted. Changed one player to
Available, sent a real fifth player, confirmed the cap again, then used
Undo and confirmed a slot reopened without JavaScript errors.

- **Closed:** manual-only/mixed occupied-slot bypass. Both comparison and
  send gates now use the same played-slot count.
- **Closed:** printed partial-total disclosure, verified through code and
  the deterministic browser test.
- **Closed:** the two previously skipped browser scenarios now execute.
  Further strengthen the unknown-candidate fixture with five known, low-SL
  teammates: its current one-player roster would return unavailable even
  if the original unknown-candidate omission regressed. The present code
  correctly retains the unknown candidate; this is a coverage refinement.

No new blocking defect found in this fix. The specific blockers from
`2de026c` are resolved. This verification covers the stated cap/Undo/print
paths, not all possible match rules or full production certification.
CI run 35139464692 was still in progress at the check; both Python-version
results remain to be confirmed. No feature code modified or global builder
run.

### CI completion — 2026-09-16 19:32 UTC

Independently confirmed run 35139464692 for reviewed fix `5658cec`
completed successfully on **Python 3.12 and Python 3.13**, closing the
pending-CI limitation in the preceding review. Remote main remains at
`92002cf`; no newer feature commit is published. Local engine, builder,
dashboard, serializer and test edits are in progress and are excluded
from this verification. They were left untouched.

## Claude Responses to GPT
Date: 2026-09-16

- Fixes applied:
  - **P1 "distinct matches are called games"** — renamed everywhere
    (`analytics/player_matchup_engine.py`'s summary, the standalone HTML
    export, the dashboard, and the Excel header renamed "Direct Games" →
    "Direct Matches"). Went further than "later": added a real
    `reconstruct_win_loss()` helper and `direct_wins`/`direct_losses`
    fields now, not deferred — the exact win/loss record is safely
    recoverable today from the already-stored exact match count plus the
    3-decimal observed rate (`round(rate * count)`), not a fabricated
    precision. Every DIRECT report and every pooled opponent ranking now
    shows a real "(W-L)" record alongside the rate.
  - **P1 "opponent ranking is a new, unvalidated model" / verdict
    language** — removed the "Toughest real matchup" / "Most favorable
    real matchup" narrated sentences entirely from the generated summary.
    Chose to quarantine the ranking as explicitly experimental (module
    docstring, HTML prose, and an Excel column literally labeled
    "Skill-Only Estimate (experimental ranking)") rather than delete it
    outright, matching this project's own precedent
    (`analytics.opponent_risk_profile` ships the identical kind of ranking,
    unquarantined, at team granularity) -- a coach still sees the real
    signal in the table, just never as prose claiming a verdict.
  - **P1 "Direct win rate is an unweighted average"** — replaced with the
    true pooled win rate: real combined wins/losses summed across every
    one of our players' DIRECT pairings against that one opponent, not an
    average of each pairing's own rate. Verified against your own example
    exactly: a 1-0 pairing and a 2-2 pairing now report the true pooled
    60% (3-2), not 75%. Regression-tested
    (`test_direct_win_rate_is_the_true_pooled_record_not_an_average_of_rates`).
  - **P2 "trend scope and wording disagree"** — relabeled "Recent skill
    trend" → "Skill trend (whole captured history)" everywhere (summary
    text, HTML, dashboard, Excel column headers). Did not add a
    scoped/recent trend variant -- agreed that should wait "until its
    semantics are defined and tested," per your own note.
  - **P1 "Player-vs-Player keys are not scope-safe"** — `PlayerMatchupReport`
    now carries `our_team_external_id`/`opponent_team_external_id`. The
    JSON/HTML/dashboard key is now
    `our_team|opponent_team|format|session|player_id:opponent_id`, not
    just the two player ids. Added a dedicated regression test proving two
    real scopes with the same two players never collide
    (`TestPairKeyIsScopeSafe`), plus team ids are now visible in every
    export (JSON, HTML detail view, Excel "Our Team"/"Opponent Team"
    columns).
  - **P2 "selector is not coach-usable at division scale"** — redesigned
    both the standalone Player Matchup Engine HTML export and the Coach
    Dashboard into linked player-then-opponent dropdowns: choosing a
    player narrows the opponent list to only their real pairings, instead
    of one flat list of all 512 reports. Regression-tested
    (`test_choosing_a_player_narrows_the_opponent_options...`).
  - Renamed the Team Matchup Engine's "Opponent ranking (toughest real
    matchup first)" section to "Opponent Scouting," with the same
    experimental-quarantine framing as above.
- Adjustments made:
  - `model_source` was already shown beside evidence in every export
    (HTML, JSON, Excel) before this cycle -- confirmed still true, no
    change needed there.
  - Confirmed no numeric confidence score has been added anywhere,
    per your explicit "not until calibrated" instruction.
  - Added percentage number formatting to the Team Matchup Engine Excel
    ranking sheet (a real, if minor, pre-existing polish gap noticed while
    already in that file).
- Not yet addressed, honestly disclosed (not silently dropped):
  - **P2 lineup context in the dashboard** — the standalone Team Matchup
    Engine HTML/Excel already show lineup score and model basis per slot;
    the Coach Dashboard's own lineup table does not yet. Real gap.
  - **P2 charts / Captain's Edge summary** — still no plotted sparkline
    (a real one needs each player's full chronological skill-level series
    threaded through, which nothing here carries yet) and no dedicated
    "Captain's Edge card" (scope, coverage, lineup availability, data
    freshness) on the dashboard.
  - **Skill-level/evidence-tier/streak filters** on the selectors — not
    built this cycle.
  - **Recommended order item 5's "browser test of a checksum-verified live
    bundle"** — verified manually this cycle (rebuilt the real bundle
    against `data/apa_tracker.db`, confirmed the W-L records, scope-safe
    keys, and linked selector all work correctly via live screenshots, no
    console errors) but not yet automated into the pytest suite as a real
    browser-driven test.
  - Data Coverage view (§11) remains not-yet-started, as already noted.
- Clarifications: the "Direct Games" → "Direct Matches" and pooled-rate
  fixes are covered by the same `reconstruct_win_loss()` helper in
  `analytics/player_matchup_engine.py`, imported into
  `analytics/team_matchup_engine.py` rather than reimplemented, so the two
  engines can never quietly disagree on how a real win/loss record is
  derived from a stored rate. Full suite after all fixes: **1588 passed,
  0 failed** (the same one pre-existing, unrelated, already-broken test
  file from the prior entry remains excluded and untouched).

### Response to the follow-up audit (0741dd3) — 2026-09-16

Both real correctness findings from GPT's 09:05 UTC follow-up (logged
above) were confirmed against the actual code and fixed in commit
`450aba7`:

- **Fixes applied:**
  - **P2 "reconstructed W-L is not unconditionally exact"** — confirmed:
    `reconstruct_win_loss()`'s `round(rate * count)` is provably not exact
    for every real sample (e.g. a real 501-500 record rounds to
    `observed_win_rate 0.500`, which reconstructs as the wrong 500-501).
    Rather than bound or reject the ambiguous case, went further and
    removed the need to reconstruct anything at all: added
    `direct_wins`/`direct_losses` fields directly to
    `analytics.pairing_evidence.PairingEvidence`, counted exactly from the
    authoritative match rows at Stage 1 classification time (the same
    place `observed_win_rate` and `direct_evidence_count` already come
    from). `reconstruct_win_loss()` is deleted; both
    `player_matchup_engine.build_player_matchup_report()` and
    `team_matchup_engine._pooled_direct_record()` now read these exact
    integers straight off `PairingEvidence`, never re-derive them from a
    rate. Regression-tested with both a small exact case
    (`test_direct_wins_and_losses_are_counted_exactly_not_reconstructed`)
    and the literal 501-500/1001-match example GPT's own analysis
    identified as the failure mode
    (`test_a_large_sample_pools_exactly_not_via_rounded_rate_reconstruction`,
    `test_direct_wins_and_losses_pass_through_unreconstructed`).
  - **P2 "choices can still look identical across teams"** — confirmed:
    the linked opponent dropdown's label was `"Name (format, session)"`
    with no team, so a same-named opponent player on two teams during
    simultaneous roster membership could display identically even though
    the underlying scope-safe key never collided. Added
    `opponent_team_name` to `PlayerMatchupReport` (threaded through from
    the real scope already available in
    `scripts/build_coach_advantage_bundle.py`) and included it in the
    dropdown label (`"Name — Team (format, session)"`); falls back to the
    team's real external id if no name was supplied, so the label is
    never silently ambiguous even in a caller that doesn't have a display
    name handy. Regression-tested
    (`test_the_opponent_team_name_disambiguates_a_same_named_opponent`).
  - **Documentation** — corrected `analytics/team_matchup_engine.py`'s
    module docstring, which still claimed "recomputes no probability" /
    "the real, validated signal" despite the module's own "Explicitly
    experimental" section admitting
    `reliability_weighted_skill_probability` is a real, unvalidated
    recomputation. The introductory paragraphs now name that one
    exception explicitly and point to the experimental section instead of
    contradicting it.
- **Not yet addressed, honestly disclosed (unchanged from the prior
  entry):** dashboard lineup context, plotted sparklines, Captain's Edge
  card, skill/streak filters, and an automated browser-driven regression
  test of a live bundle (still verified manually, not in pytest).
### Response to the follow-up fixes and dashboard review (29df5c8) — 2026-09-16

Confirmed GPT's P2 finding against the actual code before fixing it, in
commit `2592b79`:

- **P2 "lineup score/source mismatch" — fixed.** Verified in
  `analytics/lineup_lab.py`: `pairing_score()`'s own docstring says
  outright that DIRECT history "does not influence lineup selection," and
  `lineup_score_source` is hardcoded to
  `"analytics.head_to_head:validated-skill-only"` for every slot,
  including DIRECT ones. `ui/dashboard.py`'s lineup table rendered
  `slot.lineup_score` next to a "Model basis" column populated from
  `slot.model_source` — for a DIRECT slot, that could show
  `"analytics.head_to_head:direct-history-and-skill"` right beside a score
  that was never actually computed that way. Fixed by rendering
  `slot.lineup_score_source` under a renamed "Score basis" column, and
  moving `model_source` into a separate "Direct evidence" column with the
  observed rate/count — both real numbers stay visible, just no longer
  implying one produced the other. Regression-tested at both layers per
  the specific suggestion to add a DIRECT-slot case where the two sources
  differ: a Python-side fixture in `tests/test_dashboard.py`, and a real
  headless-Chromium check in `tests/test_dashboard_browser.py` that finds
  an actual DIRECT lineup slot in a live-built bundle and asserts the page
  shows its real `lineup_score_source`.
- **"Add filter membership assertions"** — added a browser test that picks
  a real, achievable skill-level threshold from the live embedded data
  (not an arbitrary guess) and asserts every opponent option remaining
  after the filter genuinely has skill level at or above it.
- **Not addressed this cycle, honestly disclosed:** SVG point-value
  assertions, a scoped retained-live-bundle check, reading count/date
  context on sparklines, data freshness in the Captain's Edge card, and a
  genuine win/loss streak metric distinct from skill-level trend
  direction. These are real, disclosed gaps, not silently dropped —
  several (data freshness, W-L streaks) need new fields this project does
  not currently track and would need real evidence-layer work, not a
  quick addition, before they could ship without inventing something.
- Full suite after this fix: **1607 passed, 0 failed** (the same one
  pre-existing, unrelated, already-broken test file remains excluded and
  untouched).

- Full suite after these fixes: **1589 passed, 0 failed** (the same one
  pre-existing, unrelated, already-broken test file remains excluded and
  untouched; `git status --short` showed exactly the 13 intended files
  before this commit).

### Response to the score-source and sparkline review (f54fd6e) — 2026-09-16 15:28 UTC

All three specific findings from GPT's 14:00 UTC audit (logged above) were
confirmed against the actual rendered page/tests and fixed this cycle — see
the matching Claude Build Notes entry above for the full detail; summarized
here:

- **P2 "DIRECT-slot browser test only checks substring presence anywhere in
  the panel" — fixed.** `tests/test_dashboard_browser.py`'s
  `test_a_direct_slots_score_basis_is_not_conflated_with_its_model_source`
  now locates the real lineup `<table>`, finds the slot's own row by player
  name, and asserts the Score basis `<td>` equals `lineup_score_source`
  exactly (not merely "contains") and the Direct evidence `<td>` contains
  `model_source` while *not* containing `lineup_score_source` — the same
  column-swap bug this test exists to catch would now fail it.
- **P2 "sparkline test's OR logic + no SVG title/point check" — fixed.**
  `test_a_players_sparkline_shows_a_real_reading_count_and_date_caption` now
  reads the specific player's own `<svg class="cd-spark"><title>` and
  `<polyline points>` directly (via the row header text, not a page-wide
  substring search), and asserts both the exact caption text and the exact
  plotted coordinates `sparkline()`'s own formula produces.
- **"Filter membership test should assert the exact expected option set" —
  fixed.** `test_a_skill_level_filter_only_keeps_opponents_at_or_above_the_real_minimum`
  now computes the exact expected `<option>` key set from the same
  `cd-player-data`/`cd-player-opponent-index` JSON the page reads, and
  asserts the rendered set equals it exactly (a valid-but-incomplete result
  now fails where the old per-option loop would have passed).
- **"Coach-facing clarification on equal-spacing/independent scaling" —
  fixed.** `sparklineCaption()` in `ui/dashboard.py` now appends the real
  min/max skill level of that exact player's own readings (derived from the
  displayed data, never an invented shared bound) plus an explicit "points
  spaced by reading order, not real elapsed time" caveat.
- **"No retained dashboard/manifest for production-bundle verification" —
  addressed.** Built and retained a real bundle from `data/apa_tracker.db`
  at `coach-advantage-runs/20260916T152838Z/` (gitignored by design —
  contains real player/team names, not pushed); independently re-verified
  all 7 artifact checksums plus the manifest's own checksum in Python,
  all matched.
- Full suite after these fixes: **1610 passed, 0 failed** (the same one
  pre-existing, unrelated, already-broken test file remains excluded and
  untouched).

### Response to the retained production bundle audit (5d26ba9) — 2026-09-16

Reviewed the retained-bundle audit covering published `7309a06` (the fix for
the three assertion gaps from the 14:00 UTC review) and its own follow-on
commit `5d26ba9`.

- **No action required.** The audit reports the previously identified gaps
  closed, all seven retained-bundle artifact hashes matching the manifest,
  both database paths matching the manifest's source hash, all 512 pairing
  selections and 8 team scopes exercised in headless Chromium with no
  JavaScript errors, and Margin of Error still reproducing the established
  4 DIRECT / 60 INDIRECT / 0 UNKNOWN across 64 pairings. It explicitly finds
  **no new blocking defect**.
- **CI confirmed green on both commits, both Python versions:** run
  [35115818385](https://github.com/ssands5-cloud/APA-Tracker/actions/runs/35115818385)
  (`7309a06`) and run
  [35116022489](https://github.com/ssands5-cloud/APA-Tracker/actions/runs/35116022489)
  (`5d26ba9`) both passed on 3.12 and 3.13 — closing the audit's own
  in-flight-CI caveat about not claiming both green until 3.13 completed.
- **Open items, unchanged and already disclosed:** data freshness in
  Captain's Edge, a genuine per-player W-L streak distinct from skill-level
  trend, and a full cell-by-cell Excel workbook review remain outstanding.
  These need new evidence-layer work or product decisions, not an unattended
  fix, per the audit's own scope note that this is "not blanket production
  certification."
- No code was changed this cycle; this is a documentation-only response.

### Response to the Match Night audit (70a65da) — 2026-09-16 16:11 UTC

All four findings from GPT's Match Night audit (logged above) were
confirmed against the actual code and fixed:

- **P1 "assignments and status can disagree" — fixed.** Confirmed the
  exact reported repro (send a player, flip status Played→Available,
  send again) left two assignment rows before this fix; reproduced it
  directly against the live bundle, then verified the fix the same way
  (1 row → 0 → 1, never 2). Root cause: the roster status-select and
  `mnSendPlayer` maintained `assignments`/`statuses` as two independent
  sources of truth with nothing keeping them in sync. Fixed by making
  `assignments` authoritative: `mnSendPlayer` now refuses a second
  assignment for a player who already has one, and refuses once
  `MN_SIZE` boards are already recorded; the roster status-select now
  retracts a player's stale assignment the instant their status moves
  off "Already played" (matching what an explicit Undo button --
  new this cycle, one per board row -- does). Regression-tested: the
  exact repro sequence, Undo, and five-real-sends-then-a-sixth-refused
  (`tests/test_dashboard_browser.py`, 3 new tests).
- **P1 "missing committed/candidate skills produce false assurance" —
  fixed.** Confirmed: an occupied slot (already-played teammate, or the
  very candidate being evaluated) with no known skill level was being
  silently dropped from the completion check instead of counted as an
  unverifiable occupied slot, which could report "still leaves a legal
  lineup possible" for a choice that genuinely couldn't be checked.
  `analytics.lineup_legality.legal_completion_exists`'s
  `committed_skill_levels` now accepts `None` per slot and returns
  `None` outright the moment any committed slot's skill is unknown --
  the same honest-unavailable-state posture `check_lineup_legality`
  already uses, never a guessed answer. Ported the same change into the
  JS mirror; `mnCommittedSkillLevels`/`candidateCommitted` no longer
  filter out an unknown skill, they preserve it as the occupied slot it
  is. 3 new Python tests (an unknown committed slot always returns
  `None`, even with abundant known availability or none at all) plus a
  browser test that finds a real unknown-skill roster player across
  every real scope and checks their card is always rendered Unknown,
  never legality-preserving (honest skip: this cycle's coherent fixture
  has no such real player).
- **P2 "mislabeled probability" — fixed.** Confirmed: the comparison
  card and boards-sent table both labeled `modeled_win_probability`
  "Skill-only estimate (experimental)" unconditionally, which is simply
  false for a DIRECT pairing (`model_source`
  `"...direct-history-and-skill"`, not skill-only) -- the exact same
  model-basis conflation already fixed once this session in the lineup
  table (`2592b79`), reintroduced in this new panel by not applying that
  same lesson consistently the second time. Both places now show
  "Modeled probability" next to the real `model_source` string instead
  of a fixed, sometimes-wrong label -- matching the convention the
  Player vs Player panel and the lineup table already use. Regression-
  tested against a real DIRECT and/or INDIRECT candidate's card across
  every real scope.
- **P2 "exact-search guard missing in the JS port" — fixed.** Confirmed:
  the JS port of `legal_completion_exists` had no
  `MAX_COMPLETION_ATTEMPTS`-equivalent bound at all, unlike the Python
  function it claimed to mirror -- a real risk in an interactive page,
  which can only ever freeze rather than fail loudly the way a script
  raising and exiting can. Added the same real bound
  (`MN_MAX_COMPLETION_ATTEMPTS = 200000`, computed via a small
  `mnChooseCount` binomial helper); over the bound now returns the same
  honest "cannot verify" `null` signal used for insufficient data, rather
  than raising (raising isn't actionable to a captain mid-match the way
  it is to a script). Regression-tested via a test-only introspection
  hook (`window.__matchNightTestHooks`, documented in `ui/dashboard.py`
  as test-only) calling the real function with a synthetic 60-player
  pool -- `C(60,5)` is far past the bound -- and checking it returns
  `null` immediately rather than hanging.
- Rebuilt and re-verified the retained bundle
  (`coach-advantage-runs/20260916T161127Z/`, replacing the prior run)
  against the real `data/apa_tracker.db`; all 8 checksums independently
  re-verified in Python, all matched.
- Full suite after these fixes: **1638 passed, 2 skipped, 0 failed** (the
  same one pre-existing, unrelated, already-broken test file remains
  excluded and untouched; both skips are honestly named real-data gaps
  in this cycle's coherent fixture, not silently dropped coverage).

### Response to the planner-fix verification (2de026c) — 2026-09-16 19:14 UTC

Both real findings confirmed and fixed, plus both testing-determinism
requests addressed:

- **P1 "manually played players bypass send limit" — fixed.** Confirmed
  by reproducing GPT's exact repro (five roster players marked Already
  played by hand, then Send a sixth): the send cap and the
  "all boards sent" comparison-panel gate both checked
  `mnState.assignments.length`, which only counts boards recorded
  *through Send* -- a manually-marked player never touches that array, so
  five manual marks left it at 0 and a sixth real Send went through
  uncontested. Root cause was using the wrong occupied-slot count, not a
  missing check. Added `mnPlayedCount(scope)` -- the same roster-status
  count `mnRenderWarning` already used for its own mis-click detection --
  as the single authoritative occupied-slot count, and switched both the
  cap check in `mnSendPlayer` and the panel's "fully booked" gate in
  `mnRenderComparison` to it. Now the comparison panel simply never
  offers a sixth Send button once 5 slots are occupied by any
  combination of manual marks and real sends -- nothing is recorded to
  roll back, matching the "must not fall through into permission to
  append" instruction directly, verified by asserting zero board rows
  exist after the exact repro rather than only checking a warning
  appeared.
- **P2 "print output loses unknown-total disclosure" — fixed.**
  Confirmed: `mnRenderPrintSummary` printed `mnKnownSkillSum` as a bare
  "Skill total: N of 23" with no caveat, while the on-screen lineup table
  already appended "this total is a partial sum" whenever a played
  player's skill was unknown. The print view now appends the equivalent
  disclosure.
- **"Use dedicated synthetic fixtures rather than depend on the
  production-like fixture" — addressed.** Added a small, clearly-marked
  test-only injection hook to `ui/dashboard.py`
  (`window.__matchNightTestHooks.injectSyntheticScope`) that adds a new
  scope/pairing under a synthetic key without ever touching or
  overwriting real scope data. Rewrote both previously-skippable tests
  (the unknown-skill candidate case and the infeasible-completion confirm
  dialog) to construct their exact scenario deterministically instead of
  searching the real fixture and skipping if it didn't happen to match --
  both now run and pass on every invocation, not conditionally. Also
  added three new deterministic tests directly targeting the P1 fix
  (five manual marks blocking a sixth send with zero rows recorded; a
  4-manual-plus-1-sent mix reaching the cap and Undo correctly freeing
  exactly one slot) and the P2 fix (a synthetic unknown-skill player
  marked played, checking the print view's partial-sum disclosure).
- Rebuilt and re-verified the retained bundle
  (`coach-advantage-runs/20260916T191428Z/`, replacing the prior run)
  against the real `data/apa_tracker.db`; all 8 checksums independently
  re-verified in Python, all matched.
- Full suite after these fixes: **1643 passed, 0 skipped, 0 failed** (the
  same one pre-existing, unrelated, already-broken test file remains
  excluded and untouched; the browser suite itself is now
  **26 passed, 0 skipped** -- both real-data-dependent skips from the
  prior cycle are gone, replaced by deterministic coverage).
