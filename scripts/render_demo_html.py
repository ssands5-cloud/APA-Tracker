#!/usr/bin/env python3
"""Render the demo dashboard HTML from a JSON export produced by
ui.export_json (normally exports/demo_apa_data.json, from build_demo.py).

The page embeds that JSON verbatim in a <script type="application/json">
tag and renders every table/card from it client-side -- nothing in the
markup is hand-typed data. That's what lets "Teams" and "Matches" cross-
link: clicking a team card filters the Matches view to that team's own
games, entirely in the browser, off the one embedded document.

Usage:
    python scripts/build_demo.py            # writes exports/demo_apa_data.json
    python scripts/render_demo_html.py      # reads it, writes the HTML page
    python scripts/render_demo_html.py --out /path/to/file.html --data path/to.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent

DEFAULT_DATA_PATH = _project_root / "exports" / "demo_apa_data.json"
DEFAULT_OUT_PATH = _project_root / "exports" / "demo_dashboard.html"

PAGE_TEMPLATE = r"""<title>APA Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=Source+Sans+3:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
__CSS__
</style>

<header>
  <div class="header-inner">
    <div>
      <h1 class="wordmark">APA Tracker<span class="dot">.</span></h1>
      <p class="tagline">Standings, rosters, and match history — pulled straight from the league's own GraphQL API.</p>
    </div>
    <span class="demo-badge">Demo data · sanitized fixtures, no live login</span>
  </div>
  <nav class="tabs">
    <button class="tab active" data-tab="overview">Overview</button>
    <button class="tab" data-tab="teams">Teams</button>
    <button class="tab" data-tab="matches">Matches</button>
    <button class="tab" data-tab="standings">Standings</button>
    <button class="tab" data-tab="career">Career</button>
    <button class="tab" data-tab="skill">Skill Level</button>
  </nav>
</header>

<main>
  <section id="panel-overview" class="panel-view active"></section>
  <section id="panel-teams" class="panel-view"></section>
  <section id="panel-matches" class="panel-view"></section>
  <section id="panel-standings" class="panel-view"></section>
  <section id="panel-career" class="panel-view"></section>
  <section id="panel-skill" class="panel-view"></section>
</main>

<footer>
  <p><strong>Every number on this page came from running the real pipeline</strong> — <code>scripts/build_demo.py</code> → <code>ingest_viewer_data</code> / <code>ingest_standings</code> / <code>ingest_match_scores</code> → SQLite → <code>ui.export_json.export_to_json</code> → this page, which loads that JSON client-side and renders every table from it. No login, no token, no network call.</p>
  <p>The underlying fixtures were written independently for their own tests, so team/match ids don't fully line up across sections (a team can appear under two ids) — matching here falls back to team name where the id doesn't bridge, and that's called out rather than hidden.</p>
  <p>Player-level stats currently exist only for matches with a full scoresheet (<code>MatchPage</code>). Roster-wide season totals need item 2 of <code>HANDOFF.md</code>, still blocked on the alias-id confirmation.</p>
</footer>

