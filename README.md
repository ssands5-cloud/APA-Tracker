# APA Tracker Scorekeeper

Personal tool for tracking your APA (pool league) team's standings, rosters,
and player stats by scraping your local league's web portal, storing the
results in a small SQLite database, and exporting summaries to Excel.

## Layout

- `auth/` — logs into the league portal and caches the session so the
  scheduler jobs don't have to re-authenticate every run.
- `scraper/` — pulls standings, team roster/schedule, and player match
  history pages.
- `parser/` — turns scraped HTML into plain dicts. `apa_page_map.py` is the
  one place that knows the site's CSS selectors — update it there if the
  portal's markup changes, rather than in each scraper.
- `database/` — SQLAlchemy models plus ingest/query helpers backed by SQLite.
- `analytics/` — derived stats: win %, standings trend, skill level
  trend/volatility (`skill_level_trends.py`), and two distinct matchup
  tools -- `matchup_insights.py` (older, simpler: compares two players'
  own overall win %, not specific to each other) and `matchups.py`, the
  Matchup Advantage Engine (real head-to-head record against one specific
  opponent -- see docs/matchups.md).
- `scheduler/` — the two jobs meant to actually run on a schedule
  (`daily_sync.py`, `weekly_refresh.py`).
- `ui/` — Excel (`export_excel.py`) and JSON (`export_json.py`) exports.
  `dashboard_stub.py` marks where a real *interactive* (Streamlit/Flask)
  dashboard would go later — separate from the static demo page below.
- `scripts/` — offline, fixture-driven demo build: `build_demo.py` runs the
  real ingestion pipeline against `tests/fixtures/*.json` (no network, no
  login) and `render_demo_html.py` turns that into a browsable
  `exports/demo_dashboard.html`. See `docs/graphql-captures/*/HANDOFF.md`
  for how it's wired.

## Setup

**Requires Python 3.12 or 3.13, NOT 3.14.** Python 3.14.3 on Windows has a
confirmed bug where `asyncio.run()` crashes the entire process with zero
output and no traceback -- not catchable by any `try/except`, since it
happens below where Python's own exception handling runs at all. Confirmed
directly: `scraper/diagnose_eventloop.py` isolates it down to the exact
call (a bare, do-nothing coroutine passed to `asyncio.run()`) and reproduces
it every time on 3.14.3, while the identical script completes cleanly under
3.12.10 on the same machine. This breaks `scraper/full_apa_scrape.py` and
`scraper/capture_apa_graphql.py` (anything using Playwright's async API)
outright, since Playwright's driver never even starts.

If `py -0` shows only 3.14 installed, get 3.12 with `winget install
Python.Python.3.12` (or the installer from python.org), then create the
venv from that version specifically: `py -3.12 -m venv venv`.

1. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your league portal login:

   ```
   APA_USERNAME=your_username
   APA_PASSWORD=your_password
   ```

   Credentials are read from the environment only — never put them in
   `apa_config.yaml` or commit them.

3. Edit `apa_config.yaml`:
   - `site.base_url` and the `*_path` / `*_path_template` fields — point
     these at your actual league portal (they're placeholders right now).
   - `league.league_id`, `team.team_id`, `team.team_name`.
   - `apa.league_id` and `apa.division_id` for GraphQL metadata.
   - `database.path` / `export.excel_output_path` if you want them
     somewhere other than `data/` and `exports/`.

4. **Inspect the real site's HTML** and update `parser/apa_page_map.py`
   accordingly. The selectors in there (`table.standings`, `table.roster`,
   etc.) are placeholders — nothing will parse correctly until they match
   what the portal actually renders. Same goes for the success markers in
   `auth/login.py::is_logged_in` and the login form field names.

## Running it

```
python -m scheduler.daily_sync      # standings + roster + new match results
python -m scheduler.weekly_refresh  # full refresh + Excel export
```

Wire either of those into Windows Task Scheduler (or cron, if running under
WSL) at the times set in `apa_config.yaml`'s `scheduler` section.

### Live GraphQL team data

The APA Teams page is a client-side app talking to a GraphQL endpoint — there
is no server-rendered HTML behind it to scrape, so team/roster/schedule data
is only reachable this way.

**1. Set the access token for this shell only.** It is short-lived, and it
must never be saved to `apa_config.yaml`, a script, a HAR file, or source
control:

```powershell
$env:APA_ACCESS_TOKEN = "<access token from your current APA session>"
```

**2. Run the sync.** By default this discovers and syncs *every team the
account plays on* -- no `team.team_id`/`division_id` config needed -- and
for each one: the team itself, its roster, every match (schedule and
score), the division standings, and a full per-player scoresheet for every
match that's actually been played. All of it writes to SQLite; the Excel
workbook and a JSON export refresh afterward:

```powershell
python -m scheduler.graphql_sync                 # every team, sync + Excel export
python -m scheduler.graphql_sync --no-export      # every team, sync only
python -m scheduler.graphql_sync --single-team    # only apa_config.yaml's team.team_id (the original, narrower path)
```

No page needs clicking through for any of this -- it's direct API calls
once the token above is set. If the token has expired (they don't last
long) the run stops with a message saying exactly that, rather than a
traceback; get a fresh one and set the env var again.

Player *career* stats (lifetime record per format, plus cross-season team
history — "how has this player done across seasons," not just this match)
are included too: the sync resolves the account's own member id to its
per-league alias id and pulls both, landing in the "Career Stats" and
"Team History" Excel sheets and the demo's Career tab. See
`docs/graphql-captures/*/HANDOFF.md` item 2 for how the alias id was found
and what's still unconfirmed (opponents' career stats aren't pulled this
way, and the alias-per-league mapping is only confirmed against one league
on a multi-league account).

**Skill level history** — APA skill levels get re-evaluated and can change
mid-season, and a player who moved that way shows up as a mystery jump in
other stats unless the change itself is visible. This isn't a new query or
extraction step: `ingest_match_roster`/`ingest_match_scores` already write
`PlayerMatch.skill_level` for every scored match; `database.queries.skill_level_history`
just reads that column back out match-by-match instead of only the single
current value on `Player.skill_level`. `analytics/skill_level_trends.py`
turns a player's ordered readings into a trend (`up`/`down`/`stable`,
comparing the first and last reading of the season — a dip that fully
recovers reads `stable`), a volatility count (how many times it actually
changed), and a plain-language last change (`"SL 5 → SL 6 in Week 7"`). It
lands in the Excel "Skill Level History" sheet, the JSON export's
`skill_level_history`/`skill_level_summary` keys, and the demo's own
"Skill Level" tab (a table plus a small inline-SVG trend line per player —
no charting library, matching the rest of the demo). Readings are kept
match-by-match rather than deduplicated to one per week: a player can have
more than one match in the same week number (a doubleheader, a makeup
match), and collapsing them would silently discard a real reading.

