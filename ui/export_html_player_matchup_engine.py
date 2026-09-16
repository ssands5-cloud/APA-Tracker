"""Player Matchup Engine (Coach Mode) HTML: a self-contained page over
already-built ``analytics.player_matchup_engine.PlayerMatchupReport``
objects. A REPORTER -- the browser only selects among precomputed reports,
never computes a rate, label, or probability itself.

Linked player-then-opponent selection (not one flat list of every real
pairing): a bundle covering several real scopes can carry hundreds of
reports, and a single dropdown of "A vs B (format, session)" options does
not scale to a real division-wide roster. Choosing a player first narrows
the second selector to only the real opponents that player has a report
against. Opponent option labels include the opponent's real team name
(GPT audit follow-up: a same-named opponent player on two teams during
simultaneous membership can otherwise produce indistinguishable choices
even though the underlying scope-safe keys never collide).
"""

from __future__ import annotations

from collections import defaultdict
from html import escape
from typing import Sequence

from analytics.player_matchup_engine import PlayerMatchupReport
from ui.export_json_coach_advantage import player_matchup_report_to_dict
from ui.tabs.tonights_match import _script_json


def _pair_key(report: PlayerMatchupReport) -> str:
    """Scope-safe: includes both real team ids, format, and session, not
    just the two internal player ids. The same two players can face each
    other under more than one real (opponent team, format, session) scope
    in one bundle (a real, likely occurrence -- e.g. the same opponent
    team in both 8-Ball and 9-Ball the same session) -- keying on
    ``player_id:opponent_id`` alone let a later scope's report silently
    overwrite an earlier one at the same JSON key.
    """
    return (
        f"{report.our_team_external_id}|{report.opponent_team_external_id}|"
        f"{report.format}|{report.session_name}|{report.player_id}:{report.opponent_id}"
    )


def _player_options_and_index(reports: Sequence[PlayerMatchupReport]) -> tuple[dict, dict]:
    """(our-player options, our-player-id -> [opponent choices]) -- built
    once from the real reports, never re-derived in the browser."""
    players: dict[int, dict] = {}
    by_player: dict[int, list[dict]] = defaultdict(list)
    for r in reports:
        players.setdefault(r.player_id, {"id": r.player_id, "name": r.player_name})
        team_display = r.opponent_team_name or r.opponent_team_external_id
        by_player[r.player_id].append({
            "key": _pair_key(r),
            "label": f"{r.opponent_name} — {team_display} ({r.format}, {r.session_name})",
        })
    for choices in by_player.values():
        choices.sort(key=lambda c: c["label"].lower())
    return players, by_player


def render(reports: Sequence[PlayerMatchupReport], title: str = "Player Matchup Engine (Coach Mode)") -> str:
    payload = {_pair_key(r): player_matchup_report_to_dict(r) for r in reports}
    players, by_player = _player_options_and_index(reports)
    player_options = "".join(
        f'<option value="{p["id"]}">{escape(p["name"])}</option>'
        for p in sorted(players.values(), key=lambda p: p["name"].lower())
    )
    opponent_index = {
        str(player_id): [{"key": c["key"], "label": c["label"]} for c in choices]
        for player_id, choices in by_player.items()
    }

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1c1f24; background: #ffffff; }}
.pme-controls {{ margin: 12px 0 18px; }}
.pme-controls select {{ font-size: 14px; padding: 4px; min-width: 320px; }}
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
"No data," never a guessed value. Skill trend covers each player's whole
captured history, not a recent window.</p>

<div class="pme-controls">
<label>Player: <select id="pme-player">{player_options}</select></label>
&nbsp;
<label>Opponent: <select id="pme-opponent"></select></label>
</div>

<div id="pme-result"></div>

<script type="application/json" id="pme-data">{_script_json(payload)}</script>
<script type="application/json" id="pme-opponent-index">{_script_json(opponent_index)}</script>
<script>
(function () {{
  var DATA = JSON.parse(document.getElementById("pme-data").textContent);
  var OPPONENT_INDEX = JSON.parse(document.getElementById("pme-opponent-index").textContent);

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

  function refreshOpponents() {{
    var playerId = document.getElementById("pme-player").value;
    var choices = OPPONENT_INDEX[playerId] || [];
    var select = document.getElementById("pme-opponent");
    select.innerHTML = choices.map(function (c) {{
      return "<option value=\\"" + esc(c.key) + "\\">" + esc(c.label) + "</option>";
    }}).join("");
    renderReport();
  }}

  function renderReport() {{
    var key = document.getElementById("pme-opponent").value;
    var target = document.getElementById("pme-result");
    var r = DATA[key];
    if (!r) {{
      target.innerHTML = "<p class='pme-none'>No report for this pairing.</p>";
      return;
    }}

    var html = "<h2>" + esc(r.player.name) + " vs " + esc(r.opponent.name) + "</h2>";
    html += "<table class='pme-summary'><tbody>";
    html += "<tr><th>Scope</th><td>" + esc(r.our_team_id) + " vs " + esc(r.opponent_team_id)
         + " &middot; " + esc(r.format) + " &middot; " + esc(r.session_name) + "</td></tr>";
    html += "<tr><th>" + esc(r.player.name) + "</th><td>SL " + orNoData(r.player.skill_level)
         + " &middot; trend (whole history): " + orNoData(r.player.trend.trend)
         + " (volatility " + r.player.trend.volatility + ")"
         + (r.player.trend.last_change ? " &middot; last change: " + esc(r.player.trend.last_change) : "")
         + "</td></tr>";
    html += "<tr><th>" + esc(r.opponent.name) + "</th><td>SL " + orNoData(r.opponent.skill_level)
         + " &middot; trend (whole history): " + orNoData(r.opponent.trend.trend)
         + " (volatility " + r.opponent.trend.volatility + ")"
         + (r.opponent.trend.last_change ? " &middot; last change: " + esc(r.opponent.trend.last_change) : "")
         + "</td></tr>";
    html += "<tr><th>Evidence</th><td>" + esc(r.evidence_label) + "</td></tr>";
    html += "<tr><th>Observed win rate</th><td>" + pct(r.observed_win_rate)
         + (r.direct_wins !== null ? " (" + r.direct_wins + "-" + r.direct_losses + ")" : "")
         + " across " + r.direct_evidence_count + " recorded match(es)</td></tr>";
    html += "<tr><th>Modeled probability</th><td>" + pct(r.modeled_win_probability)
         + (r.model_source ? " (" + esc(r.model_source) + ")" : "") + "</td></tr>";
    html += "</tbody></table>";
    html += "<p class='pme-summary-box'>" + esc(r.summary) + "</p>";

    target.innerHTML = html;
  }}

  document.getElementById("pme-player").addEventListener("change", refreshOpponents);
  document.getElementById("pme-opponent").addEventListener("change", renderReport);
  refreshOpponents();
}})();
</script>
</body></html>"""
