"""One-stop Coach Cockpit composition layer.

This module deliberately does not copy Match Night, matchup, lineup, or Data
Coverage logic. It composes the already-audited ``ui.dashboard`` page with the
already-existing ``ui.tabs.data_coverage`` reporter so a captain can see both
from one generated artifact.

The composition seam is intentionally narrow and fail-closed: the base
Dashboard must contain exactly one ``</body>`` marker. If that contract ever
changes, rendering raises instead of silently dropping, duplicating, or
misplacing Data Coverage.

The cockpit chrome below is presentation only. It moves the already-rendered
DOM nodes into a card layout after the base dashboard has initialized. Existing
IDs, event listeners, Match Night state, and analytics outputs remain the source
of truth.
"""

from __future__ import annotations

from html import escape
from typing import Optional, Sequence

from analytics.data_coverage import DataCoverageReport
from analytics.opponent_risk_profile import OpponentRiskEntry
from analytics.player_matchup_engine import PlayerMatchupReport
from analytics.team_matchup_engine import TeamMatchupReport
from ui.dashboard import render as render_dashboard
from ui.tabs.data_coverage import render as render_data_coverage

_BODY_END = "</body>"


def _scope_key_from_team(report: TeamMatchupReport) -> str:
    return f"{report.opponent_team_external_id}|{report.format}|{report.session_name}"


def _scope_key_from_coverage(report: DataCoverageReport) -> str:
    return f"{report.opponent_team_external_id}|{report.format}|{report.session_name}"


def _coverage_sections(
    reports: Sequence[DataCoverageReport],
    team_reports: Sequence[TeamMatchupReport],
    our_team_name: str,
) -> str:
    team_by_scope = {_scope_key_from_team(report): report for report in team_reports}
    sections: list[str] = []
    for report in reports:
        key = _scope_key_from_coverage(report)
        team_report = team_by_scope.get(key)
        opponent_name = (
            team_report.opponent_team_name
            if team_report is not None
            else report.opponent_team_external_id
        )
        label = f"{opponent_name} — {report.format} / {report.session_name}"
        body = render_data_coverage(
            report,
            our_team_name,
            opponent_name,
            title="Data Coverage",
        )
        sections.append(
            '<details class="dc-embedded">'
            f'<summary>{escape(label)}</summary>{body}</details>'
        )
    return "".join(sections)


