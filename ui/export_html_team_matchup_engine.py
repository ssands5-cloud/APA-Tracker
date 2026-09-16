"""Team Matchup Engine (Coach Mode) HTML: a self-contained page over
already-built ``analytics.team_matchup_engine.TeamMatchupReport`` objects,
one per real (opponent, format, session) scope. A REPORTER -- the browser
only selects among precomputed reports, never computes a rate, ranking, or
lineup itself.
"""

from __future__ import annotations

from html import escape
from typing import Sequence

from analytics.team_matchup_engine import TeamMatchupReport
from ui.export_json_coach_advantage import team_matchup_report_to_dict
from ui.tabs.tonights_match import _script_json


def _scope_key(report: TeamMatchupReport) -> str:
    return f"{report.opponent_team_external_id}|{report.format}|{report.session_name}"


def render(reports: Sequence[TeamMatchupReport], title: str = "Team Matchup Engine (Coach Mode)") -> str:
    payload = {_scope_key(r): team_matchup_report_to_dict(r) for r in reports}
    scope_options = "".join(
        f'<option value="{escape(_scope_key(r))}">'
        f'{escape(r.our_team_name)} vs {escape(r.opponent_team_name)} '
        f'({escape(r.format)}, {escape(r.session_name)})</option>'
        for r in reports
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1c1f24; background: #ffffff; }}
.tme-controls {{ margin: 12px 0 18px; }}
.tme-controls select {{ font-size: 14px; padding: 4px; min-width: 420px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 8px 0 18px; }}
th, td {{ padding: 6px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.tme-summary-box {{ background: #eef2fa; border-left: 4px solid #1F3864; padding: 10px 14px; }}
.tme-none {{ background: #fdf6e3; border-left: 4px solid #b58900; padding: 10px 14px; }}
.tme-note {{ color: #666e7a; font-size: 12.5px; }}
.tme-cols {{ display: flex; gap: 24px; flex-wrap: wrap; }}
.tme-cols > div {{ flex: 1; min-width: 280px; }}
</style></head><body>
<h1>{escape(title)}</h1>
<p class="tme-note">Opponent rankings are purely descriptive -- sorted by
real evidence, never a categorical "danger"/"favored" flag (see
<code>analytics.opponent_risk_profile</code>'s own convention, which this
mirrors). "Board" numbers below refer to this scope's own computed Lineup
Lab slot, not a persisted per-player position -- this project's data has
no such stable field.</p>

<div class="tme-controls">
<label>Match: <select id="tme-scope">{scope_options}</select></label>
</div>

<div id="tme-result"></div>

<script type="application/json" id="tme-data">{_script_json(payload)}</script>
<script>
(function () {{
  var DATA = JSON.parse(document.getElementById("tme-data").textContent);

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

  function rosterTable(name, roster) {{
    var html = "<h3>" + esc(name) + "</h3><table><thead><tr><th>Player</th><th>SL</th>"
             + "<th>Trend (whole history)</th><th>Volatility</th></tr></thead><tbody>";
    roster.forEach(function (p) {{
      html += "<tr><td>" + esc(p.name) + "</td><td>" + orNoData(p.skill_level) + "</td>"
           + "<td>" + orNoData(p.trend.trend) + "</td><td>" + p.trend.volatility + "</td></tr>";
    }});
    html += "</tbody></table>";
    return html;
  }}

  function render() {{
    var key = document.getElementById("tme-scope").value;
    var target = document.getElementById("tme-result");
    var r = DATA[key];
    if (!r) {{
      target.innerHTML = "<p class='tme-none'>No report for this match.</p>";
      return;
    }}

    var html = "<h2>" + esc(r.our_team.name) + " vs " + esc(r.opponent_team.name) + "</h2>";
    html += "<p class='tme-summary-box'>" + esc(r.summary) + "</p>";

    html += "<h3>Evidence coverage</h3><table><tbody>";
    html += "<tr><th>Direct</th><td>" + (r.evidence_counts.DIRECT || 0) + "</td></tr>";
    html += "<tr><th>Indirect</th><td>" + (r.evidence_counts.INDIRECT || 0) + "</td></tr>";
    html += "<tr><th>Unknown</th><td>" + (r.evidence_counts.UNKNOWN || 0) + "</td></tr>";
    html += "<tr><th>Total feasible</th><td>" + (r.evidence_counts.total_feasible_pairings || 0) + "</td></tr>";
    html += "</tbody></table>";

    html += "<div class='tme-cols'><div>" + rosterTable("Our roster", r.our_roster) + "</div>"
         + "<div>" + rosterTable("Opponent roster", r.opponent_roster) + "</div></div>";

    html += "<h3>Opponent Scouting</h3><p class='tme-note'>Sorted by an "
         + "experimental, not independently validated skill-only estimate "
         + "(lowest first) -- a real signal to read from the table, never "
         + "a \"toughest\"/\"favorable\" verdict a ranking like this has "
         + "not been checked against held-out real outcomes to support. "
         + "Pooled direct win rate is the true combined record across "
         + "every one of our players who has faced this opponent, not an "
         + "average of each pairing's own rate.</p>"
         + "<table><thead><tr>"
         + "<th>Opponent</th><th>SL</th><th>Pooled direct win rate</th><th>Direct W-L</th>"
         + "<th>Direct sample</th><th>Skill-only estimate (experimental)</th></tr></thead><tbody>";
    r.ranked_opponents.forEach(function (o) {{
      html += "<tr><td>" + esc(o.name) + "</td><td>" + orNoData(o.skill_level) + "</td>"
           + "<td>" + pct(o.direct_win_rate) + "</td>"
           + "<td>" + (o.direct_wins !== null ? o.direct_wins + "-" + o.direct_losses : "No data") + "</td>"
           + "<td>" + o.direct_sample_size + "</td>"
           + "<td>" + pct(o.reliability_weighted_skill_probability) + "</td></tr>";
    }});
    html += "</tbody></table>";

    html += "<h3>Approved lineup</h3>";
    if (r.lineup) {{
      html += "<table><thead><tr><th>Board</th><th>Our player</th><th>Opponent</th>"
           + "<th>Evidence</th><th>Score</th></tr></thead><tbody>";
      r.lineup.assignments.forEach(function (slot) {{
        html += "<tr><td>" + slot.board + "</td><td>" + esc(slot.player_name) + "</td>"
             + "<td>" + esc(slot.opponent_name) + "</td><td>" + esc(slot.evidence_label) + "</td>"
             + "<td>" + (slot.lineup_score !== null ? slot.lineup_score.toFixed(3) : "No data")
             + "</td></tr>";
      }});
      html += "</tbody></table>";
      if (r.lineup.unassigned_players.length) {{
        html += "<p>Unassigned players: " + r.lineup.unassigned_players.map(function (p) {{ return esc(p.name); }}).join(", ") + "</p>";
      }}
      if (r.lineup.blocked_reason) {{
        html += "<p class='tme-none'>" + esc(r.lineup.blocked_reason) + "</p>";
      }}
    }} else {{
      html += "<p class='tme-none'>" + esc(r.lineup_error || "No approved lineup available.") + "</p>";
    }}

    target.innerHTML = html;
  }}

  document.getElementById("tme-scope").addEventListener("change", render);
  render();
}})();
</script>
</body></html>"""
