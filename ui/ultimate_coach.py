"""Render the standalone offline Ultimate Coach Scout & Compare cockpit."""

from __future__ import annotations

import json
from html import escape
from typing import Any


def _script_json(value: Any) -> str:
    """Serialize for embedding inside <script type="application/json">.

    json.dumps(..., ensure_ascii=True) (the default) already backslash-
    escapes every non-ASCII character -- including U+2028/U+2029 LINE/
    PARAGRAPH SEPARATOR -- as \\uXXXX, so those never reach the page as raw
    bytes. What it does NOT do is touch plain ASCII '<', '>', '&', which is
    exactly what a source string containing a literal "</script>" or
    "<script>" needs to break out of this element. JSON syntax itself never
    uses '<', '>', or '&' outside a quoted string value, so replacing them
    globally in the dumped text only ever rewrites string CONTENT, never
    JSON structure -- and \\uXXXX is valid inside a JSON string, so
    JSON.parse() on the browser side reconstructs the original character
    exactly. This closes the '<script>'/'&entity;' cases the previous
    "</"-only replacement did not cover, without weakening JSON.parse
    compatibility at all.
    """
    text = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _trust_card(payload: dict[str, Any]) -> str:
    """Server-rendered Data Trust/Coverage summary.

    Static per payload -- no client-side JS needed for this card, and it
    degrades gracefully (all zero counts, no crash) if rendered against an
    older payload shape that never carried a "trust" section at all.
    """
    trust = payload.get("trust") or {}

    def n(key: str) -> int:
        return int(trust.get(key) or 0)

    return f"""<div class="card">
  <h2>Data Trust &amp; Coverage</h2>
  <div class="metric-grid">
    <div class="metric"><b>{n('verified_identity_count')}</b><span>Verified selectable identities</span></div>
    <div class="metric"><b>{n('identity_exclusion_count')}</b><span>Identities excluded (unresolved/ambiguous)</span></div>
    <div class="metric"><b>{n('identity_verified_game_count')}</b><span>Identity-verified games usable as evidence</span></div>
    <div class="metric"><b>{n('quarantined_game_count')}</b><span>Games quarantined (not used as evidence)</span></div>
    <div class="metric"><b>{n('suspect_participant_count')}</b><span>Suspect participant rows</span></div>
    <div class="metric"><b>{n('indeterminate_participant_count')}</b><span>Indeterminate participant rows</span></div>
    <div class="metric"><b>{n('source_coverage_issue_count')}</b><span>Source coverage issues (contract-level)</span></div>
  </div>
  <p class="muted">Only players with roster-backed, uniquely-verified identity provenance are selectable below. Only games that are both mirror-verified and identity-verified feed direct/shared-opponent evidence. Quarantined or unresolved evidence is counted above, never silently dropped or blended in.</p>
</div>"""


def render(payload: dict[str, Any], *, built_at: str = "") -> str:
    data = _script_json(payload)
    player_count = int((payload.get("counts") or {}).get("players") or 0)
    evidence_count = int((payload.get("counts") or {}).get("head_to_head_rows") or 0)
    trust_card = _trust_card(payload)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ultimate Coach — Scout & Compare</title>
