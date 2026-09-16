# Overnight Coach Advantage Report

## Claude Build Notes

**Status: built, tested, and run against real production data. Not yet reviewed by GPT** —
see the caveat at the end of this section before treating this as independently audited.

### What was built

Following the Coach Advantage architecture plan's **Option A** path (build
strictly on already-approved, already-validated evidence; no new
win-probability model, no invented categorical threshold):

- `analytics/player_matchup_engine.py` — one real (player, opponent)
  pairing's Coach Mode report: evidence label, DIRECT observed win rate or
  the validated skill-only estimate (never both blended), each side's raw
  skill-level trend, and a strictly descriptive summary sentence.
- `analytics/team_matchup_engine.py` — one real scheduled match's roster
  comparison, a purely descriptive per-opponent-player ranking (mirrors
  `analytics.opponent_risk_profile`'s own convention at player granularity
  instead of that module's team granularity), and the embedded
  `analytics.lineup_lab` approved lineup (or its real failure reason).
- `ui/export_html_player_matchup_engine.py`, `ui/export_html_team_matchup_engine.py` —
  self-contained HTML, no external resources, script-injection-hardened
  (same pattern as `ui/export_html_player_matchup_explorer.py`).
- `ui/export_excel_player_matchup_engine.py`, `ui/export_excel_team_matchup_engine.py` —
  filterable, frozen-header workbooks (same pattern as
  `scripts/build_captains_edge.py`'s own writer).
- `ui/export_json_coach_advantage.py` — plain-dict serialization for both
  engines' dataclasses.
- `ui/dashboard.py` — replaces `ui/dashboard_stub.py` (deleted). A static
  page combining Player vs Player, Team vs Team, and a whole-division
  Opponent Risk Profile ranking. Static, not a live server — matches this
  project's established demo-run architecture
  (`scripts/build_full_production_demo.py`), and `dashboard_stub.py`'s own
  original advice ("read from the same SQLite file the scheduler jobs
  write to; don't scrape from the dashboard process itself") still holds.
- `scripts/build_coach_advantage_bundle.py` — the builder: preflight →
  acquire (read-only, never scrapes) → compute → render → verify →
  finalize, with its own manifest schema (`coach-advantage-manifest-v1`)
  and event schema (`coach-advantage-event-v1` — deliberately NOT
  `build_full_production_demo.py`'s `demo-event-v1`, which would have
  mislabeled these events as coming from a different builder). Real scope
  discovery and evidence classification are not reimplemented — it calls
  `scripts.build_captain_first_edge.build_match_scopes` directly.
- README: new "Coach Advantage Tools" section.
- Tests: `test_player_matchup_engine.py`, `test_team_matchup_engine.py`,
  `test_export_json_coach_advantage.py`,
  `test_export_html_player_matchup_engine.py`,
  `test_export_html_team_matchup_engine.py`,
  `test_export_excel_player_matchup_engine.py`,
  `test_export_excel_team_matchup_engine.py`, `test_dashboard.py`,
  `test_build_coach_advantage_bundle.py`. Full suite (excluding one
  pre-existing, unrelated, already-broken test file — see Known Issues
  below): **1577 passed, 0 failed.**

### Run against real production data

```
python scripts/build_coach_advantage_bundle.py --db data/apa_tracker.db --our-team-id 13082948
```

Succeeded end-to-end: 8 real scheduled opponents for "Mark It Up"
(13082948) this Fall 2026 session, all 8 scopes usable. The
already-independently-verified real scope (opponent 13082949, "Margin of
Error") reproduced the exact same **4 DIRECT / 60 INDIRECT / 0 UNKNOWN / 64
total** figures this project's Player-vs-Player export already established
earlier this session — a real, independent cross-check that the identity
fix and this new bundle agree. 512 real player-pairing reports and 8 real
team reports were produced; every team scope's approved Lineup Lab filled
5 real boards.

Visually verified in a browser (screenshot-checked, not just asserted in
code): the dashboard's Player vs Player selector, Team vs Team selector,
roster/trend tables, opponent ranking table, and approved-lineup table all
render real names, real skill levels, real evidence labels, and honest
"No data" cells — no console errors.

### A real bug found and fixed during this build (not a pre-existing one)

While rebuilding the real bundle, `ui/dashboard.py` and both new HTML
exports were nearly unreadable in a dark-mode browser: their `body` rule
set text color but no explicit background, so a dark browser theme
rendered dark text on a dark background. Confirmed this matches an
existing gap in `ui/tabs/tonights_match.py` and
`scripts/build_full_production_demo.py`'s own templates (same missing
`background` declaration) — not something introduced here, but also not
something to knowingly repeat. Fixed by adding `background: #ffffff` to
all three of this build's own templates. The two pre-existing files were
left untouched (out of this task's scope).

Also found and fixed, before it ever reached real data: an Excel
sheet-title bug in `ui/export_excel_team_matchup_engine.py` where
truncating a full `"<scope> Lineup"` candidate to Excel's 31-character
sheet-name limit from the right could chop the suffix itself down to an
unrecognizable `"Lin"`, and a second real bug where two scopes sharing a
truncated prefix produced colliding Rank/Lineup sheet names that openpyxl
then silently renamed (pushing them back over 31 characters). Both are
covered by dedicated regression tests now
(`test_a_long_scope_name_never_truncates_the_rank_or_lineup_suffix`,
`test_duplicate_sheet_titles_are_disambiguated`).

Also found and fixed: my own new test file's module-scoped fixture
originally rebuilt the *shared* `data/demo_coherent.db` file (the same
physical path `scripts/build_full_production_demo.py`'s own tests rebuild)
— on Windows, a lingering read-only SQLite connection from my tests could
still hold that file open when a *different* test module later tried to
delete-and-rebuild the same path, causing a real, reproducible
`PermissionError` when the full suite ran (not when either file ran
alone). Fixed by building this test file's own fixture into a private
`tmp_path`, never the shared project-wide fixture file.

### Deliberately excluded (Option A, per the architecture plan)

No new win-probability/confidence model. No categorical "danger
player"/"favored" flag. No "Player A is favored because…" verdict text.
Every summary sentence states real evidence only (an observed rate, a
sample size, a validated skill-only estimate, a real trend direction) —
verified by a dedicated test in every new export module asserting the
words "favored"/"dangerous"/"recommended avoid"/"recommended target" never
appear. This matches `docs/captain_first_edge_experience.md` §13's
exclusion table, which names by module exactly why this project has
repeatedly had to fail-close invented, unfitted thresholds presented as
coach advice.

### Known gaps / disclosed limitations

- **No plotted sparkline.** Trend is shown as a direction + volatility
  count (`▲ up (volatility 2)`), not a chart. A real sparkline needs each
  player's full chronological skill-level series
  (`database.queries.skill_level_history`), which this build's dataclasses
  summarize but don't carry as a series. Real, separate follow-up.
- **No skill/streak filters on the dashboard yet** (the directive's
  "coach-friendly usability improvements" wishlist item) — the current
  page is a scope/pairing selector only, no client-side filtering by skill
  level or hot/cold streak. Would be a real, additive follow-up, not a
  blocker.
- **Data Coverage view** (§11 of `docs/captain_first_edge_experience.md`)
  is still "not yet started" per that document — this build did not add
  it either; the dashboard shows evidence *counts* per scope but not the
  fuller coverage view (missing skill levels named individually, refresh
  dates, etc.) that document specifies.

### Known issue found, NOT caused by this work

`ui/export_html_player_vs_player.py` has a substantial (149 insertions /
126 deletions), **uncommitted** change already sitting in the working tree
before this task began — `git diff --stat` confirms it, and `git log`
shows its last real commit predates this whole session. It currently
**breaks full-suite test collection**:
`tests/test_player_vs_player_unified_tab.py` fails to import because the
in-progress version of that file is missing `SUMMARY_COLUMNS`, `_fmt`, and
`_row_id`, which `ui/tabs/player_vs_player_unified.py` still depends on.
This is unrelated to the Coach Advantage Tools and was not modified,
reverted, or committed by this work — it was excluded from every full-suite
test run above via `--ignore=tests/test_player_vs_player_unified_tab.py`
specifically so it wouldn't be silently swept into a commit or mistaken
for something this task broke. **This needs your own attention separately**
— it looks like unfinished work of your own (or a prior session's) sitting
uncommitted, not something to discard without checking first.

### Overnight coordination reality check

Verified via `gh api repos/ssands5-cloud/APA-Tracker/collaborators`:
`ssands5-cloud` is the only collaborator on this repository. There is no
GPT bot, GitHub App, or second account with write access, so there is no
live GPT session that can autonomously audit this repo overnight. This
report's "GPT Audit Notes" section is a real, intentional placeholder for
you to paste GPT's actual review into when you run one by hand — nothing
was fabricated under GPT's name here.

## GPT Audit Notes
(GPT logs its periodic reviews, findings, and suggestions for improvements.)

## Claude Responses to GPT
(Claude logs how he acted on GPT’s findings — fixes, adjustments, or clarifications.)
