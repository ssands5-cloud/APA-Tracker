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
    return (
        '<div id="bc-home" class="page-view" aria-label="Home"></div><div id="bc-tabhead" class="section-header" hidden></div>'
        '<div id="bc-night" aria-label="Match Night board"></div>'
        '<section id="bc-league" data-bc="summary" aria-label="League table and results"></section>'
    )


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
body.bc main{color:var(--fg)}
body.bc .page-foot{color:var(--fg-muted)}
body.bc .freshness{padding:10px max(16px,env(safe-area-inset-left,0px));max-width:1160px;margin:12px auto 0}
body.bc #bc-home{display:none}
body.bc[data-view="home"] #bc-home,body.bc[data-view="all"] #bc-home{display:block}
@media screen{body.bc[data-view="home"] main>:not(#bc-home):not(.page-foot){display:none}}
/* Section header for the non-home tabs */
body.bc .section-header{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:14px}
body.bc .section-header[hidden]{display:none}
body.bc #bc-tabhead .section-title{font-family:var(--cond);font-weight:900;font-style:italic;font-size:clamp(24px,3.2vw,32px);letter-spacing:.02em;text-transform:uppercase;color:var(--fg);margin:0}
body.bc #bc-tabhead .section-sub{font-size:13px;color:var(--fg-dim)}
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
@media print{body.bc .app-header,body.bc .ticker-wrap,body.bc #bc-home,body.bc #bc-tabhead,body.bc #bc-night{display:none!important}
  body.bc main{background:#fff!important;color:#000!important;margin:0!important}body.bc{background:#fff!important;color:#000!important}}
"""

_CSS_DARK = r"""
/* Existing panels, re-themed to the artifact: same components and ids, dark surfaces, the artifact's accents. */
body.bc{--paper:#07090d;--card:#0d1117;--ink:#f0f4ff;--muted:#8a99b0;--line:rgba(255,255,255,.09);--line-strong:rgba(255,255,255,.2);
--felt:#0f5f73;--felt-deep:#0a3f4f;--felt-soft:rgba(0,212,240,.12);--brass-soft:rgba(245,197,24,.1);--warn-bg:rgba(245,197,24,.1);--warn-line:#f5c518;--info-bg:rgba(0,212,240,.08);--info-line:#00d4f0}
body.bc .card,body.bc .match-plan,body.bc .next-send,body.bc .pair,body.bc .fixture,body.bc .scout,body.bc .viewer-box,body.bc .metric,body.bc details.start-here{background:var(--card);color:var(--fg);border-color:var(--border);box-shadow:none}
body.bc .card{border-radius:6px}
body.bc .card-feature{border-top:3px solid var(--home)}
body.bc h1,body.bc h2,body.bc h3,body.bc h4,body.bc .section-title h2,body.bc .mp-name{color:var(--fg)}
body.bc .section-title{border-bottom:1px solid var(--border);padding-bottom:6px}
body.bc .section-title h2,body.bc .card h2,body.bc .card-head h2{font-family:var(--cond);font-weight:900;font-style:italic;letter-spacing:.02em;text-transform:uppercase}
body.bc .muted,body.bc .section-title p,body.bc .mp-sub,body.bc .mp-why{color:var(--fg-dim)}
body.bc label,body.bc .legend{color:var(--fg-dim)}
body.bc a{color:var(--home)}
body.bc select,body.bc input[type="search"],body.bc input[type="date"],body.bc input[type="number"],body.bc input[type="text"],body.bc textarea{background:#111826;color:var(--fg);border:1px solid var(--border-hi)}
body.bc select:focus,body.bc input:focus,body.bc textarea:focus{outline:2px solid var(--home);border-color:var(--home)}
body.bc select:disabled,body.bc input:disabled{background:#0b0f16;color:var(--fg-muted)}
body.bc select.plan,body.bc textarea.plan,body.bc input#ll-cap{background:rgba(245,197,24,.08);color:var(--gold);border-color:rgba(245,197,24,.45)}
body.bc table{color:var(--fg)}
body.bc th{background:#101722;color:var(--fg-dim);border-bottom:1px solid var(--border)}
body.bc td{border-bottom:1px solid var(--border)}
body.bc tbody tr:nth-child(even) td{background:rgba(255,255,255,.025)}
body.bc .matrix th a{color:var(--home)}
body.bc .pill,body.bc .tag,body.bc .badge{background:rgba(0,212,240,.12);color:var(--home);border-color:rgba(0,212,240,.25)}
body.bc .badge.side{background:var(--home);color:#000}
body.bc button.chip,body.bc button.secondary{background:transparent;color:var(--fg);border-color:var(--border-hi)}
body.bc button.chip:hover,body.bc button.secondary:hover,body.bc button.chip[aria-pressed="true"]{background:rgba(0,212,240,.14)}
body.bc .warn,body.bc .note.warn-note{background:var(--warn-bg);color:var(--gold)}
body.bc .good{background:rgba(0,200,160,.1);color:#00c8a0;border-left-color:#00c8a0}
body.bc .note{color:var(--fg)}
body.bc .freshness span{background:var(--card);color:var(--fg-dim);border-color:var(--border)}
body.bc .freshness .badge-uncal{background:rgba(245,197,24,.1);color:var(--gold);border-color:rgba(245,197,24,.3)}
body.bc details.disclosure{border-top-color:var(--border)}
body.bc details.disclosure summary,body.bc .match-plan details summary{color:var(--home)}
body.bc .match-plan,body.bc .next-send{border-left-color:var(--home)}
body.bc .mp-label,body.bc .fixture dt,body.bc .metric span{color:var(--fg-muted)}
body.bc .metric b,body.bc .fixture-when,body.bc .fixture-vs b{color:var(--fg)}
body.bc .viewer-box{background:rgba(245,197,24,.06)}
body.bc .viewer-box label{color:var(--gold)}
body.bc .ns-budget{background:rgba(245,197,24,.1);color:var(--gold)}
body.bc .ns-coach{background:rgba(0,212,240,.08);color:var(--fg)}
body.bc .quick-read{background:rgba(245,197,24,.08);color:var(--fg)}
body.bc .quick-read-badges span,body.bc .ns-chip{background:var(--bg-card);color:var(--fg);border-color:var(--border-hi)}
body.bc .ns-chip.on{background:var(--away);color:#000}
body.bc .cat-border-G,body.bc .cat-border-R,body.bc .cat-border-E,body.bc .cat-border-I{background:transparent}
body.bc .legend,body.bc .table-wrap{color:var(--fg-dim)}
body.bc .mcell{color:#102018}
body.bc .roster-head,body.bc .page-foot{color:var(--fg-dim)}
body.bc #player-section .card{background:var(--card)}
body.bc table td{color:var(--fg)}
body.bc table td:first-child{color:var(--fg)}
body.bc .quick-read b{color:var(--gold)}
body.bc details.start-here summary,body.bc details.start-here summary b{color:var(--fg)}
body.bc .mv-toggle{border-color:var(--border-hi)}
body.bc .mv-toggle button{background:transparent;color:var(--fg-dim);border:0}
body.bc .mv-toggle button[aria-pressed="true"]{background:var(--home);color:#000}
body.bc .matrix tbody th,body.bc .matrix thead th{color:var(--fg)}
"""

_CSS_LEAGUE = r"""
body.bc #bc-league:empty{display:none}
body.bc #bc-league{margin:0 0 16px}
body.bc .league-grid{display:grid;grid-template-columns:1.4fr 1fr;gap:14px}
body.bc .league-card{background:var(--bg-card);border:1px solid var(--border);border-radius:6px;padding:14px 16px;min-width:0}
body.bc .league-card h3{margin:0 0 4px;font-family:var(--cond);font-weight:900;font-style:italic;font-size:22px;letter-spacing:.02em;text-transform:uppercase;color:var(--fg)}
body.bc .league-card .sub{font-size:11.5px;color:var(--fg-muted);margin:0 0 8px}
body.bc .league-table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
body.bc .league-table th{font-family:var(--cond);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--fg-muted);text-align:right;padding:6px 8px;background:transparent;border-bottom:1px solid var(--border)}
body.bc .league-table th:nth-child(-n+2),body.bc .league-table td:nth-child(-n+2){text-align:left}
body.bc .league-table td{padding:7px 8px;text-align:right;border-bottom:1px solid var(--border);font-size:13.5px}
body.bc .league-table td.tn{font-family:var(--cond);font-weight:800;font-size:15px;letter-spacing:.03em;text-transform:uppercase}
body.bc .league-table tr.mine td{background:rgba(0,212,240,.1)}
body.bc .league-table tr.mine td.tn{color:var(--home)}
body.bc .res-row{display:grid;grid-template-columns:1fr auto;gap:8px;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px}
body.bc .res-row.mine{border-left:3px solid var(--home);padding-left:10px}
body.bc .res-row .sc{font-family:var(--cond);font-weight:800;font-size:16px;letter-spacing:.04em}
body.bc .res-row .dt{grid-column:1/-1;font-size:11px;color:var(--fg-muted)}
@media (max-width:740px){body.bc .league-grid{grid-template-columns:1fr}}
"""

_CSS_CMD = r"""
/* Captain command board: the whole remaining roster and the path through the night */
body.bc .cmd{margin-bottom:22px}
body.bc .cmd-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px;margin-bottom:10px}
body.bc .cmd-head h3{margin:0;font-family:var(--cond);font-weight:900;font-style:italic;font-size:26px;letter-spacing:.02em;text-transform:uppercase;color:var(--fg)}
body.bc .cmd-sum{font-size:13px;color:var(--fg-dim)}
body.bc .cmd-sum b{color:var(--fg)}
body.bc .path{background:var(--bg-card);border:1px solid var(--border);border-left:4px solid var(--gold);border-radius:6px;padding:12px 16px;margin-bottom:12px}
body.bc .path-tabs{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap}
body.bc .path-slots{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px}
body.bc .slot{border:1px solid var(--border-hi);border-radius:4px;padding:8px 12px;background:#0a0f17}
body.bc .slot .sn{font-family:var(--cond);font-weight:800;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--fg-muted)}
body.bc .slot .so{font-family:var(--cond);font-weight:800;font-size:17px;letter-spacing:.03em;text-transform:uppercase;color:var(--home);overflow-wrap:anywhere}
body.bc .slot .st{font-size:12px;color:var(--fg-dim)}
body.bc .slot .evidence-badge{margin-top:4px;display:inline-block}
body.bc .cmd-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:10px}
body.bc .pcard{background:var(--bg-card);border:1px solid var(--border);border-left:4px solid var(--border-hi);border-radius:6px;padding:12px 14px;display:grid;gap:6px;min-width:0}
body.bc .pcard.save{border-left-color:var(--gold)}body.bc .pcard.core{border-left-color:#c9a24a}body.bc .pcard.flexible{border-left-color:var(--home)}body.bc .pcard.situational{border-left-color:#7a8aa3}
body.bc .pcard.burn{border-left-color:var(--away)}body.bc .pcard.used,body.bc .pcard.out{opacity:.55}
body.bc .pcard-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
body.bc .pcard-name{font-family:var(--cond);font-weight:900;font-size:21px;letter-spacing:.02em;text-transform:uppercase;color:var(--fg);flex:1;min-width:8em;overflow-wrap:anywhere}
body.bc .grade{font-family:var(--cond);font-weight:900;font-size:20px;color:#000;background:var(--home);border-radius:3px;padding:0 8px;line-height:1.5}
body.bc .grade.lo{background:#7a8aa3}
body.bc .role{font-family:var(--cond);font-weight:800;font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:3px 8px;border-radius:3px;border:1px solid var(--border-hi);color:var(--fg-dim)}
body.bc .role.save,body.bc .role.core{color:var(--gold);border-color:rgba(245,197,24,.5)}body.bc .role.flexible{color:var(--home);border-color:rgba(0,212,240,.5)}
body.bc .role.burn{color:var(--away);border-color:rgba(255,61,98,.5)}
body.bc .plist{font-size:13px;color:var(--fg);margin:0}
body.bc .plist .k{font-family:var(--cond);font-weight:800;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--fg-muted);display:block}
body.bc .plist .goodt{color:#00c8a0}body.bc .plist .badt{color:var(--away)}
body.bc .precommend{font-size:14px;font-weight:600;color:var(--fg);border-top:1px solid var(--border);padding-top:6px}
body.bc .pwhatif{font-size:12px;color:var(--fg-dim)}
body.bc .pwhatif b{color:var(--fg)}
body.bc .ladder{font-size:11.5px;color:var(--fg-muted);margin:8px 0 0}
body.bc .oitem{display:block;margin-bottom:2px}body.bc .afterline{display:block;font-size:11.5px;color:var(--fg-dim);margin:0 0 3px}
body.bc .send-after{font-size:12.5px;color:var(--fg-dim)}body.bc .send-after b{color:var(--fg)}
"""

_CSS_NIGHT = r"""
/* Match Night board (built from the artifact's hero, rows, badges and bars) */
body.bc #bc-night{display:none}
body.bc[data-view="matchnight"] #bc-night,body.bc[data-view="all"] #bc-night{display:block}
body.bc[data-view="matchnight"] main{background:transparent;color:var(--fg);margin-top:0}
body.bc[data-view="matchnight"] #bc-tabhead .section-title{color:var(--fg)}
body.bc[data-view="matchnight"] #bc-tabhead .section-sub{color:var(--fg-dim)}
@media screen{body.bc:not([data-view="all"]):not(.bc-full) #tonight{display:none!important}}
body.bc[data-view="matchnight"].bc-full #tonight{display:block!important;margin-top:16px}
body.bc .night-status{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;background:var(--bg-card);border:1px solid var(--border);border-radius:6px;padding:12px 16px;margin-bottom:12px}
body.bc .night-status .nm{font-family:var(--cond);font-weight:800;font-size:18px;letter-spacing:.04em;text-transform:uppercase}
body.bc .night-status .nm i{color:var(--away);font-style:normal;margin:0 6px}
body.bc .night-pill{font-family:var(--cond);font-weight:700;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--fg-dim);border:1px solid var(--border-hi);border-radius:3px;padding:3px 9px}
body.bc .night-pill.gold{background:var(--gold);color:#000;border-color:var(--gold)}
body.bc .night-spacer{flex:1}
body.bc .night-btn{font-family:var(--cond);font-weight:800;font-size:12px;letter-spacing:.1em;text-transform:uppercase;background:transparent;color:var(--fg);border:1px solid var(--border-hi);border-radius:3px;padding:7px 12px;min-height:36px;cursor:pointer}
body.bc .night-btn:hover{border-color:var(--fg-dim);background:transparent}
body.bc .night-btn.primary{background:var(--home);color:#000;border-color:var(--home)}
body.bc .night-btn.primary:hover{opacity:.9;background:var(--home)}
body.bc .night-btn:focus-visible,body.bc .night-chip:focus-visible,body.bc .avail-btn:focus-visible{outline:2px solid var(--home);outline-offset:2px}
body.bc .night-chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:12px}
body.bc .night-ask{font-family:var(--cond);font-weight:700;font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--away);margin-right:6px}
body.bc .night-chip{font-family:var(--cond);font-weight:800;font-size:15px;letter-spacing:.04em;text-transform:uppercase;background:var(--bg-card);color:var(--fg);border:1px solid var(--border-hi);border-radius:3px;padding:8px 14px;min-height:44px;cursor:pointer}
body.bc .night-chip[aria-pressed="true"]{background:var(--away);color:#000;border-color:var(--away)}
body.bc .night-chip small{font-family:var(--sans);font-weight:600;font-size:11px;opacity:.8;margin-left:6px}
body.bc .send-hero{background:linear-gradient(135deg,#061e1e 0%,#04141a 60%,#0a0d11 100%);border:1px solid var(--border);border-left:4px solid var(--home);border-radius:6px;padding:18px 22px;margin-bottom:12px;display:grid;gap:8px}
body.bc .send-kicker{font-family:var(--cond);font-weight:700;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--home)}
body.bc .send-name{font-family:var(--cond);font-weight:900;font-style:italic;font-size:clamp(34px,6vw,56px);line-height:.95;letter-spacing:-.01em;text-transform:uppercase;color:var(--home);overflow-wrap:anywhere}
body.bc .send-why{color:var(--fg);font-size:14px;max-width:80ch}
body.bc .send-cost{color:var(--gold);font-size:12.5px;font-weight:600}
body.bc .send-row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
body.bc .send-bars{width:220px}
body.bc .night-h{font-family:var(--cond);font-weight:900;font-style:italic;font-size:22px;letter-spacing:.02em;text-transform:uppercase;margin:18px 0 8px;color:var(--fg)}
body.bc .alt-row{display:grid;grid-template-columns:34px 1fr 200px auto;gap:14px;align-items:center;background:var(--bg-card);border:1px solid var(--border);border-radius:4px;padding:11px 16px;margin-bottom:3px}
body.bc .alt-row .alt-note{grid-column:2/-1;font-size:12px;color:var(--fg-dim);margin-top:-4px}
body.bc .alt-row.avoid{border-left:3px solid var(--away)}
body.bc .alt-row .matchup-player{font-size:18px}
body.bc .risk-list{margin:0;padding:0;list-style:none;display:grid;gap:4px}
body.bc .risk-list li{background:var(--bg-card);border:1px solid var(--border);border-left:3px solid var(--gold);border-radius:4px;padding:9px 14px;font-size:13px;color:var(--fg)}
body.bc .risk-list li.bad{border-left-color:var(--away)}
body.bc .bench{display:grid;grid-template-columns:1fr 1fr;gap:12px}
body.bc .bench-col{background:var(--bg-card);border:1px solid var(--border);border-radius:6px;padding:12px 14px;min-width:0}
body.bc .bench-col h4{margin:0 0 8px;font-family:var(--cond);font-weight:800;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--fg-muted)}
body.bc .bench-item{display:flex;align-items:center;gap:8px;padding:6px 0;border-top:1px solid var(--border);flex-wrap:wrap}
body.bc .bench-item:first-of-type{border-top:0}
body.bc .bench-item .bn{font-family:var(--cond);font-weight:800;font-size:16px;letter-spacing:.03em;text-transform:uppercase;flex:1;min-width:8em}
body.bc .bench-item.used .bn{text-decoration:line-through;color:var(--fg-muted)}
body.bc .bench-item .tagx{font-size:11px;color:var(--fg-dim)}
body.bc .avail-btn{font-family:var(--cond);font-weight:700;font-size:11px;letter-spacing:.1em;text-transform:uppercase;border:1px solid var(--border-hi);background:transparent;color:var(--fg-dim);border-radius:3px;padding:5px 10px;min-height:32px;cursor:pointer}
body.bc .avail-btn.Available{color:#00c8a0;border-color:rgba(0,200,160,.4)}body.bc .avail-btn.Unavailable{color:var(--away);border-color:rgba(255,61,98,.4)}
body.bc .game-row{display:flex;flex-wrap:wrap;align-items:center;gap:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:4px;padding:10px 14px;margin-bottom:3px}
body.bc .game-row .gn{font-family:var(--cond);font-weight:800;color:var(--fg-muted);width:2.2em}
body.bc .game-row .gt{flex:1;min-width:10em;font-family:var(--cond);font-weight:800;font-size:16px;letter-spacing:.03em;text-transform:uppercase}
body.bc .game-row .res{font-family:var(--cond);font-weight:800;letter-spacing:.1em;text-transform:uppercase;padding:3px 10px;border-radius:3px}
body.bc .game-row .res.W{background:rgba(0,212,240,.18);color:var(--home)}body.bc .game-row .res.L{background:rgba(255,61,98,.18);color:var(--away)}
@media (max-width:740px){body.bc .alt-row{grid-template-columns:28px 1fr auto}body.bc .alt-row .matchup-bars{grid-column:1/-1}body.bc .bench{grid-template-columns:1fr}body.bc .send-bars{width:100%}}
"""

CSS = _CSS_BODY + _CSS_DARK + _CSS_LEAGUE + _CSS_CMD + _CSS_NIGHT + "@media screen{\n" + _hide_rules() + "\n}\n"


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
  var TEAM_LABELS={};
  function opts(sel,teams){
    var src=$(sel),list=[];
    if(teams&&teams.length) list=teams.map(function(t){return [t.key,t.label];});
    else if(src) list=Array.prototype.filter.call(src.options,function(o){return o.value;}).map(function(o){return [o.value,o.text.replace(/ · \d+ rostered$/,"")];});
    var parts=list.map(function(x){return x[1].split(" · ");}),count={};
    parts.forEach(function(p){count[p[0]]=(count[p[0]]||0)+1;});
    return '<option value="">Select a team...</option>'+list.map(function(x,i){
      var p=parts[i],label=count[p[0]]>1?p.slice(0,4).join(" · "):p[0];TEAM_LABELS[x[0]]=x[1];
      return '<option value="'+esc(x[0])+'">'+esc(label)+'</option>';}).join("");
  }
  // The classic selects only hold search matches, so make sure the chosen team is an option before selecting it.
  function relay(id,value){var s=$(id);if(!s) return;
    if(value&&!Array.prototype.some.call(s.options,function(o){return o.value===value;})){var o=document.createElement("option");o.value=value;o.text=TEAM_LABELS[value]||value;s.appendChild(o);}
    s.value=value;s.dispatchEvent(new Event("change",{bubbles:true}));}
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
      +'<label class="team-pick"><span class="vh">Our team</span><select id="bc-team-a" class="team-name-select">'+opts("team-a",m&&m.teams)+'</select></label></div>'
      +'<div class="match-center"><span class="badge-prematch">'+esc(status)+'</span><div class="vs-circle">VS</div>'
      +'<div class="match-datetime">'+esc(ready?m.dateText:"Pick a matchup")+'</div></div>'
      +'<div class="team-panel team-panel-away"><span class="team-breadcrumb-away">Opponent</span>'
      +'<div class="team-mono team-mono-away" aria-hidden="true">'+esc(mono(theirName))+'</div>'
      +'<label class="team-pick"><span class="vh">Opponent team</span><select id="bc-team-b" class="team-name-select">'+opts("team-b",m&&m.teams)+'</select></label></div></div>';
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
  /* ---------- Match Night board ---------- */
  function barsHtml(w,g,cls){
    var own=pct(w,g),opp=g>0?pct(g-w,g):null;
    var note=g>0?(w+"-"+(g-w)+" direct · "+g+(g===1?" meeting":" meetings")+(g<3?" · small sample":"")):"No direct meetings";
    return '<div class="matchup-bars '+(cls||"")+'" role="img" aria-label="Recorded head-to-head: '+esc(note)+'">'
      +'<div class="bar-row"><span class="bar-pct">'+(own==null?"—":own.toFixed(0)+"%")+'</span><div class="bar-track"><div class="bar-fill-home" style="width:'+(own||0)+'%"></div></div></div>'
      +'<div class="bar-row"><span class="bar-pct">'+(opp==null?"—":opp.toFixed(0)+"%")+'</span><div class="bar-track"><div class="bar-fill-away" style="width:'+(opp||0)+'%"></div></div></div>'
      +'<div class="bar-note">'+esc(note)+'</div></div>';
  }
  function slTag(sl){return sl!=null?'<span class="matchup-sl">SL '+esc(sl)+'</span>':'';}
  var CAT={G:"Favorable",E:"Even",I:"Shared only",R:"Avoid",X:"Unknown"};
  function candRow(c,kind,oppId){
    var mark=kind==="ranked"?((c.choice||0)<10?"0":"")+c.choice:(kind==="avoid"?"✕":"≈");
    var note=[CAT[c.cat]||"",c.tied.length?"tied with "+c.tied.join(", "):"",c.avail==="Unknown"?"availability unknown":"",c.save,c.cost,c.after?"if sent: "+afterText(c.after):""].filter(Boolean).join(" · ");
    return '<div class="alt-row'+(kind==="avoid"?" avoid":"")+'"><div class="matchup-num">'+mark+'</div>'
      +'<div class="matchup-our"><div class="matchup-kicker">'+(kind==="avoid"?"Recorded losing record":"Option")+'</div><div class="matchup-player">'+esc(c.name)+slTag(c.sl)+'</div></div>'
      +barsHtml(c.wins,c.games)
      +'<button type="button" class="night-btn" data-send="'+esc(c.id)+'" data-opp="'+esc(oppId)+'" aria-label="Send '+esc(c.name)+'">✓ Send</button>'
      +(note?'<div class="alt-note">'+esc(note)+'</div>':'')+'</div>';
  }
  /* ---------- Captain command board ---------- */
  var pathMode="weLead";
  var ROLE_LABEL={save:"Save",core:"Core",flexible:"Flexible",situational:"Situational",burn:"Burn early",used:"Used",out:"Unavailable"};
  function afterText(a){return a?(a.left?'plan after: '+a.conf+' · fragility '+a.frag+(a.leans?' (leans on '+a.leans+')':''):'night complete'):"";}
  function oppList(items,withRecord){return items.map(function(i){return '<span class="oitem">'+esc(i.opp)+(withRecord&&i.g?' <span class="matchup-sl">'+esc(i.cell)+'</span>':'')+(withRecord&&i.after?'<span class="afterline">If used now vs '+esc(i.opp)+': '+esc(afterText(i.after))+'</span>':'')+'</span>';}).join("");}
  function cardHtml(c){
    var g=c.grade?'<span class="grade'+(/^[CD]/.test(c.grade)?' lo':'')+'" title="Strategic value (rule below)">'+esc(c.grade)+'</span>':"";
    var best=c.targets.length?'<p class="plist"><span class="k">Best targets</span><span class="goodt">'+oppList(c.targets,true)+'</span></p>':'<p class="plist"><span class="k">Best targets</span><span class="matchup-sl">none with a favorable direct record left</span></p>';
    var ans=(c.answers&&c.answers.length)?'<p class="plist"><span class="k">Plan answer</span>'+c.answers.map(function(a){return esc(a.opp)+' <span class="evidence-badge '+badgeClass(a.level)+'">'+esc(a.level)+'</span>';}).join(" ")+'</p>':"";
    var av=c.avoid.length?'<p class="plist"><span class="k">Avoid</span><span class="badt">'+oppList(c.avoid,true)+'</span></p>':"";
    var wi=c.whatIf?'<div class="pwhatif"><b>With them:</b> '+esc(c.whatIf.before)+' \u00b7 <b>Without them (used up or out):</b> '+esc(c.whatIf.after)+' \u00b7 fragility '+esc(c.whatIf.fragBefore)+' \u2192 '+esc(c.whatIf.fragAfter)+'</div>':"";
    return '<article class="pcard '+esc(c.role)+'" aria-label="'+esc(c.name)+'"><div class="pcard-top"><span class="pcard-name">'+esc(c.name)+slTag(c.sl)+'</span>'+g
      +'<span class="role '+esc(c.role)+'">'+esc(ROLE_LABEL[c.role]||c.role)+'</span></div>'+best+ans+av
      +'<div class="precommend">'+esc(c.recommend)+'</div>'+wi+'</article>';
  }
  function commandHtml(m){
    var cmd=m.night&&m.night.command; if(!cmd) return "";
    var cards=cmd.cards,pl=cmd.plan;
    var names=function(role){return cards.filter(function(c){return c.role===role;}).map(function(c){return esc(c.name);}).join(", ")||"none";};
    var slots=(pathMode==="theyLead"?pl.theyLead:pl.weLead).map(function(s,i){
      return '<div class="slot"><div class="sn">Game '+(i+1)+' \u00b7 '+(s.leader==="us"?"we put up":"they put up")+'</div><div class="so">'+esc(s.our)+'</div><div class="st">vs '+esc(s.their)+'</div><span class="evidence-badge '+badgeClass(s.level)+'">'+esc(s.level)+'</span></div>';}).join("");
    var tab=function(k,l){return '<button type="button" class="night-btn'+(pathMode===k?' primary':'')+'" data-path="'+k+'">'+l+'</button>';};
    return '<section class="cmd" aria-label="Captain command board"><div class="cmd-head"><h3>Captain command board</h3>'
      +'<span class="cmd-sum">Plan: <b>'+esc(pl.conf)+'</b> \u00b7 fragility <b>'+esc(pl.fragility)+'</b>'+(pl.leans?' (leans on '+esc(pl.leans)+')':'')+' \u00b7 '+pl.gamesLeft+' game'+(pl.gamesLeft===1?'':'s')+' left</span></div>'
      +'<div class="path"><div class="path-tabs">'+tab("weLead","If we put up first")+tab("theyLead","If they put up first")+'</div><div class="path-slots">'+slots+'</div>'
      +'<p class="cmd-sum" style="margin:8px 0 0"><b>Save:</b> '+names("save")+' \u00b7 <b>Core:</b> '+names("core")+' \u00b7 <b>Flexible:</b> '+names("flexible")+' \u00b7 <b>Burn early:</b> '+names("burn")+'</p></div>'
      +'<div class="cmd-grid">'+cards.map(cardHtml).join("")+'</div>'
      +'<p class="ladder">Roles come from the engine: <b>Save</b> = the only favorable answer to an opponent, or a designated answer for one; <b>Core</b> = no favorable target, but the plan gets worse without them; <b>Flexible</b> = 2+ favorable targets; <b>Burn early</b> = no favorable target and the plan is unchanged without them. Value (v1 rule): A = unique answer and 2+ favorable targets; A- = unique answer; B+ = 2+ favorable targets; B = 1; C = even or shared-opponent evidence only; D = none. Recorded results, not odds.</p></section>';
  }

  function renderNight(m){
    var el=$("bc-night"); if(!el) return;
    if(!m||m.empty||!m.night){el.innerHTML='<div class="home-empty">Pick a team and opponent on Home (or a fixture in Schedule Planner) to run the night.</div>';return;}
    var n=m.night,played=m.played||0,gameNo=Math.min(5,played+1),done=m.gamesLeft===0;
    var undo=n.games.length?'<button type="button" class="night-btn" data-undo="1">Undo send</button>':"";
    var status='<div class="night-status"><span class="nm">'+esc(m.ourName)+'<i>vs</i>'+esc(m.theirName)+'</span>'
      +'<span class="night-pill gold">'+(done?"Final":"Game "+gameNo+" of 5")+'</span>'
      +'<span class="night-pill">Score '+n.score.w+"-"+n.score.l+'</span><span class="night-pill">'+esc(n.capText)+'</span><span class="night-spacer"></span>'+undo
      +'<button type="button" class="night-btn" data-full="1">Full evidence</button></div>';
    var chips='<div class="night-chips" role="group" aria-label="Opponent they put up"><span class="night-ask">'+(n.chosen?"They put up":"If they put up")+'</span>'
      +n.chips.map(function(c){return '<button type="button" class="night-chip" data-pick="'+esc(c.id)+'" aria-pressed="'+c.on+'">'+esc(c.name)+(c.sl!=null?'<small>SL '+esc(c.sl)+'</small>':'')+'</button>';}).join("")
      +(n.chips.length?"":'<span class="matchup-footnote">Every opponent has played.</span>')+'</div>';
    var hero="",alts="",risks="";
    if(n.opp){
      var all=n.ranked.concat(n.unordered).concat(n.avoid);
      var pick=null;
      if(n.answer) pick=all.filter(function(c){return c.name===n.answer.our;})[0]||null;
      if(!pick&&n.ranked.length) pick=n.ranked[0];
      var ourBench=n.bench.ours.filter(function(b){return n.answer&&b.name===n.answer.our;})[0];
      var pickId=pick?pick.id:(ourBench?ourBench.id:null),pickName=pick?pick.name:(n.answer?n.answer.our:null);
      if(pickName){
        hero='<section class="send-hero" aria-label="Send now"><span class="send-kicker">'+(n.chosen?"Send now":"Best answer")+' vs '+esc(n.opp.name)+(n.opp.sl!=null?' · SL '+esc(n.opp.sl):'')+'</span>'
          +'<div class="send-name">'+esc(pickName)+'</div>'
          +'<div class="send-row"><span class="evidence-badge '+badgeClass(n.answer?n.answer.level:"Unknown")+'">'+esc(n.answer?n.answer.level:"Unknown")+'</span>'
          +(pick?barsHtml(pick.wins,pick.games,"send-bars"):"")
          +(pickId?'<button type="button" class="night-btn primary" data-send="'+esc(pickId)+'" data-opp="'+esc(n.opp.id)+'">✓ Send '+esc(pickName)+'</button>':"")+'</div>'
          +(n.answer&&n.answer.why?'<div class="send-why">'+esc(n.answer.why)+'</div>':'<div class="send-why">'+esc(n.headline)+'</div>')
          +(n.answer&&n.answer.cost?'<div class="send-cost">'+esc(n.answer.cost)+'</div>':'')
          +(pick&&pick.after?'<div class="send-after"><b>After this send:</b> '+esc(afterText(pick.after))+'</div>':'')+'</section>';
      } else hero='<section class="send-hero"><span class="send-kicker">No send</span><div class="send-why">'+esc(n.headline)+'</div></section>';
      var rest=function(list,kind){return list.filter(function(c){return !pickName||c.name!==pickName;}).map(function(c){return candRow(c,kind,n.opp.id);}).join("");};
      var a1=rest(n.ranked,"ranked"),a2=rest(n.unordered,"shared"),a3=rest(n.avoid,"avoid");
      alts='<h3 class="night-h">Alternatives</h3>'+(a1+a2+a3||'<p class="matchup-footnote">No other recorded option.</p>')
        +(n.unknown.length?'<p class="matchup-footnote">Unknown (no verified evidence, not weak): '+esc(n.unknown.join(", "))+'</p>':"");
      var rl=[];
      all.forEach(function(c){if(c.save) rl.push('<li>'+esc(c.name+" — "+c.save)+'</li>');});
      n.holds.forEach(function(h){rl.push('<li>'+esc("Keep "+h.our+(h.covers.length?" for "+h.covers.join(", "):"")+" — "+h.why)+'</li>');});
      n.sacrifices.forEach(function(s){rl.push('<li class="bad">'+esc("If we must absorb a bad matchup: "+s.our+" vs "+s.their+" ("+s.level+") — "+s.why)+'</li>');});
      if(n.openRisks.length) rl.push('<li class="bad">'+esc("No favorable direct option left vs "+n.openRisks.join(", "))+'</li>');
      risks='<h3 class="night-h">Risks I accept</h3><ul class="risk-list">'+(rl.join("")||'<li>Nothing recorded to give up with this send.</li>')+'</ul>';
    }
    var avlNext={Unknown:"Available",Available:"Unavailable",Unavailable:"Unknown"};
    var bench='<h3 class="night-h">Bench</h3><div class="bench"><div class="bench-col"><h4>Our players</h4>'
      +n.bench.ours.map(function(b){return '<div class="bench-item'+(b.lineup==="Played"?" used":"")+'"><span class="bn">'+esc(b.name)+'</span>'+slTag(b.sl)
        +(b.lineup==="Played"?'<span class="tagx">played</span>':'<button type="button" class="avail-btn '+esc(b.avail)+'" data-avail="'+esc(b.id)+'" data-next="'+esc(avlNext[b.avail])+'" aria-label="'+esc(b.name+" availability "+b.avail+"; change")+'">'+esc(b.avail)+'</button>')+'</div>';}).join("")
      +'</div><div class="bench-col"><h4>Their players</h4>'
      +n.bench.theirs.map(function(b){return '<div class="bench-item'+(b.unplayed?"":" used")+'"><span class="bn">'+esc(b.name)+'</span>'+slTag(b.sl)+(b.unplayed?"":'<span class="tagx">played</span>')+'</div>';}).join("")+'</div></div>';
    var log="";
    if(n.games.length){
      log='<h3 class="night-h">Games tonight</h3>'+n.games.map(function(g){
        return '<div class="game-row"><span class="gn">G'+(g.i+1)+'</span><span class="gt">'+esc(g.our)+' vs '+esc(g.their)+'</span>'
          +(g.r?'<span class="res '+g.r+'">'+(g.r==="W"?"We won":"We lost")+'</span><button type="button" class="night-btn" data-result="'+g.i+'" data-r="">Clear</button>'
            :'<button type="button" class="night-btn primary" data-result="'+g.i+'" data-r="W">We won</button><button type="button" class="night-btn" data-result="'+g.i+'" data-r="L">We lost</button>')+'</div>';}).join("")
        +'<p class="matchup-footnote">Results are kept in this browser for tonight. They never change any recorded evidence or recommendation.</p>';
    }
    el.innerHTML=status+commandHtml(m)+chips+hero+alts+risks+bench+log;
    Array.prototype.forEach.call(el.querySelectorAll("[data-path]"),function(b){b.onclick=function(){pathMode=b.getAttribute("data-path");renderNight(m);};});
    Array.prototype.forEach.call(el.querySelectorAll("[data-pick]"),function(b){b.onclick=function(){window.UC_ACT.pick(b.getAttribute("data-pick"));};});
    Array.prototype.forEach.call(el.querySelectorAll("[data-send]"),function(b){b.onclick=function(){window.UC_ACT.send(b.getAttribute("data-send"),b.getAttribute("data-opp"));};});
    Array.prototype.forEach.call(el.querySelectorAll("[data-avail]"),function(b){b.onclick=function(){window.UC_ACT.avail(b.getAttribute("data-avail"),b.getAttribute("data-next"));};});
    Array.prototype.forEach.call(el.querySelectorAll("[data-result]"),function(b){b.onclick=function(){window.UC_ACT.result(+b.getAttribute("data-result"),b.getAttribute("data-r"));};});
    var u=el.querySelector("[data-undo]");if(u) u.onclick=function(){window.UC_ACT.undo();};
    var f=el.querySelector("[data-full]");if(f) f.onclick=function(){body.classList.toggle("bc-full");};
  }
  /* ---------- League table and results (Summary tab) ---------- */
  function renderLeague(m){
    var el=$("bc-league"); if(!el) return;
    var L=m&&!m.empty?m.league:null;
    if(!L||!L.table.length){el.innerHTML="";return;}
    var rows=L.table.map(function(r,i){return '<tr'+(r.mine?' class="mine"':'')+'><td>'+(i+1)+'</td><td class="tn">'+esc(r.name)+'</td><td>'+r.p+'</td><td>'+r.w+'</td><td>'+r.l+'</td><td>'+(r.t||0)+'</td><td>'+r.pts+'</td></tr>';}).join("");
    var res=L.recent.map(function(g){return '<div class="res-row'+(g.mine?' mine':'')+'"><span>'+esc(g.home)+' vs '+esc(g.away)+'</span><span class="sc">'+g.hs+' – '+g.as+'</span><span class="dt">'+esc(g.date)+(g.week?' · week '+esc(g.week):'')+'</span></div>';}).join("");
    el.innerHTML='<div class="league-grid"><div class="league-card"><h3>League table</h3><p class="sub">'+esc(L.session)+' · computed from the '+L.games+' scored matches recorded in this snapshot. APA’s official table also counts bye weeks and can differ.</p>'
      +'<div class="table-wrap"><table class="league-table"><thead><tr><th>#</th><th>Team</th><th>P</th><th>W</th><th>L</th><th>T</th><th>Pts</th></tr></thead><tbody>'+rows+'</tbody></table></div></div>'
      +'<div class="league-card"><h3>Recent results</h3><p class="sub">Newest first. Your team’s matches are marked.</p>'+res+'</div></div>';
  }
  window.UC_BC={render:function(m){renderHome(m);renderNight(m);renderLeague(m);ticker(m);}};
  show("home");
  renderHome(window.UC_BC_LAST||null); renderNight(window.UC_BC_LAST||null); renderLeague(window.UC_BC_LAST||null); ticker(window.UC_BC_LAST||null);
  route();
})();
"""

JS = _JS_BODY.replace("%TABS%", json.dumps([list(t) for t in TABS]))
