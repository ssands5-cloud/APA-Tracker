"""Player Matchup Engine (Coach Mode) HTML: a self-contained page over
already-built ``analytics.player_matchup_engine.PlayerMatchupReport``
objects. A REPORTER -- the browser only selects among precomputed reports,
never computes a rate, label, or probability itself.
"""

from __future__ import annotations

from html import escape
from typing import Sequence

from analytics.player_matchup_engine import PlayerMatchupReport
from ui.export_json_coach_advantage import player_matchup_report_to_dict
from ui.tabs.tonights_match import _script_json


def _pair_key(report: PlayerMatchupReport) -> str:
    return f"{report.player_id}:{report.opponent_id}"


def render(reports: Sequence[PlayerMatchupReport], title: str = "Player Matchup Engine (Coach Mode)") -> str:
    payload = {_pair_key(r): player_matchup_report_to_dict(r) for r in reports}
    players = {}
    for r in reports:
        players.setdefault(r.player_id, {"id": r.player_id, "name": r.player_name})
        players.setdefault(r.opponent_id, {"id": r.opponent_id, "name": r.opponent_name})
    pair_options = "".join(
        f'<option value="{escape(_pair_key(r))}">'
        f'{escape(r.player_name)} vs {escape(r.opponent_name)} '
        f'({escape(r.format)}, {escape(r.session_name)})</option>'
        for r in reports
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1c1f24; background: #ffffff; }}
.pme-controls {{ margin: 12px 0 18px; }}
.pme-controls select {{ font-size: 14px; padding: 4px; min-width: 380px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 8px 0 18px; }}
th, td {{ padding: 6px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.pme-summary th {{ width: 220px; }}
.pme-none {{ background: #fdf6e3; border-left: 4px solid #b58900; padding: 10px 14px; }}
.pme-summary-box {{ background: #eef2fa; border-left: 4px solid #1F3864; padding: 10px 14px; }}
.pme-note {{ color: #666e7a; font-size: 12.5px; }}
</style></head><body>
<h1>{escape(title)}</h1>
<p class="pme-note">Every number here comes from
<code>analytics.pairing_evidence</code> and
<code>analytics.skill_level_trends</code> -- no new win-probability model,
no invented danger threshold. A pairing with no usable evidence shows
"No data," never a guessed value.</p>

<div class="pme-controls">
<label>Pairing: <select id="pme-pair">{pair_options}</select></label>
</div>

<div id="pme-result"></div>

<script type="application/json" id="pme-data">{_script_json(payload)}</script>
<script>
(function () {{
  var DATA = JSON.parse(document.getElementById("pme-data").textContent);

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

  function render() {{
    var key = document.getElementById("pme-pair").value;
    var target = document.getElementById("pme-result");
    var r = DATA[key];
    if (!r) {{
      target.innerHTML = "<p class='pme-none'>No report for this pairing.</p>";
      return;
    }}

    var html = "<h2>" + esc(r.player.name) + " vs " + esc(r.opponent.name) + "</h2>";
    html += "<table class='pme-summary'><tbody>";
    html += "<tr><th>" + esc(r.player.name) + "</th><td>SL " + orNoData(r.player.skill_level)
         + " &middot; trend: " + orNoData(r.player.trend.trend)
         + " (volatility " + r.player.trend.volatility + ")"
         + (r.player.trend.last_change ? " &middot; last change: " + esc(r.player.trend.last_change) : "")
         + "</td></tr>";
    html += "<tr><th>" + esc(r.opponent.name) + "</th><td>SL " + orNoData(r.opponent.skill_level)
         + " &middot; trend: " + orNoData(r.opponent.trend.trend)
         + " (volatility " + r.opponent.trend.volatility + ")"
         + (r.opponent.trend.last_change ? " &middot; last change: " + esc(r.opponent.trend.last_change) : "")
         + "</td></tr>";
    html += "<tr><th>Evidence</th><td>" + esc(r.evidence_label) + "</td></tr>";
    html += "<tr><th>Observed win rate</th><td>" + pct(r.observed_win_rate)
         + " (" + r.direct_evidence_count + " direct game(s))</td></tr>";
    html += "<tr><th>Modeled probability</th><td>" + pct(r.modeled_win_probability)
         + (r.model_source ? " (" + esc(r.model_source) + ")" : "") + "</td></tr>";
    html += "</tbody></table>";
    html += "<p class='pme-summary-box'>" + esc(r.summary) + "</p>";

    target.innerHTML = html;
  }}

  document.getElementById("pme-pair").addEventListener("change", render);
  render();
}})();
</script>
</body></html>"""
