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


def _browser_payload(
    payload: dict[str, Any], *, consume_evidence: bool = False
) -> dict[str, Any]:
    """Compact and pre-index evidence for fast standalone-browser use.

    Production builders may drain the large raw evidence list while it is
    compacted so the dict-heavy source rows and compact browser index do not
    remain resident in memory at the same time.
    """
    compact = {key: value for key, value in payload.items() if key != "evidence"}
    index: dict[str, list[list[Any]]] = {}
    evidence = payload.get("evidence") or []
    if consume_evidence and isinstance(evidence, list):
        while evidence:
            row = evidence.pop()
            key = f"{row.get('player_id')}|{row.get('format') or ''}"
            index.setdefault(key, []).append(
                [row.get(field) for field in _BROWSER_EVIDENCE_FIELDS]
            )
    else:
        for row in evidence:
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


def render(
    payload: dict[str, Any], *, built_at: str = "", consume_evidence: bool = False
) -> str:
    data = _script_json(_browser_payload(payload, consume_evidence=consume_evidence))
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

<div class="card">
  <h2>Team vs Team — Match Night Lineup</h2>
  <div class="controls">
    <label>Our Team<input id="search-team-a" type="search" placeholder="Search our team"><select id="team-a"></select><span id="search-status-team-a" class="muted"></span></label>
    <label>Opponent Team<input id="search-team-b" type="search" placeholder="Search opponent team"><select id="team-b"></select><span id="search-status-team-b" class="muted"></span></label>
    <label>Format<select id="team-format"><option value="EIGHT">8-Ball</option><option value="NINE">9-Ball</option></select></label>
  </div>
