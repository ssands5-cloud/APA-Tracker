"""Render the Ultimate Coach Scout as one self-contained offline HTML file."""

from __future__ import annotations

import json
from html import escape
from typing import Any


def _safe_json(payload: dict[str, Any]) -> str:
    """Embed JSON inside a script element without permitting tag break-out."""
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_ultimate_coach_scout(
    payload: dict[str, Any],
    *,
    title: str = "APA Ultimate Coach",
) -> str:
    data = _safe_json(payload)
    safe_title = escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title>
<style>
:root {{
  --navy:#0f2745; --navy2:#173b65; --ink:#152033; --muted:#65758b;
  --paper:#f4f7fb; --card:#ffffff; --line:#d9e2ee; --good:#166534;
  --warn:#92400e; --bad:#991b1b; --locked:#5b21b6; --shadow:0 8px 28px rgba(15,39,69,.10);
}}
* {{ box-sizing:border-box; }}
html, body {{ width:100%; max-width:100%; }}
body {{ margin:0; font-family:Inter,Segoe UI,Arial,sans-serif; color:var(--ink); background:var(--paper); }}
header {{ background:linear-gradient(135deg,var(--navy),var(--navy2)); color:white; padding:22px 24px; }}
.header-inner {{ max-width:1500px; margin:auto; display:flex; gap:18px; align-items:center; justify-content:space-between; min-width:0; }}
.header-inner > * {{ min-width:0; }}
h1 {{ margin:0; font-size:clamp(24px,3vw,38px); letter-spacing:-.02em; }}
.subtitle {{ margin-top:6px; opacity:.86; font-size:14px; }}
.badge {{ display:inline-flex; align-items:center; gap:7px; padding:7px 11px; border-radius:999px; font-size:12px; font-weight:800; letter-spacing:.03em; }}
.badge.locked {{ background:#ede9fe; color:var(--locked); border:1px solid #c4b5fd; }}
.badge.ok {{ background:#dcfce7; color:var(--good); border:1px solid #86efac; }}
.badge.warn {{ background:#fef3c7; color:var(--warn); border:1px solid #fcd34d; }}
main {{ max-width:1500px; margin:20px auto 48px; padding:0 18px; }}
.controls, .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; box-shadow:var(--shadow); }}
.controls {{ padding:16px; display:grid; grid-template-columns:1fr 1fr 180px auto; gap:12px; align-items:end; }}
.controls > * {{ min-width:0; }}
label {{ display:block; font-size:12px; font-weight:800; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin-bottom:6px; }}
input,select {{ width:100%; min-width:0; max-width:100%; min-height:42px; border:1px solid #bcc9d8; border-radius:9px; padding:8px 10px; background:white; color:var(--ink); }}
.checkbox-wrap {{ min-height:42px; display:flex; align-items:center; gap:8px; white-space:nowrap; }}
.checkbox-wrap input {{ width:auto; min-height:auto; }}
.grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:16px; margin-top:16px; }}
.card {{ padding:16px; min-width:0; }}
.card h2,.card h3 {{ margin:0 0 12px; }}
.player-name {{ font-size:24px; font-weight:850; letter-spacing:-.02em; }}
.muted {{ color:var(--muted); }}
.stat-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:9px; margin-top:14px; }}
.stat {{ background:#f7f9fc; border:1px solid #e1e8f0; border-radius:10px; padding:10px; }}
.stat b {{ display:block; font-size:18px; margin-top:3px; }}
.full {{ grid-column:1/-1; }}
.split {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:16px; margin-top:16px; }}
.odds-lock {{ border:2px solid #c4b5fd; background:#faf8ff; }}
.odds-lock .lock-title {{ color:var(--locked); font-weight:900; font-size:18px; }}
table {{ width:100%; max-width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:left; padding:8px 7px; border-bottom:1px solid #e5ebf2; vertical-align:top; overflow-wrap:anywhere; }}
th {{ color:#516175; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }}
.scroll {{ width:100%; max-width:100%; overflow:auto; max-height:430px; }}
.empty {{ color:var(--muted); padding:12px 0; }}
.result-win {{ color:var(--good); font-weight:800; }}
.result-loss {{ color:var(--bad); font-weight:800; }}
.kpi-good {{ color:var(--good); }}
.details {{ margin-top:8px; }}
details summary {{ cursor:pointer; font-weight:800; }}
.quality-list {{ margin:8px 0 0; padding-left:18px; }}
.footer-note {{ margin-top:18px; color:var(--muted); font-size:12px; }}
@media(max-width:980px) {{
  .controls {{ grid-template-columns:1fr 1fr; }}
  .grid,.split {{ grid-template-columns:1fr; }}
  .stat-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
}}
@media(max-width:620px) {{
  .header-inner {{ flex-direction:column; align-items:flex-start; }}
  .controls {{ grid-template-columns:minmax(0,1fr); }}
  .stat-grid {{ grid-template-columns:minmax(0,1fr) minmax(0,1fr); }}
  header {{ padding:18px 14px; }}
  main {{ padding:0 10px; }}
  .player-name, h1, h2, h3 {{ overflow-wrap:anywhere; }}
}}
@media print {{
  body {{ background:white; }}
  .controls {{ display:none; }}
  .card {{ box-shadow:none; break-inside:avoid; }}
  header {{ background:white; color:black; border-bottom:2px solid #111; }}
}}
</style>
</head>
<body>
<header>
  <div class="header-inner">
    <div>
      <h1>{safe_title}</h1>
      <div class="subtitle">Real APA evidence first. Direct history, shared opponents, career context, and source coverage.</div>
    </div>
    <span class="badge locked" id="odds-status">ODDS LOCKED</span>
  </div>
</header>
<main>
  <section class="controls">
    <div>
      <label for="search-a">Player A search</label>
      <input id="search-a" placeholder="Type name or APA id">
      <select id="player-a"></select>
    </div>
    <div>
      <label for="search-b">Player B search</label>
      <input id="search-b" placeholder="Type name or APA id">
      <select id="player-b"></select>
    </div>
    <div>
      <label for="format">Format</label>
      <select id="format"><option value="EIGHT">8-Ball</option><option value="NINE">9-Ball</option></select>
    </div>
    <label class="checkbox-wrap"><input type="checkbox" id="include-unresolved"> Include scoresheet-only / unscoped identities</label>
  </section>

  <section class="grid">
    <article class="card" id="profile-a"></article>
    <article class="card" id="profile-b"></article>
  </section>

  <section class="split">
    <article class="card odds-lock">
      <div class="lock-title">🔒 Win probability is intentionally locked</div>
      <p id="odds-message">No probability is shown until the chronological backtest and calibration gate passes on real archive data.</p>
    </article>
    <article class="card" id="direct-summary"></article>
  </section>

  <section class="card" style="margin-top:16px">
    <h2>Shared Opponent Evidence</h2>
    <div class="muted">Actual records against people both selected players have faced in this format.</div>
    <div class="scroll" id="shared-opponents"></div>
  </section>

  <section class="card" style="margin-top:16px">
    <h2>Direct Meeting Ledger</h2>
    <div id="meeting-ledger"></div>
  </section>

  <section class="grid">
    <article class="card" id="career-a"></article>
    <article class="card" id="career-b"></article>
  </section>

  <section class="grid">
    <article class="card" id="history-a"></article>
    <article class="card" id="history-b"></article>
  </section>

  <section class="card" style="margin-top:16px" id="coverage"></section>
  <div class="footer-note">Facts are stored APA evidence. Aggregates are transparent arithmetic over those facts. Missing source data stays missing.</div>
</main>

<script type="application/json" id="uc-data">{data}</script>
<script>
(function() {{
"use strict";
const DATA = JSON.parse(document.getElementById("uc-data").textContent);
const byId = Object.fromEntries(DATA.players.map(p => [String(p.player_id), p]));
const el = id => document.getElementById(id);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
const pct = v => v === null || v === undefined ? "No data" : (100*Number(v)).toFixed(1)+"%";
const num = v => v === null || v === undefined ? "No data" : String(v);
const rec = f => f && f.games ? f.wins+"-"+f.losses+" ("+pct(f.win_rate)+")" : "No recorded games";
const slStatus = f => {{
  if (!f) return "No data";
  if (f.display_skill_level_status === "current_roster") return "Current roster SL "+f.display_skill_level;
  if (f.display_skill_level_status === "latest_observed") return "Latest observed SL "+f.display_skill_level;
  if (f.display_skill_level_status === "ambiguous_current_roster") return "Current SL ambiguous";
  return "SL unavailable";
}};
function fmtLabel(fmt) {{ return fmt === "EIGHT" ? "8-Ball" : "9-Ball"; }}
function fmtData(p, fmt) {{ return (p && p.formats && p.formats[fmt]) || null; }}
function canonicalPlayers(includeUnresolved) {{
  return DATA.players.filter(p => includeUnresolved || p.selectable_by_default);
}}
function fillSelect(select, query, includeUnresolved, preferred) {{
  const q = (query || "").trim().toLowerCase();
  const rows = canonicalPlayers(includeUnresolved).filter(p =>
    !q || p.name.toLowerCase().includes(q) || String(p.external_id||"").toLowerCase().includes(q)
  );
  const old = preferred || select.value;
  select.innerHTML = rows.map(p =>
    '<option value="'+p.player_id+'">'+esc(p.name)+' · '+esc(p.external_id)+'</option>'
  ).join("");
  if (rows.some(p => String(p.player_id) === String(old))) select.value = String(old);
  return rows;
}}
function identityBadge(p) {{
  return p.identity_status === "canonical_team_history"
    ? '<span class="badge ok">Canonical team history</span>'
    : '<span class="badge warn">Scoresheet-only / unscoped</span>';
}}
function profileHtml(p, fmt) {{
  if (!p) return '<div class="empty">Select a player.</div>';
  const f = fmtData(p, fmt);
  return '<div class="player-name">'+esc(p.name)+'</div>'
    + '<div class="muted">APA id '+esc(p.external_id)+'</div>'
    + '<div style="margin-top:8px">'+identityBadge(p)+'</div>'
    + '<div class="stat-grid">'
    + '<div class="stat"><span class="muted">'+fmtLabel(fmt)+' SL</span><b>'+esc(slStatus(f))+'</b></div>'
    + '<div class="stat"><span class="muted">Observed record</span><b>'+esc(rec(f))+'</b></div>'
    + '<div class="stat"><span class="muted">Recent 5</span><b>'+esc(f && f.recent5_games ? f.recent5_wins+"-"+f.recent5_losses+" ("+pct(f.recent5_win_rate)+")" : "No data")+'</b></div>'
    + '<div class="stat"><span class="muted">Unique opponents</span><b>'+esc(f ? f.unique_opponents : 0)+'</b></div>'
    + '</div>'
    + '<p class="muted">'+(f && f.first_match_date ? "Observed window: "+esc(f.first_match_date)+" → "+esc(f.last_match_date) : "No safely dated observed games in this format.")+'</p>';
}}
function careerHtml(p, fmt) {{
  if (!p) return "";
  const rows = (p.career_stats || []).filter(r => r.format === fmt);
  let html = '<h2>'+esc(p.name)+' · '+fmtLabel(fmt)+' APA Career Stats</h2>';
  if (!rows.length) return html+'<div class="empty">No league-scoped lifetime stats recovered.</div>';
  html += '<div class="scroll"><table><thead><tr><th>League</th><th>W-L</th><th>Win %</th><th>B&R</th><th>On break</th><th>Mini slams</th><th>Def avg</th><th>Last played</th></tr></thead><tbody>';
  rows.forEach(r => {{
    const losses = r.matches_played === null || r.matches_played === undefined || r.matches_won === null || r.matches_won === undefined ? null : r.matches_played-r.matches_won;
    html += '<tr><td>'+esc(r.league_slug || r.league_id)+'</td><td>'+esc(r.matches_won===null||r.matches_won===undefined ? "No data" : r.matches_won+"-"+losses)+'</td><td>'+esc(pct(r.win_rate))+'</td><td>'+esc(num(r.break_and_runs))+'</td><td>'+esc(num(r.on_break_count))+'</td><td>'+esc(num(r.mini_slams))+'</td><td>'+esc(num(r.defensive_shot_avg))+'</td><td>'+esc(r.last_played || "No data")+'</td></tr>';
  }});
  return html+'</tbody></table></div>';
}}
function historyHtml(p) {{
  if (!p) return "";
  let html = '<h2>'+esc(p.name)+' · Team / Session History</h2>';
  const rows = p.team_history || [];
  if (!rows.length) return html+'<div class="empty">No canonical team-history rows recovered.</div>';
  html += '<div class="scroll"><table><thead><tr><th>Session</th><th>Format</th><th>Team</th><th>SL</th><th>Record</th><th>Status</th></tr></thead><tbody>';
  rows.forEach(r => {{
    html += '<tr><td>'+esc(r.session_name)+'</td><td>'+esc(r.format ? fmtLabel(r.format) : "Unknown")+'</td><td>'+esc(r.team_name || r.team_external_id)+'</td><td>'+esc(num(r.skill_level))+'</td><td>'+esc(r.matches_played===null||r.matches_played===undefined ? "No data" : (r.matches_won||0)+"-"+(r.matches_played-(r.matches_won||0)))+'</td><td>'+esc(r.is_current ? "Current" : "Historical")+'</td></tr>';
  }});
  return html+'</tbody></table></div>';
}}
function computeComparison(aId, bId, fmt) {{
  const a = byId[String(aId)], b = byId[String(bId)];
  if (!a || !b || String(aId) === String(bId)) return {{a,b,direct:null,shared:[]}};
  const af = fmtData(a, fmt) || {{opponents:{{}}}};
  const bf = fmtData(b, fmt) || {{opponents:{{}}}};
  const direct = (af.opponents || {{}})[String(bId)] || null;
  const sharedIds = Object.keys(af.opponents || {{}}).filter(id =>
    (bf.opponents || {{}})[id] && id !== String(aId) && id !== String(bId)
  );
  const shared = sharedIds.map(id => {{
    const left = af.opponents[id], right = bf.opponents[id], opponent = byId[id];
    return {{
      opponent_id:id,
      opponent_name: opponent ? opponent.name : (left.opponent_name || right.opponent_name || id),
      a:left, b:right,
      combined_games:(left.games||0)+(right.games||0)
    }};
  }}).sort((x,y) => y.combined_games-x.combined_games || x.opponent_name.localeCompare(y.opponent_name));
  return {{a,b,direct,shared}};
}}
function directHtml(c, fmt) {{
  let html = '<h2>Direct '+fmtLabel(fmt)+' History</h2>';
  if (!c.a || !c.b) return html+'<div class="empty">Choose two players.</div>';
  if (c.a.player_id === c.b.player_id) return html+'<div class="empty">Choose two different players.</div>';
  if (!c.direct) return html+'<div class="empty">No recorded direct meetings.</div>';
  return html+'<div class="stat-grid"><div class="stat"><span class="muted">'+esc(c.a.name)+' record</span><b>'+esc(c.direct.wins+"-"+c.direct.losses)+'</b></div><div class="stat"><span class="muted">Win rate</span><b>'+esc(pct(c.direct.win_rate))+'</b></div><div class="stat"><span class="muted">Meetings</span><b>'+esc(c.direct.games)+'</b></div><div class="stat"><span class="muted">SL context</span><b>'+esc(num(c.direct.avg_own_skill_level))+' vs '+esc(num(c.direct.avg_opponent_skill_level))+'</b></div></div>';
}}
function sharedHtml(c) {{
  if (!c.a || !c.b || c.a.player_id === c.b.player_id) return '<div class="empty">Choose two different players.</div>';
  if (!c.shared.length) return '<div class="empty">No shared opponents in this format.</div>';
  let html='<table><thead><tr><th>Shared opponent</th><th>'+esc(c.a.name)+' W-L</th><th>'+esc(c.a.name)+' win %</th><th>'+esc(c.b.name)+' W-L</th><th>'+esc(c.b.name)+' win %</th><th>Combined sample</th></tr></thead><tbody>';
  c.shared.forEach(s => {{
    html += '<tr><td>'+esc(s.opponent_name)+'</td><td>'+esc(s.a.wins+"-"+s.a.losses)+'</td><td>'+esc(pct(s.a.win_rate))+'</td><td>'+esc(s.b.wins+"-"+s.b.losses)+'</td><td>'+esc(pct(s.b.win_rate))+'</td><td>'+esc(s.combined_games)+'</td></tr>';
  }});
  return html+'</tbody></table>';
}}
function meetingsHtml(c) {{
  if (!c.direct || !c.direct.meetings || !c.direct.meetings.length) return '<div class="empty">No direct meeting ledger for this pair and format.</div>';
  let html='<div class="scroll"><table><thead><tr><th>Date</th><th>Session</th><th>Result for '+esc(c.a.name)+'</th><th>SL</th><th>Opp SL</th><th>Points</th><th>9-ball balls</th><th>Match id</th></tr></thead><tbody>';
  c.direct.meetings.forEach(m => {{
    const cls=m.result==="W"?"result-win":"result-loss";
    html += '<tr><td>'+esc(m.match_date||"No date")+'</td><td>'+esc(m.session_name)+'</td><td class="'+cls+'">'+esc(m.result)+'</td><td>'+esc(num(m.own_skill_level))+'</td><td>'+esc(num(m.opponent_skill_level))+'</td><td>'+esc(num(m.points_earned))+'</td><td>'+esc(num(m.nine_ball_points))+'</td><td>'+esc(m.match_external_id)+'</td></tr>';
  }});
  return html+'</tbody></table></div>';
}}
function coverageHtml() {{
  const q=DATA.quality||{{}}, cat=DATA.catalog||{{}}, reports=DATA.reports||{{}};
  const limitations=cat.source_limitations||[];
  let html='<h2>Data Coverage & Trust</h2><div class="stat-grid">'
    +'<div class="stat"><span class="muted">Players</span><b>'+esc(DATA.counts.players)+'</b></div>'
    +'<div class="stat"><span class="muted">Canonical players</span><b>'+esc(DATA.counts.canonical_players)+'</b></div>'
    +'<div class="stat"><span class="muted">H2H evidence rows</span><b>'+esc(DATA.counts.head_to_head_rows_used)+'</b></div>'
    +'<div class="stat"><span class="muted">Catalog limitations</span><b>'+esc(limitations.length)+'</b></div>'
    +'</div>';
  html += '<p class="muted">Catalog: '+esc(cat.schema||"not supplied")+'. Scope conflicts: '+esc((q.catalog_scope_conflicts||[]).length)+'. Unsafe historical dates: '+esc(q.head_to_head_rows_with_unsafe_dates||0)+'.</p>';
  const reportKeys=Object.keys(reports);
  if(reportKeys.length) {{
    html += '<h3>Pipeline reports</h3><table><thead><tr><th>Stage</th><th>Status</th><th>Counts</th></tr></thead><tbody>';
    reportKeys.forEach(k => {{
      const r=reports[k]||{{}};
      html += '<tr><td>'+esc(k)+'</td><td>'+esc(r.status||"available")+'</td><td>'+esc(JSON.stringify(r.counts||{{}}))+'</td></tr>';
    }});
    html += '</tbody></table>';
  }}
  if(limitations.length) {{
    html += '<details class="details"><summary>Source limitations ('+limitations.length+')</summary><ul class="quality-list">'+limitations.map(x=>'<li>'+esc(x)+'</li>').join("")+'</ul></details>';
  }}
  return html;
}}
function render() {{
  const fmt=el("format").value;
  const a=byId[el("player-a").value], b=byId[el("player-b").value];
  el("profile-a").innerHTML=profileHtml(a,fmt);
  el("profile-b").innerHTML=profileHtml(b,fmt);
  const comp=computeComparison(a&&a.player_id,b&&b.player_id,fmt);
  el("direct-summary").innerHTML=directHtml(comp,fmt);
  el("shared-opponents").innerHTML=sharedHtml(comp);
  el("meeting-ledger").innerHTML=meetingsHtml(comp);
  el("career-a").innerHTML=careerHtml(a,fmt);
  el("career-b").innerHTML=careerHtml(b,fmt);
  el("history-a").innerHTML=historyHtml(a);
  el("history-b").innerHTML=historyHtml(b);
  el("coverage").innerHTML=coverageHtml();
}}
function refreshSelectors() {{
  const include=el("include-unresolved").checked;
  const oldA=el("player-a").value, oldB=el("player-b").value;
  const rowsA=fillSelect(el("player-a"),el("search-a").value,include,oldA);
  const rowsB=fillSelect(el("player-b"),el("search-b").value,include,oldB);
  if (!el("player-a").value && rowsA.length) el("player-a").value=String(rowsA[0].player_id);
  if (!el("player-b").value && rowsB.length) {{
    const firstDifferent=rowsB.find(p=>String(p.player_id)!==el("player-a").value) || rowsB[0];
    el("player-b").value=String(firstDifferent.player_id);
  }}
  if (el("player-a").value===el("player-b").value && rowsB.length>1) {{
    const alt=rowsB.find(p=>String(p.player_id)!==el("player-a").value);
    if(alt) el("player-b").value=String(alt.player_id);
  }}
  render();
}}
["search-a","search-b"].forEach(id => el(id).addEventListener("input",refreshSelectors));
["player-a","player-b","format"].forEach(id => el(id).addEventListener("change",render));
el("include-unresolved").addEventListener("change",refreshSelectors);
const defaults=canonicalPlayers(false);
fillSelect(el("player-a"),"",false,defaults[0]&&defaults[0].player_id);
fillSelect(el("player-b"),"",false,defaults[1]&&defaults[1].player_id);
if(defaults[0]) el("player-a").value=String(defaults[0].player_id);
if(defaults[1]) el("player-b").value=String(defaults[1].player_id);
else if(defaults[0]) el("player-b").value=String(defaults[0].player_id);
render();
window.__ultimateCoachTestHooks={{computeComparison,refreshSelectors,data:DATA}};
}})();
</script>
</body>
</html>"""


__all__ = ["render_ultimate_coach_scout"]