**Matchup Advantage Engine** — a per-opponent read for a captain setting a
lineup: real head-to-head record, not a season-wide average, plus a 0-100
`matchup_score`. Also not a new query: `MatchPage`'s per-game
`matchPositionNumber` already tells you which home player played which
away player (same-numbered positions face each other in APA team format);
`scraper/graphql_scraper.py::head_to_head_rows()` pairs them, and
`analytics/matchup_builder.py::build_matchups()` scores every (player,
opponent, format, session) group found so far -- an 8-ball record doesn't
predict a 9-ball one, and a stale session's record isn't current form
(both threaded in from the team's own context, not a new query). Called
directly by the real sync and the demo build, not a separate manual step;
`scripts/build_matchups.py` is a thin CLI wrapper for recomputing on
demand. The score is sample-size-weighted (a 1-0 record no longer scores
like a 10-0 one), recency-weighted (a recent game counts slightly more
than an old one), and includes an opponent-skill-level modifier (a bonus
for wins against tougher opponents) — plus a separate `Confidence Score`
saying how much to trust the matchup score itself. A corrected scoresheet
reconciles cleanly (stale pairings are removed, not left alongside
corrected ones), results are normalized so a malformed value never counts
as a silent loss, and a known player with no history against a specific
known opponent shows up as a neutral 50/"Has History: No" row instead of
being silently absent. Lands in the Excel "Matchups" sheet, the JSON
export's `matchups` key, and the demo's "Matchups" tab (recommended
opponents / opponents to be cautious of, per player). Full write-up,
including the score formula and what it deliberately leaves out,
in `docs/matchups.md`.

#### Capturing queries by logging in (easiest)

`tools/capture_apa_graphql.py` opens a browser, you log in by hand, and it
records every GraphQL call the site makes while you browse. One-time setup:

```powershell
pip install playwright
python -m playwright install chromium
```

Then:

```powershell
python tools/capture_apa_graphql.py           # capture only
python tools/capture_apa_graphql.py --sync    # capture, then sync immediately
```

`--sync` reuses the session you just opened, so there is no token to copy
anywhere. The token is held in memory for that run only — never written to
disk, never printed.

It writes two files, both gitignored:

| File | Contains | Share it? |
|---|---|---|
| `apa-capture-shapes.json` | Field names and **types** only — every name, id and score replaced by `str`/`int`/`float`. Enum values like `COMPLETED` are kept. | **Yes** — it's the schema, with no data in it |
| `apa-capture-full.json` | The real responses, for building local fixtures | **No** — has teammates' names |

The script never sees your password: you type it into the real APA login page
in the browser window it opens.

#### Capturing a new query from a HAR file (alternative)

Only `teamPage`, `teamRoster` and `teamSchedule` have been captured. The
division standings table needs `LeagueBox`, which hasn't been — see the
bottom of `parser/apa_graphql.py`. To capture one:

1. Log into APA in Chrome and open the page that shows the data you want.
2. DevTools → Network → Fetch/XHR, then reload the page.
3. Right-click the request list → *Save all as HAR with content*, saving to
   `%USERPROFILE%\Desktop\apa-network.har`.
4. Run the extractor:

   ```powershell
   powershell -ExecutionPolicy Bypass -File ".\tools\export-apa-graphql.ps1"
   ```

That writes `apa-graphql-requests.json` with only the operation names,
variables, queries and **response bodies** — no headers, cookies or tokens,
so the token never leaves your machine. The response bodies can still contain
teammates' names, so skim the file before sharing it with anyone.

A HAR captured on one page only contains the queries that page issued: if an
operation comes back missing, visit the page that loads it and capture again.

## Notes

- This only scrapes pages behind your own login for your own team/league —
  it's not meant to hit the portal anonymously or at any volume beyond what
  a normal logged-in user would generate. Keep the daily/weekly cadence;
  don't tighten it into a polling loop.
- The session cookie cache (`.session_cache/`) and `.env` both belong in
  `.gitignore` — they contain live credentials/session state.
