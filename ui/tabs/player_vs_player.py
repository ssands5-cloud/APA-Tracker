"""Player vs Player tab: a focused head-to-head view for two real players.

Renders ``analytics.player_vs_player.PlayerVsPlayerSummary`` -- like every
other view in this project it is a REPORTER: it displays what that module
computed and never recalculates a number itself, so the tab and the
database cannot disagree.

Output is a self-contained HTML fragment with no external resources, so it
embeds in the demo or opens on its own from a file:// URL -- the same
posture ``ui/tabs/matchups.py`` and ``ui/tabs/tonights_match.py`` already
use. The two-second-charged fields the original ask for this feature wanted
-- innings and per-opponent defensive shots -- and a third gap found while
building this (break/run events are match-level, not attributable to one
opponent) are not rendered; see analytics/player_vs_player.py's module
docstring for the real, sourced reason. This tab shows that gap explicitly
rather than a blank space or a zero.
"""

from __future__ import annotations

import json
from html import escape
from typing import Optional

from analytics.player_vs_player import PlayerVsPlayerSummary
from ui.tabs.tonights_match import _script_json

NOT_CAPTURED_NOTE = (
    "Innings and per-opponent defensive-shot averages are not shown: APA's "
    "captured data has no innings field at all, and defensive-shot average "
    "exists only as a lifetime, career-wide number, never per opponent. "
    "Break/run events are captured per match, not per opponent, and a "
    "single match can include games against more than one opponent, so a "
    "match-level count cannot be honestly attributed to this pairing. No "
    "placeholder or estimated value is used for any of the three."
)


def _pct(value: Optional[float]) -> str:
    return "No data" if value is None else f"{value * 100:.0f}%"


def _num(value) -> str:
    return "No data" if value is None else str(value)


def _game_payload(summary: PlayerVsPlayerSummary) -> list[dict]:
    return [
        {
            "match_id": g.match_id,
            "match_date": g.match_date,
            "result": g.result,
            "own_skill_level": g.own_skill_level,
            "opponent_skill_level": g.opponent_skill_level,
            "points_earned": g.points_earned,
            "nine_ball_points": g.nine_ball_points,
            "format": g.format,
            "session_name": g.session_name,
        }
        for g in summary.games
    ]


def _timeline(summary: PlayerVsPlayerSummary) -> str:
    """A minimal, real, dependency-free timeline: one marker per game in
    real chronological order, colored by its real result. Not a chart
    library -- inline SVG, matching this project's "no external resources"
    rule."""
    if not summary.games:
        return "<p>No games to show on a timeline.</p>"
    width = 24 * len(summary.games) + 20
    markers = []
    for i, g in enumerate(summary.games):
        x = 20 + i * 24
        color = "#2e7d46" if g.result == "W" else "#a83232" if g.result == "L" else "#9aa1ab"
        title = escape(f"{g.match_date or 'match ' + str(g.match_id)}: {g.result or 'unrecognized'}")
        markers.append(
            f'<circle cx="{x}" cy="20" r="7" fill="{color}"><title>{title}</title></circle>'
        )
    return (
        f'<svg viewBox="0 0 {width} 40" width="{width}" height="40" '
        'role="img" aria-label="Game-by-game result timeline">'
        '<line x1="20" y1="20" x2="' + str(width - 20) + '" y2="20" stroke="#d8dce1" stroke-width="2"/>'
        + "".join(markers) + "</svg>"
    )


def render(
    summary: PlayerVsPlayerSummary,
    player_name: str,
    opponent_name: str,
    title: str = "Player vs Player",
) -> str:
    """A self-contained HTML fragment. No external resources."""
    header = (
        f"<h2>{escape(title)}</h2>"
        f"<p class='pvp-sub'>{escape(player_name)} vs {escape(opponent_name)} -- "
        f"<b>{summary.total_games}</b> real recognized game(s), "
        f"<b>{summary.wins}-{summary.losses}</b> record.</p>"
        f"<p class='pvp-note'>{NOT_CAPTURED_NOTE}</p>"
    )

    stats = (
        "<table class='pvp-stats'><tbody>"
        f"<tr><th>Modeled win probability</th><td>{_pct(summary.modeled_win_probability)}</td></tr>"
        f"<tr><th>Skill-gap-only probability (ablation)</th><td>{_pct(summary.skill_only_probability)}</td></tr>"
        f"<tr><th>Skill-level delta (opponent - own, avg)</th><td>{_num(summary.sl_delta)}</td></tr>"
        f"<tr><th>Reliability weight (n/(n+3))</th><td>{summary.reliability:.3f}</td></tr>"
        f"<tr><th>Trend (whole history)</th><td>{escape(summary.trend)}</td></tr>"
        f"<tr><th>Trend (last games)</th><td>{escape(summary.recent_trend)}</td></tr>"
        f"<tr><th>Next-match projection</th><td>{_pct(summary.next_match_projection)}</td></tr>"
        "</tbody></table>"
    )

    header_cols = (
        ("match_id", "Match"), ("match_date", "Date"), ("result", "Result"),
        ("own_skill_level", "Own SL"), ("opponent_skill_level", "Opp SL"),
        ("points_earned", "Points"), ("nine_ball_points", "9-Ball Balls"),
        ("format", "Format"), ("session_name", "Session"),
    )
    table_header = "".join(f'<th data-key="{k}">{escape(l)}</th>' for k, l in header_cols)
    rows_html = "".join(
        "<tr>" + "".join(
            f"<td>{escape(_num(getattr(g, key)))}</td>" for key, _ in header_cols
        ) + "</tr>"
        for g in summary.games
    )
    table = (
        "<table id='pvp-games' class='pvp-games'>"
        f"<thead><tr>{table_header}</tr></thead><tbody>{rows_html}</tbody></table>"
        if summary.games else "<p>No real games recorded for this pairing yet.</p>"
    )

    payload = _script_json(_game_payload(summary))

    return f"""<section class="pvp-tab">
{header}
{stats}
<h3>Timeline</h3>
{_timeline(summary)}
<h3>Games</h3>
{table}
<style>
.pvp-tab table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 10px 0; }}
.pvp-tab th, .pvp-tab td {{ padding: 7px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.pvp-tab .pvp-stats th {{ text-align: left; color: #444b54; width: 320px; }}
.pvp-games th {{ cursor: pointer; font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: #666e7a; }}
.pvp-note {{ color: #666e7a; font-size: 12.5px; background: #f4f6f8; padding: 10px; border-radius: 6px; }}
</style>
<script>
(function () {{
  var GAMES = {payload};
  var table = document.getElementById("pvp-games");
  if (!table) return;
  var ascending = false;
  table.querySelectorAll("th").forEach(function (th, index) {{
    th.addEventListener("click", function () {{
      var rows = Array.from(table.tBodies[0].rows);
      ascending = !ascending;
      rows.sort(function (a, b) {{
        var x = a.cells[index].textContent.trim();
        var y = b.cells[index].textContent.trim();
        if (x === "No data") return 1;
        if (y === "No data") return -1;
        var nx = parseFloat(x), ny = parseFloat(y);
        if (!isNaN(nx) && !isNaN(ny)) return ascending ? nx - ny : ny - nx;
        return ascending ? x.localeCompare(y) : y.localeCompare(x);
      }});
      rows.forEach(function (row) {{ table.tBodies[0].appendChild(row); }});
    }});
  }});
}})();
</script>
</section>"""