_COCKPIT_CHROME = r"""
<style id="coach-cockpit-demo-layout">
:root {
  --cc-bg: #0d1117;
  --cc-panel: #161b22;
  --cc-panel-2: #1f2630;
  --cc-line: #30363d;
  --cc-text: #f0f6fc;
  --cc-muted: #9da7b3;
  --cc-blue: #58a6ff;
  --cc-green: #3fb950;
  --cc-yellow: #d29922;
  --cc-red: #f85149;
}
body.cc-ready {
  margin: 0;
  background: var(--cc-bg);
  color: var(--cc-text);
  font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif;
}
body.cc-ready h1, body.cc-ready h2, body.cc-ready h3, body.cc-ready h4,
body.cc-ready h5 { color: var(--cc-text); }
body.cc-ready h2 { border-top: 0; padding-top: 0; margin-top: 0; }
body.cc-ready a { color: var(--cc-blue); }
body.cc-ready .cd-note, body.cc-ready .mn-technical, body.cc-ready .dc-sub,
body.cc-ready .dc-unavailable { color: var(--cc-muted); }
body.cc-ready select, body.cc-ready input, body.cc-ready textarea {
  background: #0d1117; color: var(--cc-text); border: 1px solid var(--cc-line);
  border-radius: 8px; padding: 10px;
}
body.cc-ready button {
  background: #21262d; color: var(--cc-text); border: 1px solid var(--cc-line);
  border-radius: 8px; padding: 10px 14px; cursor: pointer;
}
body.cc-ready button:hover { border-color: #6e7681; }
body.cc-ready table { color: var(--cc-text); }
body.cc-ready th, body.cc-ready td { border-bottom-color: var(--cc-line); }
body.cc-ready th { color: var(--cc-muted); }
body.cc-ready .cd-summary-box, body.cc-ready .cd-edge-card,
body.cc-ready .mn-scouting-card {
  background: #111820; border-color: #253142; color: var(--cc-text);
}
body.cc-ready .cd-none { background: #2b2412; border-left-color: var(--cc-yellow); color: var(--cc-text); }
body.cc-ready .mn-card { background: #11161d; border-color: var(--cc-line); }
body.cc-ready .mn-card.mn-fallback { background: #2b2112; }

#coach-cockpit-shell { min-height: 100vh; }
.cc-topbar {
  position: sticky; top: 0; z-index: 20; background: rgba(13,17,23,.96);
  border-bottom: 1px solid var(--cc-line); backdrop-filter: blur(8px);
}
.cc-topbar-inner, .cc-wrap { max-width: 1180px; margin: 0 auto; padding: 18px; }
.cc-topbar-inner { display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-wrap: wrap; }
.cc-topbar h1 { margin: 0; font-size: 24px; }
.cc-kicker { color: var(--cc-muted); font-size: 13px; margin-top: 4px; }
.cc-live-badge {
  border: 1px solid var(--cc-line); border-radius: 999px; padding: 7px 11px;
  background: var(--cc-panel); color: var(--cc-green); font-size: 12px; font-weight: 700;
}
.cc-grid { display: grid; grid-template-columns: minmax(0, 1.18fr) minmax(320px, .82fr); gap: 16px; align-items: start; }
.cc-main, .cc-aside { min-width: 0; }
.cc-card {
  background: var(--cc-panel); border: 1px solid var(--cc-line); border-radius: 14px;
  padding: 16px; margin-bottom: 16px; box-shadow: 0 7px 24px rgba(0,0,0,.16);
}
.cc-card > h2:first-child { margin-top: 0; }
.cc-card .cd-controls { display: flex; gap: 12px; flex-wrap: wrap; align-items: end; }
.cc-card .cd-controls label { flex: 1 1 240px; }
.cc-card .cd-controls select { max-width: none; width: 100%; }
.cc-card .cd-filters { background: var(--cc-panel-2); border-color: var(--cc-line); border-radius: 10px; }
.cc-card .mn-sticky {
  position: static; display: grid; grid-template-columns: repeat(2, minmax(0,1fr));
  gap: 10px; background: transparent; padding: 0; margin: 14px 0; color: var(--cc-text);
}
.cc-card .mn-sticky > span {
  min-width: 0; background: var(--cc-panel-2); border: 1px solid var(--cc-line);
  border-radius: 10px; padding: 12px; overflow-wrap: anywhere;
}
.cc-card .mn-sticky > span:first-child { grid-column: 1 / -1; color: var(--cc-blue); }
.cc-card .mn-sticky.mn-sticky-warn > span:last-child { border-color: #7a3b00; background: #2b2112; }
.cc-card .mn-sticky strong { font-size: 22px; }
.cc-card #mn-roster { margin-top: 10px; }
.cc-card .mn-roster-row { border-bottom-color: var(--cc-line); }
.cc-card .mn-roster-row select { margin-left: auto; }
.cc-card #mn-comparison .mn-card { border-radius: 10px; }
.cc-card #mn-comparison .mn-send-btn { background: #1f6feb; border-color: #1f6feb; }
.cc-card #mn-lineup { overflow-x: auto; }
.cc-aside #mn-scouting { margin-bottom: 16px; }
.cc-aside #mn-scouting:empty { display: none; }
.cc-aside .mn-scouting-card { margin: 0 0 16px; border-radius: 12px; }
.cc-aside .cd-edge-card { border-radius: 12px; margin-bottom: 0; }
.cc-coverage-card .dc-cockpit-section { margin-top: 0; }
.cc-coverage-card .dc-cockpit-section > h2 { display: none; }
.cc-coverage-card .dc-embedded { border: 1px solid var(--cc-line); border-radius: 10px; padding: 0 10px; }
.cc-coverage-card .dc-embedded > summary { color: var(--cc-text); }
.cc-coverage-card .dc-tab h2 { font-size: 18px; }
.cc-advanced { max-width: 1180px; margin: 0 auto; padding: 0 18px 24px; }
.cc-advanced details { background: var(--cc-panel); border: 1px solid var(--cc-line); border-radius: 14px; padding: 12px 16px; }
.cc-advanced summary { cursor: pointer; font-weight: 700; }
.cc-advanced-body { margin-top: 14px; }
body.cc-ready .dc-embedded { overflow-x: auto; }

@media (max-width: 820px) {
  .cc-grid { grid-template-columns: 1fr; }
  .cc-topbar-inner, .cc-wrap, .cc-advanced { padding-left: 12px; padding-right: 12px; }
  .cc-card .mn-sticky { grid-template-columns: repeat(2, minmax(0,1fr)); }
}
@media (max-width: 520px) {
  .cc-card { padding: 12px; }
  .cc-card .mn-sticky { grid-template-columns: 1fr 1fr; }
  .cc-card .mn-sticky > span:first-child { grid-column: 1 / -1; }
  .cc-card .cd-controls { display: block; }
  .cc-card .cd-controls > * { display: block; margin: 8px 0; }
}
@media print {
  .cc-topbar, .cc-wrap, .cc-advanced { display: none !important; }
}
</style>
<script id="coach-cockpit-demo-layout-script">
(function () {
  function directHeading(tag, startsWith) {
    var children = Array.prototype.slice.call(document.body.children);
    return children.find(function (el) {
      return el.tagName === tag && el.textContent.trim().indexOf(startsWith) === 0;
    }) || null;
  }
  function appendIf(parent, node) { if (node) parent.appendChild(node); }
  function nearestControls(id) {
    var el = document.getElementById(id);
    return el ? el.closest('.cd-controls') : null;
  }
  function make(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text) el.textContent = text;
    return el;
  }

  var title = document.body.querySelector(':scope > h1');
  var intro = title && title.nextElementSibling && title.nextElementSibling.classList.contains('cd-note')
    ? title.nextElementSibling : null;
  var pvpH = directHeading('H2', 'Player vs Player');
  var teamH = directHeading('H2', 'Team vs Team');
  var matchH = directHeading('H2', 'Match Night');
  var matchNote = matchH && matchH.nextElementSibling && matchH.nextElementSibling.classList.contains('cd-note')
    ? matchH.nextElementSibling : null;
  var riskH = directHeading('H2', 'Opponent Risk Profile');
  var riskNote = riskH && riskH.nextElementSibling && riskH.nextElementSibling.classList.contains('cd-note')
    ? riskH.nextElementSibling : null;
  var coverage = document.getElementById('data-coverage-freshness');
  if (!title || !pvpH || !teamH || !matchH || !riskH || !coverage) {
    throw new Error('Coach Cockpit layout contract changed; refusing partial rearrangement');
  }

  var shell = make('div'); shell.id = 'coach-cockpit-shell';
  var top = make('header', 'cc-topbar');
  var topInner = make('div', 'cc-topbar-inner');
  var brand = make('div');
  brand.appendChild(title);
  var kicker = make('div', 'cc-kicker', 'One-stop captain view: Match Night + matchup evidence + data coverage');
  brand.appendChild(kicker);
  if (intro) intro.style.display = 'none';
  topInner.appendChild(brand);
  topInner.appendChild(make('div', 'cc-live-badge', 'LIVE DATA SNAPSHOT'));
  top.appendChild(topInner);
  shell.appendChild(top);

  var wrap = make('main', 'cc-wrap');
  var grid = make('section', 'cc-grid');
  var mainCol = make('div', 'cc-main');
  var aside = make('aside', 'cc-aside');

  var matchCard = make('section', 'cc-card cc-match-card');
  appendIf(matchCard, matchH);
  appendIf(matchCard, matchNote);
  appendIf(matchCard, nearestControls('mn-scope'));
  appendIf(matchCard, document.getElementById('mn-sticky'));
  appendIf(matchCard, document.getElementById('mn-warning'));
  appendIf(matchCard, document.getElementById('mn-roster'));
  appendIf(matchCard, nearestControls('mn-opponent'));
  appendIf(matchCard, document.getElementById('mn-comparison'));
  var boardsHeading = directHeading('H3', 'Boards sent');
  appendIf(matchCard, boardsHeading);
  appendIf(matchCard, document.getElementById('mn-lineup'));
  mainCol.appendChild(matchCard);

  var pvpCard = make('section', 'cc-card cc-pvp-card');
  appendIf(pvpCard, pvpH);
  appendIf(pvpCard, nearestControls('pme-player'));
  var filters = document.querySelector('.cd-filters');
  appendIf(pvpCard, filters);
  appendIf(pvpCard, document.getElementById('pme-result'));
  mainCol.appendChild(pvpCard);

  var edgeCard = make('section', 'cc-card cc-edge-card-wrap');
  appendIf(edgeCard, teamH);
  appendIf(edgeCard, nearestControls('tme-scope'));
  appendIf(edgeCard, document.getElementById('tme-result'));
  aside.appendChild(edgeCard);

  var scoutingCard = make('section', 'cc-card cc-scouting-wrap');
  scoutingCard.appendChild(make('h2', null, 'Opponent Scouting'));
  appendIf(scoutingCard, document.getElementById('mn-scouting'));
  aside.appendChild(scoutingCard);

  var coverageCard = make('section', 'cc-card cc-coverage-card');
  coverageCard.appendChild(make('h2', null, 'Data Coverage & Freshness'));
  coverageCard.appendChild(coverage);
  aside.appendChild(coverageCard);

  grid.appendChild(mainCol); grid.appendChild(aside); wrap.appendChild(grid); shell.appendChild(wrap);

  var advanced = make('section', 'cc-advanced');
  var details = document.createElement('details');
  var summary = document.createElement('summary');
  summary.textContent = 'Advanced division analysis';
  details.appendChild(summary);
  var body = make('div', 'cc-advanced-body');
  appendIf(body, riskH);
  appendIf(body, riskNote);
  appendIf(body, document.getElementById('risk-result'));
  details.appendChild(body); advanced.appendChild(details); shell.appendChild(advanced);

  document.body.insertBefore(shell, document.body.firstChild);
  document.body.classList.add('cc-ready');
})();
</script>
"""


