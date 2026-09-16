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

Known, disclosed limitation: "trend" is shown as a compact indicator
(direction + a volatility count), not a plotted sparkline. A real sparkline
needs the full chronological skill-level series per player
(``database.queries.skill_level_history``), which this dashboard's inputs
do not carry (``analytics.player_matchup_engine.SkillTrendInfo`` is a
summary, not a series) -- adding one is a real, separate follow-up, not
something to fake with an indicator dressed up as a chart.
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
</style></head><body>
<h1>Coach Dashboard — {escape(our_team_name)}</h1>
<p class="cd-note">Every number on this page traces to
<code>analytics.pairing_evidence</code>, the validated
<code>analytics.head_to_head.skill_only_win_probability</code>, or
<code>analytics.lineup_lab</code>'s approved assignment. No new
win-probability model, no invented danger threshold, no categorical
verdict -- see <code>docs/captain_first_edge_experience.md</code> §13.
"Trend" below is a direction + volatility count, not a plotted series (a
real sparkline needs the full historical series, a disclosed follow-up).</p>

<h2>Player vs Player</h2>
<div class="cd-controls">
<label>Player: <select id="pme-player">{player_options}</select></label>
&nbsp;
<label>Opponent: <select id="pme-opponent"></select></label>
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
  function trendBadge(t) {{
    var arrow = {{"up": "\\u25b2", "down": "\\u25bc", "stable": "\\u25ac"}}[t.trend] || "?";
    return arrow + " " + orNoData(t.trend) + " (whole history, volatility " + t.volatility + ")";
  }}

  function refreshOpponents() {{
    var playerId = document.getElementById("pme-player").value;
    var choices = PLAYER_OPPONENT_INDEX[playerId] || [];
    var select = document.getElementById("pme-opponent");
    select.innerHTML = choices.map(function (c) {{
      return "<option value=\\"" + esc(c.key) + "\\">" + esc(c.label) + "</option>";
    }}).join("");
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

  function renderTeam() {{
    var key = document.getElementById("tme-scope").value;
    var target = document.getElementById("tme-result");
    var r = TEAM_DATA[key];
    if (!r) {{ target.innerHTML = "<p class='cd-none'>No report for this match.</p>"; return; }}

    var html = "<p class='cd-summary-box'>" + esc(r.summary) + "</p>";
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
      html += "<table><thead><tr><th>Board</th><th>Our player</th><th>Opponent</th><th>Evidence</th></tr></thead><tbody>";
      r.lineup.assignments.forEach(function (slot) {{
        html += "<tr><td>" + slot.board + "</td><td>" + esc(slot.player_name) + "</td>"
             + "<td>" + esc(slot.opponent_name) + "</td><td>" + esc(slot.evidence_label) + "</td></tr>";
      }});
      html += "</tbody></table>";
    }} else {{
      html += "<p class='cd-none'>" + esc(r.lineup_error || "No approved lineup available.") + "</p>";
    }}
    target.innerHTML = html;
  }}

  document.getElementById("pme-player").addEventListener("change", refreshOpponents);
  document.getElementById("pme-opponent").addEventListener("change", renderPlayer);
  document.getElementById("tme-scope").addEventListener("change", renderTeam);
  refreshOpponents();
  renderTeam();
}})();
</script>
</body></html>"""
