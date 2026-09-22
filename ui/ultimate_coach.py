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


_BROWSER_EVIDENCE_FIELDS = (
    "opponent_id",
    "match_date",
    "session_name",
    "result",
    "own_skill_level",
    "opponent_skill_level",
    "points_earned",
)


def _browser_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Compact and pre-index evidence for fast standalone-browser use."""
    compact = {key: value for key, value in payload.items() if key != "evidence"}
    index: dict[str, list[list[Any]]] = {}
    for row in payload.get("evidence") or []:
        key = f"{row.get('player_id')}|{row.get('format') or ''}"
        index.setdefault(key, []).append(
            [row.get(field) for field in _BROWSER_EVIDENCE_FIELDS]
        )
    compact["browser_payload_schema"] = "ultimate-coach-browser-compact-v1"
    compact["evidence_row_fields"] = list(_BROWSER_EVIDENCE_FIELDS)
    compact["evidence_index"] = index
    return compact


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
    data = _script_json(_browser_payload(payload))
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
    <label>Player A<input id="search-a" type="search" placeholder="Search player A"><select id="player-a"></select><span id="search-status-a" class="muted"></span></label>
    <label>Player B<select id="player-b-scope" aria-label="Player B pool"><option value="played">Played opponents</option><option value="all">All players</option></select><input id="search-b" type="search" placeholder="Search player B"><select id="player-b"></select><span id="search-status-b" class="muted"></span></label>
    <label>Format<select id="format"><option value="EIGHT">8-Ball</option><option value="NINE">9-Ball</option></select></label>
  </div>
</div>
<div id="status" class="card warn"></div>
<div class="grid">
  <div id="profile-a" class="card"></div>
  <div id="profile-b" class="card"></div>
</div>
<div id="summary" class="card"></div>
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
  var EVIDENCE_INDEX=DATA.evidence_index||{{}};
  var EVIDENCE_FIELDS=DATA.evidence_row_fields||[];
  var EC={{}}; EVIDENCE_FIELDS.forEach(function(name,i){{EC[name]=i;}});
  var A=document.getElementById("player-a"), B=document.getElementById("player-b"), F=document.getElementById("format");
  var BSCOPE=document.getElementById("player-b-scope");
  var SA=document.getElementById("search-a"), SB=document.getElementById("search-b");
  var SSA=document.getElementById("search-status-a"), SSB=document.getElementById("search-status-b");
  var MAX_OPTIONS=75;
  var SEARCH_DEBOUNCE_MS=300;
  function esc(v){{return String(v===null||v===undefined?"":v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}}
  function pct(w,g){{return g?((w/g)*100).toFixed(1)+"%":"No data";}}
  function val(row,name){{return row[EC[name]];}}
  var SORTED=DATA.players.slice().sort(function(x,y){{return x.name.localeCompare(y.name);}});
  var SEARCH_NAMES={{}}; SORTED.forEach(function(p){{SEARCH_NAMES[String(p.id)]=p.name.toLowerCase();}});

  function formatName(fmt){{return fmt==="EIGHT"?"8-Ball":fmt==="NINE"?"9-Ball":fmt;}}
  function matchingPlayers(filter,candidates) {{
    var q=String(filter||"").trim().toLowerCase();
    var matches=(candidates||SORTED).filter(function(p){{return !q||SEARCH_NAMES[String(p.id)].indexOf(q)!==-1;}});
    return {{rows:matches.slice(0,MAX_OPTIONS),total:matches.length}};
  }}
  function selectMarkup(found,previous,labeler) {{
    var keep=previous&&found.rows.some(function(p){{return String(p.id)===String(previous);}});
    var placeholder='<option value="">Select a player...</option>';
    var rows=found.rows.map(function(p){{return '<option value="'+p.id+'">'+esc(labeler?labeler(p):p.name)+'</option>';}}).join("");
    return {{html:placeholder+rows,value:keep?String(previous):""}};
  }}
  function applyPlayerASearch() {{
    var previous=A.value, found=matchingPlayers(SA.value,SORTED);
    var rendered=selectMarkup(found,previous,null);
    A.innerHTML=rendered.html;
    A.value=rendered.value;
    SSA.textContent=found.total>MAX_OPTIONS
      ? "Showing first "+MAX_OPTIONS+" of "+found.total+" matches. Keep typing, then choose a player."
      : found.total+" matching player"+(found.total===1?"":"s")+". Choose a player to load opponents.";
  }}
  function rowsFor(pid,fmt){{return EVIDENCE_INDEX[String(pid)+"|"+fmt]||[];}}
  function playerBPool() {{
    var playerA=String(A.value||"");
    if(!playerA) return {{players:[],counts:{{}}}};
    if(BSCOPE.value==="all") {{
      return {{players:SORTED.filter(function(p){{return String(p.id)!==playerA;}}),counts:{{}}}};
    }}
    var counts={{}};
    rowsFor(playerA,F.value).forEach(function(r){{
      var id=String(val(r,"opponent_id"));
      if(id!==playerA&&PLAYERS[id]) counts[id]=(counts[id]||0)+1;
    }});
    return {{
      players:SORTED.filter(function(p){{return !!counts[String(p.id)];}}),
      counts:counts
    }};
  }}
  function refreshPlayerB(preserveSelection) {{
    var previous=preserveSelection?B.value:"";
    var pool=playerBPool(), found=matchingPlayers(SB.value,pool.players);
    var rendered=selectMarkup(found,previous,function(p){{
      var count=pool.counts[String(p.id)]||0;
      var suffix=BSCOPE.value==="played"&&count
        ? " · "+count+" meeting"+(count===1?"":"s")
        : "";
      return p.name+suffix;
    }});
    B.innerHTML=rendered.html;
    B.value=rendered.value;
    var pa=PLAYERS[A.value], fmt=formatName(F.value);
    if(BSCOPE.value==="played") {{
      if(!pool.players.length) {{
        SSB.textContent="No recorded opponents for "+(pa?pa.name:"Player A")+" in "+fmt+".";
      }} else if(String(SB.value||"").trim()) {{
        SSB.textContent=found.total+" matching of "+pool.players.length+" recorded opponent"+(pool.players.length===1?"":"s")+".";
      }} else {{
        SSB.textContent=pool.players.length+" recorded opponent"+(pool.players.length===1?"":"s")+" for "+(pa?pa.name:"Player A")+" in "+fmt+".";
      }}
    }} else {{
      SSB.textContent=found.total>MAX_OPTIONS
        ? "Showing first "+MAX_OPTIONS+" of "+found.total+" players. Keep typing to narrow."
        : found.total+" matching player"+(found.total===1?"":"s")+" (all-player scouting).";
    }}
  }}
  applyPlayerASearch();
  refreshPlayerB(false);
  function record(rows){{var w=rows.filter(function(r){{return val(r,"result")==="W";}}).length;return {{w:w,l:rows.length-w,g:rows.length}};}}
  function career(p,fmt){{return (p.career_stats||[]).filter(function(r){{return r.format===fmt;}});}}
  function profile(p,fmt) {{
    var c=career(p,fmt), totalW=0,totalG=0; c.forEach(function(r){{if(r.matches_won!==null) totalW+=r.matches_won;if(r.matches_played!==null) totalG+=r.matches_played;}});
    var teams=(p.team_history||[]).slice().reverse().slice(0,12);
    return '<h2>'+esc(p.name)+'</h2>'
      +'<div class="metric-grid"><div class="metric"><b>'+(p.current_skill_level===null?'—':p.current_skill_level)+'</b><span>Current captured SL</span></div>'
      +'<div class="metric"><b>'+(c.length?(totalW+'-'+Math.max(0,totalG-totalW)):'Pending')+'</b><span>League-scoped lifetime '+esc(fmt)+' W-L</span></div>'
      +'<div class="metric"><b>'+(c.length?pct(totalW,totalG):'—')+'</b><span>Lifetime win rate</span></div></div>'
      +'<h3>League stats</h3>'+(c.length?'<table><thead><tr><th>League</th><th>W-L</th><th>Last played</th><th>B&R</th><th>Mini slams</th></tr></thead><tbody>'
        +c.map(function(r){{var w=r.matches_won||0,g=r.matches_played||0;return '<tr><td>'+esc(r.league_slug||r.league_id)+'</td><td>'+w+'-'+Math.max(0,g-w)+'</td><td>'+esc(r.last_played||'—')+'</td><td>'+esc(r.break_and_runs===null?'—':r.break_and_runs)+'</td><td>'+esc(r.mini_slams===null?'—':r.mini_slams)+'</td></tr>';}}).join('')+'</tbody></table>':'<p class="muted">Career-stat enrichment is still in progress for this build. Historical match evidence below is already usable.</p>')
      +'<h3>Recent team/session history</h3>'+(teams.length?teams.map(function(t){{return '<span class="tag">'+esc(t.session_name||'Unknown session')+' · '+esc(t.team_name||'Unknown team')+(t.skill_level!==null?' · SL '+t.skill_level:'')+'</span>';}}).join(''):'<p class="muted">No team history captured.</p>');
  }}

  function compare() {{
    var pa=PLAYERS[A.value], pb=PLAYERS[B.value], fmt=F.value;
    if(!pa) return;
    document.getElementById("profile-a").innerHTML=profile(pa,fmt);
    if(!pb) {{
      document.getElementById("profile-b").innerHTML='<h2>No opponent selected</h2><p class="muted">'+(BSCOPE.value==="played"?'No recorded opponent is available for '+esc(pa.name)+' in '+esc(formatName(fmt))+'.':'Search or choose a Player B to compare.')+'</p>';
      document.getElementById("summary").innerHTML='<h2>What we know</h2><p><strong>'+(BSCOPE.value==="played"?'No recorded opponents for '+esc(pa.name)+' in '+esc(formatName(fmt))+'. Switch Player B to “All players” for broader scouting.':'Choose Player B to compare with '+esc(pa.name)+'.')+'</strong></p>';
      document.getElementById("direct").innerHTML='';
      document.getElementById("shared").innerHTML='';
      document.getElementById("meetings").innerHTML='';
      document.getElementById("status").innerHTML='<strong>Probability status: NOT CALIBRATED.</strong> Scout & Compare is showing real source evidence only. The future odds model must pass chronological backtesting before a percentage appears here.';
      return;
    }}
    document.getElementById("profile-b").innerHTML=profile(pb,fmt);
    if(String(pa.id)===String(pb.id)) {{
      document.getElementById("summary").innerHTML='<h2>What we know</h2><p>Choose two different players to compare.</p>';
      document.getElementById("direct").innerHTML='';
      document.getElementById("shared").innerHTML='';
      document.getElementById("meetings").innerHTML='';
      return;
    }}

    var ar=rowsFor(pa.id,fmt), br=rowsFor(pb.id,fmt);
    var direct=ar.filter(function(r){{return String(val(r,"opponent_id"))===String(pb.id);}});
    var dr=record(direct);
    var ag={{}},bg={{}};
    ar.forEach(function(r){{var id=String(val(r,"opponent_id"));(ag[id]||(ag[id]=[])).push(r);}});
    br.forEach(function(r){{var id=String(val(r,"opponent_id"));(bg[id]||(bg[id]=[])).push(r);}});
    var ids=Object.keys(ag).filter(function(id){{return bg[id]&&id!==String(pa.id)&&id!==String(pb.id);}});
    ids.sort(function(x,y){{return (ag[y].length+bg[y].length)-(ag[x].length+bg[x].length);}});

    var summaryText=dr.g
      ? esc(pa.name)+' and '+esc(pb.name)+' have '+dr.g+' recorded direct meeting'+(dr.g===1?'':'s')+' in '+esc(fmt)+'.'
      : 'No recorded direct meeting between '+esc(pa.name)+' and '+esc(pb.name)+' in '+esc(fmt)+'.';
    summaryText+=' '+(ids.length
      ? 'They share '+ids.length+' recorded opponent'+(ids.length===1?'':'s')+', so you still have indirect history to compare.'
      : 'No shared-opponent evidence is recorded for this format.');
    document.getElementById("summary").innerHTML='<h2>What we know</h2><p><strong>'+summaryText+'</strong></p>'
      +'<div class="metric-grid"><div class="metric"><b>'+ar.length+'</b><span>'+esc(pa.name)+' evidence rows in '+esc(fmt)+'</span></div>'
      +'<div class="metric"><b>'+br.length+'</b><span>'+esc(pb.name)+' evidence rows in '+esc(fmt)+'</span></div>'
      +'<div class="metric"><b>'+dr.g+'</b><span>Direct meetings</span></div>'
      +'<div class="metric"><b>'+ids.length+'</b><span>Shared opponents</span></div></div>';

    document.getElementById("direct").innerHTML='<h2>Direct history</h2><div class="metric-grid"><div class="metric"><b>'+(dr.g?(dr.w+'-'+dr.l):'No recorded evidence')+'</b><span>'+esc(pa.name)+' record vs '+esc(pb.name)+'</span></div><div class="metric"><b>'+(dr.g?pct(dr.w,dr.g):'—')+'</b><span>Observed direct win rate</span></div><div class="metric"><b>'+dr.g+'</b><span>Recorded meetings</span></div></div>';

    var visibleIds=ids.slice(0,100);
    var sharedRows=visibleIds.map(function(id){{var p=PLAYERS[id],ra=record(ag[id]),rb=record(bg[id]);return '<tr><td>'+esc(p?p.name:id)+'</td><td>'+ra.w+'-'+ra.l+' ('+pct(ra.w,ra.g)+')</td><td>'+rb.w+'-'+rb.l+' ('+pct(rb.w,rb.g)+')</td><td>'+ra.g+' / '+rb.g+'</td></tr>';}}).join('');
    var limitNote=ids.length>visibleIds.length?'<p class="muted">Showing the 100 shared opponents with the largest combined samples.</p>':'';
    document.getElementById("shared").innerHTML='<h2>Shared-opponent evidence</h2>'+(ids.length?'<p class="muted">'+ids.length+' opponent(s) both players have actually faced in '+esc(fmt)+'.</p>'+limitNote+'<table><thead><tr><th>Shared opponent</th><th>'+esc(pa.name)+'</th><th>'+esc(pb.name)+'</th><th>Samples A/B</th></tr></thead><tbody>'+sharedRows+'</tbody></table>':'<p class="muted">No recorded shared opponents in this format.</p>');

    var meetings=direct.slice().sort(function(x,y){{return String(val(y,"match_date")).localeCompare(String(val(x,"match_date")));}});
    document.getElementById("meetings").innerHTML='<h2>Recorded meetings</h2>'+(meetings.length?'<table><thead><tr><th>Date</th><th>Session</th><th>Result</th><th>SL</th><th>Opponent SL</th><th>Points</th></tr></thead><tbody>'+meetings.map(function(r){{return '<tr><td>'+esc(val(r,"match_date")||'—')+'</td><td>'+esc(val(r,"session_name")||'—')+'</td><td>'+esc(val(r,"result"))+'</td><td>'+esc(val(r,"own_skill_level")===null?'—':val(r,"own_skill_level"))+'</td><td>'+esc(val(r,"opponent_skill_level")===null?'—':val(r,"opponent_skill_level"))+'</td><td>'+esc(val(r,"points_earned")===null?'—':val(r,"points_earned"))+'</td></tr>';}}).join('')+'</tbody></table>':'<p class="muted">These players have no recorded direct meeting in this format.</p>');

    document.getElementById("status").innerHTML='<strong>Probability status: NOT CALIBRATED.</strong> Scout & Compare is showing real source evidence only. The future odds model must pass chronological backtesting before a percentage appears here.';
  }}

  A.addEventListener("change",function(){{SB.value="";refreshPlayerB(false);compare();}});
  B.addEventListener("change",compare);
  F.addEventListener("change",function(){{SB.value="";refreshPlayerB(false);compare();}});
  BSCOPE.addEventListener("change",function(){{SB.value="";refreshPlayerB(false);compare();}});
  var searchTimers={{a:null,b:null}};
  SA.addEventListener("input",function(){{
    clearTimeout(searchTimers.a);
    searchTimers.a=setTimeout(function(){{
      applyPlayerASearch();
    }},SEARCH_DEBOUNCE_MS);
  }});
  SB.addEventListener("input",function(){{
    clearTimeout(searchTimers.b);
    searchTimers.b=setTimeout(function(){{
      refreshPlayerB(true);
    }},SEARCH_DEBOUNCE_MS);
  }});
  compare();
}})();
</script></body></html>"""