def render(
    player_reports: Sequence[PlayerMatchupReport],
    team_reports: Sequence[TeamMatchupReport],
    opponent_risk_entries: Sequence[OpponentRiskEntry],
    our_team_name: str,
    built_at: Optional[str] = None,
    data_coverage_reports: Sequence[DataCoverageReport] = (),
) -> str:
    """Render one Coach Cockpit from existing trusted reporter outputs.

    ``data_coverage_reports`` defaults to empty for backwards-compatible
    callers. Missing coverage is shown explicitly rather than inferred from
    another timestamp or silently omitted.
    """
    base = render_dashboard(
        player_reports,
        team_reports,
        opponent_risk_entries,
        our_team_name,
        built_at=built_at,
    )
    if base.count(_BODY_END) != 1:
        raise ValueError("Coach Dashboard must contain exactly one </body> marker")

    sections = _coverage_sections(data_coverage_reports, team_reports, our_team_name)
    coverage_html = f"""
<section id="data-coverage-freshness" class="dc-cockpit-section">
<style>
.dc-cockpit-section {{ margin-top: 32px; }}
.dc-embedded {{ margin: 10px 0; overflow-x: auto; }}
.dc-embedded > summary {{ cursor: pointer; font-weight: 700; padding: 10px 0; }}
.dc-embedded .dc-tab {{ min-width: 0; }}
</style>
<h2>Data Coverage &amp; Freshness</h2>
<p class="cd-note">Real evidence coverage, missing posted skill levels, sample sizes, and
refresh timestamps already captured by the Data Coverage reporter. No age threshold or
"fresh/stale" verdict is invented here. Read the real timestamps and gaps before relying
on a matchup decision.</p>
{sections if sections else '<p class="cd-none">No Data Coverage report is available for this bundle.</p>'}
</section>
"""
    return base.replace(_BODY_END, coverage_html + _COCKPIT_CHROME + _BODY_END)
