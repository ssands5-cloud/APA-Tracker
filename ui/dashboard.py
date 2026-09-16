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
.mn-roster-row {{ display: flex; align-items: center; gap: 10px; padding: 6px 4px;
  border-bottom: 1px solid #e2e5ea; flex-wrap: wrap; }}
.mn-roster-row select {{ font-size: 15px; padding: 6px; }}
.mn-roster-name {{ min-width: 140px; font-weight: 600; }}
.mn-card {{ border: 1px solid #e2e5ea; border-radius: 6px; padding: 12px 14px;
  margin: 10px 0; background: #fff; }}
.mn-card.mn-ok {{ border-left: 5px solid #1a7f37; }}
.mn-card.mn-warn {{ border-left: 5px solid #b58900; }}
.mn-card.mn-unknown {{ border-left: 5px solid #8a919c; }}
.mn-card h4 {{ margin: 0 0 4px; }}
.mn-send-btn {{ font-size: 15px; padding: 8px 16px; margin-top: 6px; }}
.mn-status-line {{ font-weight: 600; }}
#mn-warning .cd-none {{ font-weight: 600; }}
.mn-print-only {{ display: none; }}
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

<h2 class="mn-screen-only">Match Night</h2>
<p class="cd-note mn-screen-only">"They put up this player -- who should I send?" Mark who's
available tonight, pick the opponent's announced player, and compare your legal options
side by side. A skill-level estimate is not a promise, and skill-level movement is not a
winning streak -- both are shown as what they really are, not as a verdict.</p>
<div class="cd-controls mn-screen-only">
<label>Match: <select id="mn-scope">{scope_options}</select></label>
&nbsp;
<button type="button" id="mn-reset">Reset Match Night</button>
&nbsp;
<button type="button" id="mn-print">Print summary</button>
</div>
<div id="mn-warning" class="mn-screen-only"></div>
<div id="mn-roster" class="mn-screen-only"></div>
<div class="cd-controls mn-screen-only">
<label>They put up: <select id="mn-opponent"></select></label>
</div>
<div id="mn-comparison" class="mn-screen-only"></div>
<div id="mn-lineup" class="mn-screen-only"></div>
<div id="mn-print-summary" class="mn-print-only"></div>

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
  function sparklineCaption(readings, dates) {{
    // GPT audit follow-up (2026-09-16): a sparkline plotted as equally-
    // spaced points with no date/count context can imply an even cadence
    // the real, irregularly-dated series does not have -- this caption
    // gives the real count and real date range alongside the chart,
    // rather than letting the shape alone imply either.
    //
    // GPT audit follow-up (2026-09-16, 14:00 UTC): the caption still didn't
    // disclose that the chart is independently scaled per player (own
    // min/max, not a shared domain) or that points are spaced by reading
    // index, not by real elapsed time. Rather than invent a shared skill
    // bound to plot against, disclose the real min/max already used to
    // scale this exact chart, plus the spacing caveat, in the same text.
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
    // A real plotted series, not a decoration -- fewer than two readings
    // means there is nothing to plot, shown honestly as no chart at all.
    // Independently scaled per player (own min/max, not a shared domain):
    // this project has no established real skill-level bound to plot
    // against instead, so the caption above is the honest disclosure,
    // not a fabricated shared axis.
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

  // ---- Match Night ----
  // "They put up this player -- who should I send?" plus a live lineup
  // planner. Reuses the exact same PLAYER_DATA/TEAM_DATA already embedded
  // above -- no new estimate, no new model. The only new computation here
  // is the real APA 23-Rule *completion* check (can a legal 5-player
  // lineup still be finished, not just "is this one already legal") --
  // ported from analytics.lineup_legality.legal_completion_exists (see
  // that function's own docstring, and analytics/lineup_legality.py's
  // module docstring for the real rule's cited source) because this
  // planner is live and interactive in the browser, not a build-time
  // report. Same real constants: LINEUP_SIZE=5, TEAM_SKILL_LEVEL_LIMIT_5=23.
  var MN_LIMIT = 23;
  var MN_SIZE = 5;
  // Same real bound, same "exact or refuse" posture, as
  // analytics.lineup_legality.MAX_COMPLETION_ATTEMPTS -- GPT audit
  // follow-up (2026-09-16): the first version of this port had no such
  // guard at all, unlike the Python function it claimed to mirror. An
  // unbounded recursive search is a real risk in an interactive page (it
  // can only ever freeze the tab, not just fail loudly like a script can
  // raise and exit) -- rather than crash or hang, return the same honest
  // "cannot verify" signal as the not-enough-information case below.
  var MN_MAX_COMPLETION_ATTEMPTS = 200000;
  var MN_STATUSES = ["available", "absent", "played", "held"];
  var MN_STATUS_LABELS = {{
    available: "Available", absent: "Absent", played: "Already played", held: "Held back"
  }};
  var mnState = {{ statuses: {{}}, assignments: [] }};

  function mnChooseCount(n, k) {{
    var result = 1;
    for (var i = 0; i < k; i++) {{ result = result * (n - i) / (i + 1); }}
    return result;
  }}

  function mnLegalCompletionExists(committed, available) {{
    // committed: one entry per already-occupied board slot -- null means
    // that slot's own player has no known current skill level. GPT audit
    // follow-up (2026-09-16): an earlier version of every caller here
    // silently dropped an unknown-skill occupied slot instead of passing
    // null, which understated how many of the MN_SIZE slots were really
    // used and could report a completion as still possible when it
    // couldn't honestly be verified at all. Direct port of
    // analytics.lineup_legality.legal_completion_exists -- see that
    // function's own docstring for the full reasoning.
    if (committed.some(function (v) {{ return v === null || v === undefined; }})) return null;
    var stillNeeded = MN_SIZE - committed.length;
    if (stillNeeded < 0) return null;
    var committedTotal = committed.reduce(function (a, b) {{ return a + b; }}, 0);
    if (stillNeeded === 0) return committedTotal <= MN_LIMIT;
    var known = available.filter(function (v) {{ return v !== null && v !== undefined; }});
    if (known.length < stillNeeded) return null;
    if (mnChooseCount(known.length, stillNeeded) > MN_MAX_COMPLETION_ATTEMPTS) return null;
    var remainingCap = MN_LIMIT - committedTotal;
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

  function mnKnownSkillSum(committed) {{
    // Display-only: the sum of whatever committed skill levels are
    // actually known, never a guessed contribution for an unknown one.
    return committed
      .filter(function (v) {{ return v !== null && v !== undefined; }})
      .reduce(function (a, b) {{ return a + b; }}, 0);
  }}

  function mnStorageKey(scopeKey) {{ return "match-night:" + scopeKey; }}

  function mnLoadState(scopeKey) {{
    try {{
      var raw = window.localStorage.getItem(mnStorageKey(scopeKey));
      if (raw) return JSON.parse(raw);
    }} catch (e) {{ /* private browsing or storage disabled -- honest fallback below */ }}
    return {{ statuses: {{}}, assignments: [] }};
  }}

  function mnSaveState(scopeKey, state) {{
    try {{ window.localStorage.setItem(mnStorageKey(scopeKey), JSON.stringify(state)); }}
    catch (e) {{ /* real, honest limitation: state just won't persist across reloads */ }}
  }}

  function mnCurrentScope() {{
    return TEAM_DATA[document.getElementById("mn-scope").value];
  }}

  function mnCommittedSkillLevels(scope) {{
    // One entry per player already marked "played" -- null preserved
    // (not dropped) for an unknown skill level, since that slot is still
    // occupied either way. See mnLegalCompletionExists's own comment for
    // why dropping it was a real correctness bug.
    return scope.our_roster
      .filter(function (p) {{ return mnState.statuses[p.id] === "played"; }})
      .map(function (p) {{ return p.skill_level; }});
  }}

  function mnPairKey(scope, playerId, opponentId) {{
    return scope.our_team.id + "|" + scope.opponent_team.id + "|" + scope.format + "|"
      + scope.session_name + "|" + playerId + ":" + opponentId;
  }}

  function mnPlayedCount(scope) {{
    // GPT audit follow-up (2026-09-16): the send cap and duplicate guard
    // previously checked mnState.assignments.length, which only counts
    // boards recorded through Send -- a player marked "Already played"
    // manually (a real, intended way to enter a match already in
    // progress) occupies a slot too, without ever adding an assignment.
    // Five players marked played by hand, then one more sent through the
    // comparison flow, produced a real "6 of 5 boards used" -- this is
    // the single authoritative occupied-slot count both checks must use.
    return scope.our_roster.filter(function (p) {{
      return mnState.statuses[p.id] === "played";
    }}).length;
  }}

  function mnRenderWarning(scope) {{
    var target = document.getElementById("mn-warning");
    var playedCount = mnPlayedCount(scope);
    if (playedCount > MN_SIZE) {{
      target.innerHTML = "<p class='cd-none'>" + playedCount + " players are marked "
        + "Already played -- a standard lineup only uses " + MN_SIZE + ". Check for a "
        + "mis-click before relying on the legality check below.</p>";
      return;
    }}
    var committed = mnCommittedSkillLevels(scope);
    var available = scope.our_roster
      .filter(function (p) {{ return (mnState.statuses[p.id] || "available") === "available"; }})
      .map(function (p) {{ return p.skill_level; }});
    var verdict = mnLegalCompletionExists(committed, available);
    if (verdict === false) {{
      target.innerHTML = "<p class='cd-none'>No legal " + MN_SIZE + "-player lineup "
        + "(combined skill level " + MN_LIMIT + " or less) can still be completed from "
        + "tonight's Available players. Reconsider who's marked available/held back "
        + "before sending anyone else.</p>";
    }} else if (verdict === null && playedCount < MN_SIZE) {{
      var unknownCommitted = committed.some(function (v) {{ return v === null || v === undefined; }});
      target.innerHTML = unknownCommitted
        ? "<p class='cd-note'>A player already marked Already played has no known current "
          + "skill level, so the real skill total can't be verified.</p>"
        : "<p class='cd-note'>Not enough Available players with a known current skill "
          + "level to verify a legal completion yet.</p>";
    }} else {{
      target.innerHTML = "";
    }}
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
          // GPT audit follow-up (2026-09-16): manually moving a player off
          // "Already played" while a formal Send record still exists for
          // them left assignments and statuses disagreeing (the exact
          // desync the duplicate-boards bug came from) -- an explicit
          // status change away from "played" now retracts that record too,
          // the same as clicking Undo on it would.
          mnState.assignments = mnState.assignments.filter(function (a) {{
            return String(a.player_id) !== String(pid);
          }});
          mnState.assignments.forEach(function (a, i) {{ a.board = i + 1; }});
        }}
        mnState.statuses[pid] = newStatus;
        mnSaveState(document.getElementById("mn-scope").value, mnState);
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
    if (mnPlayedCount(scope) >= MN_SIZE) {{
      target.innerHTML = "<p class='cd-none'>All " + MN_SIZE + " boards are already accounted "
        + "for (sent or marked Already played) this match. Undo a sent board below, or change "
        + "a player's status, if you need to free one up.</p>";
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
    var available = scope.our_roster.filter(function (p) {{
      return (mnState.statuses[p.id] || "available") === "available";
    }});
    if (!available.length) {{
      target.innerHTML = "<p class='cd-none'>No players are marked Available.</p>";
      return;
    }}
    var committed = mnCommittedSkillLevels(scope);
    var html = "<h4>They put up " + esc(opponent ? opponent.name : "?") + " -- who should you send?</h4>";
    available.forEach(function (p) {{
      var report = PLAYER_DATA[mnPairKey(scope, p.id, opponentId)];
      var otherAvailableSkills = available
        .filter(function (q) {{ return q.id !== p.id; }})
        .map(function (q) {{ return q.skill_level; }});
      // GPT audit follow-up (2026-09-16): this candidate's own skill level
      // must be passed through even when it's null/unknown -- silently
      // omitting it understated the occupied-slot count and could show
      // "still legal" for a choice that genuinely can't be verified.
      var candidateCommitted = committed.concat([p.skill_level]);
      var verdict = mnLegalCompletionExists(candidateCommitted, otherAvailableSkills);
      var cls = verdict === false ? "mn-warn" : (verdict === null ? "mn-unknown" : "mn-ok");
      html += "<div class='mn-card " + cls + "'><h4>" + esc(p.name) + " <span class='cd-note'>SL "
        + orNoData(p.skill_level) + "</span>" + trendBadge(p.trend) + "</h4>";
      if (report) {{
        html += "<table><tbody>"
          + "<tr><th>Evidence</th><td>" + esc(report.evidence_label) + "</td></tr>"
          + "<tr><th>Direct record</th><td>" + (report.direct_wins !== null && report.direct_wins !== undefined
              ? report.direct_wins + "-" + report.direct_losses + " (" + pct(report.observed_win_rate) + ")"
              : "No data") + " across " + report.direct_evidence_count + " match(es)</td></tr>"
          // GPT audit follow-up (2026-09-16): modeled_win_probability is
          // NOT always skill-only -- a DIRECT pairing's real model_source
          // can be "...direct-history-and-skill". Labeling it "Skill-only
          // estimate" unconditionally repeated the exact model-basis
          // conflation already fixed once this session in the lineup
          // table; show the real model_source alongside instead of a
          // fixed, sometimes-wrong label.
          + "<tr><th>Modeled probability</th><td>" + pct(report.modeled_win_probability)
              + " <span class='cd-note'>(" + orNoData(report.model_source) + ")</span></td></tr>"
          + "</tbody></table>"
          + "<p class='cd-summary-box'>" + esc(report.summary) + "</p>";
      }} else {{
        html += "<p class='cd-none'>No matchup data found for this pairing.</p>";
      }}
      if (verdict === false) {{
        html += "<p class='mn-status-line'>\\u26a0 Sending " + esc(p.name) + " would leave "
          + "no legal lineup possible with tonight's remaining Available players.</p>";
      }} else if (verdict === null) {{
        html += "<p class='cd-note'>Not enough known skill levels among the rest of "
          + "tonight's Available players to verify a legal completion.</p>";
      }} else {{
        html += "<p class='cd-note'>Sending " + esc(p.name) + " still leaves a legal "
          + "lineup possible.</p>";
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
    var player = scope.our_roster.filter(function (p) {{ return String(p.id) === String(playerId); }})[0];
    var opponent = scope.opponent_roster.filter(function (o) {{ return String(o.id) === String(opponentId); }})[0];
    if (!player) return;
    // GPT audit follow-up (2026-09-16): assignments and per-player status
    // could previously disagree -- toggling a player back to Available and
    // sending them again against a different opponent left BOTH records in
    // place. Assignments are now the authoritative record for *who played
    // whom*, but the occupied-slot COUNT must come from mnPlayedCount --
    // GPT audit follow-up (2026-09-16, 2de026c): checking
    // assignments.length here let five players marked Already played
    // manually plus one real Send exceed the 5-board cap entirely,
    // since none of the five manual entries ever touched assignments.
    if (mnPlayedCount(scope) >= MN_SIZE) {{
      window.alert(
        "All " + MN_SIZE + " boards are already accounted for (sent or marked Already "
        + "played) this match."
      );
      return;
    }}
    if (mnState.assignments.some(function (a) {{ return String(a.player_id) === String(playerId); }})) {{
      window.alert(
        player.name + " already has a recorded board this match. Undo it below first "
        + "if you need to send them again."
      );
      return;
    }}
    var committed = mnCommittedSkillLevels(scope);
    var otherAvailable = scope.our_roster
      .filter(function (p) {{
        return (mnState.statuses[p.id] || "available") === "available" && String(p.id) !== String(playerId);
      }})
      .map(function (p) {{ return p.skill_level; }});
    // GPT audit follow-up (2026-09-16): pass the real skill level through
    // even when null/unknown -- see mnRenderComparison's matching note.
    var candidateCommitted = committed.concat([player.skill_level]);
    var verdict = mnLegalCompletionExists(candidateCommitted, otherAvailable);
    if (verdict === false) {{
      var proceed = window.confirm(
        "Sending " + player.name + " would leave no legal " + MN_SIZE + "-player lineup "
        + "possible with tonight's remaining Available players. Send anyway?"
      );
      if (!proceed) return;
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
    mnSaveState(document.getElementById("mn-scope").value, mnState);
    mnRenderAll();
  }}

  function mnUndoAssignment(scope, index) {{
    var removed = mnState.assignments.splice(index, 1)[0];
    if (removed && mnState.statuses[removed.player_id] === "played") {{
      // Only restore Available if the status is still exactly what Send
      // set it to -- a captain may have since marked them Absent/Held back
      // on purpose, which Undo must not silently override.
      mnState.statuses[removed.player_id] = "available";
    }}
    mnState.assignments.forEach(function (a, i) {{ a.board = i + 1; }});
    mnSaveState(document.getElementById("mn-scope").value, mnState);
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
          // Same real model_source shown alongside the number here too --
          // it is not always the skill-only model (see mnRenderComparison).
          + "<td>" + pct(a.modeled_win_probability) + " <span class='cd-note'>("
              + orNoData(a.model_source) + ")</span></td>"
          + "<td><button type='button' class='mn-undo-btn' data-index='" + index + "'>Undo</button></td>"
          + "</tr>";
      }});
      html += "</tbody></table>";
    }}
    var committed = mnCommittedSkillLevels(scope);
    html += "<p>Committed skill total so far: <strong>" + mnKnownSkillSum(committed)
      + "</strong> of " + MN_LIMIT + " (" + committed.length + " of " + MN_SIZE + " boards used)";
    if (committed.some(function (v) {{ return v === null || v === undefined; }})) {{
      html += " <span class='cd-note'>-- includes a player with no known skill level; "
        + "this total is a partial sum, not the real full total</span>";
    }}
    html += "</p>";
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
    html += "<p>Skill total: " + mnKnownSkillSum(committed) + " of " + MN_LIMIT;
    // GPT audit follow-up (2026-09-16, 2de026c): the on-screen total
    // already disclosed a missing skill as a partial sum; the printed
    // summary silently dropped that same caveat, showing a bare number
    // that looked complete when it wasn't.
    if (committed.some(function (v) {{ return v === null || v === undefined; }})) {{
      html += " -- a player with no known skill level is included in the board "
        + "count above but not in this total; this is a partial sum, not the real "
        + "full total";
    }}
    html += "</p>";
    target.innerHTML = html;
  }}

  function mnRenderAll() {{
    var scope = mnCurrentScope();
    if (!scope) return;
    mnRenderRoster(scope);
    mnRenderOpponentSelect(scope);
    mnRenderComparison(scope);
    mnRenderLineup(scope);
    mnRenderWarning(scope);
    mnRenderPrintSummary(scope);
  }}

  function mnInitScope() {{
    mnState = mnLoadState(document.getElementById("mn-scope").value);
    mnRenderAll();
  }}

  document.getElementById("mn-scope").addEventListener("change", mnInitScope);
  document.getElementById("mn-opponent").addEventListener("change", function () {{
    mnRenderComparison(mnCurrentScope());
  }});
  document.getElementById("mn-reset").addEventListener("click", function () {{
    if (!window.confirm("Reset all Match Night state for this match?")) return;
    mnState = {{ statuses: {{}}, assignments: [] }};
    mnSaveState(document.getElementById("mn-scope").value, mnState);
    mnRenderAll();
  }});
  document.getElementById("mn-print").addEventListener("click", function () {{ window.print(); }});

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
  mnInitScope();

  // Test-only introspection/injection hooks -- tests/test_dashboard_browser.py
  // uses these for deterministic Match Night coverage that shouldn't have to
  // depend on whether a given real fixture happens to contain a matching
  // edge case (an unknown skill level, an infeasible completion). Nothing
  // else on the page reads this object, and injectSyntheticScope only ever
  // *adds* a new scope/pairing under a synthetic key -- it never touches or
  // overwrites any real scope's data.
  window.__matchNightTestHooks = {{
    legalCompletionExists: mnLegalCompletionExists,
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
