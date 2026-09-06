"""Captain's Edge tab: the recommended lineup, ranked.

Renders the Captain's Decision Engine's output. Like every other view here
it is a REPORTER -- it displays what ``analytics.captains_edge`` computed and
never recalculates, so the tab, the JSON and the workbook cannot disagree.

Display rules:

  * NULL renders as "No data" -- never 0, never a blank cell
  * high confidence is highlighted green, high risk red
  * every column sorts, and "No data" always sorts last

Self-contained HTML with no external resources: a captain's laptop at a
venue may have no internet.
"""

from __future__ import annotations

from html import escape
from typing import Any, Optional, Sequence

NO_DATA = "No data"

# Highlight thresholds. Confidence and risk are independent signals, so a
# player can be both -- a strong recent run on an unsettled skill level is
# exactly the call a captain wants flagged twice.
HIGH_CONFIDENCE = 0.70
HIGH_RISK = 0.50

# (key, header, numeric) -- header order is part of the spec.
COLUMNS = (
    ("player_name", "Player", False),
    ("opponent_name", "Opponent", False),
    ("matchup_score", "Matchup Score", True),
    ("risk_factor", "Risk", True),
    ("confidence", "Confidence", True),
    ("recommended_order", "Recommended Order", True),
    ("rationale", "Rationale", False),
)


def row_class(row: dict[str, Any]) -> str:
    """Highlight classes for one row. Both may apply."""
    classes = []
    confidence = row.get("confidence")
    risk = row.get("risk_factor")
    if confidence is not None and confidence >= HIGH_CONFIDENCE:
        classes.append("high-confidence")
    if risk is not None and risk >= HIGH_RISK:
        classes.append("high-risk")
    return " ".join(classes)


def load_rows(document: dict[str, Any],
              team_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Flatten the decision document's lineups into display rows.

    Reads the JSON the builder wrote rather than the database: the ranking
    is the builder's output, and recomputing it here could disagree with the
    file a captain is holding.
    """
    rows = []
    for lineup in document.get("lineups") or []:
        if team_id and str(lineup.get("team_id")) != str(team_id):
            continue
        for player in lineup.get("players") or []:
            record = dict(player)
            record["team_name"] = lineup.get("team_name") or ""
            rows.append(record)
    # Ranked players first, in order; unranked last -- ordering a player with
    # no score would imply a judgement the evidence does not support.
    rows.sort(key=lambda r: (r.get("recommended_order") is None,
                             r.get("recommended_order") or 0))
    return rows


def _cell(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        return NO_DATA
    if key in ("matchup_score", "risk_factor", "confidence"):
        return f"{value:.3f}"
    return escape(str(value))


def render(rows: Sequence[dict[str, Any]], title: str = "Captain's Edge",
           resolution: Optional[str] = None) -> str:
    """A self-contained, sortable HTML fragment."""
    if not rows:
        return (
            f'<section class="edge-tab"><h2>{escape(title)}</h2>'
            '<p class="edge-empty">No lineup yet. Run the pipeline, then '
            "scripts/build_captains_edge.py.</p></section>"
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

    ranked = sum(1 for r in rows if r.get("recommended_order") is not None)
    note = (f"{ranked} ranked of {len(rows)} player(s). Click any column to sort. "
            "Scores come from the Captain's Decision Engine, not from this page.")
    if resolution and "player_name" in resolution:
        note += (" Roster matched by NAME, not team id -- see "
                 "docs/captains_edge.md.")

    return f"""<section class="edge-tab">
<h2>{escape(title)}</h2>
<p class="edge-note">{escape(note)}</p>
<style>
.edge-tab table {{ border-collapse: collapse; width: 100%; min-width: 720px; font-size: 13.5px; }}
.edge-tab th, .edge-tab td {{ padding: 7px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; vertical-align: top; }}
.edge-tab td:last-child {{ min-width: 260px; max-width: 460px; font-size: 12.5px; color: #666e7a; }}
.edge-tab td:first-child, .edge-tab td:nth-child(2) {{ white-space: nowrap; }}
.edge-tab th {{ cursor: pointer; font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: #666e7a; white-space: nowrap; }}
.edge-tab td.num, .edge-tab th.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.edge-tab tr.high-confidence {{ background: #e6f6ec; }}
.edge-tab tr.high-risk {{ background: #fdecec; }}
.edge-tab tr.high-confidence.high-risk {{ background: #fdf3e3; }}
.edge-empty {{ color: #666e7a; padding: 18px 0; }}
</style>
<table class="edge-table"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>
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
        var nx = parseFloat(x);
        var ny = parseFloat(y);
        if (!isNaN(nx) && !isNaN(ny)) return ascending ? nx - ny : ny - nx;
        return ascending ? x.localeCompare(y) : y.localeCompare(x);
      }});
      rows.forEach(function (row) {{ table.tBodies[0].appendChild(row); }});
    }});
  }});
}})();
</script>
</section>"""


def build(document: dict[str, Any], team_id: Optional[str] = None,
          title: str = "Captain's Edge") -> str:
    """Render one section PER TEAM.

    Flattening several teams into one table produced two rows numbered #1
    and a player with a higher score sitting below one with a lower score --
    correct per-team, but indistinguishable from a sorting bug at a glance.
    Each lineup is its own table, headed by the team it belongs to.
    """
    lineups = document.get("lineups") or []
    if team_id:
        lineups = [l for l in lineups if str(l.get("team_id")) == str(team_id)]
    if not lineups:
        return render([], title, document.get("roster_resolution"))

    resolution = document.get("roster_resolution")
    if len(lineups) == 1:
        heading = lineups[0].get("team_name") or title
        return render(load_rows(document, lineups[0].get("team_id")),
                      f"{title} - {heading}" if heading != title else title,
                      resolution)

    return "\n".join(
        render(
            load_rows(document, lineup.get("team_id")),
            f"{title} - {lineup.get('team_name') or lineup.get('team_id')}",
            resolution,
        )
        for lineup in lineups
    )