<script type="application/json" id="demo-data">__DATA__</script>
<script>
__JS__
</script>
"""

CSS = r"""
:root {
  --bg: #f6f5f0; --surface: #ffffff; --surface-alt: #edeee6; --border: #dcded2;
  --ink: #1f2a22; --muted: #5c6459;
  --felt: #2f6b4f; --felt-strong: #1f4d38; --felt-tint: #e3ede7;
  --chalk: #3b5b8c; --chalk-tint: #e6ebf4;
  --brass: #93691f; --brass-tint: #f3e8cf;
  --win: #24824f; --loss: #a8422a; --warn-tint: #f6ecd2;
  --shadow: 0 1px 2px rgba(31,42,34,.06), 0 6px 16px rgba(31,42,34,.06);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #121c17; --surface: #182620; --surface-alt: #1f322a; --border: #2c4234;
    --ink: #e9efe9; --muted: #9db3a2;
    --felt: #5fbb8c; --felt-strong: #85d4ac; --felt-tint: #1e3529;
    --chalk: #8bafe6; --chalk-tint: #1e2c40;
    --brass: #e0b559; --brass-tint: #3a2f18;
    --win: #6fcf9a; --loss: #e0906f; --warn-tint: #3a2f18;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 20px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"] {
  --bg: #121c17; --surface: #182620; --surface-alt: #1f322a; --border: #2c4234;
  --ink: #e9efe9; --muted: #9db3a2;
  --felt: #5fbb8c; --felt-strong: #85d4ac; --felt-tint: #1e3529;
  --chalk: #8bafe6; --chalk-tint: #1e2c40;
  --brass: #e0b559; --brass-tint: #3a2f18;
  --win: #6fcf9a; --loss: #e0906f; --warn-tint: #3a2f18;
  --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 20px rgba(0,0,0,.35);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: "Source Sans 3", system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
.display, h1, h2, .tab, th { font-family: "Barlow Semi Condensed", system-ui, sans-serif; }
.mono, td.num, th.num, .num { font-family: "IBM Plex Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums; }
a { color: var(--chalk); }
header { border-bottom: 1px solid var(--border); background: var(--surface); }
.header-inner { max-width: 1180px; margin: 0 auto; padding: 22px max(20px, calc((100% - 1180px) / 2)) 14px; display: flex; align-items: baseline; justify-content: space-between; gap: 20px; flex-wrap: wrap; }
h1.wordmark { margin: 0; font-size: 28px; font-weight: 700; }
h1.wordmark .dot { color: var(--felt); }
.tagline { margin: 2px 0 0; color: var(--muted); font-size: 14px; }
.demo-badge { font-family: "Barlow Semi Condensed", sans-serif; font-weight: 600; font-size: 12.5px; letter-spacing: .04em; text-transform: uppercase; background: var(--brass-tint); color: var(--brass); border: 1px solid color-mix(in srgb, var(--brass) 35%, transparent); border-radius: 5px; padding: 6px 11px; white-space: nowrap; }
.tabs { max-width: 1180px; margin: 0 auto; padding: 0 max(20px, calc((100% - 1180px) / 2)); display: flex; gap: 6px; }
.tab { font: inherit; font-weight: 600; font-size: 14px; letter-spacing: .01em; color: var(--muted); background: none; border: none; border-bottom: 2px solid transparent; padding: 10px 4px; margin-right: 18px; cursor: pointer; }
.tab:hover { color: var(--ink); }
.tab.active { color: var(--felt-strong); border-bottom-color: var(--felt); }
main { max-width: 1180px; margin: 0 auto; padding: 26px 20px 50px; }
.panel-view { display: none; }
.panel-view.active { display: block; }
section.block { margin-bottom: 30px; }
section.block > h2 { font-size: 13px; font-weight: 600; letter-spacing: .09em; text-transform: uppercase; color: var(--muted); margin: 0 0 12px; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.tile { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; box-shadow: var(--shadow); }
.tile .num { font-weight: 600; font-size: 30px; color: var(--felt-strong); line-height: 1.1; }
.tile .lbl { margin-top: 4px; font-size: 13px; color: var(--muted); }
.team-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.team-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 8px; cursor: pointer; transition: border-color .12s ease; }
.team-card:hover { border-color: var(--felt); }
.team-card .name { font-weight: 600; font-size: 19px; }
.team-card .meta { color: var(--muted); font-size: 12.5px; margin-top: 2px; }
.hint { color: var(--chalk); font-size: 12px; }
.team-card .hint { margin-top: 2px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
th { font-size: 11.5px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); background: var(--surface-alt); }
td.num, th.num { text-align: right; }
tbody tr:last-child td { border-bottom: none; }
tbody tr.clickable { cursor: pointer; }
tbody tr.clickable:hover { background: var(--surface-alt); }
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; box-shadow: var(--shadow); overflow: hidden; margin-bottom: 16px; }
.panel .table-wrap { overflow-x: auto; }
.pill { border-radius: 999px; padding: 2px 9px; font-size: 12px; font-weight: 600; }
.pill.win { background: color-mix(in srgb, var(--win) 16%, transparent); color: var(--win); }
.pill.loss { background: color-mix(in srgb, var(--loss) 14%, transparent); color: var(--loss); }
.pill.bye { background: var(--surface-alt); color: var(--muted); }
.crumb { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; font-size: 13.5px; }
.crumb button { font: inherit; color: var(--chalk); background: none; border: none; cursor: pointer; padding: 0; }
.crumb button:hover { text-decoration: underline; }
.detail-title { font-size: 20px; font-weight: 600; margin: 0 0 4px; }
.detail-meta { color: var(--muted); font-size: 13px; margin-bottom: 16px; }
.scoreboard { display: flex; align-items: center; justify-content: center; gap: 26px; padding: 22px 20px; border-bottom: 1px solid var(--border); background: var(--surface-alt); }
.scoreboard .side { text-align: center; min-width: 130px; }
.scoreboard .side .team-name { font-weight: 600; font-size: 16px; }
.scoreboard .side .score { font-weight: 600; font-size: 40px; color: var(--felt-strong); line-height: 1.1; }
.scoreboard .side.away .score { color: var(--chalk); }
.scoreboard .vs { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
.empty { padding: 30px 20px; color: var(--muted); font-size: 13.5px; text-align: center; }
footer { max-width: 1180px; margin: 10px auto 0; padding: 20px 20px 40px; color: var(--muted); font-size: 12.5px; border-top: 1px solid var(--border); }
footer p { margin: 4px 0; }
footer code { font-family: "IBM Plex Mono", monospace; background: var(--surface-alt); border-radius: 4px; padding: 1px 5px; font-size: 11.5px; }
@media (max-width: 860px) {
  .tiles { grid-template-columns: repeat(2, 1fr); }
  .team-grid { grid-template-columns: 1fr; }
}
"""

JS = r"""
const DATA = JSON.parse(document.getElementById('demo-data').textContent);

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// Matches don't reliably share a team id with the Teams list (see footer) --
// fall back to matching by team name so "view this team's matches" still
// works across the two id spaces the underlying fixtures happen to use.
function matchesForTeam(team) {
  return DATA.matches.filter(m =>
    m.home_team_id === team.team_id || m.away_team_id === team.team_id ||
    m.home_team_name === team.team_name || m.away_team_name === team.team_name
  );
}

function scoreCell(m) {
  if (m.is_bye) return '<span class="pill bye">Bye</span>';
  if (!m.is_scored) return '<span class="pill bye">Unscored</span>';
  return `${m.home_score ?? '—'} – ${m.away_score ?? '—'}`;
}

function statusPill(m) {
  if (m.is_bye) return '<span class="pill bye">Bye</span>';
  if (m.is_finalized) return '<span class="pill win">Completed</span>';
  if (m.is_scored) return '<span class="pill loss">Scored</span>';
  return '<span class="pill bye">Scheduled</span>';
}

function renderOverview() {
  const teamCount = DATA.teams.length;
  const matchCount = DATA.matches.length;
  const standingsCount = DATA.standings.length;
  const statRows = DATA.player_stats.length;
  document.getElementById('panel-overview').innerHTML = `
    <section class="block">
      <h2>This account, right now</h2>
      <div class="tiles">
        <div class="tile"><div class="num">${teamCount}</div><div class="lbl">Teams played on</div></div>
        <div class="tile"><div class="num">${matchCount}</div><div class="lbl">Matches tracked</div></div>
        <div class="tile"><div class="num">${standingsCount}</div><div class="lbl">Teams in division standings</div></div>
        <div class="tile"><div class="num">${statRows}</div><div class="lbl">Player scoresheet rows</div></div>
      </div>
    </section>
    <section class="block">
      <h2>Generated</h2>
      <p style="color:var(--muted); font-size:13.5px;">This document was generated ${esc(DATA.generated_at)} by <code style="font-family:'IBM Plex Mono',monospace; background:var(--surface-alt); padding:1px 5px; border-radius:4px;">scripts/build_demo.py</code>. Use the tabs above to browse teams, matches, and division standings.</p>
    </section>
  `;
}

function renderTeamsList() {
  const cards = DATA.teams.map(t => {
    const n = matchesForTeam(t).length;
    return `
      <div class="team-card" data-team-id="${esc(t.team_id)}">
        <div class="name">${esc(t.team_name)}</div>
        <div class="meta">Team ID ${esc(t.team_id)}</div>
        <div class="hint">${n} match${n === 1 ? '' : 'es'} tracked →</div>
      </div>`;
  }).join('');
  document.getElementById('panel-teams').innerHTML = `
    <section class="block">
      <h2>My teams</h2>
      <div class="team-grid">${cards || '<div class="empty">No teams ingested yet.</div>'}</div>
    </section>
  `;
  document.querySelectorAll('#panel-teams .team-card').forEach(card => {
    card.addEventListener('click', () => renderTeamDetail(card.dataset.teamId));
  });
}

function renderTeamDetail(teamId) {
  const team = DATA.teams.find(t => t.team_id === teamId);
  if (!team) return renderTeamsList();
  const matches = matchesForTeam(team);
  const rows = matches.map(m => `
    <tr>
      <td class="num">${esc(m.week ?? '—')}</td>
      <td>${esc(m.home_team_name)}</td>
      <td>${esc(m.away_team_name || '—')}</td>
      <td class="num">${scoreCell(m)}</td>
      <td>${statusPill(m)}</td>
    </tr>`).join('');
  document.getElementById('panel-teams').innerHTML = `
    <div class="crumb"><button id="back-to-teams">← All teams</button></div>
    <h3 class="detail-title">${esc(team.team_name)}</h3>
    <p class="detail-meta">Team ID ${esc(team.team_id)} · ${matches.length} match${matches.length === 1 ? '' : 'es'} tracked</p>
    <div class="panel table-wrap">
      <table>
        <thead><tr><th class="num">Week</th><th>Home</th><th>Away</th><th class="num">Score</th><th>Status</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="5" class="empty">No matches for this team yet.</td></tr>'}</tbody>
      </table>
    </div>
  `;
  document.getElementById('back-to-teams').addEventListener('click', renderTeamsList);
}

function renderMatchesList() {
  const rows = DATA.matches.map(m => {
    const hasScoresheet = ((DATA.match_scores || {})[m.match_id] || []).length > 0;
    return `
    <tr class="clickable" data-match-id="${esc(m.match_id)}">
      <td class="num">${esc(m.week ?? '—')}</td>
      <td>${esc(m.home_team_name)}</td>
      <td>${esc(m.away_team_name || '—')}</td>
      <td class="num">${scoreCell(m)}</td>
      <td>${statusPill(m)}</td>
      <td>${hasScoresheet ? '<span class="hint">Scoresheet →</span>' : '<span class="hint" style="color:var(--muted);">Details →</span>'}</td>
    </tr>`;
  }).join('');
  document.getElementById('panel-matches').innerHTML = `
    <section class="block">
      <h2>Matches — click a row for detail</h2>
      <div class="panel table-wrap">
        <table>
          <thead><tr><th class="num">Week</th><th>Home</th><th>Away</th><th class="num">Score</th><th>Status</th><th></th></tr></thead>
          <tbody>${rows || '<tr><td colspan="6" class="empty">No matches ingested yet.</td></tr>'}</tbody>
        </table>
      </div>
    </section>
  `;
  document.querySelectorAll('#panel-matches tbody tr.clickable').forEach(row => {
    row.addEventListener('click', () => renderMatchDetail(row.dataset.matchId));
  });
}

function resultPill(result) {
  const r = (result || '').toUpperCase();
  if (r === 'W') return '<span class="pill win">W</span>';
  if (r === 'L') return '<span class="pill loss">L</span>';
  return '<span class="pill bye">—</span>';
}

function renderMatchDetail(matchId) {
  const match = DATA.matches.find(m => m.match_id === matchId);
  if (!match) return renderMatchesList();
  const scoresheet = (DATA.match_scores || {})[matchId] || [];
  const scoresheetRows = scoresheet.map(row => `
    <tr>
      <td>${esc(row.player)}</td>
      <td>${esc(row.team_name || '—')}</td>
      <td class="num">${esc(row.skill_level ?? '—')}</td>
      <td>${resultPill(row.result)}</td>
      <td class="num">${row.points_earned ?? '—'}</td>
    </tr>`).join('');
  const scoresheetBlock = scoresheet.length
    ? `<div class="table-wrap"><table>
        <thead><tr><th>Player</th><th>Team</th><th class="num">SL</th><th>Result</th><th class="num">Pts</th></tr></thead>
        <tbody>${scoresheetRows}</tbody>
      </table></div>`
    : `<p class="empty" style="text-align:left; padding:12px 20px 20px;">No per-player scoresheet ingested for this match. Only matches with a full <code>MatchPage</code> capture carry one -- see HANDOFF.md item 2 for the alias-id work that would add roster-wide stats to every match, not just scored ones.</p>`;
  document.getElementById('panel-matches').innerHTML = `
    <div class="crumb"><button id="back-to-matches">← All matches</button></div>
    <div class="panel">
      <div class="scoreboard">
        <div class="side home"><div class="team-name">${esc(match.home_team_name)}</div><div class="score">${match.home_score ?? '—'}</div></div>
        <div class="vs">${match.is_bye ? 'bye' : 'vs'}</div>
        <div class="side away"><div class="team-name">${esc(match.away_team_name || '—')}</div><div class="score">${match.away_score ?? '—'}</div></div>
      </div>
      <p class="detail-meta" style="padding:12px 20px 0;">Week ${esc(match.week ?? '—')} · ${esc(match.status || '')} ${match.match_date ? '· ' + esc(match.match_date) : ''}</p>
      ${scoresheetBlock}
    </div>
  `;
  document.getElementById('back-to-matches').addEventListener('click', renderMatchesList);
}

function renderStandings() {
  const rows = DATA.standings.map(s => `
    <tr>
      <td class="num">${esc(s.rank ?? '—')}</td>
      <td>${esc(s.team_name)}</td>
      <td class="num">${s.points ?? '—'}</td>
    </tr>`).join('');
  document.getElementById('panel-standings').innerHTML = `
    <section class="block">
      <h2>Division standings</h2>
      <div class="panel table-wrap">
        <table>
          <thead><tr><th class="num">Rank</th><th>Team</th><th class="num">Session Pts</th></tr></thead>
          <tbody>${rows || '<tr><td colspan="3" class="empty">No standings ingested yet.</td></tr>'}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderCareer() {
  const careerStats = DATA.career_stats || [];
  const teamHistory = DATA.team_history || [];
  const players = [...new Set([...careerStats, ...teamHistory].map(r => r.player))];

  if (players.length === 0) {
    document.getElementById('panel-career').innerHTML = `
      <section class="block">
        <h2>Career stats</h2>
        <p class="empty">No career stats ingested yet -- see HANDOFF.md item 2 for what feeds this tab (getEightBallStats / TeamStat).</p>
      </section>`;
    return;
  }

  const sections = players.map(player => {
    const stats = careerStats.filter(r => r.player === player);
    const history = teamHistory.filter(r => r.player === player);

    const statRows = stats.map(s => `
      <tr>
        <td>${esc(s.format)}</td>
        <td class="num">${s.matches_won ?? '—'}</td>
        <td class="num">${s.matches_played ?? '—'}</td>
        <td class="num">${s.cla ?? '—'}</td>
        <td class="num">${s.defensive_shot_avg ?? '—'}</td>
        <td class="num">${s.match_count_last_two_yrs ?? '—'}</td>
        <td>${esc(s.last_played ?? '—')}</td>
      </tr>`).join('');

    const historyRows = history.map(h => `
      <tr>
        <td>${esc(h.team_name)}</td>
        <td>${esc(h.session_name)}</td>
        <td>${h.is_current ? '<span class="pill win">Current</span>' : '<span class="pill bye">Past</span>'}</td>
        <td class="num">${h.skill_level ?? '—'}</td>
        <td class="num">${h.rank ?? '—'}</td>
        <td class="num">${h.matches_won ?? '—'}</td>
        <td class="num">${h.matches_played ?? '—'}</td>
      </tr>`).join('');

    return `
      <section class="block">
        <h2>${esc(player)} — lifetime stats</h2>
        <div class="panel table-wrap">
          <table>
            <thead><tr><th>Format</th><th class="num">Won</th><th class="num">Played</th><th class="num">CLA</th><th class="num">Def. Shot Avg</th><th class="num">Last 2 Yrs</th><th>Last Played</th></tr></thead>
            <tbody>${statRows || '<tr><td colspan="7" class="empty">No lifetime stats.</td></tr>'}</tbody>
          </table>
        </div>
        <h2>${esc(player)} — team history</h2>
        <div class="panel table-wrap">
          <table>
            <thead><tr><th>Team</th><th>Session</th><th></th><th class="num">SL</th><th class="num">Rank</th><th class="num">Won</th><th class="num">Played</th></tr></thead>
            <tbody>${historyRows || '<tr><td colspan="7" class="empty">No team history.</td></tr>'}</tbody>
          </table>
        </div>
      </section>`;
  }).join('');

  document.getElementById('panel-career').innerHTML = sections;
}

// Small dependency-free line chart -- this page uses no charting library
// anywhere else, so a sparkline drawn as plain inline SVG stays consistent
// with the rest of the demo instead of pulling one in for a single tab.
function sparkline(values) {
  const w = 240, h = 48, pad = 6;
  if (values.length === 0) return '';
  if (values.length === 1) {
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
      <circle cx="${w / 2}" cy="${h / 2}" r="3" fill="var(--felt-strong)"></circle>
    </svg>`;
  }
  const min = Math.min(...values), max = Math.max(...values);
  const span = (max - min) || 1;
  const stepX = (w - pad * 2) / (values.length - 1);
  const points = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return [x, y];
  });
  const polyline = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const dots = points.map(([x, y]) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5" fill="var(--felt-strong)"></circle>`).join('');
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <polyline points="${polyline}" fill="none" stroke="var(--felt)" stroke-width="2"></polyline>
    ${dots}
  </svg>`;
}

function trendDisplay(trend) {
  if (trend === 'up') return { symbol: '▲', color: 'var(--win)' };
  if (trend === 'down') return { symbol: '▼', color: 'var(--loss)' };
  if (trend === 'stable') return { symbol: '▬', color: 'var(--muted)' };
  return { symbol: '—', color: 'var(--muted)' };
}

function renderSkillLevel() {
  const history = DATA.skill_level_history || [];
  const summary = DATA.skill_level_summary || [];

  if (summary.length === 0) {
    document.getElementById('panel-skill').innerHTML = `
      <section class="block">
        <h2>Skill level history</h2>
        <p class="empty">No match-linked skill level readings ingested yet -- this comes from the same per-match scoresheet (MatchPage) that feeds match detail, so it fills in as matches get scored.</p>
      </section>`;
    return;
  }

  const sections = summary.map(s => {
    const readings = history.filter(r => r.player_id === s.player_id);
    const t = trendDisplay(s.trend);
    const rows = readings.map(r => `
      <tr>
        <td class="num">${esc(r.week ?? '—')}</td>
        <td class="num">${esc(r.skill_level ?? '—')}</td>
        <td>${esc(r.match_date ?? '—')}</td>
        <td>${esc(r.source)}</td>
      </tr>`).join('');

    return `
      <section class="block">
        <h2>${esc(s.player)}</h2>
        <div class="tiles">
          <div class="tile"><div class="num">${esc(s.current_skill_level ?? '—')}</div><div class="lbl">Current skill level</div></div>
          <div class="tile"><div class="num" style="color:${t.color};">${t.symbol}</div><div class="lbl">Trend: ${esc(s.trend)}</div></div>
          <div class="tile"><div class="num">${s.volatility}</div><div class="lbl">Times it changed</div></div>
        </div>
        <p class="detail-meta">${s.last_change ? 'Last change: ' + esc(s.last_change) : 'No change recorded this season.'}</p>
        <div class="panel" style="padding:14px 18px;">${sparkline(readings.map(r => r.skill_level).filter(v => v !== null && v !== undefined))}</div>
        <div class="panel table-wrap">
          <table>
            <thead><tr><th class="num">Week</th><th class="num">Skill Level</th><th>Match Date</th><th>Source</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="4" class="empty">No readings.</td></tr>'}</tbody>
          </table>
        </div>
      </section>`;
  }).join('');

  document.getElementById('panel-skill').innerHTML = sections;
}

function activateTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.panel-view').forEach(p => p.classList.toggle('active', p.id === `panel-${name}`));
}

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => activateTab(tab.dataset.tab));
});

renderOverview();
renderTeamsList();
renderMatchesList();
renderStandings();
renderCareer();
renderSkillLevel();
"""


def render(data: dict) -> str:
    html = PAGE_TEMPLATE.replace("__CSS__", CSS).replace("__JS__", JS)
    # Safe to embed directly inside a <script type="application/json"> tag;
    # escape only the sequence that would otherwise close the tag early.
    payload = json.dumps(data, default=str).replace("</script>", "<\\/script>")
    return html.replace("__DATA__", payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH), help="Path to the JSON export to render")
    parser.add_argument("--out", default=str(DEFAULT_OUT_PATH), help="Path to write the rendered HTML page to")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        sys.exit(f"{data_path} does not exist -- run scripts/build_demo.py first.")

    data = json.loads(data_path.read_text())
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(data), encoding="utf-8")
    print(f"Rendered demo dashboard to {out_path}")


if __name__ == "__main__":
    main()
