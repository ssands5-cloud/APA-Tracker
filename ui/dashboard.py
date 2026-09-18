"""Coach Dashboard: one static, self-contained page combining the Coach
Advantage Tools -- Player vs Player, Team vs Team, Opponent Risk Profile.

Replaces ``ui/dashboard_stub.py``. That stub's own advice still holds
("read from the same SQLite file the scheduler jobs write to; don't scrape
from the dashboard process itself") -- this stays a static page built by
``scripts/build_coach_advantage_bundle.py`` from one locked database
snapshot, matching every other artifact in this project's demo-run
architecture (``scripts/build_full_production_demo.py``), not a live
server process.

A REPORTER over three already-computed inputs -- ``PlayerMatchupReport``,
``TeamMatchupReport``, and ``OpponentRiskEntry`` -- combined into one page.
Nothing here recomputes a rate, a label, a ranking, or a lineup.

"Trend" is shown as a compact indicator (direction + a volatility count)
plus a real plotted sparkline: ``SkillTrendInfo.readings`` now carries the
player's whole real chronological skill-level series
(``database.queries.skill_level_history``), so the inline SVG polyline
drawn in the browser is the real series, not a decoration standing in for
one. A player with fewer than two readings shows the text indicator alone
-- there is nothing to plot, and that is shown honestly rather than faked.

Filters (skill level range, minimum volatility, trend direction) narrow
the opponent list in Player vs Player to only real opponents matching the
real, already-computed fields on their report -- no new threshold or
model is introduced to power a filter.

The Team vs Team section's "Captain's Edge" card is a purely descriptive
summary of one real scope: evidence coverage, lineup fill status, and the
lowest/highest experimental skill-only estimate already in the ranked
table below it -- never narrated as a "favored"/"danger" verdict (see
``analytics.team_matchup_engine``'s own "Explicitly experimental" note).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from typing import Optional, Sequence

from analytics.opponent_risk_profile import OpponentRiskEntry
from analytics.player_matchup_engine import PlayerMatchupReport
from analytics.team_matchup_engine import TeamMatchupReport
from ui.export_html_player_matchup_engine import _pair_key, _player_options_and_index
from ui.export_json_coach_advantage import (
    player_matchup_report_to_dict,
    team_matchup_report_to_dict,
)
from ui.tabs.tonights_match import _script_json


def _scope_key(report: TeamMatchupReport) -> str:
    return f"{report.opponent_team_external_id}|{report.format}|{report.session_name}"


def render(
    player_reports: Sequence[PlayerMatchupReport],
    team_reports: Sequence[TeamMatchupReport],
    opponent_risk_entries: Sequence[OpponentRiskEntry],
    our_team_name: str,
    built_at: Optional[str] = None,
) -> str:
    player_payload = {_pair_key(r): player_matchup_report_to_dict(r) for r in player_reports}
    team_payload = {_scope_key(r): team_matchup_report_to_dict(r) for r in team_reports}

    players, by_player = _player_options_and_index(player_reports)
    player_options = "".join(
        f'<option value="{p["id"]}">{escape(p["name"])}</option>'
        for p in sorted(players.values(), key=lambda p: p["name"].lower())
    )
    opponent_index = {
        str(player_id): [{"key": c["key"], "label": c["label"]} for c in choices]
        for player_id, choices in by_player.items()
    }
    scope_options = "".join(
        f'<option value="{escape(_scope_key(r))}">'
        f'{escape(r.opponent_team_name)} ({escape(r.format)}, {escape(r.session_name)})</option>'
        for r in team_reports
    )
    if built_at:
        try:
            _built_dt = datetime.fromisoformat(built_at)
            freshness_text = _built_dt.strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            freshness_text = built_at
    else:
        freshness_text = "not available"

    risk_rows = "".join(
        f"<tr><td>{escape(e.opponent_team_name)}</td>"
        f"<td>{e.direct_pairing_count}/{e.total_pairings}</td>"
        f"<td>{'No data' if e.direct_win_rate is None else f'{e.direct_win_rate:.1%}'}</td>"
        f"<td>{e.sample_size}</td>"
        f"<td>{'No data' if e.reliability_weighted_skill_probability is None else f'{e.reliability_weighted_skill_probability:.1%}'}</td>"
        "</tr>"
        for e in opponent_risk_entries
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Coach Dashboard — {escape(our_team_name)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1c1f24; background: #ffffff; }}
h2 {{ border-top: 2px solid #1F3864; padding-top: 18px; margin-top: 32px; }}
input, select, textarea, button {{ max-width: 100%; box-sizing: border-box; }}
.cd-controls select {{ font-size: 14px; padding: 4px; width: 100%; max-width: 380px;
  box-sizing: border-box; }}
#pme-result, #tme-result, #dc-result, #risk-result,
#mn-comparison, #mn-lineup, #mn-scouting {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 8px 0 18px; }}
th, td {{ padding: 6px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.cd-summary-box {{ background: #eef2fa; border-left: 4px solid #1F3864; padding: 10px 14px; }}
.cd-none {{ background: #fdf6e3; border-left: 4px solid #b58900; padding: 10px 14px; }}
.cd-note {{ color: #666e7a; font-size: 12.5px; }}
.cd-cols {{ display: flex; gap: 24px; flex-wrap: wrap; }}
.cd-cols > div {{ flex: 1; min-width: 280px; }}
.cd-filters {{ display: flex; gap: 16px; flex-wrap: wrap; align-items: center;
  background: #f4f6fa; border: 1px solid #e2e5ea; border-radius: 4px;
  padding: 8px 12px; margin: 10px 0; font-size: 13px; }}
.cd-filters label {{ display: inline-flex; align-items: center; gap: 4px; }}
.cd-filters input[type="number"] {{ width: 48px; }}
.cd-spark {{ vertical-align: middle; margin-left: 6px; }}
.cd-edge-card {{ background: #eef2fa; border: 1px solid #1F3864; border-radius: 4px;
  padding: 10px 14px; margin: 8px 0 18px; }}
.cd-edge-card h3 {{ margin-top: 0; }}
.mn-roster-row {{ display: flex; align-items: center; gap: 10px; padding: 6px 4px;
  border-bottom: 1px solid #e2e5ea; flex-wrap: wrap; }}
.mn-roster-row select {{ font-size: 15px; padding: 6px; }}
.mn-roster-name {{ min-width: 140px; font-weight: 600; }}
.mn-card {{ border: 1px solid #e2e5ea; border-radius: 6px; padding: 12px 14px;
  margin: 10px 0; background: #fff; }}
.mn-card.mn-ok {{ border-left: 5px solid #1a7f37; }}
.mn-card.mn-fallback {{ border-left: 5px solid #7a3b00; background: #fffaf0; }}
.mn-card.mn-warn {{ border-left: 5px solid #b58900; }}
.mn-card.mn-unknown {{ border-left: 5px solid #8a919c; }}
.mn-card h4 {{ margin: 0 0 4px; }}
.mn-send-btn {{ font-size: 16px; padding: 10px 18px; margin-top: 6px; min-height: 44px; }}
.mn-status-line {{ font-weight: 600; }}
#mn-warning .cd-none {{ font-weight: 600; }}
.mn-print-only {{ display: none; }}
#mn-scope, #mn-match, #mn-opponent, .mn-status-select {{
  font-size: 16px; padding: 10px; min-height: 44px;
}}
#mn-reset, #mn-print, #mn-undo-btn, .mn-undo-btn, #mn-scouting-notes-save {{
  font-size: 15px; padding: 10px 16px; min-height: 44px;
}}
.mn-sticky {{ position: sticky; top: 0; z-index: 5; background: #1F3864; color: #fff;
  padding: 10px 14px; margin: 10px 0; border-radius: 4px; font-size: 15px;
  display: flex; gap: 18px; flex-wrap: wrap; align-items: center; }}
.mn-sticky strong {{ font-size: 17px; }}
.mn-sticky.mn-sticky-warn {{ background: #7a3b00; }}
.mn-technical {{ color: #666e7a; font-size: 12.5px; margin-top: 4px; }}
.mn-technical summary {{ cursor: pointer; }}
.mn-scouting-card {{ border: 1px solid #1F3864; border-radius: 6px; padding: 12px 14px;
  margin: 10px 0; background: #f4f6fa; }}
.mn-scouting-card h2 {{ margin: 0 0 4px; border-top: none; padding-top: 0; font-size: 20px; }}
.mn-scouting-card h5 {{ margin: 14px 0 4px; }}
#mn-scouting-notes {{ font-size: 16px; padding: 10px; width: 100%; box-sizing: border-box;
  font-family: inherit; }}
#mn-scouting-notes-status {{ margin-left: 8px; }}
@media (max-width: 600px) {{
  body {{ margin: 12px; }}
  .cd-cols > div {{ min-width: 0; }}
  .mn-sticky > span {{ min-width: 0; overflow-wrap: anywhere; }}
}}
@media print {{
  body * {{ display: none !important; }}
  #mn-print-summary, #mn-print-summary * {{ display: revert !important; }}
}}
</style></head><body>
<h1>Coach Dashboard — {escape(our_team_name)}</h1>
<p class="cd-note">Every number on this page traces to
<code>analytics.pairing_evidence</code>, the validated
<code>analytics.head_to_head.skill_only_win_probability</code>, or
<code>analytics.lineup_lab</code>'s approved assignment. No new
win-probability model, no invented danger threshold, no categorical
verdict -- see <code>docs/captain_first_edge_experience.md</code> §13.
"Trend" below is a direction + volatility count plus a real plotted
sparkline of the player's whole skill-level history.</p>

<h2>Player vs Player</h2>
<div class="cd-controls">
<label>Your player: <select id="pme-player">{player_options}</select></label>
&nbsp;
<label>Opposing team: <select id="pme-opponent-team"></select></label>
&nbsp;
<label>Opponent player: <select id="pme-opponent"></select></label>
</div>
<p class="cd-note">Choose your player, then the opposing team, then the opposing player. Head-to-head is the real direct record captured for that exact pairing and scope; no direct history is shown explicitly rather than inferred.</p>
<div class="cd-filters">
<strong>Opponent filters:</strong>
<label>SL min <input type="number" id="pme-filter-sl-min" min="0" max="9"></label>
<label>SL max <input type="number" id="pme-filter-sl-max" min="0" max="9"></label>
<label>Min volatility <input type="number" id="pme-filter-vol-min" min="0" value="0"></label>
<label><input type="checkbox" class="pme-filter-trend" value="up" checked>Up</label>
<label><input type="checkbox" class="pme-filter-trend" value="down" checked>Down</label>
<label><input type="checkbox" class="pme-filter-trend" value="stable" checked>Stable</label>
<label><input type="checkbox" class="pme-filter-trend" value="no data" checked>No data</label>
</div>
<div id="pme-result"></div>

<h2>Team vs Team</h2>
<div class="cd-controls">
<label>Match: <select id="tme-scope">{scope_options}</select></label>
</div>
<div id="tme-result"></div>

<h2 class="mn-screen-only">Match Night</h2>
<p class="cd-note mn-screen-only">"They put up this player -- who should I send?" Confirm
tonight's scheduled match and who's available, pick the opponent's announced player, and
compare your legal options side by side. The normal APA path is five players totaling 23
or less. If and only if that path is proven impossible, the planner can surface APA's
verified four-player/19 fallback, which requires forfeiting match 5. A skill-level estimate
is not a promise, and skill-level movement is not a winning streak -- both are shown as
what they really are, not as a verdict.</p>
<div class="cd-controls mn-screen-only">
<label>Match: <select id="mn-scope">{scope_options}</select></label>
&nbsp;
<label>Scheduled match: <select id="mn-match"></select></label>
<p class="cd-note">Bundle generated: {escape(freshness_text)} -- when this export was built,
not necessarily when the underlying data was last synced from the league portal.</p>
&nbsp;
<button type="button" id="mn-reset">Reset Match Night</button>
&nbsp;
<button type="button" id="mn-print">Print summary</button>
</div>
<div id="mn-sticky" class="mn-sticky mn-screen-only"></div>
<div id="mn-warning" class="mn-screen-only"></div>
<div id="mn-roster" class="mn-screen-only"></div>
<div class="cd-controls mn-screen-only">
<label>They put up: <select id="mn-opponent"></select></label>
</div>
<div id="mn-scouting" class="mn-screen-only"></div>
<div id="mn-comparison" class="mn-screen-only"></div>
<h3 class="mn-screen-only">Boards sent (detail)</h3>
<div id="mn-lineup" class="mn-screen-only"></div>
<div id="mn-print-summary" class="mn-print-only"></div>

<h2>Opponent Risk Profile (whole-division, purely descriptive ranking)</h2>
<p class="cd-note">Ranked by reliability-weighted skill-only probability,
toughest first -- never a categorical "danger" label
(<code>analytics.opponent_risk_profile</code>).</p>
<div id="risk-result"><table><thead><tr><th>Opponent</th><th>Direct pairings</th>
<th>Direct win rate</th><th>Direct sample</th>
<th>Skill-only estimate</th></tr></thead>
<tbody>{risk_rows or '<tr><td colspan="5">No data</td></tr>'}</tbody></table></div>

<script type="application/json" id="cd-player-data">{_script_json(player_payload)}</script>
<script type="application/json" id="cd-player-opponent-index">{_script_json(opponent_index)}</script>
<script type="application/json" id="cd-team-data">{_script_json(team_payload)}</script>
<script>
(function () {{
  var PLAYER_DATA = JSON.parse(document.getElementById("cd-player-data").textContent);
  var PLAYER_OPPONENT_INDEX = JSON.parse(document.getElementById("cd-player-opponent-index").textContent);
  var TEAM_DATA = JSON.parse(document.getElementById("cd-team-data").textContent);

  function esc(value) {{
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }}
  function orNoData(value) {{
    return (value === null || value === undefined || value === "") ? "No data" : esc(value);
  }}
  function pct(value) {{
    return (value === null || value === undefined) ? "No data" : (value * 100).toFixed(1) + "%";
  }}
  function sparklineCaption(readings, dates) {{
    if (!readings || !readings.length) return "";
    var realDates = (dates || []).filter(function (d) {{ return !!d; }});
    var range = realDates.length ? realDates[0] + " \\u2192 " + realDates[realDates.length - 1] : "no dates recorded";
    var scale = readings.length > 1
      ? ", skill level " + Math.min.apply(null, readings) + "\\u2013" + Math.max.apply(null, readings)
          + " (points spaced by reading order, not real elapsed time)"
      : "";
    return readings.length + " reading(s), " + range + scale;
  }}
  function sparkline(readings, dates) {{
    if (!readings || readings.length < 2) return "";
    var w = 90, h = 22, pad = 2;
    var min = Math.min.apply(null, readings), max = Math.max.apply(null, readings);
    var range = (max - min) || 1;
    var step = (w - pad * 2) / (readings.length - 1);
    var points = readings.map(function (v, i) {{
      var x = pad + i * step;
      var y = h - pad - ((v - min) / range) * (h - pad * 2);
      return x.toFixed(1) + "," + y.toFixed(1);
    }}).join(" ");
    var title = esc(sparklineCaption(readings, dates));
    return "<svg class='cd-spark' width='" + w + "' height='" + h + "' viewBox='0 0 " + w + " " + h
         + "' role='img' aria-label='Skill level trend sparkline: " + title + "'>"
         + "<title>" + title + "</title>"
         + "<polyline points='" + points + "' fill='none' stroke='#1F3864' stroke-width='1.5'/></svg>";
  }}
  function trendBadge(t) {{
    var arrow = {{"up": "\\u25b2", "down": "\\u25bc", "stable": "\\u25ac"}}[t.trend] || "?";
    var badge = arrow + " " + orNoData(t.trend) + " (whole history, volatility " + t.volatility + ")"
         + sparkline(t.readings, t.reading_dates);
    var caption = sparklineCaption(t.readings, t.reading_dates);
    if (caption) {{
      badge += " <span class='cd-note' style='display:inline'>(" + esc(caption) + ")</span>";
    }}
    return badge;
  }}

  function opponentFilters() {{
    var slMin = parseFloat(document.getElementById("pme-filter-sl-min").value);
    var slMax = parseFloat(document.getElementById("pme-filter-sl-max").value);
    var volMin = parseFloat(document.getElementById("pme-filter-vol-min").value);
    var trends = Array.prototype.slice.call(
      document.querySelectorAll(".pme-filter-trend:checked")
    ).map(function (cb) {{ return cb.value; }});
    return {{ slMin: slMin, slMax: slMax, volMin: volMin, trends: trends }};
  }}

  function passesFilters(choice, filters) {{
    var r = PLAYER_DATA[choice.key];
    if (!r) return true;
    var sl = r.opponent.skill_level;
    if (!isNaN(filters.slMin) && (sl === null || sl < filters.slMin)) return false;
    if (!isNaN(filters.slMax) && (sl === null || sl > filters.slMax)) return false;
    if (!isNaN(filters.volMin) && r.opponent.trend.volatility < filters.volMin) return false;
    if (filters.trends.indexOf(r.opponent.trend.trend) === -1) return false;
    return true;
  }}

  function pmeScopeKey(r) {{
    return String(r.opponent_team_id) + "|" + String(r.format) + "|" + String(r.session_name);
  }}

  function pmeScopeLabel(r) {{
    var team = r.opponent_team_name || r.opponent_team_id || "Unknown team";
    return team + " (" + r.format + ", " + r.session_name + ")";
  }}

  function refreshOpponentTeams() {{
    var playerId = document.getElementById("pme-player").value;
    var choices = PLAYER_OPPONENT_INDEX[playerId] || [];
    var previous = document.getElementById("pme-opponent-team").value;
    var seen = {{}};
    var teams = [];
    choices.forEach(function (choice) {{
      var r = PLAYER_DATA[choice.key];
      if (!r) return;
      var key = pmeScopeKey(r);
      if (seen[key]) return;
      seen[key] = true;
      teams.push({{key: key, label: pmeScopeLabel(r)}});
    }});
    teams.sort(function (a, b) {{ return a.label.localeCompare(b.label); }});

    var select = document.getElementById("pme-opponent-team");
    select.innerHTML = teams.length
      ? teams.map(function (team) {{
          return "<option value=\\\"" + esc(team.key) + "\\\">" + esc(team.label) + "</option>";
        }}).join("")
      : "<option value=\\\"\\\">No opposing teams available</option>";
    if (teams.some(function (team) {{ return team.key === previous; }})) {{
      select.value = previous;
    }}
    refreshOpponents();
  }}

  function refreshOpponents() {{
    var playerId = document.getElementById("pme-player").value;
    var scopeKey = document.getElementById("pme-opponent-team").value;
    var choices = (PLAYER_OPPONENT_INDEX[playerId] || []).filter(function (choice) {{
      var r = PLAYER_DATA[choice.key];
      return r && pmeScopeKey(r) === scopeKey && passesFilters(choice, opponentFilters());
    }});
    var select = document.getElementById("pme-opponent");
    select.innerHTML = choices.length
      ? choices.map(function (choice) {{
          var r = PLAYER_DATA[choice.key];
          var label = r && r.opponent
            ? r.opponent.name + " (SL " + orNoData(r.opponent.skill_level) + ")"
            : choice.label;
          return "<option value=\\\"" + esc(choice.key) + "\\\">" + esc(label) + "</option>";
        }}).join("")
      : "<option value=\\\"\\\">No opponents match this team/filter selection</option>";
    renderPlayer();
  }}

  function renderPlayer() {{
    var key = document.getElementById("pme-opponent").value;
    var target = document.getElementById("pme-result");
    var r = PLAYER_DATA[key];
    if (!r) {{ target.innerHTML = "<p class='cd-none'>No report for this pairing.</p>"; return; }}

    var html = "<table><tbody>";
    html += "<tr><th>Scope</th><td>" + esc(r.our_team_id) + " vs " + esc(r.opponent_team_id)
         + " &middot; " + esc(r.format) + " &middot; " + esc(r.session_name) + "</td></tr>";
    html += "<tr><th>" + esc(r.player.name) + "</th><td>SL " + orNoData(r.player.skill_level)
         + " &middot; " + trendBadge(r.player.trend) + "</td></tr>";
    html += "<tr><th>" + esc(r.opponent.name) + "</th><td>SL " + orNoData(r.opponent.skill_level)
         + " &middot; " + trendBadge(r.opponent.trend) + "</td></tr>";
    html += "<tr><th>Evidence</th><td>" + esc(r.evidence_label) + "</td></tr>";
    html += "<tr><th>Head-to-head record</th><td>"
         + (r.direct_wins !== null
            ? r.direct_wins + "-" + r.direct_losses + " &middot; " + pct(r.observed_win_rate)
              + " observed win rate across " + r.direct_evidence_count + " recorded direct match(es)"
            : "No direct history (" + r.direct_evidence_count + " recorded direct match(es))")
         + "</td></tr>";
    html += "<tr><th>Modeled probability</th><td>" + pct(r.modeled_win_probability) + "</td></tr>";
    html += "</tbody></table><p class='cd-summary-box'>" + esc(r.summary) + "</p>";
    target.innerHTML = html;
  }}

  function captainsEdgeCard(r) {{
    var counts = r.evidence_counts;
    var total = counts.total_feasible_pairings || 0;
    var directPct = total ? Math.round(((counts.DIRECT || 0) / total) * 100) + "%" : "No data";
    var lineupStatus;
    if (r.lineup) {{
      lineupStatus = r.lineup.assignments.length + " board(s) filled";
      if (r.lineup.unassigned_players.length) {{
        lineupStatus += ", " + r.lineup.unassigned_players.length + " player(s) unassigned";
      }}
    }} else {{
      lineupStatus = "No approved lineup: " + esc(r.lineup_error || "unavailable");
    }}
    var ranked = r.ranked_opponents.filter(function (o) {{
      return o.reliability_weighted_skill_probability !== null;
    }});
    var lowest = ranked.length ? ranked[0] : null;
    var highest = ranked.length ? ranked[ranked.length - 1] : null;

    var html = "<div class='cd-edge-card'><h3>Captain's Edge</h3><table><tbody>";
    html += "<tr><th>Scope</th><td>" + esc(r.our_team.name) + " vs " + esc(r.opponent_team.name)
         + " &middot; " + esc(r.format) + " &middot; " + esc(r.session_name) + "</td></tr>";
    html += "<tr><th>Evidence coverage</th><td>" + (counts.DIRECT || 0) + " direct / "
         + (counts.INDIRECT || 0) + " indirect / " + (counts.UNKNOWN || 0) + " unknown of "
         + total + " (" + directPct + " direct)</td></tr>";
    html += "<tr><th>Lineup</th><td>" + lineupStatus + "</td></tr>";
    html += "<tr><th>Lowest experimental estimate</th><td>"
         + (lowest ? esc(lowest.name) + " (" + pct(lowest.reliability_weighted_skill_probability) + ")" : "No data")
         + "</td></tr>";
    html += "<tr><th>Highest experimental estimate</th><td>"
         + (highest ? esc(highest.name) + " (" + pct(highest.reliability_weighted_skill_probability) + ")" : "No data")
         + "</td></tr>";
    html += "</tbody></table><p class='cd-note'>Descriptive only -- the "
         + "lowest/highest experimental skill-only estimate from the ranked "
         + "table below, not a validated \\"favored\\"/\\"danger\\" verdict.</p></div>";
    return html;
  }}

  function renderTeam() {{
    var key = document.getElementById("tme-scope").value;
    var target = document.getElementById("tme-result");
    var r = TEAM_DATA[key];
    if (!r) {{ target.innerHTML = "<p class='cd-none'>No report for this match.</p>"; return; }}

    var html = captainsEdgeCard(r);
    html += "<p class='cd-summary-box'>" + esc(r.summary) + "</p>";
    html += "<table><tbody>";
    html += "<tr><th>Direct</th><td>" + (r.evidence_counts.DIRECT || 0) + "</td></tr>";
    html += "<tr><th>Indirect</th><td>" + (r.evidence_counts.INDIRECT || 0) + "</td></tr>";
    html += "<tr><th>Unknown</th><td>" + (r.evidence_counts.UNKNOWN || 0) + "</td></tr>";
    html += "</tbody></table>";

    function rosterTable(name, roster) {{
      var out = "<h4>" + esc(name) + "</h4><table><thead><tr><th>Player</th><th>SL</th><th>Trend</th></tr></thead><tbody>";
      roster.forEach(function (p) {{
        out += "<tr><td>" + esc(p.name) + "</td><td>" + orNoData(p.skill_level) + "</td>"
             + "<td>" + trendBadge(p.trend) + "</td></tr>";
      }});
      return out + "</tbody></table>";
    }}
    html += "<div class='cd-cols'><div>" + rosterTable("Our roster", r.our_roster) + "</div>"
         + "<div>" + rosterTable("Opponent roster", r.opponent_roster) + "</div></div>";

    html += "<h4>Opponent ranking</h4><p class='cd-note'>Sorted by an "
         + "experimental, not independently validated skill-only estimate "
         + "(lowest first) -- a ranking signal to read from the table, not "
         + "a tactical verdict. Pooled direct win rate is the real combined "
         + "record, not an average of averages.</p>"
         + "<table><thead><tr>"
         + "<th>Opponent</th><th>SL</th><th>Pooled direct win rate</th><th>Direct W-L</th>"
         + "<th>Skill-only estimate (experimental)</th></tr></thead><tbody>";
    r.ranked_opponents.forEach(function (o) {{
      html += "<tr><td>" + esc(o.name) + "</td><td>" + orNoData(o.skill_level) + "</td>"
           + "<td>" + pct(o.direct_win_rate) + "</td>"
           + "<td>" + (o.direct_wins !== null ? o.direct_wins + "-" + o.direct_losses : "No data") + "</td>"
           + "<td>" + pct(o.reliability_weighted_skill_probability) + "</td></tr>";
    }});
    html += "</tbody></table>";

    html += "<h4>Approved lineup</h4>";
    if (r.lineup) {{
      html += "<table><thead><tr><th>Board</th><th>Our player</th><th>Opponent</th>"
           + "<th>Evidence</th><th>Score</th><th>Score basis</th><th>Direct evidence</th></tr></thead><tbody>";
      r.lineup.assignments.forEach(function (slot) {{
        html += "<tr><td>" + slot.board + "</td><td>" + esc(slot.player_name) + "</td>"
             + "<td>" + esc(slot.opponent_name) + "</td><td>" + esc(slot.evidence_label) + "</td>"
             + "<td>" + (slot.lineup_score !== null && slot.lineup_score !== undefined
                 ? slot.lineup_score.toFixed(3) : "No data") + "</td>"
             + "<td>" + orNoData(slot.lineup_score_source) + "</td>"
             + "<td>" + (slot.observed_win_rate !== null
                 ? pct(slot.observed_win_rate) + " (" + slot.direct_evidence_count + " match(es), "
                     + orNoData(slot.model_source) + ")" : "No data")
             + "</td></tr>";
      }});
      html += "</tbody></table>";
      if (r.lineup.unassigned_players.length) {{
        html += "<p>Unassigned players: " + r.lineup.unassigned_players.map(function (p) {{
          return esc(p.name);
        }}).join(", ") + "</p>";
      }}
      if (r.lineup.unassigned_opponents.length) {{
        html += "<p>Unassigned opponents: " + r.lineup.unassigned_opponents.map(function (p) {{
          return esc(p.name);
        }}).join(", ") + "</p>";
      }}
      if (r.lineup.blocked_reason) {{
        html += "<p class='cd-none'>" + esc(r.lineup.blocked_reason) + "</p>";
      }}
    }} else {{
      html += "<p class='cd-none'>" + esc(r.lineup_error || "No approved lineup available.") + "</p>";
    }}
    target.innerHTML = html;
  }}

  // ---- Match Night ----
  // The browser mirrors analytics.lineup_legality.assess_completion_options:
  // prefer the normal 5-player/23 path whenever proven legal; only surface
  // the verified 4-player/19 path when five is proven impossible and four is
  // proven legal; never recommend a forfeit while five remains unresolved.
  var MN_LIMIT_5 = 23;
  var MN_SIZE_5 = 5;
  var MN_LIMIT_4 = 19;
  var MN_SIZE_4 = 4;
  // Backwards-compatible aliases for the rest of the existing Match Night UI.
  var MN_LIMIT = MN_LIMIT_5;
  var MN_SIZE = MN_SIZE_5;
  var MN_MAX_COMPLETION_ATTEMPTS = 200000;
  var MN_SEARCH_BOUND_EXCEEDED = "too-many-to-check";
  var MN_STATUSES = ["available", "absent", "played", "held"];
  var MN_STATUS_LABELS = {{
    available: "Available", absent: "Absent", played: "Already played", held: "Held back"
  }};
  var mnState = {{ statuses: {{}}, assignments: [] }};
  var mnSelectionUnavailableReason = null;

  function mnChooseCount(n, k) {{
    var result = 1;
    for (var i = 0; i < k; i++) {{ result = result * (n - i) / (i + 1); }}
    return result;
  }}

  function mnCompletionExistsForTarget(
    committed, available, targetSize, skillLimit, insufficientPlayersAreUnknown
  ) {{
    if (committed.some(function (v) {{ return v === null || v === undefined; }})) return null;
    if (committed.length > targetSize) return false;
    var stillNeeded = targetSize - committed.length;
    var committedTotal = committed.reduce(function (a, b) {{ return a + b; }}, 0);
    if (stillNeeded === 0) return committedTotal <= skillLimit;
    if (available.length < stillNeeded) return insufficientPlayersAreUnknown ? null : false;
    var known = available.filter(function (v) {{ return v !== null && v !== undefined; }});
    if (known.length < stillNeeded) return null;
    if (mnChooseCount(known.length, stillNeeded) > MN_MAX_COMPLETION_ATTEMPTS) {{
      return MN_SEARCH_BOUND_EXCEEDED;
    }}
    var remainingCap = skillLimit - committedTotal;
    var found = false;
    (function combos(start, chosen) {{
      if (found || chosen.length === stillNeeded) {{
        if (chosen.length === stillNeeded) {{
          var sum = chosen.reduce(function (a, b) {{ return a + b; }}, 0);
          if (sum <= remainingCap) found = true;
        }}
        return;
      }}
      for (var i = start; i < known.length && !found; i++) {{
        chosen.push(known[i]);
        combos(i + 1, chosen);
        chosen.pop();
      }}
    }})(0, []);
    return found;
  }}

  function mnLegalCompletionExists(committed, available) {{
    if (committed.length > MN_SIZE_5) return null;
    var result = mnCompletionExistsForTarget(
      committed, available, MN_SIZE_5, MN_LIMIT_5, true
    );
    return result === MN_SEARCH_BOUND_EXCEEDED ? null : result;
  }}

  function mnBoundExceededAssessment(standard) {{
    return {{
      standardFivePossible: standard === MN_SEARCH_BOUND_EXCEEDED ? null : standard,
      fourPlayerFallbackPossible: null,
      preferredLineupSize: null,
      skillLimit: null,
      requiresForfeit: false,
      verificationStatus: MN_SEARCH_BOUND_EXCEEDED,
    }};
  }}

  function mnAssessCompletionOptions(committed, available) {{
    if (committed.length > MN_SIZE_5) return null;
    if (committed.some(function (v) {{ return v === null || v === undefined; }})) return null;

    var standard = mnCompletionExistsForTarget(
      committed, available, MN_SIZE_5, MN_LIMIT_5, false
    );
    if (standard === MN_SEARCH_BOUND_EXCEEDED) {{
      return mnBoundExceededAssessment(standard);
    }}
    var fallback = mnCompletionExistsForTarget(
      committed, available, MN_SIZE_4, MN_LIMIT_4, false
    );
    if (fallback === MN_SEARCH_BOUND_EXCEEDED) {{
      return mnBoundExceededAssessment(standard);
    }}
    var preferredLineupSize = null;
    var skillLimit = null;
    var requiresForfeit = false;

    if (standard === true) {{
      preferredLineupSize = MN_SIZE_5;
      skillLimit = MN_LIMIT_5;
    }} else if (standard === false && fallback === true) {{
      preferredLineupSize = MN_SIZE_4;
      skillLimit = MN_LIMIT_4;
      requiresForfeit = true;
    }}

    return {{
      standardFivePossible: standard,
      fourPlayerFallbackPossible: fallback,
      preferredLineupSize: preferredLineupSize,
      skillLimit: skillLimit,
      requiresForfeit: requiresForfeit,
    }};
  }}

  function mnFriendlyModelSource(modelSource) {{
    if (!modelSource) return "No data";
    if (modelSource.indexOf("direct-history-and-skill") !== -1) {{
      return "Based on head-to-head history and skill level";
    }}
    if (modelSource.indexOf("skill-only") !== -1) {{
      return "Based on skill level only (no head-to-head history)";
    }}
    return "Based on this project's matchup model";
  }}

  function mnKnownSkillSum(committed) {{
    return committed
      .filter(function (v) {{ return v !== null && v !== undefined; }})
      .reduce(function (a, b) {{ return a + b; }}, 0);
  }}

  function mnFindCompletionWitnessForTarget(
    committedSkills, availablePlayers, targetSize, skillLimit, insufficientPlayersAreUnknown
  ) {{
    if (committedSkills.some(function (v) {{ return v === null || v === undefined; }})) {{
      return {{ status: "unknown", players: [] }};
    }}
    if (committedSkills.length > targetSize) {{
      return {{ status: "no-legal", players: [] }};
    }}
    var stillNeeded = targetSize - committedSkills.length;
    var committedTotal = committedSkills.reduce(function (a, b) {{ return a + b; }}, 0);
    if (stillNeeded === 0) {{
      return committedTotal <= skillLimit
        ? {{ status: "ok", players: [] }} : {{ status: "no-legal", players: [] }};
    }}
    if (availablePlayers.length < stillNeeded) {{
      return insufficientPlayersAreUnknown
        ? {{ status: "unknown", players: [] }}
        : {{ status: "no-legal", players: [] }};
    }}
    var known = availablePlayers.filter(function (p) {{
      return p.skill_level !== null && p.skill_level !== undefined;
    }});
    if (known.length < stillNeeded) return {{ status: "unknown", players: [] }};
    if (mnChooseCount(known.length, stillNeeded) > MN_MAX_COMPLETION_ATTEMPTS) {{
      return {{ status: MN_SEARCH_BOUND_EXCEEDED, players: [] }};
    }}
    var remainingCap = skillLimit - committedTotal;
    var found = null;
    (function combos(start, chosen) {{
      if (found) return;
      if (chosen.length === stillNeeded) {{
        var sum = chosen.reduce(function (a, b) {{ return a + b.skill_level; }}, 0);
        if (sum <= remainingCap) found = chosen.slice();
        return;
      }}
      for (var i = start; i < known.length && !found; i++) {{
        chosen.push(known[i]);
        combos(i + 1, chosen);
        chosen.pop();
      }}
    }})(0, []);
    return found ? {{ status: "ok", players: found }} : {{ status: "no-legal", players: [] }};
  }}

  function mnFindCompletionWitness(committedSkills, availablePlayers) {{
    return mnFindCompletionWitnessForTarget(
      committedSkills, availablePlayers, MN_SIZE_5, MN_LIMIT_5, true
    );
  }}

  function mnCompletionDecision(committedSkills, availablePlayers) {{
    var levels = availablePlayers.map(function (p) {{ return p.skill_level; }});
    var assessment = mnAssessCompletionOptions(committedSkills, levels);
    if (!assessment) {{
      return {{ status: "unknown", players: [], assessment: null }};
    }}
    if (assessment.verificationStatus === MN_SEARCH_BOUND_EXCEEDED) {{
      return {{ status: MN_SEARCH_BOUND_EXCEEDED, players: [], assessment: assessment }};
    }}
    if (assessment.preferredLineupSize === MN_SIZE_5) {{
      var standardWitness = mnFindCompletionWitnessForTarget(
        committedSkills, availablePlayers, MN_SIZE_5, MN_LIMIT_5, false
      );
      if (standardWitness.status === MN_SEARCH_BOUND_EXCEEDED) {{
        return {{ status: MN_SEARCH_BOUND_EXCEEDED, players: [], assessment: assessment }};
      }}
      return {{ status: "standard", players: standardWitness.players, assessment: assessment }};
    }}
    if (assessment.preferredLineupSize === MN_SIZE_4) {{
      var fallbackWitness = mnFindCompletionWitnessForTarget(
        committedSkills, availablePlayers, MN_SIZE_4, MN_LIMIT_4, false
      );
      if (fallbackWitness.status === MN_SEARCH_BOUND_EXCEEDED) {{
        return {{ status: MN_SEARCH_BOUND_EXCEEDED, players: [], assessment: assessment }};
      }}
      return {{ status: "fallback", players: fallbackWitness.players, assessment: assessment }};
    }}
    if (assessment.standardFivePossible === null || assessment.fourPlayerFallbackPossible === null) {{
      return {{ status: "unknown", players: [], assessment: assessment }};
    }}
    return {{ status: "no-legal", players: [], assessment: assessment }};
  }}

  function mnStorageKey(matchKey) {{ return "match-night:" + matchKey; }}

  function mnLoadState(matchKey) {{
    try {{
      var raw = window.localStorage.getItem(mnStorageKey(matchKey));
      if (raw) return JSON.parse(raw);
    }} catch (e) {{ }}
    return {{ statuses: {{}}, assignments: [] }};
  }}

  function mnSaveState(matchKey, state) {{
    try {{ window.localStorage.setItem(mnStorageKey(matchKey), JSON.stringify(state)); }}
    catch (e) {{ }}
  }}

  function mnCurrentScope() {{
    return TEAM_DATA[document.getElementById("mn-scope").value];
  }}

  function mnCurrentMatchKey() {{
    var scopeKey = document.getElementById("mn-scope").value;
    var matchSelect = document.getElementById("mn-match");
    var matchId = matchSelect && matchSelect.value ? matchSelect.value : "";
    return matchId ? (scopeKey + "|match:" + matchId) : scopeKey;
  }}

  function mnSelectedMatchLabel(scope) {{
    var matches = scope.real_matches || [];
    var matchId = document.getElementById("mn-match").value;
    var selected = matches.filter(function (m) {{ return String(m.external_id) === String(matchId); }})[0];
    if (!selected) return "no specific scheduled match identified";
    return (selected.match_date || "unknown date") + " (id " + selected.external_id + ")";
  }}

  function mnRenderMatchSelect(scope) {{
    var select = document.getElementById("mn-match");
    var matches = scope.real_matches || [];
    if (!matches.length) {{
      select.innerHTML = "<option value=''>No specific scheduled match identified</option>";
      return;
    }}
    select.innerHTML = matches.map(function (m) {{
      var label = (m.match_date || "Unknown date")
        + (m.is_finalized ? " (finalized)" : (m.is_scored ? " (scored)" : " (not yet played)"));
      return "<option value='" + esc(m.external_id) + "'>" + esc(label) + "</option>";
    }}).join("");
  }}

  function mnCommittedSkillLevels(scope) {{
    return scope.our_roster
      .filter(function (p) {{ return mnState.statuses[p.id] === "played"; }})
      .map(function (p) {{ return p.skill_level; }});
  }}

  function mnAvailablePlayers(scope) {{
    return scope.our_roster.filter(function (p) {{
      return (mnState.statuses[p.id] || "available") === "available";
    }});
  }}

  function mnCurrentCompletionAssessment(scope) {{
    return mnAssessCompletionOptions(
      mnCommittedSkillLevels(scope),
      mnAvailablePlayers(scope).map(function (p) {{ return p.skill_level; }})
    );
  }}

  function mnPairKey(scope, playerId, opponentId) {{
    return scope.our_team.id + "|" + scope.opponent_team.id + "|" + scope.format + "|"
      + scope.session_name + "|" + playerId + ":" + opponentId;
  }}

  function mnPlayedCount(scope) {{
    return scope.our_roster.filter(function (p) {{
      return mnState.statuses[p.id] === "played";
    }}).length;
  }}

  function mnSelectionUnavailableMessage() {{
    return mnSelectionUnavailableReason === "scope"
      ? "Your previously selected match's opponent/format/session is no longer in this bundle."
      : "Your previously selected scheduled match is no longer available for this opponent, format, and session.";
  }}

  function mnBoundExceededMessage() {{
    return "Too many remaining Available players to check every exact legal completion. Narrow tonight's Available list before relying on Match Night. No fallback or forfeit recommendation is being made.";
  }}

  function mnRenderWarning(scope) {{
    var target = document.getElementById("mn-warning");
    if (mnSelectionUnavailableReason) {{
      target.innerHTML = "<p class='cd-none mn-selection-unavailable'>" + mnSelectionUnavailableMessage()
        + " Choose a match above to continue -- Send is disabled until you do.</p>";
      return;
    }}
    var playedCount = mnPlayedCount(scope);
    if (playedCount > MN_SIZE_5) {{
      target.innerHTML = "<p class='cd-none'>" + playedCount + " players are marked Already played -- a standard lineup only uses "
        + MN_SIZE_5 + ". Check for a mis-click before relying on the legality check below.</p>";
      return;
    }}
    var committed = mnCommittedSkillLevels(scope);
    var assessment = mnCurrentCompletionAssessment(scope);
    var unknownCommitted = committed.some(function (v) {{ return v === null || v === undefined; }});

    if (!assessment) {{
      target.innerHTML = "<p class='cd-note'>The current lineup cannot be verified because "
        + (unknownCommitted ? "an already-played player's skill level is unknown. " : "the state is incomplete. ")
        + "The 4-player fallback is not recommended while the standard 5-player path cannot be verified.</p>";
      return;
    }}
    if (assessment.verificationStatus === MN_SEARCH_BOUND_EXCEEDED) {{
      target.innerHTML = "<p class='cd-none'>" + mnBoundExceededMessage() + "</p>";
      return;
    }}
    if (assessment.preferredLineupSize === MN_SIZE_4) {{
      target.innerHTML = playedCount >= MN_SIZE_4
        ? "<p class='cd-none'>Verified 4-player / 19 fallback is complete. Match 5 must be forfeited; no fifth Send is legal under this fallback.</p>"
        : "<p class='cd-none'>No legal 5-player / 23 completion remains. A verified 4-player / 19 fallback is available, and using it requires forfeiting match 5.</p>";
      return;
    }}
    if (assessment.standardFivePossible === false && assessment.fourPlayerFallbackPossible === false) {{
      target.innerHTML = "<p class='cd-none'>No legal 5-player / 23 lineup and no legal 4-player / 19 fallback can still be completed from tonight's Available players.</p>";
      return;
    }}
    if (assessment.standardFivePossible === null) {{
      target.innerHTML = "<p class='cd-note'>Cannot verify the standard 5-player / 23 path because one or more remaining skill levels are unknown. The 4-player fallback is not recommended while the standard path is unresolved.</p>";
      return;
    }}
    if (assessment.standardFivePossible === false && assessment.fourPlayerFallbackPossible === null) {{
      target.innerHTML = "<p class='cd-note'>The standard 5-player / 23 path is not legal, but the 4-player / 19 fallback cannot be verified from the known skill levels. Do not assume a forfeit path.</p>";
      return;
    }}
    target.innerHTML = "";
  }}

  function mnRenderRoster(scope) {{
    var target = document.getElementById("mn-roster");
    var html = "<h4>Tonight's roster</h4>";
    scope.our_roster.forEach(function (p) {{
      var status = mnState.statuses[p.id] || "available";
      html += "<div class='mn-roster-row'><span class='mn-roster-name'>" + esc(p.name)
        + "</span><span class='cd-note'>SL " + orNoData(p.skill_level) + "</span>"
        + "<select data-player-id='" + p.id + "' class='mn-status-select'>"
        + MN_STATUSES.map(function (s) {{
            return "<option value='" + s + "'" + (s === status ? " selected" : "") + ">"
              + MN_STATUS_LABELS[s] + "</option>";
          }}).join("")
        + "</select></div>";
    }});
    target.innerHTML = html;
    target.querySelectorAll(".mn-status-select").forEach(function (sel) {{
      sel.addEventListener("change", function () {{
        var pid = sel.getAttribute("data-player-id");
        var newStatus = sel.value;
        if (newStatus !== "played") {{
          mnState.assignments = mnState.assignments.filter(function (a) {{
            return String(a.player_id) !== String(pid);
          }});
          mnState.assignments.forEach(function (a, i) {{ a.board = i + 1; }});
        }}
        mnState.statuses[pid] = newStatus;
        mnSaveState(mnCurrentMatchKey(), mnState);
        mnRenderAll();
      }});
    }});
  }}

  function mnRenderOpponentSelect(scope) {{
    var select = document.getElementById("mn-opponent");
    var previous = select.value;
    var usedOpponentIds = {{}};
    mnState.assignments.forEach(function (a) {{ usedOpponentIds[a.opponent_id] = true; }});
    var remaining = scope.opponent_roster.filter(function (o) {{ return !usedOpponentIds[o.id]; }});
    select.innerHTML = remaining.length
      ? remaining.map(function (o) {{
          return "<option value='" + o.id + "'>" + esc(o.name) + " (SL "
            + orNoData(o.skill_level) + ")</option>";
        }}).join("")
      : "<option value=''>No remaining opponents identified</option>";
    if (remaining.some(function (o) {{ return String(o.id) === previous; }})) {{
      select.value = previous;
    }}
  }}

  function mnRenderComparison(scope) {{
    var target = document.getElementById("mn-comparison");
    if (mnSelectionUnavailableReason) {{
      target.innerHTML = "<p class='cd-none mn-selection-unavailable'>" + mnSelectionUnavailableMessage()
        + " Choose a match above before comparing options.</p>";
      return;
    }}
    var playedCount = mnPlayedCount(scope);
    var currentAssessment = mnCurrentCompletionAssessment(scope);
    if (playedCount >= MN_SIZE_4 && currentAssessment
        && currentAssessment.preferredLineupSize === MN_SIZE_4) {{
      target.innerHTML = "<p class='cd-none'>The verified 4-player / 19 fallback is complete. Match 5 must be forfeited, so no fifth Send is available.</p>";
      return;
    }}
    if (playedCount >= MN_SIZE_5) {{
      target.innerHTML = "<p class='cd-none'>All " + MN_SIZE_5 + " boards are already accounted for (sent or marked Already played) this match. Undo a sent board below, or change a player's status, if you need to free one up.</p>";
      return;
    }}
    var opponentId = document.getElementById("mn-opponent").value;
    if (!opponentId) {{
      target.innerHTML = "<p class='cd-none'>Select who they put up.</p>";
      return;
    }}
    var opponent = scope.opponent_roster.filter(function (o) {{
      return String(o.id) === String(opponentId);
    }})[0];
    var available = mnAvailablePlayers(scope);
    if (!available.length) {{
      target.innerHTML = "<p class='cd-none'>No players are marked Available.</p>";
      return;
    }}
    var committed = mnCommittedSkillLevels(scope);
    var html = "<h4>They put up " + esc(opponent ? opponent.name : "?") + " -- who should you send?</h4>";
    available.forEach(function (p) {{
      var report = PLAYER_DATA[mnPairKey(scope, p.id, opponentId)];
      var otherAvailablePlayers = available.filter(function (q) {{ return String(q.id) !== String(p.id); }});
      var candidateCommitted = committed.concat([p.skill_level]);
      var decision = mnCompletionDecision(candidateCommitted, otherAvailablePlayers);
      var cls = decision.status === "no-legal" ? "mn-warn"
        : ((decision.status === "unknown" || decision.status === MN_SEARCH_BOUND_EXCEEDED) ? "mn-unknown"
        : (decision.status === "fallback" ? "mn-fallback" : "mn-ok"));
      html += "<div class='mn-card " + cls + "'><h4>" + esc(p.name) + " <span class='cd-note'>SL "
        + orNoData(p.skill_level) + "</span>" + trendBadge(p.trend) + "</h4>";
      if (report) {{
        html += "<table><tbody>"
          + "<tr><th>Evidence</th><td>" + esc(report.evidence_label) + "</td></tr>"
          + "<tr><th>Direct record</th><td>" + (report.direct_wins !== null && report.direct_wins !== undefined
              ? report.direct_wins + "-" + report.direct_losses + " (" + pct(report.observed_win_rate) + ")"
              : "No data") + " -- sample size " + report.direct_evidence_count + " match(es)</td></tr>"
          + "<tr><th>Estimate</th><td>" + pct(report.modeled_win_probability)
              + " <details class='mn-technical'><summary>"
              + esc(mnFriendlyModelSource(report.model_source)) + "</summary>"
              + esc(orNoData(report.model_source)) + "</details></td></tr>"
          + "</tbody></table>"
          + "<p class='cd-summary-box'>" + esc(report.summary) + "</p>";
      }} else {{
        html += "<p class='cd-none'>No matchup data found for this pairing.</p>";
      }}
      if (decision.status === "no-legal") {{
        html += "<p class='mn-status-line'>\\u26a0 Sending " + esc(p.name)
          + " -- No combination of tonight's remaining Available players produces a legal 5-player / 23 completion or 4-player / 19 fallback.</p>";
      }} else if (decision.status === MN_SEARCH_BOUND_EXCEEDED) {{
        html += "<p class='cd-none'>" + mnBoundExceededMessage() + "</p>";
      }} else if (decision.status === "unknown") {{
        html += "<p class='cd-note'>The standard 5-player / 23 path cannot be verified after this send. The 4-player fallback is not recommended while the standard path is unresolved.</p>";
      }} else if (decision.status === "fallback") {{
        if (decision.players.length) {{
          html += "<p class='mn-status-line'>Verified 4-player / 19 fallback finish: "
            + decision.players.map(function (w) {{ return esc(w.name) + " (SL " + w.skill_level + ")"; }}).join(", ")
            + ". Using this fallback requires forfeiting match 5.</p>";
        }} else {{
          html += "<p class='mn-status-line'>Sending " + esc(p.name)
            + " completes the verified 4-player / 19 fallback. Match 5 must be forfeited.</p>";
        }}
      }} else if (decision.players.length) {{
        html += "<p class='cd-note'>A valid finish: 5-player / 23: " + decision.players.map(function (w) {{
            return esc(w.name) + " (SL " + w.skill_level + ")";
          }}).join(", ") + ".</p>";
      }} else {{
        html += "<p class='cd-note'>Sending " + esc(p.name) + " completes a legal 5-player / 23 lineup.</p>";
      }}
      html += "<button type='button' class='mn-send-btn' data-player-id='" + p.id + "'>Send "
        + esc(p.name) + "</button></div>";
    }});
    target.innerHTML = html;
    target.querySelectorAll(".mn-send-btn").forEach(function (btn) {{
      btn.addEventListener("click", function () {{
        mnSendPlayer(scope, btn.getAttribute("data-player-id"), opponentId);
      }});
    }});
  }}

  function mnSendPlayer(scope, playerId, opponentId) {{
    if (mnSelectionUnavailableReason) return;
    var player = scope.our_roster.filter(function (p) {{ return String(p.id) === String(playerId); }})[0];
    var opponent = scope.opponent_roster.filter(function (o) {{ return String(o.id) === String(opponentId); }})[0];
    if (!player) return;

    var playedCount = mnPlayedCount(scope);
    var currentAssessment = mnCurrentCompletionAssessment(scope);
    if (playedCount >= MN_SIZE_4 && currentAssessment
        && currentAssessment.preferredLineupSize === MN_SIZE_4) {{
      window.alert("The verified 4-player / 19 fallback is complete. Match 5 must be forfeited; a fifth Send is not allowed under this fallback.");
      return;
    }}
    if (playedCount >= MN_SIZE_5) {{
      window.alert("All " + MN_SIZE_5 + " boards are already accounted for (sent or marked Already played) this match.");
      return;
    }}
    if (mnState.assignments.some(function (a) {{ return String(a.player_id) === String(playerId); }})) {{
      window.alert(player.name + " already has a recorded board this match. Undo it below first if you need to send them again.");
      return;
    }}

    var committed = mnCommittedSkillLevels(scope);
    var otherAvailablePlayers = mnAvailablePlayers(scope).filter(function (p) {{
      return String(p.id) !== String(playerId);
    }});
    var candidateCommitted = committed.concat([player.skill_level]);
    var decision = mnCompletionDecision(candidateCommitted, otherAvailablePlayers);
    if (decision.status === MN_SEARCH_BOUND_EXCEEDED) {{
      window.alert(mnBoundExceededMessage() + " Send was not recorded.");
      return;
    }}
    if (decision.status === "no-legal") {{
      var proceedIllegal = window.confirm(
        "Sending " + player.name + " would leave no legal 5-player / 23 lineup and no legal 4-player / 19 fallback possible with tonight's remaining Available players. Send anyway?"
      );
      if (!proceedIllegal) return;
    }} else if (decision.status === "fallback") {{
      var proceedFallback = window.confirm(
        "Sending " + player.name + " leaves the verified 4-player / 19 fallback as the legal path. Using that fallback requires forfeiting match 5. Continue?"
      );
      if (!proceedFallback) return;
    }}

    var report = PLAYER_DATA[mnPairKey(scope, playerId, opponentId)];
    mnState.assignments.push({{
      board: mnState.assignments.length + 1,
      player_id: player.id, player_name: player.name, player_skill_level: player.skill_level,
      opponent_id: opponent ? opponent.id : opponentId,
      opponent_name: opponent ? opponent.name : "?",
      opponent_skill_level: opponent ? opponent.skill_level : null,
      evidence_label: report ? report.evidence_label : null,
      observed_win_rate: report ? report.observed_win_rate : null,
      direct_wins: report ? report.direct_wins : null,
      direct_losses: report ? report.direct_losses : null,
      modeled_win_probability: report ? report.modeled_win_probability : null,
      model_source: report ? report.model_source : null,
    }});
    mnState.statuses[playerId] = "played";
    mnSaveState(mnCurrentMatchKey(), mnState);
    mnRenderAll();
  }}

  function mnUndoAssignment(scope, index) {{
    var removed = mnState.assignments.splice(index, 1)[0];
    if (removed && mnState.statuses[removed.player_id] === "played") {{
      mnState.statuses[removed.player_id] = "available";
    }}
    mnState.assignments.forEach(function (a, i) {{ a.board = i + 1; }});
    mnSaveState(mnCurrentMatchKey(), mnState);
    mnRenderAll();
  }}

  function mnRenderLineup(scope) {{
    var target = document.getElementById("mn-lineup");
    var html = "<h4>Boards sent tonight</h4>";
    if (!mnState.assignments.length) {{
      html += "<p class='cd-none'>No boards sent yet.</p>";
    }} else {{
      html += "<table><thead><tr><th>Board</th><th>Our player</th><th>Opponent</th>"
        + "<th>Evidence</th><th>Direct record</th><th>Modeled probability</th><th></th></tr></thead><tbody>";
      mnState.assignments.forEach(function (a, index) {{
        html += "<tr><td>" + a.board + "</td><td>" + esc(a.player_name) + " (SL "
          + orNoData(a.player_skill_level) + ")</td><td>" + esc(a.opponent_name) + " (SL "
          + orNoData(a.opponent_skill_level) + ")</td><td>" + esc(a.evidence_label) + "</td>"
          + "<td>" + (a.direct_wins !== null && a.direct_wins !== undefined
              ? a.direct_wins + "-" + a.direct_losses : "No data") + "</td>"
          + "<td>" + pct(a.modeled_win_probability)
              + " <details class='mn-technical'><summary>"
              + esc(mnFriendlyModelSource(a.model_source)) + "</summary>"
              + esc(orNoData(a.model_source)) + "</details></td>"
          + "<td><button type='button' class='mn-undo-btn' data-index='" + index + "'>Undo</button></td>"
          + "</tr>";
      }});
      html += "</tbody></table>";
    }}
    var committed = mnCommittedSkillLevels(scope);
    var assessment = mnCurrentCompletionAssessment(scope);
    var targetSize = assessment && assessment.preferredLineupSize === MN_SIZE_4 ? MN_SIZE_4 : MN_SIZE_5;
    var limit = targetSize === MN_SIZE_4 ? MN_LIMIT_4 : MN_LIMIT_5;
    html += "<p>Committed skill total so far: <strong>" + mnKnownSkillSum(committed)
      + "</strong> of " + limit + " (" + committed.length + " of " + targetSize + " "
      + (targetSize === MN_SIZE_4 ? "fallback slots" : "boards") + " used)";
    if (committed.some(function (v) {{ return v === null || v === undefined; }})) {{
      html += " <span class='cd-note'>-- includes a player with no known skill level; this total is a partial sum, not the real full total</span>";
    }}
    html += "</p>";
    if (assessment && assessment.verificationStatus === MN_SEARCH_BOUND_EXCEEDED) {{
      html += "<p class='cd-none'>" + mnBoundExceededMessage() + "</p>";
    }} else if (targetSize === MN_SIZE_4) {{
      html += "<p class='cd-none'>Verified 4-player / 19 fallback. Match 5 must be forfeited.</p>";
    }}
    target.innerHTML = html;
    target.querySelectorAll(".mn-undo-btn").forEach(function (btn) {{
      btn.addEventListener("click", function () {{
        mnUndoAssignment(scope, parseInt(btn.getAttribute("data-index"), 10));
      }});
    }});
  }}

  function mnRenderPrintSummary(scope) {{
    var target = document.getElementById("mn-print-summary");
    var html = "<h2>Match Night summary -- " + esc(scope.our_team.name) + " vs "
      + esc(scope.opponent_team.name) + " (" + esc(scope.format) + ", " + esc(scope.session_name) + ")</h2>";
    html += "<p>Scheduled match: " + esc(mnSelectedMatchLabel(scope)) + "</p>";
    html += "<h3>Roster status</h3><ul>";
    scope.our_roster.forEach(function (p) {{
      html += "<li>" + esc(p.name) + " -- " + MN_STATUS_LABELS[mnState.statuses[p.id] || "available"] + "</li>";
    }});
    html += "</ul><h3>Boards sent</h3>";
    if (!mnState.assignments.length) {{
      html += "<p>No boards sent yet.</p>";
    }} else {{
      html += "<ol>";
      mnState.assignments.forEach(function (a) {{
        html += "<li>" + esc(a.player_name) + " vs " + esc(a.opponent_name) + " -- "
          + esc(a.evidence_label) + ", "
          + (a.direct_wins !== null && a.direct_wins !== undefined
              ? a.direct_wins + "-" + a.direct_losses + " direct" : "no direct history")
          + "</li>";
      }});
      html += "</ol>";
    }}
    var committed = mnCommittedSkillLevels(scope);
    var assessment = mnCurrentCompletionAssessment(scope);
    var targetSize = assessment && assessment.preferredLineupSize === MN_SIZE_4 ? MN_SIZE_4 : MN_SIZE_5;
    var limit = targetSize === MN_SIZE_4 ? MN_LIMIT_4 : MN_LIMIT_5;
    html += "<p>Skill total: " + mnKnownSkillSum(committed) + " of " + limit;
    if (committed.some(function (v) {{ return v === null || v === undefined; }})) {{
      html += " -- a player with no known skill level is included in the board count above but not in this total; this is a partial sum, not the real full total";
    }}
    html += "</p>";
    if (assessment && assessment.verificationStatus === MN_SEARCH_BOUND_EXCEEDED) {{
      html += "<p>" + mnBoundExceededMessage() + "</p>";
    }} else if (targetSize === MN_SIZE_4) {{
      html += "<p>Verified 4-player / 19 fallback. Match 5 must be forfeited.</p>";
    }}
    target.innerHTML = html;
  }}

  function mnRenderSticky(scope) {{
    var target = document.getElementById("mn-sticky");
    var committed = mnCommittedSkillLevels(scope);
    var playedCount = mnPlayedCount(scope);
    var knownSum = mnKnownSkillSum(committed);
    var hasUnknown = committed.some(function (v) {{ return v === null || v === undefined; }});
    var assessment = mnCurrentCompletionAssessment(scope);
    var targetSize = assessment && assessment.preferredLineupSize === MN_SIZE_4 ? MN_SIZE_4 : MN_SIZE_5;
    var limit = targetSize === MN_SIZE_4 ? MN_LIMIT_4 : MN_LIMIT_5;
    var remainingSlots = Math.max(0, targetSize - playedCount);
    var warn = !assessment
      || (assessment && assessment.verificationStatus === MN_SEARCH_BOUND_EXCEEDED)
      || (assessment && assessment.preferredLineupSize === MN_SIZE_4)
      || (assessment && assessment.standardFivePossible !== true);
    var status = "";
    if (assessment && assessment.verificationStatus === MN_SEARCH_BOUND_EXCEEDED) {{
      status = "<span>&#9888; Too many Available players to check exactly; narrow tonight's Available list</span>";
    }} else if (!assessment || assessment.standardFivePossible === null) {{
      status = "<span>&#9888; Standard 5-player path cannot be verified; fallback not recommended</span>";
    }} else if (assessment.preferredLineupSize === MN_SIZE_4) {{
      status = "<span>&#9888; 4-player / 19 fallback — match 5 must be forfeited</span>";
    }} else if (assessment.standardFivePossible === false && assessment.fourPlayerFallbackPossible === false) {{
      status = "<span>&#9888; No legal 5-player / 23 or 4-player / 19 finish</span>";
    }} else if (assessment.standardFivePossible === false && assessment.fourPlayerFallbackPossible === null) {{
      status = "<span>&#9888; Fallback cannot be verified</span>";
    }}
    target.className = "mn-sticky mn-screen-only" + (warn ? " mn-sticky-warn" : "");
    target.innerHTML = "<span>" + esc(mnSelectedMatchLabel(scope)) + "</span>"
      + "<span><strong>" + remainingSlots + "</strong> " + (targetSize === MN_SIZE_4 ? "fallback slot(s)" : "board(s)") + " remaining</span>"
      + "<span>Skill total: <strong>" + knownSum + (hasUnknown ? "+?" : "") + "</strong> of " + limit + "</span>"
      + status;
  }}

  function mnRenderAll() {{
    var scope = mnCurrentScope();
    if (!scope) return;
    mnRenderRoster(scope);
    mnRenderOpponentSelect(scope);
    mnRenderScouting(scope);
    mnRenderComparison(scope);
    mnRenderLineup(scope);
    mnRenderWarning(scope);
    mnRenderSticky(scope);
    mnRenderPrintSummary(scope);
  }}

  function mnActiveSelectionStorageKey() {{ return "match-night:active-selection"; }}

  function mnSaveActiveSelection() {{
    try {{
      window.localStorage.setItem(mnActiveSelectionStorageKey(), JSON.stringify({{
        scopeKey: document.getElementById("mn-scope").value,
        matchId: document.getElementById("mn-match").value,
      }}));
    }} catch (e) {{ }}
  }}

  function mnLoadActiveSelection() {{
    try {{
      var raw = window.localStorage.getItem(mnActiveSelectionStorageKey());
      if (raw) return JSON.parse(raw);
    }} catch (e) {{ }}
    return null;
  }}

  function mnScoutingNotesKey(playerExternalId) {{
    return "match-night:scouting-notes:" + playerExternalId;
  }}

  function mnLoadScoutingNotes(playerExternalId) {{
    try {{
      return window.localStorage.getItem(mnScoutingNotesKey(playerExternalId)) || "";
    }} catch (e) {{ return ""; }}
  }}

  function mnSaveScoutingNotes(playerExternalId, text) {{
    try {{ window.localStorage.setItem(mnScoutingNotesKey(playerExternalId), text); }}
    catch (e) {{ }}
  }}

  function mnRenderScouting(scope) {{
    var target = document.getElementById("mn-scouting");
    if (mnSelectionUnavailableReason) {{ target.innerHTML = ""; return; }}
    var opponentId = document.getElementById("mn-opponent").value;
    if (!opponentId) {{ target.innerHTML = ""; return; }}
    var opponent = scope.opponent_roster.filter(function (o) {{
      return String(o.id) === String(opponentId);
    }})[0];
    if (!opponent) {{ target.innerHTML = ""; return; }}

    var available = mnAvailablePlayers(scope);
    var html = "<div class='mn-scouting-card'><h2>Scouting: " + esc(opponent.name)
      + " <span class='cd-note'>SL " + orNoData(opponent.skill_level) + "</span></h2>"
      + "<p class='cd-note'>Window: " + esc(scope.format) + ", " + esc(scope.session_name)
      + " only -- not this player's whole history, and not other formats/sessions.</p>";

    html += "<table><thead><tr><th>Our player</th><th>Evidence</th><th>Record</th>"
      + "<th>Sample size</th></tr></thead><tbody>";
    var recentGames = [];
    available.forEach(function (p) {{
      var report = PLAYER_DATA[mnPairKey(scope, p.id, opponentId)];
      if (!report) return;
      var recordText = (report.direct_wins !== null && report.direct_wins !== undefined)
        ? report.direct_wins + "-" + report.direct_losses
        : "No recorded meetings";
      html += "<tr><td>" + esc(p.name) + "</td><td>" + esc(report.evidence_label) + "</td>"
        + "<td>" + recordText + "</td><td>" + report.direct_evidence_count + "</td></tr>";
      (report.direct_games || []).forEach(function (g) {{
        recentGames.push({{ player: p.name, date: g.match_date, result: g.result }});
      }});
    }});
    html += "</tbody></table>";

    if (recentGames.length) {{
      html += "<h5>Recent recorded results</h5><ul>";
      recentGames.forEach(function (g) {{
        html += "<li>" + esc(g.date || "date unknown") + " -- " + esc(g.player) + " "
          + (g.result === "W" ? "won" : "lost") + "</li>";
      }});
      html += "</ul>";
    }} else {{
      html += "<p class='cd-none'>No recorded meetings within this window against any currently Available teammate.</p>";
    }}

    html += "<p class='cd-note'>Every estimate above uses skill levels only where no direct history exists within this window. A missing or small sample is shown exactly as that -- never treated as a loss, and this project does not track a win/loss streak separate from this real evidence.</p>";

    var savedNotes = mnLoadScoutingNotes(opponent.external_id);
    html += "<h5>Coach Observations <span class='cd-note'>(your own notes -- not calculated, saved for " + esc(opponent.name) + " across every match)</span></h5>"
      + "<textarea id='mn-scouting-notes' rows='3'>" + esc(savedNotes) + "</textarea>"
      + "<div><button type='button' id='mn-scouting-notes-save'>Save notes</button>"
      + " <span id='mn-scouting-notes-status' class='cd-note'></span></div>";

    html += "</div>";
    target.innerHTML = html;

    var saveBtn = document.getElementById("mn-scouting-notes-save");
    if (saveBtn) {{
      saveBtn.addEventListener("click", function () {{
        var text = document.getElementById("mn-scouting-notes").value;
        mnSaveScoutingNotes(opponent.external_id, text);
        document.getElementById("mn-scouting-notes-status").textContent = "Saved.";
      }});
    }}
  }}

  function mnInitScope() {{
    mnSelectionUnavailableReason = null;
    var scope = mnCurrentScope();
    if (scope) mnRenderMatchSelect(scope);
    mnState = mnLoadState(mnCurrentMatchKey());
    mnRenderAll();
    mnSaveActiveSelection();
  }}

  function mnOnMatchChange() {{
    mnSelectionUnavailableReason = null;
    mnState = mnLoadState(mnCurrentMatchKey());
    mnRenderAll();
    mnSaveActiveSelection();
  }}

  function mnRestoreActiveSelectionOnLoad() {{
    var saved = mnLoadActiveSelection();
    var scopeSelect = document.getElementById("mn-scope");
    var missingScope = false;

    if (saved) {{
      var hasScope = Array.prototype.some.call(scopeSelect.options, function (o) {{
        return o.value === saved.scopeKey;
      }});
      if (hasScope) {{
        scopeSelect.value = saved.scopeKey;
      }} else {{
        missingScope = true;
      }}
    }}

    var scope = mnCurrentScope();
    if (scope) mnRenderMatchSelect(scope);

    var missingMatch = false;
    if (saved && !missingScope && saved.matchId) {{
      var matchSelect = document.getElementById("mn-match");
      var hasMatch = Array.prototype.some.call(matchSelect.options, function (o) {{
        return o.value === saved.matchId;
      }});
      if (hasMatch) {{
        matchSelect.value = saved.matchId;
      }} else {{
        missingMatch = true;
      }}
    }}

    mnSelectionUnavailableReason = missingScope ? "scope" : (missingMatch ? "match" : null);

    if (mnSelectionUnavailableReason) {{
      mnState = {{ statuses: {{}}, assignments: [] }};
      mnRenderAll();
      return;
    }}

    mnState = mnLoadState(mnCurrentMatchKey());
    mnRenderAll();
    mnSaveActiveSelection();
  }}

  document.getElementById("mn-scope").addEventListener("change", mnInitScope);
  document.getElementById("mn-match").addEventListener("change", mnOnMatchChange);
  document.getElementById("mn-opponent").addEventListener("change", function () {{
    var scope = mnCurrentScope();
    mnRenderScouting(scope);
    mnRenderComparison(scope);
  }});
  document.getElementById("mn-reset").addEventListener("click", function () {{
    if (!window.confirm("Reset all Match Night state for this match?")) return;
    mnState = {{ statuses: {{}}, assignments: [] }};
    mnSaveState(mnCurrentMatchKey(), mnState);
    mnRenderAll();
  }});
  document.getElementById("mn-print").addEventListener("click", function () {{ window.print(); }});

  document.getElementById("pme-player").addEventListener("change", refreshOpponentTeams);
  document.getElementById("pme-opponent-team").addEventListener("change", refreshOpponents);
  document.getElementById("pme-opponent").addEventListener("change", renderPlayer);
  document.getElementById("tme-scope").addEventListener("change", renderTeam);
  ["pme-filter-sl-min", "pme-filter-sl-max", "pme-filter-vol-min"].forEach(function (id) {{
    document.getElementById(id).addEventListener("input", refreshOpponents);
  }});
  document.querySelectorAll(".pme-filter-trend").forEach(function (cb) {{
    cb.addEventListener("change", refreshOpponents);
  }});
  refreshOpponentTeams();
  renderTeam();
  mnRestoreActiveSelectionOnLoad();

  window.__matchNightTestHooks = {{
    legalCompletionExists: mnLegalCompletionExists,
    assessCompletionOptions: mnAssessCompletionOptions,
    completionDecision: mnCompletionDecision,
    injectSyntheticScope: function (scopeKey, scopeData, playerReports) {{
      TEAM_DATA[scopeKey] = scopeData;
      (playerReports || []).forEach(function (entry) {{ PLAYER_DATA[entry.key] = entry.report; }});
      var select = document.getElementById("mn-scope");
      if (!Array.prototype.some.call(select.options, function (o) {{ return o.value === scopeKey; }})) {{
        var opt = document.createElement("option");
        opt.value = scopeKey;
        opt.textContent = scopeKey;
        select.appendChild(opt);
      }}
      select.value = scopeKey;
      mnInitScope();
    }},
  }};
}})();
</script>
</body></html>"""
