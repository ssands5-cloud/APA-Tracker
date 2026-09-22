# Ultimate Coach — Project Summary

Status of this document: **project closeout summary, documentation-only.**
It describes what has been built and independently tested as of
2026-09-21, and is explicit everywhere about what is still in progress or
unproven. It does not authorize a release, merge, or production promotion
by itself — see [Current release/state snapshot](#10-current-releasestate-snapshot).

## 1. Mission / outcome

APA-Tracker already answers "who should I send now?" for a captain's own
roster using data the tracker has already scraped. **Ultimate Coach**
extends that to players the captain has *not* scraped yet: an opponent's
new teammate, a substitute who has never played against your team before,
or anyone who shows up on a scoresheet without prior local history.

The scouting problem it solves: APA's own portal only shows you a
player's history if you already know which teams/divisions to look under.
Ultimate Coach instead starts from your own team's authenticated roster
and *recursively* walks the real APA GraphQL history graph outward —
every team any of your teammates ever played on, every opponent on those
scoresheets, every team those opponents played on — building a
league-wide map of real matches without requiring the coach to know in
advance who might show up. The outcome is the ability to look up **any**
player who appears in front of you on a scoresheet, not just ones already
in the local database.

## 2. Current architecture

Ultimate Coach is a four-stage, resumable pipeline, driven by one entry
point: `tools/run_ultimate_coach_browser.py`. Each stage is its own
script with its own checkpoint file, chained together by
`run_pipeline()` in the runner:

| Stage | Script | Purpose |
|---|---|---|
| 1/4 | `scripts/build_historical_catalog.py` | Seed catalog: starting from the authenticated viewer's own APA member id, walks that member's real league aliases, each alias's historical sessions, and each session's league divisions to build the seed of divisions/sessions the crawl expands from. |
| 2/4 | `scripts/expand_ultimate_coach_history.py` | History graph: recursively expands outward from that seed through every real roster member's own team history, discovering opponent teams/divisions not directly visible to the logged-in account. |
| 3/4 | `scripts/build_ultimate_coach_archive.py` | League-wide archive: crawls every division discovered by Stage 2 into a local staging database of real matches/scoresheets. |
| 4/4 | `scripts/enrich_ultimate_coach_players.py` | Player enrichment: fetches league-scoped real APA career stats for every safely resolvable canonical player discovered by Stage 3 and writes them into the staging database, per format (8-Ball/9-Ball kept strictly separate). |

Each stage only ever consumes evidence the *previous* stage already
verified. Identity is never guessed globally or unscoped — resolution is
bounded to team/session/display-name evidence within a known scope, and
an ambiguous case fails closed rather than being guessed — see PR #53–#56
(identity manifest and namespace-collision audit) for the
identity-resolution safeguards this pipeline depends on. The broader
leakage-safe/`as_of`-aware evaluation and calibration work (PR #38–#48)
is a separate, not-yet-integrated lineage layered on top of this
data-foundation pipeline — Stage 4 as implemented here does not itself
take or enforce an `as_of` instant.

The runner chains all four stages under a single captured auth token
(`run_pipeline(token, resume=resume)`), so one login session (manual or
persistent) can carry the crawl all the way through, and a confirmed
token expiry mid-run reopens authentication and continues rather than
restarting.

## 3. Persistent authentication

Two authentication modes, selected by mutually exclusive CLI flags:

- **`--manual-auth`** (default, unchanged): a real Chromium window opens
  to the APA login page, the coach logs in and clicks through to Member
  Services by hand, then presses Enter in the terminal once the GraphQL
  token has been observed.
- **`--persistent-auth`**: a password-free, unattended mode for
  overnight/long-running crawls, added in PR #62.
  - Uses `chromium.launch_persistent_context()` against
    `.session_cache/apa_chromium/` (already gitignored) — the same kind
    of on-disk cookie/local-storage state any browser keeps, reused
    across process restarts.
  - **One-time manual bootstrap:** the very first run against a fresh
    profile still requires a real, one-time manual APA login. After that,
    the persistent browser profile itself stays logged in.
  - **In-memory token capture:** success is defined only by observing a
    real `authorization` header on a `gql.poolplayers.com` GraphQL
    response — never a URL or a timer. The token exists only in a local
    Python variable and the `APA_ACCESS_TOKEN` environment variable for
    the lifetime of `run_pipeline()`, popped in its `finally` block. It
    is never written to disk, printed, or logged.
  - **Automatic refresh:** when the short-lived GraphQL token expires,
    the runner reopens the same persistent profile automatically —
    no `input()`, no Enter key, no rerunning PowerShell.
  - **Debounced UI handling:** the "Continue to Member Services"
    transitional page is auto-clicked, but only once per visibility
    transition — it will not click on every polling tick, and will only
    click again if the control genuinely disappears and reappears (fixed
    in PR #62 after a real-site test showed 14 repeated clicks under the
    original tick-based version).
  - **Fail-closed boundary:** if the underlying APA *web session itself*
    has expired (not just the short-lived token), the bounded wait
    (`PERSISTENT_AUTH_TIMEOUT_S`, default 300s) elapses and the runner
    prints `MANUAL APA LOGIN REQUIRED` and exits. It never attempts to
    detect, read, or interact with a login form.
  - **No credential handling anywhere in this file:** no `.env`, no
    `APA_USERNAME`/`APA_PASSWORD`, no password field lookup, no
    autofill. Proven with AST-based tests against the actual
    import/call/literal nodes (not string-matched against comments,
    which initially gave false passes/fails during development).
  - **No recording:** no screenshots, video, HAR files, or Playwright
    tracing are ever enabled, also proven with an AST-based test.

## 4. Resume/checkpoint model

Every stage checks for its own prior checkpoint file before deciding
whether to build from scratch or continue:

| Stage | Checkpoint file(s) | `--resume` behavior |
|---|---|---|
| 1/4 Seed catalog | `data/ultimate_coach_historical_catalog.json` | If present, reused as-is ("Reusing seed catalog for resume"); otherwise rebuilt from the authenticated viewer. |
| 2/4 History graph | `data/ultimate_coach_historical_catalog_expanded.json` + `data/ultimate_coach_history_graph_report.json` | Only resumes if *both* files exist; otherwise expansion restarts from the seed catalog. |
| 3/4 Archive | `data/ultimate_coach_staging.db` (+ `data/ultimate_coach_archive_report.json`) | Resumes into the existing staging database rather than rebuilding it. If the archive report's `completed_division_keys` is also present, resume uses it as a shortcut to skip already-completed divisions; if the staging DB exists but the report doesn't, the DB is still preserved and per-match resume/idempotency still protects already-ingested work, but that division-level shortcut isn't available. |
| 4/4 Enrichment | `data/ultimate_coach_player_enrichment_report.json` | Resumes remaining player enrichment against the existing report. |

Why interruption is recoverable: each stage script writes its own
checkpoint/report incrementally as it works, not only at the end. A
non-authentication failure in any stage prints an explicit "Checkpoint
files were left intact" message and stops (exit code 1) rather than
corrupting partial state. An authentication interruption
(`AccessTokenExpired`/`AccessTokenMissing`) is handled one level up, in
the runner's own retry loop, and does not unwind or discard any stage's
checkpoint. Both the staging database and the JSON checkpoint/report
files are written during a run, and any of them caught mid-write by an
unclean kill (e.g. `taskkill`) is a real risk to that specific in-flight
artifact — which is exactly why the operator runbook below keeps the
guidance simple: avoid force-killing the process, and prefer one
`Ctrl+C` at a natural boundary instead.

## 5. Verified evidence

Persistent-auth evidence has two distinct reference points that must not be conflated:

- **Historical live-site acceptance head:** `26d5c44ceef12f793568c51c30511e33422da777`. This is the exact code the long-running live crawler remains frozen on while the crawl is in flight, and it is the head used for the real two-cycle browser/session acceptance below.
- **Final integrated PR #62 head:** `62d6ff7d1683a600ec0d059fec1eb02cd62c52e2`, which passed fresh integrated CI run #285 on Python 3.12 and 3.13 before PR #62 merged to `main` as merge commit `e1973b375654ea58120880f1b87fee3def114549`.

The targeted/full-suite and real-site evidence below refers to the historical live-accepted head unless a later integrated head is named explicitly:

- Targeted tests: `pytest tests/test_ultimate_coach_browser_runner.py -v`
  → **17/17 passed** (15 from the initial persistent-auth build + 2 added
  for the Continue-button debounce fix).
- Full suite: `pytest tests/ -q` → **1800 passed, 0 failed** (only
  pre-existing, unrelated `datetime.utcnow()` deprecation warnings).
- Mutation testing: reverting the debounce guard to unconditional
  per-tick clicking reproduced the exact real-site symptom (the
  "Continue to Member Services" click line printed 14 times before the
  token appeared), and the new regression test correctly failed against
  that mutation; the mutation was then reverted with zero diff drift.
  Earlier mutation rounds on the same PR also confirmed the
  `MANUAL APA LOGIN REQUIRED` fail-closed message, the `--persistent-auth`
  CLI dispatch, and the mutual-exclusivity guard are each covered by a
  test that fails without them.
- CI on the historical live-accepted head: GitHub Actions run #265 (id `35492418672`) — both job-level lanes green, `pytest (3.12)` and `pytest (3.13)`.
- Final PR #62 integration check: branch head `62d6ff7d1683a600ec0d059fec1eb02cd62c52e2` passed fresh integrated CI run #285 on both Python 3.12 and 3.13 before merge to `main`.
- **Real two-cycle live-site acceptance, performed by Paul directly
  against APA (not simulated):**
  - Cycle 1: one manual login bootstrap in the persistent profile → token
    captured automatically with no Enter key → result printed
    `PERSISTENT AUTH CYCLE 1: PASS`.
  - Cycle 2: the persistent profile was closed and reopened, with **zero**
    further human interaction (no typing, no Enter, no clicks) → the
    saved APA web session was reused, fresh authenticated GraphQL traffic
    was observed, and the result printed `PERSISTENT AUTH CYCLE 2: PASS`.
  - This is the one thing the mocked/offline test suite could not prove
    on its own: that a real APA web session genuinely survives being
    closed and reopened through Playwright's persistent-context
    mechanism.
- **Real live switch, observed after the debounce fix landed:** the live
  crawl worktree was switched to head `26d5c44...` and restarted with
  `python tools/run_ultimate_coach_browser.py --resume --persistent-auth`.
  Console evidence: persistent auth opened successfully, the Continue
  button was clicked exactly once (debounce fix confirmed live), a
  GraphQL token was captured automatically, viewer validation passed, and
  Stage 1 printed `Reusing seed catalog for resume` — proving the crawl
  picked up its existing checkpoints rather than starting over.

## 6. Operator runbook

Normal command to run or resume the full pipeline unattended:

```
python tools/run_ultimate_coach_browser.py --resume --persistent-auth
```

**What healthy output looks like**, in order:

```
APA AUTH OK - authenticated viewer found.

[1/4] Reusing seed catalog for resume: ...ultimate_coach_historical_catalog.json
[2/4] Recursively expanding history through real roster members...
[3/4] Building/resuming league-wide historical archive...
[4/4] Enriching every safely resolvable player with APA career stats...

ULTIMATE COACH DATA FOUNDATION COMPLETE
  expanded catalog: ...ultimate_coach_historical_catalog_expanded.json
  staging: ...ultimate_coach_staging.db
  production database was not promoted or replaced.
```

(On a fresh, non-resumed run, `[1/4]` instead prints "Building
authenticated-member seed catalog..." — expected the first time only.)

**On GraphQL token expiry** (short-lived token only, web session still
valid), the console prints a clearly bannered block:

```
========================================================================
APA AUTHENTICATION NEEDS REFRESH
  confirmed auth interruption #<n>
  server signal: <server error text>
  crawl checkpoints are preserved.
  reopening the persistent profile automatically...
  no Enter key or PowerShell command is required.
========================================================================
```

No action is needed — the runner reopens the persistent profile on its
own and resumes from checkpoints.

**On `MANUAL APA LOGIN REQUIRED`**: this means the underlying APA *web
session itself* has expired, not just the short-lived token — this is
the designed fail-closed behavior, not a bug. All checkpoints remain
intact. Log in by hand once in the browser window that opens, then rerun
the same command; `--resume` will pick up exactly where the crawl left
off.

**Do not force-kill the process during an in-flight write.** If you need
to stop the crawl, prefer a single `Ctrl+C` at a natural boundary
(between the bracketed `[n/4]` print blocks) over `taskkill` or a
process-tree kill — the sub-pipeline scripts write their own
checkpoint/report files incrementally, and an abrupt kill mid-write to
*any* in-flight generated artifact (the staging database or a JSON
checkpoint/report file) is what can genuinely corrupt state that
`--resume` cannot otherwise recover from.

## 7. Data outputs

All paths are relative to the repository root and live under `data/`,
which is gitignored:

| File | Written by | Purpose |
|---|---|---|
| `ultimate_coach_historical_catalog.json` | Stage 1/4 | Seed catalog: divisions discovered by walking the authenticated viewer's own member id through their real league aliases, each alias's historical sessions, and each session's league divisions. |
| `ultimate_coach_historical_catalog_expanded.json` | Stage 2/4 | Full recursively-expanded catalog of divisions discovered through the roster-member history graph. |
| `ultimate_coach_history_graph_report.json` | Stage 2/4 | Report describing how the expansion reached that catalog (aliases, sessions, discovery mode, source limitations). |
| `ultimate_coach_staging.db` | Stage 3/4 | SQLite staging database holding every archived match/scoresheet the crawl has collected so far. |
| `ultimate_coach_archive_report.json` | Stage 3/4 | Crawl status/progress report (division counts, coverage observations, checksums) for the staging database above. |
| `ultimate_coach_player_enrichment_report.json` | Stage 4/4 | Per-player, per-format career-stat enrichment report built from the staging database. |

**The production database (`data/apa_tracker.db`) is never touched by
this pipeline.** `run_pipeline()` has no production-promotion step at
all — its own module docstring says so explicitly, and the completion
banner itself prints "production database was not promoted or replaced."
Promoting any of this staging data into production would be a distinct,
separately reviewed action that has not happened and is not part of what
this runner does.

## 8. Security / privacy boundaries

Guarantees currently enforced and covered by tests:

- No `.env` file, `APA_USERNAME`/`APA_PASSWORD` environment variable,
  password field lookup, or form autofill exists anywhere in the
  persistent-auth code path — verified by AST-based source inspection,
  not a docstring claim.
- The GraphQL access token is held only in a local variable and the
  `APA_ACCESS_TOKEN` process environment variable for the lifetime of one
  `run_pipeline()` call, and is explicitly popped in a `finally` block.
  It is never written to disk, printed to the console, or logged.
- No screenshots, video capture, HAR files, or Playwright tracing are
  ever enabled — verified by AST-based source inspection.
- The persistent browser profile (`.session_cache/apa_chromium/`) is
  already excluded from version control by `.gitignore`. It holds the
  same kind of on-disk session state (cookies, local storage) any
  logged-in browser keeps; it is not a separately extracted credential.
- The runner never attempts to detect, read, or interact with an APA
  login form. On a genuinely expired web session it stops at
  `MANUAL APA LOGIN REQUIRED` rather than guessing or retrying blindly.
- No production-promotion step exists in this pipeline at all (see §7).

## 9. Known limitations / residual risks

- **APA may expire the underlying web session**, not just the short-lived
  GraphQL token. When that happens, one manual login is unavoidable —
  the whole design goal of `--persistent-auth` is to avoid *routine*
  logins, not to eliminate every possible one.
- **External site/API behavior can change.** The token-capture mechanism
  depends on observing a real `authorization` header on
  `gql.poolplayers.com` responses; if APA changes its auth flow, header
  shape, or the Member Services transitional page, this may need
  updating.
- **Long crawl runtime and API dependence.** A full four-stage run
  crawls potentially thousands of real divisions (the live run currently
  in progress had discovered 2,691 divisions to crawl as of the snapshot
  in §10, a number that itself grows as Stage 2 discovers more) and is
  bounded by APA's own API responsiveness, not by anything in this
  codebase.
- **Source-coverage limitations are real and already tracked, not
  hidden.** The Stage 2/3 reports carry their own
  `source_limitations`/`coverage_observations` arrays (398 catalog-level
  limitations and 9 coverage observations recorded at the same snapshot
  as §10, and still growing while the crawl runs) — for example,
  individual completed matches missing a scoresheet. These are reported,
  not silently dropped.
- **The real APA login-form/"Continue to Member Services" DOM interaction
  was validated live by Paul, not fabricated** — but only across two
  cycles so far. Extended unattended reliability over many days/weeks of
  real overnight cycles has not yet been observed.
- **The 300-second bootstrap timeout is a judgment call**, long enough
  for one real manual login but still bounded so a truly dead session
  fails closed on a later unattended cycle. It is adjustable via the
  `timeout_s` parameter if it proves too short or too long in practice.

## 10. Current release/state snapshot

As of this writing:

- **The core data-foundation/auth/canonical-cockpit and steady-state-maintenance guard line is integrated into `main`.** PRs #30, #31, #33, #35, #60, #61, #62, #73, #74, and #76 have merged. After PR #76, the exact `main` SHA is `d6868a9a2a9d091610b6983b65aa27bf0361baec`.
- PR #71 is closed as superseded by #73. #73 preserved the accepted #71 hardening, then exposed and fixed two unrelated date-sensitive game-night tests on current `main`; fresh CI run #295 passed on Python 3.12 and 3.13 before merge.
- The canonical offline cockpit / identity / leakage-safe enrichment work is now integrated through PR #74. The superseded stacked PRs #32, #34, #36–#59, #71, #72, and #75 have been closed after ancestry/content verification. The incremental-maintenance scope guard merged through PR #76 as `d6868a9a2a9d091610b6983b65aa27bf0361baec`, locking routine daily/game-night refreshes to the current-team/current-division path and explicitly keeping the full historical crawler out of steady-state maintenance. A separate current-main replacement of the old PvP multi-scope browser regression is staged in PR #77 and is not yet merged at this snapshot.
- The live crawl worktree (`APA-Tracker-Ultimate-Coach-Live`) remains deliberately detached at historical live-accepted head `26d5c44ceef12f793568c51c30511e33422da777` while the crawl runs. It is intentionally not being updated to newer `main` during the in-flight four-stage crawl.
- **The four-stage crawl has not yet reported completion.** The latest meaningful read-only progress posted to Issue #24 before this documentation refresh showed Stage 3/4 still at `status: crawl_in_progress`, **2,011 of 2,691** discovered divisions crawled. No Stage 4 completion evidence and no explicit `ULTIMATE COACH DATA FOUNDATION COMPLETE` banner/report evidence has been posted. This document therefore does **not** claim the data foundation is complete.
- PR #63 itself remains documentation-only and intentionally unmerged until the live crawl reaches a meaningful terminal state so this runtime snapshot can receive one final factual refresh.

## 11. What this enables for Paul

Once the archive and enrichment stages have real, complete coverage, the
practical game-night payoff is:

- **Scouting players your team has never faced.** If an opponent's
  scoresheet shows a substitute or new teammate your local database has
  no record of, Ultimate Coach's league-wide archive can still surface
  that player's real match history from divisions your own team was
  never directly part of.
- **Comparing unfamiliar players before you have to decide a matchup**,
  using the same kind of evidence-based, fail-closed disclosure the rest
  of the tracker already uses — not a guess dressed up as a stat.
- **A clear line between direct historical evidence and modeled
  insight.** Everything this pipeline produces through Stage 4 is
  archived, verifiable match history and descriptive career-stat
  summaries built from it — not a prediction. Separate work in the
  broader Ultimate Coach PR stack (evidence-quality gates, chronological
  backtest-readiness gates, calibration) exists specifically to keep any
  future predictive/modeled layer clearly labeled and gated behind its
  own promotion review, with `matchup_probability`/`predictive_confidence`
  explicitly locked to `None` and publication `FORBIDDEN` until that
  separate review passes. This document covers only the data-foundation
  layer (Stages 1–4); it does not claim any predictive capability exists
  or is ready.