</div>
<div id="team-rosters" class="grid"></div>
<div id="team-matchups" class="card"></div>
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
    var seenTeamTags={{}};
    var teams=(p.team_history||[]).slice().reverse().filter(function(t){{
      var tag=[t.session_name||"",t.team_name||"",t.skill_level===null?"":t.skill_level].join("|");
      if(seenTeamTags[tag]) return false;
      seenTeamTags[tag]=true;
      return true;
    }}).slice(0,12);
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

  // ---- Team vs Team ----
  // Rosters are derived entirely from data already embedded above
  // (p.team_history) -- no additional server payload, so this carries no
  // extra memory cost for the standalone build. Built once at load, not
  // per keystroke: same responsive-search contract as Player A/B (debounced
  // input, capped rendered options, no expensive work while typing).
  function teamScopeKey(t){{
    return [String(t.team_external_id||t.team_name||""),String(t.division_id||""),String(t.session_name||"")].join("|");
  }}
  function teamDisplay(team){{
    var parts=[team.name];
    if(team.session_name) parts.push(team.session_name);
    if(team.division_id) parts.push("Div "+team.division_id);
    return parts.join(" · ");
  }}
  var TEAM_INDEX=(function(){{
    var idx={{}};
    DATA.players.forEach(function(p){{
      (p.team_history||[]).forEach(function(t){{
        if(!t.is_current||!t.team_name) return;
        var key=teamScopeKey(t);
        if(!idx[key]) idx[key]={{
          key:key,
          name:t.team_name,
          team_external_id:t.team_external_id||"",
          division_id:t.division_id||"",
          session_name:t.session_name||"",
          seen:{{}},
          players:[]
        }};
        // Team display names are not identities. Same-named teams in
        // different divisions/sessions remain separate roster scopes.
        // Within one exact scope, dedupe repeated history rows by player id.
        if(idx[key].seen[p.id]) return;
        idx[key].seen[p.id]=true;
        var sl=p.current_skill_level!==null&&p.current_skill_level!==undefined?p.current_skill_level:t.skill_level;
        idx[key].players.push({{id:p.id,name:p.name,skill_level:sl,skill_level_is_live:p.current_skill_level!==null&&p.current_skill_level!==undefined,matches_won:t.matches_won,matches_played:t.matches_played}});
      }});
    }});
    return idx;
  }})();
  var TEAM_KEYS=Object.keys(TEAM_INDEX).sort(function(x,y){{return teamDisplay(TEAM_INDEX[x]).localeCompare(teamDisplay(TEAM_INDEX[y]));}});
  var TEAM_SEARCH_NAMES={{}}; TEAM_KEYS.forEach(function(k){{TEAM_SEARCH_NAMES[k]=teamDisplay(TEAM_INDEX[k]).toLowerCase();}});
  var TA=document.getElementById("team-a"),TB=document.getElementById("team-b"),TF=document.getElementById("team-format");
  var STA=document.getElementById("search-team-a"),STB=document.getElementById("search-team-b");
  var SSTA=document.getElementById("search-status-team-a"),SSTB=document.getElementById("search-status-team-b");
  var STANDARD_SKILL_CAP=23;

  function matchingTeams(filter) {{
    var q=String(filter||"").trim().toLowerCase();
    var matches=TEAM_KEYS.filter(function(k){{return !q||TEAM_SEARCH_NAMES[k].indexOf(q)!==-1;}});
    return {{rows:matches.slice(0,MAX_OPTIONS),total:matches.length}};
  }}
  function teamSelectMarkup(found,previous) {{
    var keep=previous&&found.rows.indexOf(previous)!==-1;
    var placeholder='<option value="">Select a team...</option>';
    var rows=found.rows.map(function(k){{var team=TEAM_INDEX[k];return '<option value="'+esc(k)+'">'+esc(teamDisplay(team))+' · '+team.players.length+' rostered</option>';}}).join("");
    return {{html:placeholder+rows,value:keep?previous:""}};
  }}
  function applyTeamSearch(input,select,status) {{
    var previous=select.value,found=matchingTeams(input.value);
    var rendered=teamSelectMarkup(found,previous);
    select.innerHTML=rendered.html;
    select.value=rendered.value;
    status.textContent=found.total>MAX_OPTIONS
      ? "Showing first "+MAX_OPTIONS+" of "+found.total+" matches. Keep typing, then choose a team."
      : found.total+" matching team"+(found.total===1?"":"s")+".";
  }}
  applyTeamSearch(STA,TA,SSTA);
  applyTeamSearch(STB,TB,SSTB);

  function rosterTable(title,team,fmt) {{
    if(!team) return '<h2>'+esc(title)+'</h2><p class="muted">Choose a team to load its current roster.</p>';
    var known=team.players.filter(function(m){{return m.skill_level!==null&&m.skill_level!==undefined;}});
    var totalSkill=known.reduce(function(sum,m){{return sum+m.skill_level;}},0);
    var totalNote=known.length===team.players.length
      ? 'full-roster skill total '+totalSkill
      : 'full-roster skill total '+totalSkill+' from '+known.length+' of '+team.players.length+' players with a captured skill level (missing players excluded, not counted as 0)';
    var rows=team.players.slice().sort(function(x,y){{return (y.skill_level||0)-(x.skill_level||0);}}).map(function(m){{
      var evid=rowsFor(m.id,fmt).length;
      var slLabel=m.skill_level===null||m.skill_level===undefined?'—':(m.skill_level+(m.skill_level_is_live?'':'*'));
      return '<tr><td>'+esc(m.name)+'</td><td>'+slLabel+'</td><td>'+(m.matches_won===null||m.matches_played===null?'—':m.matches_won+'-'+Math.max(0,m.matches_played-m.matches_won))+'</td><td>'+evid+'</td></tr>';
    }}).join("");
    var liveMissing=team.players.some(function(m){{return !m.skill_level_is_live&&m.skill_level!==null&&m.skill_level!==undefined;}});
    return '<h2>'+esc(title)+'</h2><p class="muted">'+esc(teamDisplay(team))+' · '+team.players.length+' rostered · '+totalNote+
      ' (not a 5-player lineup total — this data source does not capture your division\\'s actual modified skill cap; the commonly used APA default is '+STANDARD_SKILL_CAP+' for a 5-player team, verify against your own division rules).'+
      (liveMissing?' * = division-scoped skill level, no live current rating captured for that player.':'')+'</p>'+
      '<table><thead><tr><th>Player</th><th>Current SL</th><th>Current W-L</th><th>Evidence rows ('+esc(formatName(fmt))+')</th></tr></thead><tbody>'+rows+'</tbody></table>';
  }}

  function sharedOpponentRecord(rowsA,rowsB) {{
    var oppRowsA={{}};
    rowsA.forEach(function(r){{var id=String(val(r,"opponent_id"));(oppRowsA[id]||(oppRowsA[id]=[])).push(r);}});
    var oppIdsB={{}};
    rowsB.forEach(function(r){{oppIdsB[String(val(r,"opponent_id"))]=true;}});
    var shared=[],combined=[];
    Object.keys(oppRowsA).forEach(function(id){{
      if(oppIdsB[id]) {{ shared.push(id); combined=combined.concat(oppRowsA[id]); }}
    }});
    return {{sharedCount:shared.length,record:record(combined)}};
  }}

  function bestSendFor(opponent,ourRoster,fmt) {{
    var oppRows=rowsFor(opponent.id,fmt);
    var candidates=ourRoster.map(function(p){{
      var direct=rowsFor(p.id,fmt).filter(function(r){{return String(val(r,"opponent_id"))===String(opponent.id);}});
      if(direct.length) {{
        var dr=record(direct);
        return {{player:p,kind:"direct",count:direct.length,record:dr,rank:[3,dr.g?dr.w/dr.g:0,dr.g]}};
      }}
      var shared=sharedOpponentRecord(rowsFor(p.id,fmt),oppRows);
      if(shared.sharedCount) {{
        var sr=shared.record;
        return {{player:p,kind:"shared",sharedCount:shared.sharedCount,record:sr,rank:[2,sr.g?sr.w/sr.g:0,shared.sharedCount]}};
      }}
      return {{player:p,kind:"none",rank:[1,0,0]}};
    }});
    candidates.sort(function(x,y){{
      for(var i=0;i<3;i++) {{ if(y.rank[i]!==x.rank[i]) return y.rank[i]-x.rank[i]; }}
      return 0;
    }});
    return candidates;
  }}

  function explainSend(opponent,candidates) {{
    var best=candidates[0];
    if(best.kind==="direct") {{
      return esc(best.player.name)+' — strongest evidence-backed option: '+best.record.w+'-'+best.record.l+' direct ('+best.count+' meeting'+(best.count===1?'':'s')+') vs '+esc(opponent.name)+'.';
    }}
    if(best.kind==="shared") {{
      var tie=candidates.filter(function(c){{return c.kind==="shared"&&c.sharedCount===best.sharedCount&&c.record.g===best.record.g;}});
      if(tie.length>1) return 'Insufficient evidence to distinguish '+tie.map(function(c){{return esc(c.player.name);}}).join(' / ')+' against '+esc(opponent.name)+' — no direct history; '+best.sharedCount+' shared opponent(s) each, evidence too similar to rank.';
      return esc(best.player.name)+' — no direct history vs '+esc(opponent.name)+'; best-supported by '+best.sharedCount+' shared-opponent result'+(best.sharedCount===1?'':'s')+' ('+best.record.w+'-'+best.record.l+' vs those shared opponents).';
    }}
    return 'No direct or shared-opponent evidence for any of our roster against '+esc(opponent.name)+' in this format yet.';
  }}

  function renderTeamMatchups() {{
    var ta=TEAM_INDEX[TA.value],tb=TEAM_INDEX[TB.value],fmt=TF.value;
    document.getElementById("team-rosters").innerHTML=
      '<div class="card">'+rosterTable("Our roster",ta,fmt)+'</div>'+
      '<div class="card">'+rosterTable("Opponent roster",tb,fmt)+'</div>';
    var out=document.getElementById("team-matchups");
    if(!ta||!tb) {{
      out.innerHTML='<h2>Recommended sends</h2><p class="muted">Choose both teams to see evidence-backed send recommendations per opponent player.</p>';
      return;
    }}
    if(!ta.players.length||!tb.players.length) {{
      out.innerHTML='<h2>Recommended sends</h2><p class="muted">One of these rosters has no current players captured — insufficient roster data to recommend sends.</p>';
      return;
    }}
    var rows=tb.players.map(function(opp){{
      var candidates=bestSendFor(opp,ta.players,fmt);
      return '<tr><td>'+esc(opp.name)+(opp.skill_level===null||opp.skill_level===undefined?'':' (SL '+opp.skill_level+')')+'</td><td>'+explainSend(opp,candidates)+'</td></tr>';
    }}).join("");
    out.innerHTML='<h2>Recommended sends</h2>'+
      '<p class="muted">Per opponent player, the best-supported send from our roster. Captain-assistance only — never a solved optimal lineup and never a win-probability claim; probability_publication stays FORBIDDEN throughout.</p>'+
      '<table><thead><tr><th>Opponent player</th><th>Suggested send &amp; evidence</th></tr></thead><tbody>'+rows+'</tbody></table>';
  }}
  renderTeamMatchups();

  TA.addEventListener("change",renderTeamMatchups);
  TB.addEventListener("change",renderTeamMatchups);
  TF.addEventListener("change",renderTeamMatchups);
  var teamSearchTimers={{a:null,b:null}};
  STA.addEventListener("input",function(){{
    clearTimeout(teamSearchTimers.a);
    teamSearchTimers.a=setTimeout(function(){{applyTeamSearch(STA,TA,SSTA);}},SEARCH_DEBOUNCE_MS);
  }});
  STB.addEventListener("input",function(){{
    clearTimeout(teamSearchTimers.b);
    teamSearchTimers.b=setTimeout(function(){{applyTeamSearch(STB,TB,SSTB);}},SEARCH_DEBOUNCE_MS);
  }});
}})();
</script></body></html>"""
