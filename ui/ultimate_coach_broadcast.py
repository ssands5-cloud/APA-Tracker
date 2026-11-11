"""Broadcast presentation for the standalone Ultimate Coach page, built from the "APA Pool App Redesign" artifact.

The artifact's header, seven tabs, ticker, scoreboard hero, facts strip and matchup rows are reproduced here with its
own markup, class names and tokens. The Ultimate Coach engine is untouched: every control, id, calculation and
evidence rule of the classic page still runs. This layer only (a) groups the existing sections under the artifact's
seven tabs, and (b) draws the Home screen from a plain-data model the engine publishes (`window.UC_BC_LAST`).

`render(..., ui="classic")` is unchanged and remains the default. The page stays one offline file: no network, no
external fonts (the artifact's Barlow faces are used when installed and fall back to system condensed fonts; embedding
them is pending the owner's permission to bundle the font files).
"""

from __future__ import annotations

import json
from html import escape

# The artifact's seven tabs, in its order, with its own one-line intent for each placeholder.
TABS = (
    ("home", "Home", ""),
    ("schedule", "Schedule Planner", "Plan your lineups across upcoming matches."),
    ("matchnight", "Match Night", "Live response explorer for tonight's put-ups."),
    ("recs", "Recommendations", "Full evidence comparison across the roster."),
    ("threats", "Threats", "Opponent dossiers with recorded concerns."),
    ("team", "Team Status", "Roster availability and skill levels."),
    ("summary", "Summary", "One-minute captain briefing."),
)


def tag(ui: str, tab: str) -> str:
    """Attribute that files an existing element under a tab ('' on the classic page)."""
    return f' data-bc="{tab}"' if ui == "broadcast" else ""


def body_class(ui: str) -> str:
    return " bc" if ui == "broadcast" else ""


def top_markup(ui: str, facts: list[str]) -> str:
    """Artifact header, nav and ticker. Placed right after <body>."""
    if ui != "broadcast":
        return ""
    nav = "".join(
        f'<a class="nav-tab{" active" if key == "home" else ""}" href="#bc-{key}" data-tab="{key}">{escape(label)}</a>'
        for key, label, _ in TABS
    )
    return (
        '<header class="app-header"><a class="logo" href="#bc-home"><span class="logo-mark">UC</span>'
        '<span class="logo-text"><span>ULTIMATE</span><span><b>COACH</b></span></span></a>'
        f'<nav class="main-nav" aria-label="Main">{nav}</nav></header>'
        f'<div class="ticker-wrap" aria-label="Match context"><div class="ticker-track" id="ticker" '
        f'data-facts="{escape(json.dumps(facts), quote=True)}"></div></div>'
    )


def home_markup(ui: str) -> str:
    """Containers the broadcast script draws into (inside <main>)."""
    if ui != "broadcast":
        return ""
    return '<div id="bc-home" class="page-view" aria-label="Home"></div><div id="bc-tabhead" class="section-header" hidden></div>'


def style_markup(ui: str) -> str:
    return f"<style>{CSS}</style>" if ui == "broadcast" else ""


def script_markup(ui: str) -> str:
    return f"<script>{JS}</script>" if ui == "broadcast" else ""


def _hide_rules() -> str:
    rules = ['body.bc[data-view="home"] [data-bc]{display:none!important}']
    for key, _, _ in TABS:
        if key != "home":
            rules.append(f'body.bc[data-view="{key}"] [data-bc]:not([data-bc="{key}"]){{display:none!important}}')
    return "\n".join(rules)


