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
- `analytics/` — derived stats: win %, standings trend, head-to-head,
  simple matchup comparisons.
- `scheduler/` — the two jobs meant to actually run on a schedule
  (`daily_sync.py`, `weekly_refresh.py`).
- `ui/` — Excel export today; `dashboard_stub.py` marks where a real
  dashboard would go later.

## Setup

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

## Notes

- This only scrapes pages behind your own login for your own team/league —
  it's not meant to hit the portal anonymously or at any volume beyond what
  a normal logged-in user would generate. Keep the daily/weekly cadence;
  don't tighten it into a polling loop.
- The session cookie cache (`.session_cache/`) and `.env` both belong in
  `.gitignore` — they contain live credentials/session state.
