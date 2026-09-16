"""Player Matchup Explorer HTML: pick any two distinct captured players.

A REPORTER over an already-built
``analytics.player_matchup_explorer.PlayerMatchupExplorerDocument``. The
browser selects among values that were computed server-side; it never
computes a meeting, a record, or a probability.

Self-contained, no external resources.
"""

from __future__ import annotations

from html import escape
from typing import Optional

from analytics.player_matchup_explorer import (
    MODELED_LABEL,
    NO_DIRECT_MEETINGS,
    PlayerMatchupExplorerDocument,
)
from ui.tabs.tonights_match import _script_json


def _pct(value: Optional[float]) -> str:
    return "No data" if value is None else f"{value * 100:.1f}%"


def _payload(document: PlayerMatchupExplorerDocument) -> dict:
    return {
        "players": [
            {
                "id": p.player_id,
                "external_id": p.player_external_id,
                "name": p.player_name,
                "team": p.team_name,
                "team_id": p.team_external_id,
                "skill_level": p.skill_level,
            }
            for p in document.players
        ],
        "pairs": {
            f"{pair.player_id}:{pair.opponent_id}": {
                "meetings": pair.meetings,
                "wins": pair.wins,
                "losses": pair.losses,
                "undecided": pair.undecided,
                "modeled": pair.modeled_skill_only_probability,
                "unavailable_reason": pair.unavailable_reason,
                "games": [
                    {
                        "match_id": g.match_id,
                        "date": g.match_date,
                        "week": g.week,
                        "own_sl": g.own_skill_level,
                        "opp_sl": g.opponent_skill_level,
                        "result": g.result,
                        "points": g.points_earned,
                    }
                    for g in pair.games
                ],
            }
            for pair in document.pairs
        },
    }


def render(document: PlayerMatchupExplorerDocument, title: str = "Player Matchup Explorer") -> str:
    options = "".join(
        f'<option value="{p.player_id}">{escape(p.player_name)}'
        f"{escape(' -- ' + p.team_name) if p.team_name else ''}"
        f"{escape(f' (SL {p.skill_level})') if p.skill_level is not None else ''}"
        "</option>"
        for p in document.players
    )
    second_options = options

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1c1f24; }}
.pme-controls {{ margin: 12px 0 18px; }}
.pme-controls select {{ font-size: 14px; padding: 4px; min-width: 260px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 8px 0 18px; }}
th, td {{ padding: 6px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.pme-summary th {{ width: 280px; }}
.pme-none {{ background: #fdf6e3; border-left: 4px solid #b58900; padding: 10px 14px; }}
.pme-modeled {{ background: #eef2fa; border-left: 4px solid #1F3864; padding: 10px 14px; }}
.pme-note {{ color: #666e7a; font-size: 12.5px; }}
</style></head><body>
<h1>{escape(title)}</h1>
<p class="pme-sub">{escape(document.session_name)}
{escape(' -- ' + document.format) if document.format else ''}.
Any two distinct captured players, including two who are both on other
teams. {document.captured_pair_count} ordered pair(s) have real captured
meetings.</p>

<div class="pme-controls">
<label>Player: <select id="pme-a">{options}</select></label>
&nbsp;vs&nbsp;
<label>Opponent: <select id="pme-b">{second_options}</select></label>
</div>

<div id="pme-result"></div>

<p class="pme-note">Captured meetings are real recorded games only. A pair
with none is reported as "{escape(NO_DIRECT_MEETINGS)}" -- never a zero
that could read as a measured result, and never a meeting inferred from a
shared match or team. The modeled comparison is a separate field:
{escape(MODELED_LABEL)}.</p>

<script type="application/json" id="pme-data">{_script_json(_payload(document))}</script>
<script>
(function () {{
  var DATA = JSON.parse(document.getElementById("pme-data").textContent);
  var byId = {{}};
  DATA.players.forEach(function (p) {{ byId[String(p.id)] = p; }});

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
    var a = document.getElementById("pme-a").value;
    var b = document.getElementById("pme-b").value;
    var target = document.getElementById("pme-result");

    if (a === b) {{
      target.innerHTML = "<p class='pme-none'>Select two different players.</p>";
      return;
    }}

    var pa = byId[a], pb = byId[b];
    var pair = DATA.pairs[a + ":" + b];
    if (!pair) {{
      target.innerHTML = "<p class='pme-none'>" + esc("{NO_DIRECT_MEETINGS}") + "</p>";
      return;
    }}

    var html = "<h2>" + esc(pa.name) + " vs " + esc(pb.name) + "</h2>";
    html += "<table class='pme-summary'><tbody>";
    html += "<tr><th>" + esc(pa.name) + "</th><td>" + orNoData(pa.team)
         + " &middot; SL " + orNoData(pa.skill_level) + "</td></tr>";
    html += "<tr><th>" + esc(pb.name) + "</th><td>" + orNoData(pb.team)
         + " &middot; SL " + orNoData(pb.skill_level) + "</td></tr>";
    html += "</tbody></table>";

    if (pair.meetings === 0) {{
      html += "<p class='pme-none'><b>" + esc(pair.unavailable_reason) + "</b></p>";
    }} else {{
      html += "<table class='pme-summary'><tbody>";
      html += "<tr><th>Captured meetings</th><td>" + pair.meetings + "</td></tr>";
      html += "<tr><th>Record (" + esc(pa.name) + ")</th><td>"
           + pair.wins + "-" + pair.losses
           + (pair.undecided ? " (" + pair.undecided + " undecided)" : "")
           + "</td></tr>";
      html += "</tbody></table>";

      html += "<h3>Every captured meeting</h3><table><thead><tr>"
           + "<th>Date</th><th>Week</th><th>Match</th>"
           + "<th>" + esc(pa.name) + " SL</th><th>" + esc(pb.name) + " SL</th>"
           + "<th>Outcome</th><th>Points</th></tr></thead><tbody>";
      pair.games.forEach(function (g) {{
        html += "<tr><td>" + orNoData(g.date) + "</td><td>" + orNoData(g.week) + "</td>"
             + "<td>" + orNoData(g.match_id) + "</td>"
             + "<td>" + orNoData(g.own_sl) + "</td><td>" + orNoData(g.opp_sl) + "</td>"
             + "<td>" + orNoData(g.result) + "</td><td>" + orNoData(g.points) + "</td></tr>";
      }});
      html += "</tbody></table>";
    }}

    html += "<p class='pme-modeled'><b>Modeled comparison: " + pct(pair.modeled)
         + "</b><br>" + esc("{MODELED_LABEL}") + ".</p>";

    target.innerHTML = html;
  }}

  document.getElementById("pme-a").addEventListener("change", render);
  document.getElementById("pme-b").addEventListener("change", render);
  if (DATA.players.length > 1) {{
    document.getElementById("pme-b").selectedIndex = 1;
  }}
  render();
}})();
</script>
</body></html>"""