_CSS_BODY = r"""
/* Tokens from the artifact (dark sports dashboard). */
body.bc{--bg:#07090d;--bg-card:#0d1117;--bg-nav:#0a0d13;--bg-ticker:#030507;--fg:#f0f4ff;--fg-dim:#8090a8;--fg-muted:#7a8aa3;
--home:#00d4f0;--away:#ff3d62;--gold:#f5c518;--border:rgba(255,255,255,0.07);--border-hi:rgba(255,255,255,0.14);
--badge-strong-bg:rgba(0,212,240,0.18);--badge-strong-fg:#00d4f0;--badge-thin-bg:rgba(130,140,160,0.15);--badge-thin-fg:#8090a8;
--badge-caution-bg:rgba(245,197,24,0.18);--badge-caution-fg:#f5c518;
--felt:#0e2f3d;--felt-deep:#07151f;--felt-soft:#e3f1f5;--brass:#b8862b;
--cond:'Barlow Condensed','Arial Narrow','Franklin Gothic Medium','Segoe UI',system-ui,sans-serif;
--sans:'Barlow','Segoe UI',system-ui,-apple-system,Roboto,sans-serif;
background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:14px;line-height:1.4}
body.bc header.hero,body.bc nav.sections,body.bc .mn-banner{display:none}
body.bc .vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
/* Header */
body.bc .app-header{position:sticky;top:0;z-index:100;background:var(--bg-nav);border-bottom:1px solid var(--border);display:flex;align-items:stretch}
body.bc .logo{display:flex;align-items:center;gap:10px;padding:0 20px;border-right:1px solid var(--border);flex-shrink:0;text-decoration:none}
body.bc .logo-mark{background:var(--home);color:#000;font-family:var(--cond);font-weight:900;font-size:18px;letter-spacing:-.03em;padding:4px 7px;line-height:1}
body.bc .logo-text{font-family:var(--cond);font-weight:800;font-size:12px;letter-spacing:.12em;color:var(--fg);line-height:1.2;text-transform:uppercase}
body.bc .logo-text span{display:block}
body.bc .main-nav{display:flex;align-items:stretch;flex:1;overflow-x:auto;scrollbar-width:none}
body.bc .main-nav::-webkit-scrollbar{display:none}
body.bc .nav-tab{display:flex;align-items:center;padding:0 16px;min-height:48px;font-family:var(--cond);font-weight:700;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--fg-dim);border-bottom:2px solid transparent;white-space:nowrap;text-decoration:none;transition:color .15s,border-color .15s}
body.bc .nav-tab:hover{color:var(--fg)}
body.bc .nav-tab.active{color:var(--home);border-bottom-color:var(--home)}
body.bc .nav-tab:focus-visible,body.bc .logo:focus-visible{outline:2px solid var(--home);outline-offset:-2px}
/* Ticker */
body.bc .ticker-wrap{background:var(--bg-ticker);border-bottom:1px solid var(--border);padding:7px 0;overflow:hidden;position:relative}
body.bc .ticker-wrap::before,body.bc .ticker-wrap::after{content:'';position:absolute;top:0;width:48px;height:100%;z-index:1}
body.bc .ticker-wrap::before{left:0;background:linear-gradient(90deg,var(--bg-ticker),transparent)}
body.bc .ticker-wrap::after{right:0;background:linear-gradient(-90deg,var(--bg-ticker),transparent)}
body.bc .ticker-track{display:flex;white-space:nowrap;animation:bc-ticker 48s linear infinite;width:max-content}
@keyframes bc-ticker{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
body.bc .ticker-item{font-family:var(--cond);font-weight:600;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--fg-dim);padding:0 18px}
body.bc .ticker-item::before{content:'\25C6 ';color:var(--home);font-size:7px;vertical-align:1px}
@media (prefers-reduced-motion:reduce){body.bc .ticker-track{animation:none}}
/* Content area: dark on Home (the artifact), a light reading surface on the other tabs that hold existing panels. */
body.bc main{max-width:1160px;margin:0 auto;padding:24px max(16px,env(safe-area-inset-right,0px)) 40px max(16px,env(safe-area-inset-left,0px));width:100%}
body.bc:not([data-view="home"]) main{background:#f4f1ea;color:#17221c;margin-top:18px;border-radius:6px}
body.bc .page-foot{color:var(--fg-muted)}
body.bc:not([data-view="home"]) .page-foot{color:#5b6a61}
body.bc .freshness{padding:10px max(16px,env(safe-area-inset-left,0px));max-width:1160px;margin:12px auto 0}
body.bc #bc-home{display:none}
body.bc[data-view="home"] #bc-home,body.bc[data-view="all"] #bc-home{display:block}
body.bc[data-view="home"] main>:not(#bc-home):not(.page-foot){display:none}
/* Section header for the non-home tabs */
body.bc .section-header{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:14px}
body.bc .section-header[hidden]{display:none}
body.bc #bc-tabhead .section-title{font-family:var(--cond);font-weight:900;font-style:italic;font-size:clamp(24px,3.2vw,32px);letter-spacing:.02em;text-transform:uppercase;color:#07151f;margin:0}
body.bc #bc-tabhead .section-sub{font-size:13px;color:#4a5a52}
/* Home: hero */
body.bc .match-hero{display:grid;grid-template-columns:1fr auto 1fr;border:1px solid var(--border);border-radius:6px;overflow:hidden;margin-bottom:2px;min-height:200px}
body.bc .team-panel{padding:24px 28px 28px;display:flex;flex-direction:column;justify-content:flex-end;position:relative;min-width:0}
body.bc .team-panel-home{background:linear-gradient(135deg,#061e1e 0%,#04141a 60%,#0a0d11 100%)}
body.bc .team-panel-away{background:linear-gradient(225deg,#1c0609 0%,#120408 60%,#0a0d11 100%);text-align:right;align-items:flex-end}
body.bc .team-breadcrumb{position:absolute;top:16px;left:20px;font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--fg-muted)}
body.bc .team-breadcrumb span{color:var(--fg-dim)}
body.bc .team-breadcrumb-away{position:absolute;top:16px;right:20px;font-family:var(--cond);font-size:10px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:var(--away);opacity:.9}
body.bc .team-mono{font-family:var(--cond);font-weight:900;font-style:italic;font-size:clamp(52px,8vw,88px);line-height:.92;letter-spacing:-.03em;margin-bottom:10px}
body.bc .team-mono-home{color:var(--home)}body.bc .team-mono-away{color:var(--away)}
body.bc .team-pick{display:block;max-width:100%}
body.bc .team-name-select{appearance:none;-webkit-appearance:none;background-color:transparent;border:0;border-bottom:1px dashed var(--border-hi);border-radius:0;color:var(--fg);font-family:var(--cond);font-weight:800;font-size:clamp(16px,2.4vw,24px);letter-spacing:.05em;text-transform:uppercase;line-height:1.15;padding:2px 22px 2px 0;margin:0;width:100%;max-width:100%;text-overflow:ellipsis;cursor:pointer;background-image:linear-gradient(45deg,transparent 50%,var(--fg-dim) 50%),linear-gradient(135deg,var(--fg-dim) 50%,transparent 50%);background-position:calc(100% - 9px) 55%,calc(100% - 4px) 55%;background-size:5px 5px,5px 5px;background-repeat:no-repeat}
body.bc .team-panel-away .team-name-select{text-align:right;text-align-last:right}
body.bc .team-name-select option{background:#0d1117;color:#f0f4ff;text-transform:none}
body.bc .team-name-select:focus-visible{outline:2px solid var(--home);outline-offset:3px}
body.bc .match-center{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px 16px;background:#07090d;border-left:1px solid var(--border);border-right:1px solid var(--border);min-width:160px;gap:12px}
body.bc .badge-prematch{font-family:var(--cond);font-weight:800;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#000;background:var(--gold);padding:4px 10px;border-radius:2px}
body.bc .vs-circle{width:52px;height:52px;border-radius:50%;background:#0f1218;border:2px solid var(--border-hi);display:flex;align-items:center;justify-content:center;font-family:var(--cond);font-weight:900;font-size:16px;letter-spacing:.05em;color:var(--fg-dim)}
body.bc .match-datetime{font-family:var(--cond);font-weight:600;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--fg-dim);text-align:center;line-height:1.5}
/* Facts strip */
body.bc .match-stats{display:grid;grid-template-columns:repeat(4,1fr);background:var(--bg-card);border:1px solid var(--border);border-top:none;border-radius:0 0 6px 6px;margin-bottom:28px;overflow:hidden}
body.bc .stat-cell{padding:14px 20px;border-right:1px solid var(--border);min-width:0}
body.bc .stat-cell:last-child{border-right:none}
body.bc .stat-label{font-family:var(--cond);font-weight:600;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--fg-muted);margin-bottom:4px}
body.bc .stat-label label{font:inherit;letter-spacing:inherit;text-transform:inherit;color:inherit;display:inline}
body.bc .stat-value{font-family:var(--cond);font-weight:800;font-size:17px;letter-spacing:.03em;text-transform:uppercase;color:var(--fg);overflow-wrap:anywhere}
body.bc .stat-value.dim{color:var(--fg-dim)}
body.bc .cap-input{background:transparent;border:0;border-bottom:1px dashed var(--border-hi);border-radius:0;color:var(--fg);font:800 17px var(--cond);letter-spacing:.03em;width:7em;padding:0;margin:0;text-transform:uppercase;box-shadow:none}
body.bc .cap-input::placeholder{color:var(--fg-dim);text-transform:uppercase}
body.bc .cap-input:focus-visible{outline:2px solid var(--home);outline-offset:2px}
/* Matchup rows */
body.bc .home-head .section-title{font-family:var(--cond);font-weight:900;font-style:italic;font-size:clamp(22px,3vw,30px);letter-spacing:.02em;text-transform:uppercase;color:var(--fg);margin:0}
body.bc .section-link{font-family:var(--cond);font-weight:700;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--home);text-decoration:none;white-space:nowrap}
body.bc .section-link:hover{opacity:.75}
body.bc .matchup-list{display:flex;flex-direction:column;gap:3px;padding:0;margin:0;list-style:none}
body.bc .matchup-row{display:grid;grid-template-columns:36px 1fr auto 1fr auto;align-items:center;gap:16px;background:var(--bg-card);border:1px solid var(--border);border-radius:4px;padding:14px 20px;color:inherit;text-align:left;font:inherit;width:100%;cursor:pointer;transition:border-color .15s}
body.bc .matchup-row:hover,body.bc .matchup-row:focus-visible{border-color:var(--border-hi);background:var(--bg-card)}
body.bc .matchup-row:focus-visible{outline:2px solid var(--home);outline-offset:2px}
body.bc .matchup-row.lead{border-left:3px solid var(--gold)}
body.bc .matchup-num{font-family:var(--cond);font-weight:800;font-size:18px;color:var(--fg-muted);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
body.bc .matchup-our,body.bc .matchup-their{min-width:0}
body.bc .matchup-kicker{font-size:9px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--fg-muted);margin-bottom:2px}
body.bc .matchup-player{font-family:var(--cond);font-weight:800;font-size:20px;letter-spacing:.02em;text-transform:uppercase;color:var(--fg);line-height:1.1;overflow-wrap:anywhere}
body.bc .matchup-sl{font-family:var(--sans);font-weight:600;font-size:11px;color:var(--fg-dim);letter-spacing:.06em;margin-left:6px}
body.bc .matchup-bars{display:flex;flex-direction:column;gap:6px;width:200px;flex-shrink:0}
body.bc .bar-row{display:flex;align-items:center;gap:8px;font-variant-numeric:tabular-nums}
body.bc .bar-pct{font-family:var(--cond);font-weight:700;font-size:11px;color:var(--fg-dim);width:44px;text-align:right;flex-shrink:0}
body.bc .bar-track{flex:1;height:4px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden}
body.bc .bar-fill-home{height:100%;background:var(--home);border-radius:2px}
body.bc .bar-fill-away{height:100%;background:var(--away);border-radius:2px}
body.bc .bar-note{font-size:10.5px;color:var(--fg-dim);letter-spacing:.04em;text-align:center}
body.bc .matchup-their{text-align:right}
body.bc .matchup-kicker-away{color:var(--away);opacity:.9}
body.bc .evidence-badge{font-family:var(--cond);font-weight:800;font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:4px 10px;border-radius:3px;border:1px solid transparent;white-space:nowrap;flex-shrink:0}
body.bc .badge-strong{background:var(--badge-strong-bg);color:var(--badge-strong-fg);border-color:rgba(0,212,240,.25)}
body.bc .badge-solid{background:rgba(0,200,160,.15);color:#00c8a0;border-color:rgba(0,200,160,.25)}
body.bc .badge-thin,body.bc .badge-unknown{background:var(--badge-thin-bg);color:var(--badge-thin-fg);border-color:rgba(130,140,160,.2)}
body.bc .badge-caution,body.bc .badge-conflicted{background:var(--badge-caution-bg);color:var(--badge-caution-fg);border-color:rgba(245,197,24,.3)}
body.bc .matchup-why{grid-column:2/-1;font-size:12px;color:var(--fg-dim);margin-top:-6px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
body.bc .matchup-footnote{font-size:11px;color:var(--fg-muted);margin:10px 0 0;line-height:1.5}
body.bc .home-empty{padding:28px 20px;color:var(--fg-dim);font-size:14px;border:1px dashed var(--border-hi);border-radius:4px}
body.bc .card-feature{border-top-color:#0e2f3d}
body.bc .section-title h2{color:#07151f}
@media (max-width:740px){
  body.bc .match-hero{grid-template-columns:1fr}
  body.bc .match-center{flex-direction:row;border-left:none;border-right:none;border-top:1px solid var(--border);border-bottom:1px solid var(--border);min-width:unset;padding:14px 20px}
  body.bc .team-panel-away{text-align:left;align-items:flex-start}
  body.bc .team-panel-away .team-name-select{text-align:left;text-align-last:left}
  body.bc .team-mono{font-size:52px}
  body.bc .match-stats{grid-template-columns:repeat(2,1fr)}
  body.bc .match-stats .stat-cell:nth-child(2){border-right:none}
  body.bc .matchup-row{grid-template-columns:28px 1fr 1fr;grid-template-rows:auto auto;gap:10px 12px}
  body.bc .matchup-bars{width:100%;grid-column:1/-1;grid-row:2}
  body.bc .matchup-their{grid-column:3;grid-row:1}
  body.bc .evidence-badge{grid-column:3;grid-row:1;align-self:end;justify-self:end}
  body.bc .matchup-why{grid-column:1/-1;grid-row:3;margin-top:0}
}
@media (max-width:480px){
  body.bc .nav-tab{padding:0 10px;font-size:11px}body.bc .logo{padding:0 12px}
}
@media print{body.bc .app-header,body.bc .ticker-wrap,body.bc #bc-home,body.bc #bc-tabhead{display:none!important}
  body.bc [data-bc]{display:revert!important}body.bc main{background:#fff!important;color:#000!important}}
"""