<style>
:root {{ color-scheme: light; }}
body {{ font-family: system-ui,-apple-system,Segoe UI,sans-serif; margin:0; background:#f5f7fb; color:#18202b; }}
header {{ background:#162b4d; color:white; padding:18px 22px; }}
header h1 {{ margin:0; font-size:26px; }}
header p {{ margin:5px 0 0; opacity:.85; }}
main {{ max-width:1400px; margin:auto; padding:18px; }}
.card {{ background:white; border:1px solid #dfe5ee; border-radius:10px; padding:16px; margin-bottom:16px; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
.controls {{ display:grid; grid-template-columns:1fr 1fr 180px; gap:12px; }}
label {{ font-size:12px; font-weight:700; color:#526070; display:block; }}
select,input[type="search"] {{ width:100%; margin-top:5px; padding:10px; font-size:15px; box-sizing:border-box; }}
input[type="search"] {{ margin-bottom:6px; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.metric-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:8px; }}
.metric {{ background:#f5f7fb; border-radius:7px; padding:10px; }}
.metric b {{ display:block; font-size:19px; color:#162b4d; }}
.metric span {{ font-size:11px; color:#687688; }}
.tag {{ display:inline-block; padding:3px 7px; border-radius:999px; background:#e9eef7; margin:2px; font-size:12px; }}
.warn {{ background:#fff7df; border-left:5px solid #b78300; padding:10px 12px; }}
.good {{ background:#edf8f0; border-left:5px solid #27813b; padding:10px 12px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ padding:7px 8px; border-bottom:1px solid #e7ebf0; text-align:left; }}
th {{ color:#566274; font-size:11px; text-transform:uppercase; }}
.muted {{ color:#6b7582; font-size:12px; }}
h2,h3 {{ margin-top:0; }}
@media(max-width:760px) {{ .controls,.grid {{ grid-template-columns:1fr; }} }}
</style></head>
<body>
<header><h1>Ultimate Coach — Scout & Compare</h1>
<p>{player_count} verified players · {evidence_count} identity-verified evidence rows · offline scouting cockpit</p></header>
<main>
{trust_card}
<div class="card">
  <div class="controls">
    <label>Player A<input id="search-a" type="search" placeholder="Search player A"><select id="player-a"></select></label>
    <label>Player B<input id="search-b" type="search" placeholder="Search player B"><select id="player-b"></select></label>
    <label>Format<select id="format"><option value="EIGHT">8-Ball</option><option value="NINE">9-Ball</option></select></label>
  </div>
</div>
<div id="status" class="card warn"></div>
<div class="grid">
  <div id="profile-a" class="card"></div>
  <div id="profile-b" class="card"></div>
</div>
<div id="direct" class="card"></div>
<div id="shared" class="card"></div>
<div id="meetings" class="card"></div>
<p class="muted">Built {escape(built_at) if built_at else "from the selected SQLite snapshot"}. This page shows recorded APA facts and derived comparisons only. No matchup probability is displayed until a separately back-tested calibration gate passes.</p>
</main>
<script id="uc-data" type="application/json">{data}</script>
<script>
(function() {{
  var DATA=JSON.parse(document.getElementById("uc-data").textContent);
  var PLAYERS={{}}; DATA.players.forEach(function(p){{PLAYERS[String(p.id)]=p;}});
  var A=document.getElementById("player-a"), B=document.getElementById("player-b"), F=document.getElementById("format");
  function esc(v){{return String(v===null||v===undefined?"":v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}}
  function pct(w,g){{return g?((w/g)*100).toFixed(1)+"%":"No data";}}
  var SORTED=DATA.players.slice().sort(function(x,y){{return x.name.localeCompare(y.name);}});
  function options(filter){{var q=String(filter||"").trim().toLowerCase();return SORTED.filter(function(p){{return !q||p.name.toLowerCase().indexOf(q)!==-1;}}).map(function(p){{return '<option value="'+p.id+'">'+esc(p.name)+'</option>';}}).join("");}}
  function applySearch(input,select){{var previous=select.value;select.innerHTML=options(input.value);if(Array.prototype.some.call(select.options,function(o){{return o.value===previous;}}))select.value=previous;compare();}}
  A.innerHTML=options(""); B.innerHTML=options(""); if(B.options.length>1) B.selectedIndex=1;

  function rowsFor(pid,fmt){{return DATA.evidence.filter(function(r){{return String(r.player_id)===String(pid)&&r.format===fmt;}});}}
  function record(rows){{var w=rows.filter(function(r){{return r.result==="W";}}).length;return {{w:w,l:rows.length-w,g:rows.length}};}}
  function career(p,fmt){{return (p.career_stats||[]).filter(function(r){{return r.format===fmt;}});}}
  function profile(p,fmt) {{
    var c=career(p,fmt), totalW=0,totalG=0; c.forEach(function(r){{if(r.matches_won!==null) totalW+=r.matches_won;if(r.matches_played!==null) totalG+=r.matches_played;}});
    var teams=(p.team_history||[]).slice().reverse().slice(0,12);
    return '<h2>'+esc(p.name)+'</h2>'
      +'<div class="metric-grid"><div class="metric"><b>'+(p.current_skill_level===null?'—':p.current_skill_level)+'</b><span>Current captured SL</span></div>'
      +'<div class="metric"><b>'+(c.length?(totalW+'-'+Math.max(0,totalG-totalW)):'No recorded evidence')+'</b><span>League-scoped lifetime '+esc(fmt)+' W-L</span></div>'
      +'<div class="metric"><b>'+(c.length?pct(totalW,totalG):'—')+'</b><span>Lifetime win rate</span></div></div>'
      +'<h3>League stats</h3>'+(c.length?'<table><thead><tr><th>League</th><th>W-L</th><th>Last played</th><th>B&R</th><th>Mini slams</th></tr></thead><tbody>'
        +c.map(function(r){{var w=r.matches_won||0,g=r.matches_played||0;return '<tr><td>'+esc(r.league_slug||r.league_id)+'</td><td>'+w+'-'+Math.max(0,g-w)+'</td><td>'+esc(r.last_played||'—')+'</td><td>'+esc(r.break_and_runs===null?'—':r.break_and_runs)+'</td><td>'+esc(r.mini_slams===null?'—':r.mini_slams)+'</td></tr>';}}).join('')+'</tbody></table>':'<p class="muted">No league-scoped lifetime stats captured for this format.</p>')
      +'<h3>Recent team/session history</h3>'+(teams.length?teams.map(function(t){{return '<span class="tag">'+esc(t.session_name||'Unknown session')+' · '+esc(t.team_name||'Unknown team')+(t.skill_level!==null?' · SL '+t.skill_level:'')+'</span>';}}).join(''):'<p class="muted">No team history captured.</p>');
  }}
  function compare() {{
    var pa=PLAYERS[A.value], pb=PLAYERS[B.value], fmt=F.value;
    if(!pa||!pb) return;
    document.getElementById("profile-a").innerHTML=profile(pa,fmt);
    document.getElementById("profile-b").innerHTML=profile(pb,fmt);
    var ar=rowsFor(pa.id,fmt), br=rowsFor(pb.id,fmt);
    var direct=ar.filter(function(r){{return String(r.opponent_id)===String(pb.id);}});
    var dr=record(direct);
    document.getElementById("direct").innerHTML='<h2>Direct history</h2><div class="metric-grid"><div class="metric"><b>'+(dr.g?(dr.w+'-'+dr.l):'No recorded evidence')+'</b><span>'+esc(pa.name)+' record vs '+esc(pb.name)+'</span></div><div class="metric"><b>'+(dr.g?pct(dr.w,dr.g):'—')+'</b><span>Observed direct win rate</span></div><div class="metric"><b>'+dr.g+'</b><span>Recorded meetings</span></div></div>';
    var ag={{}},bg={{}}; ar.forEach(function(r){{(ag[String(r.opponent_id)]||(ag[String(r.opponent_id)]=[])).push(r);}}); br.forEach(function(r){{(bg[String(r.opponent_id)]||(bg[String(r.opponent_id)]=[])).push(r);}});
    var ids=Object.keys(ag).filter(function(id){{return bg[id]&&id!==String(pa.id)&&id!==String(pb.id);}});
    var sharedRows=ids.map(function(id){{var p=PLAYERS[id],ra=record(ag[id]),rb=record(bg[id]);return '<tr><td>'+esc(p?p.name:id)+'</td><td>'+ra.w+'-'+ra.l+' ('+pct(ra.w,ra.g)+')</td><td>'+rb.w+'-'+rb.l+' ('+pct(rb.w,rb.g)+')</td><td>'+ra.g+' / '+rb.g+'</td></tr>';}}).join('');
    document.getElementById("shared").innerHTML='<h2>Shared-opponent evidence</h2>'+(ids.length?'<p class="muted">'+ids.length+' opponent(s) both players have actually faced in '+esc(fmt)+'.</p><table><thead><tr><th>Shared opponent</th><th>'+esc(pa.name)+'</th><th>'+esc(pb.name)+'</th><th>Samples A/B</th></tr></thead><tbody>'+sharedRows+'</tbody></table>':'<p class="muted">No recorded shared opponents in this format.</p>');
    var meetings=direct.slice().sort(function(x,y){{return String(y.match_date).localeCompare(String(x.match_date));}});
    document.getElementById("meetings").innerHTML='<h2>Recorded meetings</h2>'+(meetings.length?'<table><thead><tr><th>Date</th><th>Session</th><th>Result</th><th>SL</th><th>Opponent SL</th><th>Points</th></tr></thead><tbody>'+meetings.map(function(r){{return '<tr><td>'+esc(r.match_date||'—')+'</td><td>'+esc(r.session_name||'—')+'</td><td>'+esc(r.result)+'</td><td>'+esc(r.own_skill_level===null?'—':r.own_skill_level)+'</td><td>'+esc(r.opponent_skill_level===null?'—':r.opponent_skill_level)+'</td><td>'+esc(r.points_earned===null?'—':r.points_earned)+'</td></tr>';}}).join('')+'</tbody></table>':'<p class="muted">These players have no recorded direct meeting in this format.</p>');
    document.getElementById("status").innerHTML='<strong>Probability status: NOT CALIBRATED.</strong> Scout & Compare is showing real source evidence only. The future odds model must pass chronological backtesting before a percentage appears here.';
  }}
  [A,B,F].forEach(function(el){{el.addEventListener("change",compare);}});
  document.getElementById("search-a").addEventListener("input",function(){{applySearch(this,A);}});
  document.getElementById("search-b").addEventListener("input",function(){{applySearch(this,B);}});
  compare();
}})();
</script></body></html>"""
