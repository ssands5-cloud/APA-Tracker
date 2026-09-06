"""Player Trends tab: how every player's skill level is moving.

Renders from ``player_trends`` -- the Player Trend Analyzer's output. Like
every other view here it is a REPORTER: it displays what
``analytics.player_trends`` computed and never recalculates, so the tab, the
workbook and the database cannot disagree.

Display rules come from the spec:

  * NULL renders as "No data" -- never 0, never a blank cell that could be
    read as zero
  * HOT is highlighted green, COLD red, NEUTRAL not at all
  * slope, volatility and stability are numerically formatted
  * every column sorts, and "No data" always sorts last

Self-contained HTML with no external resources, so it embeds in the demo or
opens on its own from a file:// URL -- a captain's laptop at a venue may
have no internet.
"""

from __future__ import annotations

from html import escape
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from database.models import Player, PlayerTrend

NO_DATA = "No data"

# (key, header, numeric) -- header order is part of the spec.
COLUMNS = (
    ("player_name", "Player", False),
    ("format", "Format", False),
    ("session_name", "Session", False),
    ("sample_size", "Sample Size", True),
    ("current_skill_level", "Current SL", True),
    ("regression_slope", "Regression Slope", True),
    ("volatility", "Volatility", True),
    ("sl_stability", "SL Stability", True),
    ("hot_cold_flag", "Hot/Cold", False),
    ("projected_sl_change_probability", "Projected SL Change Probability", True),
)


def load_rows(db: Session, format_: Optional[str] = None,
              session_name: Optional[str] = None) -> list[dict[str, Any]]:
    """Trends as plain dicts, player names resolved, steepest climb first.

    NULL slopes sort last rather than as zero -- a player with too little
    history has not "not moved", they are unmeasured.
    """
    rows = []
    for trend, player in db.query(PlayerTrend, Player).join(
        Player, Player.id == PlayerTrend.player_id
    ).all():
        if format_ and trend.format != format_:
            continue
        if session_name and trend.session_name != session_name:
            continue
        rows.append({
            "player_name": player.name,
            "player_id": player.external_id,
            "format": trend.format,
            "session_name": trend.session_name,
            "sample_size": trend.sample_size,
            "current_skill_level": trend.current_skill_level,
            "regression_slope": trend.regression_slope,
            "volatility": trend.volatility,
            "sl_stability": trend.sl_stability,
            "hot_cold_flag": trend.hot_cold_flag,
            "projected_sl_change_probability": trend.projected_sl_change_probability,
        })
    rows.sort(key=lambda r: (r["regression_slope"] is None, -(r["regression_slope"] or 0)))
    return rows


def row_class(row: dict[str, Any]) -> str:
    """Highlight class. NEUTRAL and NULL are both unhighlighted -- "measured
    and unremarkable" and "not enough evidence" should neither shout."""
    flag = row.get("hot_cold_flag")
    if flag == "HOT":
        return "hot"
    if flag == "COLD":
        return "cold"
    return ""


def _cell(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        return NO_DATA
    if key == "projected_sl_change_probability":
        return f"{value * 100:.1f}%"
    if key == "regression_slope":
        # Signed: direction is the point of this column.
        return f"{value:+.4f}"
    if key in ("volatility", "sl_stability"):
        return f"{value:.4f}"
    return escape(str(value))


def render(rows: Sequence[dict[str, Any]], title: str = "Player Trends") -> str:
    """A self-contained, sortable HTML fragment."""
    if not rows:
        return (
            f'<section class="trends-tab"><h2>{escape(title)}</h2>'
            '<p class="trends-empty">No player trends yet. Run the pipeline, '
            "then scripts/build_player_trends.py.</p></section>"
        )

    header = "".join(
        f'<th class="{"num" if numeric else ""}">{escape(label)}</th>'
        for _, label, numeric in COLUMNS
    )
    body = "".join(
        '<tr class="{cls}">{cells}</tr>'.format(
            cls=row_class(row),
            cells="".join(
                f'<td class="{"num" if numeric else ""}">{_cell(row, key)}</td>'
                for key, _, numeric in COLUMNS
            ),
        )
        for row in rows
    )

    hot = sum(1 for r in rows if r.get("hot_cold_flag") == "HOT")
    cold = sum(1 for r in rows if r.get("hot_cold_flag") == "COLD")
    unmeasured = sum(1 for r in rows if r.get("hot_cold_flag") is None)

    return f"""<section class="trends-tab">
<h2>{escape(title)}</h2>
<p class="trends-note">{len(rows)} row(s) · {hot} hot · {cold} cold ·
{unmeasured} without enough history to classify. Click any column to sort.
Skill-level trends come from the Player Trend Analyzer, not from this page.</p>
<style>
.trends-tab table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }}
.trends-tab th, .trends-tab td {{ padding: 7px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; white-space: nowrap; }}
.trends-tab th {{ cursor: pointer; font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: #666e7a; }}
.trends-tab td.num, .trends-tab th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.trends-tab tr.hot {{ background: #e6f6ec; }}
.trends-tab tr.cold {{ background: #fdecec; }}
.trends-empty {{ color: #666e7a; padding: 18px 0; }}
</style>
<table class="trends-table"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>
<script>
(function () {{
  var table = document.currentScript.previousElementSibling;
  var ascending = false;
  table.querySelectorAll("th").forEach(function (th, index) {{
    th.addEventListener("click", function () {{
      var rows = Array.from(table.tBodies[0].rows);
      ascending = !ascending;
      rows.sort(function (a, b) {{
        var x = a.cells[index].textContent.trim();
        var y = b.cells[index].textContent.trim();
        // "No data" always sorts last, never as zero.
        if (x === "{NO_DATA}") return 1;
        if (y === "{NO_DATA}") return -1;
        var nx = parseFloat(x.replace(/[%+]/g, ""));
        var ny = parseFloat(y.replace(/[%+]/g, ""));
        if (!isNaN(nx) && !isNaN(ny)) return ascending ? nx - ny : ny - nx;
        return ascending ? x.localeCompare(y) : y.localeCompare(x);
      }});
      rows.forEach(function (row) {{ table.tBodies[0].appendChild(row); }});
    }});
  }});
}})();
</script>
</section>"""


def build(db: Session, format_: Optional[str] = None,
          session_name: Optional[str] = None,
          title: str = "Player Trends") -> str:
    """Query and render in one call."""
    return render(load_rows(db, format_, session_name), title)