CSS = _CSS_BODY + _hide_rules() + "\n"


_JS_BODY = r"""
(function(){
  var body=document.body;
  if(!body.classList.contains("bc")) return;
  var TABS=%TABS%;
  var names=TABS.map(function(t){return t[0];}).concat(["all"]);
  var current="home";
  function $(id){return document.getElementById(id);}
  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
  function tabOf(el){var w=el&&el.closest?el.closest("[data-bc]"):null;return w?w.getAttribute("data-bc"):null;}

  /* ---------- tabs and hash routing ---------- */
  var navTabs=Array.prototype.slice.call(document.querySelectorAll(".nav-tab"));
  function show(name){
    if(names.indexOf(name)<0) name="home";
    current=name; body.setAttribute("data-view",name);
    navTabs.forEach(function(t){var on=t.getAttribute("data-tab")===name;t.classList.toggle("active",on);if(on) t.setAttribute("aria-current","page"); else t.removeAttribute("aria-current");});
    var head=$("bc-tabhead"),meta=TABS.filter(function(t){return t[0]===name;})[0];
    if(head){
      if(meta&&name!=="home"){head.hidden=false;head.innerHTML='<h2 class="section-title">'+esc(meta[1])+'</h2><span class="section-sub">'+esc(meta[2])+'</span>';}
      else {head.hidden=true;head.innerHTML="";}
    }
  }
  function route(){
    var id=decodeURIComponent((location.hash||"").slice(1)),view=null,target=null;
    if(id.indexOf("bc-")===0&&names.indexOf(id.slice(3))>=0) view=id.slice(3);
    else if(id){target=$(id);view=tabOf(target);}
    if(!view&&target) view=current;
    if(current==="all"&&id.indexOf("bc-")!==0) view="all";
    show(view||current);
    if(target){window.setTimeout(function(){target.scrollIntoView();},0);} else if(view){window.scrollTo(0,0);}
  }
  var nativeScroll=Element.prototype.scrollIntoView;
  Element.prototype.scrollIntoView=function(){
    var v=tabOf(this); if(v&&v!==current&&current!=="all") show(v);
    return nativeScroll.apply(this,arguments);
  };
  window.addEventListener("hashchange",route);

  /* ---------- ticker ---------- */
  function ticker(m){
    var el=$("ticker"); if(!el) return;
    var facts=[]; try{facts=JSON.parse(el.getAttribute("data-facts")||"[]");}catch(e){}
    var dyn=[];
    if(m&&!m.empty){
      dyn.push(m.ourName+" vs "+m.theirName,m.format,m.dateText);
      dyn.push(m.cap?"Reference Cap "+m.cap:"Reference Cap not entered");
      dyn.push(m.rostered+" vs "+m.theirRostered+" Captured Players");
    }
    var items=dyn.concat(facts),html=items.map(function(t){return '<span class="ticker-item">'+esc(t)+'</span>';}).join("");
    el.innerHTML=html+html;
  }

  /* ---------- Home ---------- */
  function mono(name){
    var w=String(name||"").replace(/[^A-Za-z0-9 ]/g," ").split(/\s+/).filter(Boolean);
    if(w.length>=2) return (w[0].charAt(0)+w[1].charAt(0)).toUpperCase();
    return (w[0]||"?").slice(0,2).toUpperCase();
  }
  function pct(w,g){return g>0&&w!=null?Math.round(1000*w/g)/10:null;}
  function badgeClass(level){return "badge-"+String(level||"unknown").toLowerCase();}
  // Team options read "Name · Session · Format · Div · N rostered". The hero shows the name, and adds
  // the format and division only where two teams share a name.
  function opts(sel){
    var src=$(sel); if(!src) return "";
    var all=Array.prototype.map.call(src.options,function(o){return o.text.split(" · ");});
    var count={};all.forEach(function(p){count[p[0]]=(count[p[0]]||0)+1;});
    return Array.prototype.map.call(src.options,function(o,i){
      var p=all[i],label=o.value?(count[p[0]]>1?p.slice(0,4).join(" · "):p[0]):o.text;
      return '<option value="'+esc(o.value)+'">'+esc(label)+'</option>';}).join("");
  }
  function relay(id,value){var s=$(id);if(!s) return;s.value=value;s.dispatchEvent(new Event("change",{bubbles:true}));}
  function openNight(theirId){
    show("matchnight");
    if(theirId){var chip=document.querySelector('#next-send .ns-chip[data-next="'+String(theirId).replace(/"/g,'\\"')+'"]');if(chip) chip.click();}
    if(location.hash!=="#bc-matchnight") history.replaceState(null,"","#bc-matchnight");
    window.scrollTo(0,0);
  }
  function rowHtml(r,lead){
    var our=esc(r.our)+(r.ourSl!=null?'<span class="matchup-sl">SL '+esc(r.ourSl)+'</span>':'');
    var their=esc(r.their)+(r.theirSl!=null?'<span class="matchup-sl">SL '+esc(r.theirSl)+'</span>':'');
    var g=r.games||0,w=r.wins,own=pct(w,g),opp=g>0?pct(g-w,g):null;
    var note=g>0?(w+"-"+(g-w)+" direct · "+g+(g===1?" meeting":" meetings")+(g<3?" · small sample":"")):"No direct meetings · see Match Night for shared-opponent evidence";
    var bars='<div class="matchup-bars" role="img" aria-label="Recorded head-to-head: '+esc(note)+'">'
      +'<div class="bar-row"><span class="bar-pct">'+(own==null?"—":own.toFixed(0)+"%")+'</span><div class="bar-track"><div class="bar-fill-home" style="width:'+(own||0)+'%"></div></div></div>'
      +'<div class="bar-row"><span class="bar-pct">'+(opp==null?"—":opp.toFixed(0)+"%")+'</span><div class="bar-track"><div class="bar-fill-away" style="width:'+(opp||0)+'%"></div></div></div>'
      +'<div class="bar-note">'+esc(note)+'</div></div>';
    if(lead){
      return '<li><button type="button" class="matchup-row lead" data-lead="1" aria-label="If we put up first, send '+esc(r.our)+'. '+esc(r.level)+' evidence.">'
        +'<div class="matchup-num" aria-hidden="true">▶</div>'
        +'<div class="matchup-our"><div class="matchup-kicker">If we put up first</div><div class="matchup-player">'+esc(r.our)+'</div></div>'
        +'<div></div><div></div>'
        +'<span class="evidence-badge '+badgeClass(r.level)+'">'+esc(r.level)+'</span>'+(r.why?'<div class="matchup-why">'+esc(r.why)+'</div>':'')+'</button></li>';
    }
    return '<li><button type="button" class="matchup-row" data-their="'+esc(r.theirId||"")+'" aria-label="'+esc("If they put up "+r.their+", send "+r.our+". "+r.level+" evidence. Open in Match Night.")+'">'
      +'<div class="matchup-num">'+(r.n<10?"0":"")+r.n+'</div>'
      +'<div class="matchup-our"><div class="matchup-kicker">Our Answer</div><div class="matchup-player">'+our+'</div></div>'
      +bars
      +'<div class="matchup-their"><div class="matchup-kicker matchup-kicker-away">They Put Up</div><div class="matchup-player">'+their+'</div></div>'
      +'<span class="evidence-badge '+badgeClass(r.level)+'">'+esc(r.level)+'</span>'
      +(r.why?'<div class="matchup-why">'+esc(r.why)+(r.cost?' · '+esc(r.cost):'')+'</div>':'')+'</button></li>';
  }
  function renderHome(m){
    var el=$("bc-home"); if(!el) return;
    var keepFocus=document.activeElement&&document.activeElement.id==="bc-cap";
    var ready=m&&!m.empty;
    var ourName=ready?m.ourName:"Choose your team",theirName=ready?m.theirName:"Choose an opponent";
    var played=ready?(m.played||0):0,left=ready?m.gamesLeft:null;
    var status=!ready?"No Matchup":(left===0?"Final":(played>0?"In Progress":"Pre-Match"));
    var side=ready&&m.side?(m.side==="home"?"Home":"Away"):"";
    var capVal=ready&&m.cap?m.cap:"";
    var hero='<div class="match-hero" aria-label="Fixture">'
      +'<div class="team-panel team-panel-home"><span class="team-breadcrumb">'+(side?esc(side)+' &rsaquo; ':'')+'<span>Your Team</span></span>'
      +'<div class="team-mono team-mono-home" aria-hidden="true">'+esc(mono(ourName))+'</div>'
      +'<label class="team-pick"><span class="vh">Our team</span><select id="bc-team-a" class="team-name-select">'+opts("team-a")+'</select></label></div>'
      +'<div class="match-center"><span class="badge-prematch">'+esc(status)+'</span><div class="vs-circle">VS</div>'
      +'<div class="match-datetime">'+esc(ready?m.dateText:"Pick a matchup")+'</div></div>'
      +'<div class="team-panel team-panel-away"><span class="team-breadcrumb-away">Opponent</span>'
      +'<div class="team-mono team-mono-away" aria-hidden="true">'+esc(mono(theirName))+'</div>'
      +'<label class="team-pick"><span class="vh">Opponent team</span><select id="bc-team-b" class="team-name-select">'+opts("team-b")+'</select></label></div></div>';
    var stats='<div class="match-stats" aria-label="Match details">'
      +'<div class="stat-cell"><div class="stat-label">Match Date</div><div class="stat-value">'+esc(ready?m.dateText:"—")+'</div></div>'
      +'<div class="stat-cell"><div class="stat-label">Format</div><div class="stat-value">'+esc(ready?m.format:"—")+'</div></div>'
      +'<div class="stat-cell"><div class="stat-label"><label for="bc-cap">Reference Cap</label></div><input id="bc-cap" class="cap-input" type="number" min="1" inputmode="numeric" placeholder="Not entered" value="'+esc(capVal)+'"'+(ready?'':' disabled')+'></div>'
      +'<div class="stat-cell"><div class="stat-label">Venue</div><div class="stat-value'+(ready&&m.venue?'':' dim')+'">'+esc(ready&&m.venue?m.venue:"Not Captured")+'</div></div></div>';
    var rows="";
    if(ready){
      rows=(m.lead?rowHtml({our:m.lead.our,level:m.lead.level,why:m.lead.why},true):"")+m.rows.map(function(r){return rowHtml(r,false);}).join("");
      if(!m.rows.length) rows+='<li><div class="home-empty">'+esc(m.gamesLeft?"No legal send fits the entered skill cap — check the cap and remaining skill levels.":"No games left to plan tonight.")+'</div></li>';
    } else rows='<li><div class="home-empty">'+esc((m&&m.note&&m.note.text)||"Choose your team and an opponent above, or pick a fixture in Schedule Planner. The matchup rows and recommendations appear here.")+'</div></li>';
    var head='<div class="section-header home-head"><h2 class="section-title">Key Matchups</h2><a class="section-link" href="#bc-recs">Full Stat Sheet →</a></div>';
    var foot='<p class="matchup-footnote">Evidence strength within the conditional plan; not a predicted win or loss. Bars show recorded head-to-head results with their sample size, not odds.</p>';
    el.innerHTML=hero+stats+head+'<ul class="matchup-list" role="list">'+rows+'</ul>'+foot;
    var a=$("bc-team-a"),b=$("bc-team-b"),cap=$("bc-cap");
    if(a){if(ready) a.value=m.ourKey; else if($("team-a")) a.value=$("team-a").value; a.onchange=function(){relay("team-a",a.value);};}
    if(b){if(ready) b.value=m.theirKey; else if($("team-b")) b.value=$("team-b").value; b.onchange=function(){relay("team-b",b.value);};}
    if(cap){cap.oninput=function(){var c=$("ll-cap");if(c){c.value=cap.value;c.dispatchEvent(new Event("input",{bubbles:true}));}};
      if(keepFocus){cap.focus();try{cap.setSelectionRange(cap.value.length,cap.value.length);}catch(e){}}}
    Array.prototype.forEach.call(el.querySelectorAll(".matchup-row"),function(btn){btn.onclick=function(){openNight(btn.getAttribute("data-their"));};});
  }
  window.UC_BC={render:function(m){renderHome(m);ticker(m);}};
  show("home");
  renderHome(window.UC_BC_LAST||null); ticker(window.UC_BC_LAST||null);
  route();
})();
"""

JS = _JS_BODY.replace("%TABS%", json.dumps([list(t) for t in TABS]))
