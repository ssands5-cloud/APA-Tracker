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
from html import escape
from typing import Sequence

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
) -> str:
    player_payload = {_pair_key(r): player_matchup_report_to_dict(r) for r in player_reports}
    team_payload = {_scope_key(r): team_matchup_report_to_dict(r) for r in team_reports}

    # Linked player-then-opponent selection, not one flat list of every
    # real pairing -- a bundle with several real scopes can carry hundreds
    # of reports (512 in this project's real division-wide run), which
    # does not scale to a single dropdown.
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
.cd-controls select {{ font-size: 14px; padding: 4px; min-width: 380px; }}
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
<label>Player: <select id="pme-player">{player_options}</select></label>
&nbsp;
<label>Opponent: <select id="pme-opponent"></select></label>
</div>
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

<h2>Opponent Risk Profile (whole-division, purely descriptive ranking)</h2>
<p class="cd-note">Ranked by reliability-weighted skill-only probability,
toughest first -- never a categorical "danger" label
(<code>analytics.opponent_risk_profile</code>).</p>
<table><thead><tr><th>Opponent</th><th>Direct pairings</th>
<th>Direct win rate</th><th>Direct sample</th>
<th>Skill-only estimate</th></tr></thead>
<tbody>{risk_rows or '<tr><td colspan="5">No data</td></tr>'}</tbody></table>

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
  function sparkline(readings) {{
    // A real plotted series, not a decoration -- fewer than two readings
    // means there is nothing to plot, shown honestly as no chart at all.
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
    return "<svg class='cd-spark' width='" + w + "' height='" + h + "' viewBox='0 0 " + w + " " + h
         + "' role='img' aria-label='Skill level trend sparkline'>"
         + "<polyline points='" + points + "' fill='none' stroke='#1F3864' stroke-width='1.5'/></svg>";
  }}
  function trendBadge(t) {{
    var arrow = {{"up": "\\u25b2", "down": "\\u25bc", "stable": "\\u25ac"}}[t.trend] || "?";
    return arrow + " " + orNoData(t.trend) + " (whole history, volatility " + t.volatility + ")"
         + sparkline(t.readings);
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
    // Filters read only real, already-computed fields on the opponent's
    // own report -- no new threshold or model backs a filter.
    var r = PLAYER_DATA[choice.key];
    if (!r) return true;
    var sl = r.opponent.skill_level;
    if (!isNaN(filters.slMin) && (sl === null || sl < filters.slMin)) return false;
    if (!isNaN(filters.slMax) && (sl === null || sl > filters.slMax)) return false;
    if (!isNaN(filters.volMin) && r.opponent.trend.volatility < filters.volMin) return false;
    if (filters.trends.indexOf(r.opponent.trend.trend) === -1) return false;
    return true;
  }}

  function refreshOpponents() {{
    var playerId = document.getElementById("pme-player").value;
    var choices = (PLAYER_OPPONENT_INDEX[playerId] || []).filter(function (c) {{
      return passesFilters(c, opponentFilters());
    }});
    var select = document.getElementById("pme-opponent");
    select.innerHTML = choices.length
      ? choices.map(function (c) {{
          return "<option value=\\"" + esc(c.key) + "\\">" + esc(c.label) + "</option>";
        }}).join("")
      : "<option value=\\"\\">No opponents match these filters</option>";
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
    html += "<tr><th>Observed win rate</th><td>" + pct(r.observed_win_rate)
         + (r.direct_wins !== null ? " (" + r.direct_wins + "-" + r.direct_losses + ")" : "")
         + " across " + r.direct_evidence_count + " recorded match(es)</td></tr>";
    html += "<tr><th>Modeled probability</th><td>" + pct(r.modeled_win_probability) + "</td></tr>";
    html += "</tbody></table><p class='cd-summary-box'>" + esc(r.summary) + "</p>";
    target.innerHTML = html;
  }}

  function captainsEdgeCard(r) {{
    // Purely descriptive: real evidence coverage, real lineup status, and
    // the lowest/highest experimental estimate already in the ranked
    // table below -- never narrated as a "favored"/"danger" verdict.
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
      // GPT audit follow-up (2026-09-16): lineup_score is ALWAYS the
      // validated skill-only score (analytics.lineup_lab.pairing_score
      // deliberately excludes DIRECT history from lineup selection --
      // see that module's own docstring), never model_source's own
      // evidence classification -- those are two different real numbers
      // with two different real sources, shown in two separate columns
      // rather than one column implying the score came from model_source.
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

  document.getElementById("pme-player").addEventListener("change", refreshOpponents);
  document.getElementById("pme-opponent").addEventListener("change", renderPlayer);
  document.getElementById("tme-scope").addEventListener("change", renderTeam);
  ["pme-filter-sl-min", "pme-filter-sl-max", "pme-filter-vol-min"].forEach(function (id) {{
    document.getElementById(id).addEventListener("input", refreshOpponents);
  }});
  document.querySelectorAll(".pme-filter-trend").forEach(function (cb) {{
    cb.addEventListener("change", refreshOpponents);
  }});
  refreshOpponents();
  renderTeam();
}})();
</script>
</body></html>"""
